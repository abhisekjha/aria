import smtplib
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from datetime import datetime, timedelta

from aria.config import Config
from aria.utils.logger import get_logger, log_email_sent
from aria.utils.rate_limiter import gmail_send_limiter

logger = get_logger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
    html: bool = False,
) -> bool:
    """
    Send email via Gmail SMTP.
    Returns True on success, False on failure. Never raises.
    """
    if Config.DRY_RUN:
        logger.info(f"[GMAIL] DRY_RUN — would send to={to} subject='{subject}'")
        return True

    gmail_send_limiter.wait()

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = Config.GMAIL_ADDRESS
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to

        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(Config.GMAIL_ADDRESS, Config.GMAIL_APP_PASSWORD)
            server.sendmail(Config.GMAIL_ADDRESS, to, msg.as_string())

        log_email_sent(logger, to, subject)
        return True

    except Exception as e:
        logger.error(f"[GMAIL] send_email failed to={to}: {e}")
        return False


def send_alert(subject: str, body: str) -> bool:
    """Send an alert email to the human. Convenience wrapper."""
    return send_email(
        to=Config.HUMAN_EMAIL,
        subject=subject,
        body=body,
        html=True,
    )


def get_new_replies(since_hours: int = 2) -> List[dict]:
    """
    Read Gmail inbox for new replies from known prospects.
    Uses Gmail API (OAuth2).
    Returns list of {sender, subject, body, message_id, thread_id}.
    Never raises.
    """
    if Config.DRY_RUN:
        logger.info("[GMAIL] DRY_RUN — skipping inbox read")
        return []

    if not Config.GMAIL_OAUTH_CREDENTIALS:
        logger.error("[GMAIL] GMAIL_OAUTH_CREDENTIALS not set — cannot read inbox")
        return []

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds_dict = json.loads(Config.GMAIL_OAUTH_CREDENTIALS)
        creds = Credentials.from_authorized_user_info(creds_dict)
        service = build("gmail", "v1", credentials=creds)

        # Search for unread emails in inbox from last N hours
        since = (datetime.utcnow() - timedelta(hours=since_hours)).strftime("%Y/%m/%d")
        query = f"in:inbox is:unread after:{since} -from:me"

        result = service.users().messages().list(userId="me", q=query).execute()
        messages = result.get("messages", [])

        replies = []
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full"
            ).execute()

            parsed = _parse_gmail_message(msg)
            if parsed:
                replies.append(parsed)
                # Mark as read
                service.users().messages().modify(
                    userId="me",
                    id=msg_ref["id"],
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()

        logger.info(f"[GMAIL] Found {len(replies)} new replies")
        return replies

    except Exception as e:
        logger.error(f"[GMAIL] get_new_replies failed: {e}")
        return []


def _parse_gmail_message(msg: dict) -> Optional[dict]:
    """Extract sender, subject, body from a Gmail API message object."""
    try:
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        sender = headers.get("From", "")
        subject = headers.get("Subject", "")
        message_id = msg["id"]
        thread_id = msg["threadId"]

        # Extract body
        body = _extract_body(msg["payload"])

        # Extract sender email
        import re
        email_match = re.search(r"<(.+?)>", sender)
        sender_email = email_match.group(1) if email_match else sender

        return {
            "sender": sender_email,
            "sender_raw": sender,
            "subject": subject,
            "body": body,
            "message_id": message_id,
            "thread_id": thread_id,
        }
    except Exception as e:
        logger.error(f"[GMAIL] _parse_gmail_message failed: {e}")
        return None


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from Gmail payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text

    return ""
