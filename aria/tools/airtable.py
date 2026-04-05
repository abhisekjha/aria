from typing import Optional, List
from pyairtable import Api
from aria.config import Config
from aria.state import Prospect
from aria.utils.logger import get_logger, log_airtable_write
from aria.utils.rate_limiter import airtable_limiter
from datetime import datetime

logger = get_logger(__name__)

TABLE_PROSPECTS = "Prospects"
TABLE_ACTIVITY = "Activity Log"

_api: Optional[Api] = None


def _get_api() -> Api:
    global _api
    if _api is None:
        _api = Api(Config.AIRTABLE_API_KEY)
    return _api


def _get_table(table_name: str):
    return _get_api().table(Config.AIRTABLE_BASE_ID, table_name)


# ── Prospects ──────────────────────────────────────────────────────────────────

def upsert_prospect(prospect: Prospect) -> str:
    """
    Create or update a prospect in Airtable.
    Returns the Airtable record ID.
    Never raises.
    """
    if Config.DRY_RUN:
        logger.info(f"[AIRTABLE] DRY_RUN — skipping upsert for {prospect['email']}")
        return "dry-run-id"

    airtable_limiter.wait()

    try:
        table = _get_table(TABLE_PROSPECTS)
        fields = _prospect_to_fields(prospect)

        if prospect.get("airtable_id"):
            table.update(prospect["airtable_id"], fields)
            log_airtable_write(logger, TABLE_PROSPECTS, prospect["airtable_id"], "UPDATE")
            return prospect["airtable_id"]
        else:
            record = table.create(fields)
            record_id = record["id"]
            log_airtable_write(logger, TABLE_PROSPECTS, record_id, "CREATE")
            return record_id

    except Exception as e:
        logger.error(f"[AIRTABLE] upsert_prospect failed for {prospect.get('email')}: {e}")
        return ""


def get_prospect_by_email(email: str) -> Optional[dict]:
    """Check if a prospect already exists. Returns raw Airtable record or None."""
    if Config.DRY_RUN:
        return None

    airtable_limiter.wait()

    try:
        table = _get_table(TABLE_PROSPECTS)
        records = table.all(formula=f"{{Email}} = '{email}'")
        return records[0] if records else None
    except Exception as e:
        logger.error(f"[AIRTABLE] get_prospect_by_email failed: {e}")
        return None


def get_all_prospect_emails() -> List[str]:
    """Return all emails in Airtable for deduplication."""
    if Config.DRY_RUN:
        return []

    airtable_limiter.wait()

    try:
        table = _get_table(TABLE_PROSPECTS)
        records = table.all(fields=["Email"])
        return [r["fields"].get("Email", "") for r in records if r["fields"].get("Email")]
    except Exception as e:
        logger.error(f"[AIRTABLE] get_all_prospect_emails failed: {e}")
        return []


def update_prospect(airtable_id: str, fields: dict) -> bool:
    """Update specific fields on a prospect record."""
    if Config.DRY_RUN:
        logger.info(f"[AIRTABLE] DRY_RUN — skipping update for {airtable_id}")
        return True

    airtable_limiter.wait()

    try:
        table = _get_table(TABLE_PROSPECTS)
        table.update(airtable_id, fields)
        log_airtable_write(logger, TABLE_PROSPECTS, airtable_id, "UPDATE")
        return True
    except Exception as e:
        logger.error(f"[AIRTABLE] update_prospect failed for {airtable_id}: {e}")
        return False


def get_prospects_for_followup() -> List[dict]:
    """Return prospects due for follow-up today."""
    if Config.DRY_RUN:
        return []

    airtable_limiter.wait()

    try:
        today = datetime.utcnow().date().isoformat()
        table = _get_table(TABLE_PROSPECTS)
        formula = (
            f"AND("
            f"{{Outreach Sent}} = 1, "
            f"{{Reply Received}} = 0, "
            f"{{Do Not Contact}} = 0, "
            f"{{Breakup Sent}} = 0"
            f")"
        )
        return table.all(formula=formula)
    except Exception as e:
        logger.error(f"[AIRTABLE] get_prospects_for_followup failed: {e}")
        return []


# ── Activity Log ───────────────────────────────────────────────────────────────

def log_activity(airtable_prospect_id: str, action: str, details: str) -> None:
    """Append an activity log entry. Never raises."""
    if Config.DRY_RUN:
        logger.info(f"[AIRTABLE] DRY_RUN — activity log: {action} — {details[:50]}")
        return

    airtable_limiter.wait()

    try:
        table = _get_table(TABLE_ACTIVITY)
        table.create({
            "Prospect": [airtable_prospect_id],
            "Action": action,
            "Details": details,
            "Timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error(f"[AIRTABLE] log_activity failed: {e}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _prospect_to_fields(p: Prospect) -> dict:
    """Map Prospect TypedDict to Airtable field names."""
    return {
        "Name": f"{p['first_name']} {p['last_name']}".strip(),
        "Email": p["email"],
        "Title": p["title"],
        "Company": p["company"],
        "Domain": p["company_domain"],
        "Score": p["score"],
        "Tier": p["tier"] or "",
        "Deal Stage": p["deal_stage"],
        "Research Summary": p["research_summary"],
        "Pain Angle": p["pain_angle"],
        "Email Body": p.get("email_body") or "",
        "Outreach Sent": p["outreach_sent"],
        "Follow Up 1 Sent": p["follow_up_1_sent"],
        "Follow Up 2 Sent": p["follow_up_2_sent"],
        "Breakup Sent": p["breakup_sent"],
        "Reply Received": p["reply_received"],
        "Reply Classification": p.get("reply_classification") or "",
        "Meeting Booked": p["meeting_booked"],
        "Meeting Date": p.get("meeting_datetime") or "",
        "Re-engage Date": p.get("re_engage_date") or "",
        "Do Not Contact": p["do_not_contact"],
        "LinkedIn URL": p["linkedin_url"],
        "Notes": p["notes"],
    }
