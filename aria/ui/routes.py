"""
UI routes — mounted on the FastAPI app at /ui
Serves HTML dashboard for monitoring and configuring Aria.
"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aria.config import Config
from aria.tools.airtable import _get_table
from aria.utils.logger import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui")

DEAL_STAGES = [
    "new", "contacted", "replied", "demo_booked",
    "demo_done", "proposal", "closed_won", "closed_lost", "not_now", "cold"
]


# ── Helper data fetchers ──────────────────────────────────────────────────────

def _fetch_prospects(tier_filter: str = "all") -> list:
    try:
        table = _get_table("Prospects")
        formula = f"{{Tier}} = '{tier_filter}'" if tier_filter != "all" else ""
        records = table.all(formula=formula) if formula else table.all()
        return [_map_prospect(r) for r in records]
    except Exception as e:
        logger.error(f"[UI] _fetch_prospects failed: {e}")
        return []


def _fetch_activity(limit: int = 50) -> list:
    try:
        table = _get_table("Activity Log")
        records = table.all(sort=[{"field": "Timestamp", "direction": "desc"}])[:limit]
        return [_map_activity(r) for r in records]
    except Exception as e:
        logger.error(f"[UI] _fetch_activity failed: {e}")
        return []


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
        "revenue": f.get("Research Summary", "")[:30] if f.get("Research Summary") else "",
        "retailers": _parse_retailers(f.get("Research Summary", "")),
        "research_summary": f.get("Research Summary", ""),
        "pain_angle": f.get("Pain Angle", ""),
        "email_subject": f.get("Email Body", "").split("\n")[0] if f.get("Email Body") else "",
        "email_body": f.get("Email Body", ""),
        "linkedin_connection_msg": f.get("LinkedIn URL", ""),
        "linkedin_dm": "",
        "outreach_sent": bool(f.get("Outreach Sent")),
        "follow_up_1_sent": bool(f.get("Follow Up 1 Sent")),
        "follow_up_2_sent": bool(f.get("Follow Up 2 Sent")),
        "breakup_sent": bool(f.get("Breakup Sent")),
        "reply_received": bool(f.get("Reply Received")),
        "reply_classification": f.get("Reply Classification", ""),
        "meeting_booked": bool(f.get("Meeting Booked")),
        "meeting_datetime": f.get("Meeting Date", ""),
        "do_not_contact": bool(f.get("Do Not Contact")),
        "job_signal": "job" in f.get("Research Summary", "").lower(),
        "notes": f.get("Notes", ""),
    }


def _map_activity(record: dict) -> dict:
    f = record.get("fields", {})
    ts_str = f.get("Timestamp", "")
    time_ago = _time_ago(ts_str)
    prospect_links = f.get("Prospect", [])
    return {
        "action": f.get("Action", ""),
        "details": f.get("Details", ""),
        "timestamp": ts_str,
        "time_ago": time_ago,
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


def _build_stats(prospects: list) -> list:
    total = len(prospects)
    hot = sum(1 for p in prospects if p["tier"] == "hot")
    contacted = sum(1 for p in prospects if p["outreach_sent"])
    replied = sum(1 for p in prospects if p["reply_received"])
    demos = sum(1 for p in prospects if p["meeting_booked"])
    reply_rate = round(replied / contacted * 100, 1) if contacted else 0

    return [
        {"label": "Total Prospects", "value": total, "sub": None},
        {"label": "Hot", "value": hot, "sub": None},
        {"label": "Contacted", "value": contacted, "sub": None},
        {"label": "Replied", "value": replied, "sub": f"{reply_rate}% rate"},
        {"label": "Demos Booked", "value": demos, "sub": None},
    ]


def _build_funnel(prospects: list) -> tuple:
    stages = [
        ("Found", lambda p: True),
        ("Contacted", lambda p: p["outreach_sent"]),
        ("Replied", lambda p: p["reply_received"]),
        ("Demo", lambda p: p["meeting_booked"]),
        ("Won", lambda p: p["deal_stage"] == "closed_won"),
    ]
    funnel = [{"label": label, "count": sum(1 for p in prospects if fn(p))}
              for label, fn in stages]
    funnel_max = max((s["count"] for s in funnel), default=1)
    return funnel, funnel_max


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    prospects = _fetch_prospects()
    activity = _fetch_activity(10)
    hot_prospects = [p for p in prospects if p["tier"] == "hot"]
    stats = _build_stats(prospects)
    funnel, funnel_max = _build_funnel(prospects)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active": "dashboard",
        "dry_run": Config.DRY_RUN,
        "date_str": datetime.utcnow().strftime("%B %d, %Y"),
        "stats": stats,
        "hot_prospects": hot_prospects,
        "activity": activity,
        "funnel": funnel,
        "funnel_max": max(funnel_max, 1),
    })


@router.get("/prospects", response_class=HTMLResponse)
async def prospects_list(request: Request, tier: str = "all"):
    all_prospects = _fetch_prospects(tier)
    return templates.TemplateResponse("prospects.html", {
        "request": request,
        "active": "prospects",
        "dry_run": Config.DRY_RUN,
        "prospects": all_prospects,
        "tier_filter": tier,
        "total": len(all_prospects),
    })


@router.get("/prospects/{airtable_id}", response_class=HTMLResponse)
async def prospect_detail(request: Request, airtable_id: str):
    try:
        table = _get_table("Prospects")
        record = table.get(airtable_id)
        p = _map_prospect(record)
    except Exception as e:
        logger.error(f"[UI] prospect_detail failed: {e}")
        return RedirectResponse("/ui/prospects")

    return templates.TemplateResponse("prospect_detail.html", {
        "request": request,
        "active": "prospects",
        "dry_run": Config.DRY_RUN,
        "p": p,
        "stages": DEAL_STAGES,
    })


@router.post("/prospects/{airtable_id}/update-stage")
async def update_stage(airtable_id: str, stage: str = Form(...)):
    from aria.tools.airtable import update_prospect, log_activity
    update_prospect(airtable_id, {"Deal Stage": stage})
    log_activity(airtable_id, "stage_changed", f"Stage manually updated to: {stage}")
    return RedirectResponse(f"/ui/prospects/{airtable_id}", status_code=303)


@router.post("/prospects/{airtable_id}/add-note")
async def add_note(airtable_id: str, note: str = Form(...)):
    from aria.tools.airtable import _get_table as get_t
    try:
        table = get_t("Prospects")
        record = table.get(airtable_id)
        existing = record["fields"].get("Notes", "")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        new_notes = f"{existing}\n[{timestamp}] {note}".strip()
        table.update(airtable_id, {"Notes": new_notes})
    except Exception as e:
        logger.error(f"[UI] add_note failed: {e}")
    return RedirectResponse(f"/ui/prospects/{airtable_id}", status_code=303)


@router.get("/activity", response_class=HTMLResponse)
async def activity_log(request: Request):
    activity = _fetch_activity(100)
    return templates.TemplateResponse("activity.html", {
        "request": request,
        "active": "activity",
        "dry_run": Config.DRY_RUN,
        "activity": activity,
    })


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    env_vars = [
        {"name": k, "set": bool(getattr(Config, k, ""))}
        for k in Config.REQUIRED_FOR_PIPELINE
    ]
    cfg = {
        "titles": "Deductions Manager, Director of Deductions, VP Finance, Trade Finance Manager",
        "revenue_min": "$50M",
        "revenue_max": "$500M",
        "max_per_day": Config.MAX_PROSPECTS_PER_DAY,
    }
    return templates.TemplateResponse("config.html", {
        "request": request,
        "active": "config",
        "dry_run": Config.DRY_RUN,
        "env_vars": env_vars,
        "config": cfg,
    })


@router.post("/config/toggle-dry-run")
async def toggle_dry_run():
    import os
    current = os.environ.get("DRY_RUN", "true").lower() == "true"
    os.environ["DRY_RUN"] = "false" if current else "true"
    Config.DRY_RUN = not current
    return RedirectResponse("/ui/config", status_code=303)


@router.post("/trigger-run")
async def trigger_run():
    """Trigger the full pipeline (runs in background)."""
    import threading
    from aria.graph import main as run_pipeline

    def _run():
        try:
            run_pipeline()
        except Exception as e:
            logger.error(f"[UI] Manual pipeline run failed: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("[UI] Manual pipeline run triggered")
    return RedirectResponse("/ui", status_code=303)


@router.post("/trigger-reply-check")
async def trigger_reply_check():
    import threading
    from aria.agents.reply_handler import run as check_replies

    def _run():
        try:
            check_replies()
        except Exception as e:
            logger.error(f"[UI] Manual reply check failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return RedirectResponse("/ui/config", status_code=303)


@router.post("/trigger-followups")
async def trigger_followups():
    import threading
    from aria.agents.follow_up import run as send_followups

    def _run():
        try:
            send_followups()
        except Exception as e:
            logger.error(f"[UI] Manual follow-up failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return RedirectResponse("/ui/config", status_code=303)
