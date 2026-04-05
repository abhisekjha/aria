from datetime import datetime, timedelta
from typing import List

from aria.state import Prospect
from aria.tools.airtable import get_prospects_for_followup, update_prospect, log_activity
from aria.tools.gmail import send_email
from aria.config import Config
from aria.utils.logger import get_logger

logger = get_logger(__name__)

FOLLOW_UP_1_DAYS = 3
FOLLOW_UP_2_DAYS = 10
BREAKUP_DAYS = 17


def run() -> None:
    """
    Follow-up agent: checks all prospects in outreach and sends
    follow-ups on the correct schedule.
    Runs as part of the nightly pipeline.
    """
    logger.info("[FOLLOW_UP] Checking follow-up schedule")

    if Config.DRY_RUN:
        logger.info("[FOLLOW_UP] DRY_RUN=true — skipping")
        return

    records = get_prospects_for_followup()
    logger.info(f"[FOLLOW_UP] {len(records)} prospects in active outreach")

    for record in records:
        try:
            _process_record(record)
        except Exception as e:
            logger.error(f"[FOLLOW_UP] Failed for {record.get('id')}: {e}")


def _process_record(record: dict) -> None:
    fields = record["fields"]
    airtable_id = record["id"]

    sent_at_str = fields.get("Outreach Sent At", "")
    if not sent_at_str:
        return

    try:
        sent_at = datetime.fromisoformat(sent_at_str.replace("Z", "+00:00"))
    except ValueError:
        return

    now = datetime.utcnow().replace(tzinfo=None)
    sent_at_naive = sent_at.replace(tzinfo=None)
    days_since = (now - sent_at_naive).days

    email = fields.get("Email", "")
    name = fields.get("Name", "").split()[0] or "there"
    company = fields.get("Company", "")

    if days_since >= BREAKUP_DAYS and not fields.get("Breakup Sent"):
        _send_breakup(email, name, company, airtable_id)

    elif days_since >= FOLLOW_UP_2_DAYS and not fields.get("Follow Up 2 Sent"):
        _send_follow_up_2(email, name, company, airtable_id)

    elif days_since >= FOLLOW_UP_1_DAYS and not fields.get("Follow Up 1 Sent"):
        _send_follow_up_1(email, name, company, airtable_id)


def _send_follow_up_1(email: str, name: str, company: str, airtable_id: str) -> None:
    subject = f"Re: Retailer deductions — {company}"
    body = f"""Hi {name} —

Following up on my email from a few days ago.

If a growing deduction backlog is something your team is dealing with, I'd love to show you how we're helping similar CPG teams recover disputed dollars before windows close.

Worth a 20-minute call?

Abhisek | Auralix | auralix.ai"""

    sent = send_email(email, subject, body)
    if sent:
        update_prospect(airtable_id, {
            "Follow Up 1 Sent": True,
            "Deal Stage": "contacted",
        })
        log_activity(airtable_id, "email_sent", f"Follow-up #1 sent")
        logger.info(f"[FOLLOW_UP] Sent follow-up #1 to {email}")


def _send_follow_up_2(email: str, name: str, company: str, airtable_id: str) -> None:
    subject = f"Re: Retailer deductions — {company}"
    body = f"""Hi {name} —

One more follow-up. CPG companies typically lose 1–3% of revenue annually to unresolved retailer deductions — most of it preventable.

Happy to send a 3-minute demo video if a call isn't convenient right now.

Abhisek | Auralix | auralix.ai"""

    sent = send_email(email, subject, body)
    if sent:
        update_prospect(airtable_id, {"Follow Up 2 Sent": True})
        log_activity(airtable_id, "email_sent", "Follow-up #2 sent")
        logger.info(f"[FOLLOW_UP] Sent follow-up #2 to {email}")


def _send_breakup(email: str, name: str, company: str, airtable_id: str) -> None:
    subject = f"Closing the loop — {company}"
    body = f"""Hi {name} —

I'll stop following up after this. If deduction recovery isn't a priority right now, completely understand.

If that changes, I'm at abhisek@auralix.ai.

Abhisek | Auralix | auralix.ai"""

    sent = send_email(email, subject, body)
    if sent:
        update_prospect(airtable_id, {
            "Breakup Sent": True,
            "Deal Stage": "cold",
        })
        log_activity(airtable_id, "email_sent", "Breakup email sent — moved to cold")
        logger.info(f"[FOLLOW_UP] Sent breakup email to {email}")
