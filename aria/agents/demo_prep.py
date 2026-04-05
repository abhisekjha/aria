from datetime import datetime
import anthropic

from aria.tools.airtable import get_prospect_by_email
from aria.tools.gmail import send_alert
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


def run(attendee_email: str, meeting_datetime: str) -> None:
    """
    Generate and send a pre-meeting brief 60 minutes before a booked demo.
    Triggered by Cal.com webhook via the approval server.
    """
    logger.info(f"[DEMO_PREP] Generating brief for {attendee_email} at {meeting_datetime}")

    # Pull prospect data from Airtable
    record = get_prospect_by_email(attendee_email)
    if not record:
        logger.info(f"[DEMO_PREP] Prospect {attendee_email} not in Airtable — generating generic brief")
        prospect_context = f"New prospect: {attendee_email}"
    else:
        fields = record["fields"]
        prospect_context = _build_context(fields)

    # Generate brief with Claude Sonnet
    brief_html = _generate_brief(prospect_context, meeting_datetime)

    # Send to human
    meeting_time_str = _format_time(meeting_datetime)
    send_alert(
        subject=f"📋 Demo prep — meeting at {meeting_time_str}",
        body=brief_html,
    )

    logger.info(f"[DEMO_PREP] Brief sent for {attendee_email}")


def _build_context(fields: dict) -> str:
    return f"""
Name: {fields.get('Name', 'Unknown')}
Title: {fields.get('Title', 'Unknown')}
Company: {fields.get('Company', 'Unknown')}
Score: {fields.get('Score', 'N/A')}
Research Summary: {fields.get('Research Summary', 'N/A')}
Pain Angle: {fields.get('Pain Angle', 'N/A')}
Reply Classification: {fields.get('Reply Classification', 'N/A')}
Notes: {fields.get('Notes', 'None')}
""".strip()


def _generate_brief(context: str, meeting_datetime: str) -> str:
    prompt = f"""Generate a demo prep brief for this sales call.

Prospect info:
{context}

Meeting: {meeting_datetime}

Format as clean HTML email with these exact sections:

<h2>📋 Demo Prep Brief</h2>

<h3>1. WHO YOU'RE MEETING</h3>
[Name, title, company, 1-2 sentences of context]

<h3>2. WHAT THEY CARE ABOUT</h3>
[Top 3 likely pain points — be specific to their situation]

<h3>3. DEMO FLOW (15 minutes)</h3>
[Numbered steps — ALWAYS start with Claims Workbench.
Show: risk scoring → expiring claims → evidence pack generator.
Do NOT mention Scenario Lab, ICC, or Outreach on this call.]

<h3>4. DISCOVERY QUESTIONS</h3>
[3 specific questions to open the call and uncover depth of pain]

<h3>5. LIKELY OBJECTIONS</h3>
[Top 2 objections + how to handle each briefly]

<h3>6. GOAL FOR THIS CALL</h3>
[One clear goal — book second call with finance decision maker]

Keep it tight. You're reading this 60 minutes before the meeting."""

    anthropic_limiter.wait()
    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


def _format_time(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%I:%M %p UTC on %b %d")
    except Exception:
        return dt_str
