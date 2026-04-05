from pathlib import Path

from aria.state import AriaState, Prospect
from aria.config import Config
from aria.utils.llm import call_llm
from aria.utils.logger import get_logger, log_agent_start, log_agent_end

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def run(state: AriaState) -> AriaState:
    """
    Outreach writer node: writes personalized email + LinkedIn content
    for each approved prospect.
    """
    approved = [p for p in state["prospects"] if p.get("approved") is True]
    log_agent_start(logger, "outreach_writer", len(approved))

    written = []
    for p in state["prospects"]:
        if p.get("approved") is True:
            try:
                p = dict(p)
                p = _write_outreach(p)
            except Exception as e:
                logger.error(f"[OUTREACH_WRITER] Failed for {p.get('company')}: {e}")
                state["errors"].append(f"outreach_writer:{p.get('company')}: {e}")
        written.append(Prospect(**p))

    log_agent_end(logger, "outreach_writer", len(approved))
    return {**state, "prospects": written}


def _write_outreach(p: dict) -> dict:
    personalization = p.get("personalization_hook") or p.get("pain_angle") or ""
    revenue = p.get("company_revenue_estimate", "mid-size")
    retailers_str = ", ".join(p.get("retailers", [])[:2]) if p.get("retailers") else "major retailers"

    prompt = f"""Write a cold outreach email for this CPG sales prospect.

Prospect: {p['first_name']} {p['last_name']}, {p['title']} at {p['company']}
Revenue: {revenue}
Sells to: {retailers_str}
Personalization: {personalization}

Rules (enforce strictly):
- Under 120 words total
- Lead with THEIR pain (deduction backlog), not our product
- One question only, at the end
- No bullet points
- No "I hope this email finds you well"
- No "synergy", "leverage", "game-changing", "revolutionary"
- Sound like a human, not an AI
- Sign as: Abhisek | Auralix | auralix.ai

Return ONLY two lines:
SUBJECT: <subject line>
BODY:
<email body>"""

    raw = call_llm(prompt, tier="quality", max_tokens=400)

    # Parse subject and body
    subject = ""
    body = ""
    if "SUBJECT:" in raw and "BODY:" in raw:
        subject_line = raw.split("SUBJECT:")[1].split("BODY:")[0].strip()
        body_content = raw.split("BODY:")[1].strip()
        subject = subject_line
        body = body_content
    else:
        # Fallback: use full text as body
        subject = f"Retailer deductions — {p['company']}"
        body = raw

    # LinkedIn connection request (under 300 chars)
    linkedin_connection = (
        f"Hi {p['first_name']} — I work with CPG finance teams dealing with "
        f"retailer deduction backlogs. Think it could be relevant. Happy to connect."
    )

    # LinkedIn DM (after they accept)
    linkedin_dm = _write_linkedin_dm(p)

    p["email_subject"] = subject
    p["email_body"] = body
    p["linkedin_connection_msg"] = linkedin_connection[:300]
    p["linkedin_dm"] = linkedin_dm

    logger.info(f"[OUTREACH_WRITER] Wrote outreach for {p['first_name']} at {p['company']}")
    return p


def _write_linkedin_dm(p: dict) -> str:
    personalization = p.get("personalization_hook") or ""
    hook = f"\n\n{personalization}" if personalization else ""

    return (
        f"Thanks for connecting {p['first_name']}."
        f"{hook}\n\n"
        f"Quick question — how many unresolved retailer deductions is your team "
        f"sitting on right now? Most teams I talk to are managing 500–2,000 open "
        f"claims with dispute windows closing fast.\n\n"
        f"We built something that auto-generates evidence packs and flags which "
        f"ones are about to expire. Cut resolution time significantly for a few CPG teams.\n\n"
        f"Worth a 20-min call?"
    )
