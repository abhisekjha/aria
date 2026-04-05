import hmac
import hashlib
from typing import Optional
from datetime import datetime, timedelta

from aria.config import Config
from aria.tools.airtable import update_prospect, log_activity, get_prospect_by_email
from aria.utils.logger import get_logger

logger = get_logger(__name__)


def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """Verify Cal.com webhook HMAC signature."""
    if not Config.CAL_COM_WEBHOOK_SECRET:
        logger.error("[CAL_COM] CAL_COM_WEBHOOK_SECRET not set")
        return False

    expected = hmac.new(
        Config.CAL_COM_WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def handle_booking_created(payload: dict) -> Optional[dict]:
    """
    Handle Cal.com BOOKING_CREATED webhook.
    Finds prospect in Airtable, updates status, returns prospect data.
    """
    try:
        attendee = _extract_attendee(payload)
        if not attendee:
            return None

        meeting_dt = payload.get("startTime", "")
        logger.info(f"[CAL_COM] Booking created: {attendee['email']} at {meeting_dt}")

        # Find prospect in Airtable
        record = get_prospect_by_email(attendee["email"])
        if not record:
            logger.info(f"[CAL_COM] Prospect not in Airtable: {attendee['email']} — still logging")
            return attendee

        airtable_id = record["id"]
        update_prospect(airtable_id, {
            "Meeting Booked": True,
            "Meeting Date": meeting_dt,
            "Deal Stage": "demo_booked",
        })
        log_activity(airtable_id, "meeting_booked", f"Demo booked for {meeting_dt}")

        return {**record["fields"], "airtable_id": airtable_id, "meeting_datetime": meeting_dt}

    except Exception as e:
        logger.error(f"[CAL_COM] handle_booking_created failed: {e}")
        return None


def handle_booking_cancelled(payload: dict) -> None:
    """Handle Cal.com BOOKING_CANCELLED webhook."""
    try:
        attendee = _extract_attendee(payload)
        if not attendee:
            return

        record = get_prospect_by_email(attendee["email"])
        if record:
            update_prospect(record["id"], {"Meeting Booked": False, "Deal Stage": "replied"})
            log_activity(record["id"], "note_added", "Meeting was cancelled by prospect")

        logger.info(f"[CAL_COM] Booking cancelled: {attendee.get('email')}")

    except Exception as e:
        logger.error(f"[CAL_COM] handle_booking_cancelled failed: {e}")


def get_demo_prep_send_time(meeting_datetime_str: str) -> Optional[datetime]:
    """Return the datetime to send the demo prep brief (60 min before meeting)."""
    try:
        meeting_dt = datetime.fromisoformat(meeting_datetime_str.replace("Z", "+00:00"))
        return meeting_dt - timedelta(hours=1)
    except Exception as e:
        logger.error(f"[CAL_COM] get_demo_prep_send_time failed: {e}")
        return None


def _extract_attendee(payload: dict) -> Optional[dict]:
    """Extract attendee info from Cal.com webhook payload."""
    try:
        attendees = payload.get("attendees", [])
        if not attendees:
            return None
        attendee = attendees[0]
        return {
            "name": attendee.get("name", ""),
            "email": attendee.get("email", ""),
            "timezone": attendee.get("timeZone", "UTC"),
        }
    except Exception as e:
        logger.error(f"[CAL_COM] _extract_attendee failed: {e}")
        return None
