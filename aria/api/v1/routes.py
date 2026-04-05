"""
JSON API for the Next.js frontend.
All routes return JSON. Mounted at /api/v1.
"""
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import JSONResponse

from aria.config import Config
from aria.tools.airtable import _get_table, update_prospect, log_activity
from aria.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

DEAL_STAGES = [
    "new", "contacted", "replied", "demo_booked",
    "demo_done", "proposal", "closed_won", "closed_lost", "not_now", "cold",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _map_prospect(record: dict) -> dict:
    f = record.get("fields", {})
    return {
        "airtable_id": record["id"],
        "name": f.get("Name", ""),
        "title": f.get("Title", ""),
        "company": f.get("Company", ""),
        "email": f.get("Email", ""),
        "linkedin_url": f.get("LinkedIn URL", ""),
        "score": f.get("Score", 0),
        "tier": f.get("Tier", "cold"),
        "deal_stage": f.get("Deal Stage", "new"),
        "research_summary": f.get("Research Summary", ""),
        "pain_angle": f.get("Pain Angle", ""),
        "email_subject": f.get("Email Body", "").split("\n")[0] if f.get("Email Body") else "",
        "email_body": f.get("Email Body", ""),
        "outreach_sent": bool(f.get("Outreach Sent")),
        "follow_up_1_sent": bool(f.get("Follow Up 1 Sent")),
        "follow_up_2_sent": bool(f.get("Follow Up 2 Sent")),
        "breakup_sent": bool(f.get("Breakup Sent")),
        "reply_received": bool(f.get("Reply Received")),
        "reply_classification": f.get("Reply Classification", ""),
        "meeting_booked": bool(f.get("Meeting Booked")),
        "meeting_datetime": f.get("Meeting Date", ""),
        "do_not_contact": bool(f.get("Do Not Contact")),
        "notes": f.get("Notes", ""),
        "retailers": _parse_retailers(f.get("Research Summary", "")),
        "job_signal": "job" in f.get("Research Summary", "").lower(),
    }


def _map_activity(record: dict) -> dict:
    f = record.get("fields", {})
    ts_str = f.get("Timestamp", "")
    prospect_links = f.get("Prospect", [])
    return {
        "action": f.get("Action", ""),
        "details": f.get("Details", ""),
        "timestamp": ts_str,
        "time_ago": _time_ago(ts_str),
        "prospect_name": prospect_links[0] if prospect_links else "Unknown",
    }


def _parse_retailers(summary: str) -> list:
    known = ["Walmart", "Target", "Kroger", "Costco", "Whole Foods", "CVS", "Walgreens", "Amazon"]
    return [r for r in known if r.lower() in summary.lower()]


def _time_ago(ts_str: str) -> str:
    if not ts_str:
        return "unknown"
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
        diff = datetime.utcnow() - ts
        if diff.seconds < 3600:
            return f"{diff.seconds // 60}m ago"
        if diff.days == 0:
            return f"{diff.seconds // 3600}h ago"
        return f"{diff.days}d ago"
    except Exception:
        return ts_str[:10]


# ── dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard():
    try:
        table = _get_table("Prospects")
        records = table.all()
        prospects = [_map_prospect(r) for r in records]
    except Exception as e:
        logger.error(f"[API] dashboard failed: {e}")
        prospects = []

    try:
        act_table = _get_table("Activity Log")
        act_records = act_table.all(sort=[{"field": "Timestamp", "direction": "desc"}])[:10]
        activity = [_map_activity(r) for r in act_records]
    except Exception as e:
        logger.error(f"[API] activity fetch failed: {e}")
        activity = []

    total = len(prospects)
    hot = sum(1 for p in prospects if p["tier"] == "hot")
    contacted = sum(1 for p in prospects if p["outreach_sent"])
    replied = sum(1 for p in prospects if p["reply_received"])
    demos = sum(1 for p in prospects if p["meeting_booked"])
    reply_rate = round(replied / contacted * 100, 1) if contacted else 0

    funnel = [
        {"label": "Found", "count": total},
        {"label": "Contacted", "count": contacted},
        {"label": "Replied", "count": replied},
        {"label": "Demo", "count": demos},
        {"label": "Won", "count": sum(1 for p in prospects if p["deal_stage"] == "closed_won")},
    ]

    return {
        "stats": {
            "total": total,
            "hot": hot,
            "contacted": contacted,
            "replied": replied,
            "demos": demos,
            "reply_rate": reply_rate,
        },
        "hot_prospects": [p for p in prospects if p["tier"] == "hot"][:5],
        "activity": activity,
        "funnel": funnel,
        "dry_run": Config.DRY_RUN,
        "date": datetime.utcnow().strftime("%B %d, %Y"),
    }


# ── prospects ─────────────────────────────────────────────────────────────────

@router.get("/prospects")
async def list_prospects(tier: str = "all"):
    try:
        table = _get_table("Prospects")
        formula = f"{{Tier}} = '{tier}'" if tier != "all" else ""
        records = table.all(formula=formula) if formula else table.all()
        return {"prospects": [_map_prospect(r) for r in records], "tier_filter": tier}
    except Exception as e:
        logger.error(f"[API] list_prospects failed: {e}")
        return {"prospects": [], "tier_filter": tier}


@router.get("/prospects/{airtable_id}")
async def get_prospect(airtable_id: str):
    try:
        table = _get_table("Prospects")
        record = table.get(airtable_id)
        return {"prospect": _map_prospect(record), "stages": DEAL_STAGES}
    except Exception as e:
        logger.error(f"[API] get_prospect failed: {e}")
        raise HTTPException(404, "Prospect not found")


@router.post("/prospects/{airtable_id}/update-stage")
async def update_stage(airtable_id: str, stage: str = Form(...)):
    update_prospect(airtable_id, {"Deal Stage": stage})
    log_activity(airtable_id, "stage_changed", f"Stage manually updated to: {stage}")
    return {"ok": True}


@router.post("/prospects/{airtable_id}/add-note")
async def add_note(airtable_id: str, note: str = Form(...)):
    try:
        table = _get_table("Prospects")
        record = table.get(airtable_id)
        existing = record["fields"].get("Notes", "")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        new_notes = f"{existing}\n[{timestamp}] {note}".strip()
        table.update(airtable_id, {"Notes": new_notes})
        return {"ok": True}
    except Exception as e:
        logger.error(f"[API] add_note failed: {e}")
        raise HTTPException(500, str(e))


# ── activity ──────────────────────────────────────────────────────────────────

@router.get("/activity")
async def activity_log(limit: int = 100):
    try:
        table = _get_table("Activity Log")
        records = table.all(sort=[{"field": "Timestamp", "direction": "desc"}])[:limit]
        return {"activity": [_map_activity(r) for r in records]}
    except Exception as e:
        logger.error(f"[API] activity_log failed: {e}")
        return {"activity": []}


# ── config ────────────────────────────────────────────────────────────────────

@router.get("/config")
async def config_status():
    env_vars = [
        {"name": k, "set": bool(getattr(Config, k, ""))}
        for k in Config.REQUIRED_FOR_PIPELINE
    ]
    return {
        "dry_run": Config.DRY_RUN,
        "max_per_day": Config.MAX_PROSPECTS_PER_DAY,
        "env_vars": env_vars,
        "llm_provider": Config.LLM_PROVIDER or "auto",
    }


@router.post("/config/toggle-dry-run")
async def toggle_dry_run():
    current = Config.DRY_RUN
    os.environ["DRY_RUN"] = "false" if current else "true"
    Config.DRY_RUN = not current
    return {"dry_run": Config.DRY_RUN}


# ── triggers ──────────────────────────────────────────────────────────────────

@router.post("/trigger-run")
async def trigger_run():
    import threading
    from aria.graph import main as run_pipeline

    def _run():
        try:
            run_pipeline()
        except Exception as e:
            logger.error(f"[API] Manual pipeline run failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Pipeline started"}


@router.post("/trigger-reply-check")
async def trigger_reply_check():
    import threading
    from aria.agents.reply_handler import run as check_replies

    def _run():
        try:
            check_replies()
        except Exception as e:
            logger.error(f"[API] Manual reply check failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Reply check started"}


@router.post("/trigger-followups")
async def trigger_followups():
    import threading
    from aria.agents.follow_up import run as send_followups

    def _run():
        try:
            send_followups()
        except Exception as e:
            logger.error(f"[API] Manual follow-up failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Follow-up check started"}
