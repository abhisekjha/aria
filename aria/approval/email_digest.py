from typing import List
from datetime import datetime

from aria.state import Prospect
from aria.approval.tokens import generate_token
from aria.tools.gmail import send_alert
from aria.config import Config
from aria.utils.logger import get_logger

logger = get_logger(__name__)


def send_morning_digest(prospects: List[Prospect], run_id: str) -> str:
    """
    Build and send the morning digest email to the human.
    Returns the digest token (same for all prospects in this run).
    """
    hot = [p for p in prospects if p.get("tier") == "hot"]

    if not hot:
        logger.info("[DIGEST] No hot prospects to review today")
        send_alert(
            subject="Aria — No hot prospects today",
            body="<p>No hot prospects found in today's run. Warm prospects have been stored in Airtable for future outreach.</p>"
        )
        return ""

    # Generate tokens for each prospect
    tokens = {p["id"]: generate_token(p["id"]) for p in hot}

    body = _build_digest_html(hot, tokens, run_id)
    subject = f"Aria — {len(hot)} prospect{'s' if len(hot) > 1 else ''} ready for review ({datetime.utcnow().strftime('%b %d')})"

    send_alert(subject=subject, body=body)
    logger.info(f"[DIGEST] Sent morning digest with {len(hot)} prospects")

    return run_id


def _build_digest_html(prospects: List[Prospect], tokens: dict, run_id: str) -> str:
    base_url = Config.RAILWAY_WEBHOOK_URL
    date_str = datetime.utcnow().strftime("%B %d, %Y")

    cards = ""
    for i, p in enumerate(prospects, 1):
        token = tokens[p["id"]]
        approve_url = f"{base_url}/approve?token={token}&prospect={p['id']}&run={run_id}"
        reject_url = f"{base_url}/reject?token={token}&prospect={p['id']}&run={run_id}"

        email_preview = (p.get("email_body") or "")[:200].replace("\n", "<br>")
        retailers_str = ", ".join(p.get("retailers", [])[:3]) or "unknown retailers"
        hook = p.get("personalization_hook") or p.get("pain_angle") or "No specific hook found."

        cards += f"""
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:20px">
  <div style="display:flex;align-items:center;margin-bottom:12px">
    <span style="background:#22c55e;color:white;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:bold;margin-right:10px">
      🟢 HOT #{i}
    </span>
    <strong style="font-size:16px">{p['first_name']} {p['last_name']}</strong>
    <span style="color:#64748b;margin-left:8px">{p['title']} @ {p['company']}</span>
  </div>

  <table style="width:100%;margin-bottom:12px">
    <tr>
      <td style="color:#64748b;width:80px">Score</td>
      <td><strong>{p['score']}/100</strong></td>
    </tr>
    <tr>
      <td style="color:#64748b">Revenue</td>
      <td>{p.get('company_revenue_estimate', 'unknown')}</td>
    </tr>
    <tr>
      <td style="color:#64748b">Retailers</td>
      <td>{retailers_str}</td>
    </tr>
    <tr>
      <td style="color:#64748b">Why</td>
      <td>{p.get('research_summary', '')[:150]}</td>
    </tr>
    <tr>
      <td style="color:#64748b">Hook</td>
      <td><em>{hook[:120]}</em></td>
    </tr>
  </table>

  <div style="background:#f8fafc;padding:12px;border-radius:4px;margin-bottom:16px;font-size:13px;color:#374151">
    <strong>Email preview:</strong><br><br>
    {email_preview}...
  </div>

  <div>
    <a href="{approve_url}"
       style="background:#22c55e;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;margin-right:12px;display:inline-block">
      ✅ APPROVE
    </a>
    <a href="{reject_url}"
       style="background:#ef4444;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block">
      ❌ REJECT
    </a>
  </div>
</div>
"""

    approve_all_url = f"{base_url}/approve-all?run={run_id}&ids={','.join(p['id'] for p in prospects)}"

    return f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;padding:20px">

  <h1 style="font-size:22px;margin-bottom:4px">Good morning.</h1>
  <p style="color:#64748b;margin-bottom:24px">
    Here are today's Auralix prospects — {date_str}.<br>
    Tap Approve or Reject for each. Approved emails go out automatically.
  </p>

  {cards}

  <div style="text-align:center;margin-top:24px;padding:16px;background:#f1f5f9;border-radius:8px">
    <a href="{approve_all_url}"
       style="background:#1d4ed8;color:white;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block">
      ✅ APPROVE ALL {len(prospects)}
    </a>
  </div>

  <p style="color:#94a3b8;font-size:12px;margin-top:24px;text-align:center">
    Aria — running daily for Auralix · Reply with any notes before approving
  </p>
</div>
"""
