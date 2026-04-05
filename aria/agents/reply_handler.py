import json
from datetime import datetime, timedelta
import anthropic

from aria.state import Prospect
from aria.tools.gmail import get_new_replies, send_alert, send_email
from aria.tools.airtable import get_prospect_by_email, update_prospect, log_activity
from aria.config import Config
from aria.utils.logger import get_logger
from aria.utils.rate_limiter import anthropic_limiter

logger = get_logger(__name__)
_client: anthropic.Anthropic = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _client


def run() -> None:
    """
    Reply handler: runs every 2 hours via GitHub Actions.
    Reads Gmail inbox, classifies replies, takes action.
    """
    logger.info("[REPLY_HANDLER] Starting reply monitor")
    replies = get_new_replies(since_hours=2)

    if not replies:
        logger.info("[REPLY_HANDLER] No new replies")
        return

    for reply in replies:
        try:
            _handle_reply(reply)
        except Exception as e:
            logger.error(f"[REPLY_HANDLER] Failed to handle reply from {reply.get('sender')}: {e}")


def _handle_reply(reply: dict) -> None:
    sender = reply["sender"]
    body = reply["body"]
    subject = reply["subject"]

    logger.info(f"[REPLY_HANDLER] Processing reply from {sender}")

    # Find prospect in Airtable
    record = get_prospect_by_email(sender)
    if not record:
        logger.info(f"[REPLY_HANDLER] Unknown sender {sender} — not in CRM, skipping")
        return

    airtable_id = record["id"]

    # Classify reply with Claude Haiku
    classification = _classify_reply(body)
    logger.info(f"[REPLY_HANDLER] {sender} → {classification['classification']}")

    # Update Airtable
    update_prospect(airtable_id, {
        "Reply Received": True,
        "Reply Classification": classification["classification"],
    })
    log_activity(airtable_id, "reply_received",
                 f"Classification: {classification['classification']}. Notes: {classification.get('notes', '')}")

    # Route based on classification
    c = classification["classification"]

    if c in ("POSITIVE", "QUESTION"):
        _handle_positive(reply, record, classification)

    elif c == "NOT_NOW":
        _handle_not_now(reply, record, classification)

    elif c == "WRONG_PERSON":
        _handle_wrong_person(reply, record, classification)

    elif c == "OUT_OF_OFFICE":
        _handle_ooo(reply, record, classification)

    elif c == "UNSUBSCRIBE":
        update_prospect(airtable_id, {"Do Not Contact": True, "Deal Stage": "cold"})
        log_activity(airtable_id, "stage_changed", "Unsubscribed — marked do not contact")
        logger.info(f"[REPLY_HANDLER] {sender} unsubscribed — marked DNC")

    elif c == "NEGATIVE":
        update_prospect(airtable_id, {"Deal Stage": "closed_lost"})
        log_activity(airtable_id, "stage_changed", "Negative reply — closed lost")

    else:
        # OTHER — flag for human
        send_alert(
            subject=f"⚠️ Aria — unusual reply from {sender}",
            body=f"<p>Reply from <strong>{sender}</strong> needs your attention:</p>"
                 f"<blockquote>{body[:500]}</blockquote>"
                 f"<p>Classification: {c}</p>"
        )


def _handle_positive(reply: dict, record: dict, classification: dict) -> None:
    sender = reply["sender"]
    body = reply["body"]
    airtable_id = record["id"]
    prospect_name = record["fields"].get("Name", sender)
    company = record["fields"].get("Company", "")

    # Draft a response with Cal.com link
    draft = _draft_response(body, record["fields"])

    # Update stage
    update_prospect(airtable_id, {"Deal Stage": "replied"})

    # Send immediate alert to human
    send_alert(
        subject=f"🔥 Reply from {prospect_name} @ {company} — action needed",
        body=f"""
<h2>🔥 Hot Reply</h2>
<p><strong>{prospect_name}</strong> ({company}) replied:</p>
<blockquote style="border-left:3px solid #ccc;padding:10px;color:#555">
{body[:600]}
</blockquote>

<hr>
<h3>My suggested response:</h3>
<blockquote style="border-left:3px solid #22c55e;padding:10px">
{draft}
</blockquote>

<p>
<a href="{Config.RAILWAY_WEBHOOK_URL}/send-reply?airtable_id={airtable_id}&approved=true"
   style="background:#22c55e;color:white;padding:12px 20px;text-decoration:none;border-radius:5px;margin-right:10px">
✅ SEND THIS RESPONSE
</a>
<a href="{Config.RAILWAY_WEBHOOK_URL}/send-reply?airtable_id={airtable_id}&approved=false"
   style="background:#64748b;color:white;padding:12px 20px;text-decoration:none;border-radius:5px">
✏️ I'LL REPLY MYSELF
</a>
</p>
"""
    )
    logger.info(f"[REPLY_HANDLER] Hot reply alert sent for {sender}")


def _handle_not_now(reply: dict, record: dict, classification: dict) -> None:
    airtable_id = record["id"]
    extracted = classification.get("extracted_info", "")

    # Try to extract re-engage date
    re_engage = (datetime.utcnow() + timedelta(days=90)).date().isoformat()

    update_prospect(airtable_id, {
        "Deal Stage": "not_now",
        "Re-engage Date": re_engage,
    })
    log_activity(airtable_id, "note_added", f"Not now reply. Re-engage: {re_engage}. Info: {extracted}")
    logger.info(f"[REPLY_HANDLER] Not now — re-engage scheduled for {re_engage}")


def _handle_wrong_person(reply: dict, record: dict, classification: dict) -> None:
    airtable_id = record["id"]
    extracted = classification.get("extracted_info", "")
    log_activity(airtable_id, "note_added", f"Wrong person reply. Redirect info: {extracted}")
    send_alert(
        subject=f"↪️ Aria — wrong person redirect from {reply['sender']}",
        body=f"<p>They redirected us to someone else:</p><p><strong>{extracted}</strong></p>"
             f"<p>Add the new contact to Apollo and requeue.</p>"
    )


def _handle_ooo(reply: dict, record: dict, classification: dict) -> None:
    airtable_id = record["id"]
    extracted = classification.get("extracted_info", "")
    return_date = extracted if extracted else (datetime.utcnow() + timedelta(days=7)).date().isoformat()
    update_prospect(airtable_id, {"Re-engage Date": return_date})
    log_activity(airtable_id, "note_added", f"OOO — return date: {return_date}")
    logger.info(f"[REPLY_HANDLER] OOO — re-engage on {return_date}")


def _classify_reply(body: str) -> dict:
    prompt = f"""Classify this email reply into exactly one category:
- POSITIVE: interested, wants to learn more, asks questions
- QUESTION: asks a specific question but hasn't committed
- NOT_NOW: reach out later (note any timeframe given)
- WRONG_PERSON: redirects to someone else (extract name/email if given)
- OUT_OF_OFFICE: auto-reply (extract return date if given)
- UNSUBSCRIBE: asks to be removed from emails
- NEGATIVE: clearly not interested
- OTHER: anything else

Email:
{body[:800]}

Return ONLY JSON: {{"classification": "...", "notes": "...", "extracted_info": "..."}}"""

    anthropic_limiter.wait()
    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return json.loads(response.content[0].text.strip())
    except Exception:
        return {"classification": "OTHER", "notes": "Could not parse", "extracted_info": ""}


def _draft_response(reply_body: str, prospect_fields: dict) -> str:
    name = prospect_fields.get("Name", "").split()[0] if prospect_fields.get("Name") else "there"

    prompt = f"""Draft a brief, human reply to this prospect's email.
Include the Cal.com booking link: {Config.CAL_COM_LINK}
Sign as: Abhisek | Auralix | auralix.ai

Their email:
{reply_body[:600]}

Rules: Under 80 words. Warm but not salesy. Suggest a quick call. Include booking link naturally."""

    anthropic_limiter.wait()
    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()
