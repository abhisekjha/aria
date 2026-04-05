"""
Main LangGraph pipeline for Aria.
Runs nightly via GitHub Actions.
"""
import uuid
from datetime import datetime

from langgraph.graph import StateGraph, END

from aria.state import AriaState
from aria.config import Config
from aria.utils.logger import get_logger
from aria.tools.airtable import upsert_prospect, log_activity
from aria.tools.gmail import send_alert
from aria.approval.email_digest import send_morning_digest
from aria.agents import prospector, researcher, qualifier, outreach_writer, follow_up

logger = get_logger(__name__)


# ── Node functions ────────────────────────────────────────────────────────────

def prospector_node(state: AriaState) -> AriaState:
    return prospector.run(state)


def researcher_node(state: AriaState) -> AriaState:
    return researcher.run(state)


def qualifier_node(state: AriaState) -> AriaState:
    return qualifier.run(state)


def build_digest_node(state: AriaState) -> AriaState:
    """Save all prospects to Airtable, then send morning digest for hot ones."""
    # Save everyone to Airtable first
    for p in state["prospects"]:
        p = dict(p)
        airtable_id = upsert_prospect(p)
        if airtable_id and not p.get("airtable_id"):
            p["airtable_id"] = airtable_id

    hot = [p for p in state["prospects"] if p.get("tier") == "hot"]
    warm = [p for p in state["prospects"] if p.get("tier") == "warm"]
    cold = [p for p in state["prospects"] if p.get("tier") == "cold"]

    logger.info(f"[GRAPH] Saved to Airtable: hot={len(hot)} warm={len(warm)} cold={len(cold)}")

    if hot:
        # Pre-write outreach content BEFORE sending digest
        # (so human can preview the email in the digest)
        state_with_written = outreach_writer.run({**state, "prospects": hot})
        hot_written = state_with_written["prospects"]

        # Temporarily mark all as approved for writing, then reset
        for p in hot_written:
            p = dict(p)
            p["approved"] = None  # Reset — human hasn't decided yet

        token = send_morning_digest(hot_written, state["run_id"])
        return {**state, "digest_sent": True, "digest_token": token}
    else:
        logger.info("[GRAPH] No hot prospects — skipping digest")
        return {**state, "digest_sent": False}


def send_outreach_node(state: AriaState) -> AriaState:
    """Send approved outreach emails and log to Airtable."""
    from aria.tools.gmail import send_email as gmail_send
    from datetime import datetime

    approved = [p for p in state["prospects"] if p.get("approved") is True]
    sent_count = 0

    for p in approved:
        if not p.get("email_body") or not p.get("email"):
            continue

        success = gmail_send(
            to=p["email"],
            subject=p.get("email_subject", f"Retailer deductions — {p['company']}"),
            body=p["email_body"],
        )

        if success:
            sent_count += 1
            now = datetime.utcnow().isoformat()
            if p.get("airtable_id"):
                from aria.tools.airtable import update_prospect
                update_prospect(p["airtable_id"], {
                    "Outreach Sent": True,
                    "Outreach Sent At": now,
                    "Deal Stage": "contacted",
                })
                log_activity(p["airtable_id"], "email_sent",
                             f"Cold outreach sent: {p.get('email_subject', '')}")

    logger.info(f"[GRAPH] Sent {sent_count} outreach emails")
    return {**state, "outreach_sent_count": sent_count}


def linkedin_digest_node(state: AriaState) -> AriaState:
    """Email human the LinkedIn copy-paste content for approved prospects."""
    approved = [p for p in state["prospects"] if p.get("approved") is True]

    if not approved:
        return state

    content = "<h2>📱 LinkedIn Actions for Today</h2><p>Copy-paste these into LinkedIn (takes ~10 min):</p>"

    for p in approved:
        content += f"""
<hr>
<h3>{p['first_name']} {p['last_name']} — {p['title']} @ {p['company']}</h3>
<p><a href="{p.get('linkedin_url', '#')}">LinkedIn Profile →</a></p>

<p><strong>Connection request message:</strong></p>
<blockquote style="background:#f1f5f9;padding:12px;border-radius:4px">
{p.get('linkedin_connection_msg', '')}
</blockquote>

<p><strong>First DM (send after they accept):</strong></p>
<blockquote style="background:#f1f5f9;padding:12px;border-radius:4px">
{(p.get('linkedin_dm') or '').replace(chr(10), '<br>')}
</blockquote>
"""

    send_alert(subject=f"Aria — LinkedIn actions for {len(approved)} prospect(s)", body=content)
    logger.info(f"[GRAPH] Sent LinkedIn digest for {len(approved)} prospects")
    return state


def followup_node(state: AriaState) -> AriaState:
    """Run the follow-up scheduler."""
    follow_up.run()
    return state


def error_check_node(state: AriaState) -> AriaState:
    """If too many errors, send alert to human."""
    errors = state.get("errors", [])
    if len(errors) >= 3:
        send_alert(
            subject=f"⚠️ Aria — {len(errors)} errors in tonight's run",
            body="<p>Aria encountered multiple errors:</p><ul>"
                 + "".join(f"<li>{e}</li>" for e in errors)
                 + "</ul>"
        )
        logger.error(f"[GRAPH] {len(errors)} errors — alert sent")
    return state


# ── Graph definition ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AriaState)

    graph.add_node("prospector", prospector_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("qualifier", qualifier_node)
    graph.add_node("build_digest", build_digest_node)
    graph.add_node("send_outreach", send_outreach_node)
    graph.add_node("linkedin_digest", linkedin_digest_node)
    graph.add_node("follow_up", followup_node)
    graph.add_node("error_check", error_check_node)

    graph.set_entry_point("prospector")
    graph.add_edge("prospector", "researcher")
    graph.add_edge("researcher", "qualifier")
    graph.add_edge("qualifier", "build_digest")
    graph.add_edge("build_digest", "follow_up")
    graph.add_edge("follow_up", "error_check")
    graph.add_edge("error_check", END)

    return graph.compile()


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    missing = Config.validate_soft()
    if missing and not Config.DRY_RUN:
        logger.error(f"[ARIA] Missing env vars: {missing}. Set DRY_RUN=true or fill in .env")
        return

    if Config.DRY_RUN:
        logger.info("[ARIA] Running in DRY_RUN mode — no emails or Airtable writes")

    initial_state: AriaState = {
        "run_id": str(uuid.uuid4()),
        "run_date": datetime.utcnow().date().isoformat(),
        "prospects": [],
        "digest_sent": False,
        "digest_token": "",
        "approvals_received": [],
        "rejections_received": [],
        "outreach_sent_count": 0,
        "errors": [],
    }

    logger.info(f"[ARIA] Starting nightly run {initial_state['run_id']}")

    graph = build_graph()
    final_state = graph.invoke(initial_state)

    logger.info(
        f"[ARIA] Run complete — "
        f"prospects={len(final_state['prospects'])} "
        f"outreach_sent={final_state['outreach_sent_count']} "
        f"errors={len(final_state['errors'])}"
    )


if __name__ == "__main__":
    main()
