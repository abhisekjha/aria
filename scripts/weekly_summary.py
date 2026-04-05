"""
Weekly summary: pulls stats from Airtable and emails human.
Run every Monday via GitHub Actions.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyairtable import Api
from aria.config import Config
from aria.tools.gmail import send_alert
from aria.utils.logger import get_logger
import anthropic

logger = get_logger("weekly_summary")


def main():
    logger.info("[WEEKLY] Generating weekly summary")

    if Config.DRY_RUN:
        logger.info("[WEEKLY] DRY_RUN — skipping")
        return

    stats = _fetch_stats()
    summary_html = _generate_summary(stats)
    send_alert(subject="Aria — Weekly Sales Summary", body=summary_html)
    logger.info("[WEEKLY] Summary sent")


def _fetch_stats() -> dict:
    try:
        api = Api(Config.AIRTABLE_API_KEY)
        table = api.table(Config.AIRTABLE_BASE_ID, "Prospects")
        records = table.all()

        total = len(records)
        contacted = sum(1 for r in records if r["fields"].get("Outreach Sent"))
        replied = sum(1 for r in records if r["fields"].get("Reply Received"))
        demos = sum(1 for r in records if r["fields"].get("Meeting Booked"))
        hot = sum(1 for r in records if r["fields"].get("Tier") == "hot")
        closed_won = sum(1 for r in records if r["fields"].get("Deal Stage") == "closed_won")

        reply_rate = round((replied / contacted * 100) if contacted else 0, 1)

        return {
            "total_prospects": total,
            "contacted": contacted,
            "replied": replied,
            "reply_rate": reply_rate,
            "demos_booked": demos,
            "hot_in_pipeline": hot,
            "closed_won": closed_won,
        }
    except Exception as e:
        logger.error(f"[WEEKLY] _fetch_stats failed: {e}")
        return {}


def _generate_summary(stats: dict) -> str:
    if not stats:
        return "<p>Could not fetch stats this week.</p>"

    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    prompt = f"""Write a brief Monday morning sales summary email for Auralix.
Stats this week:
{stats}

Format as clean HTML. Keep it under 150 words.
Include: what's working, what needs attention, one suggested action for the week.
Be direct and honest — no fluff."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    narrative = response.content[0].text.strip()

    return f"""
<h2>📊 Aria — Weekly Summary</h2>
<table style="border-collapse:collapse;width:100%;margin-bottom:20px">
  <tr style="background:#f1f5f9">
    <th style="padding:8px;text-align:left">Metric</th>
    <th style="padding:8px;text-align:right">Count</th>
  </tr>
  <tr><td style="padding:8px">Total prospects</td><td style="padding:8px;text-align:right">{stats.get('total_prospects', 0)}</td></tr>
  <tr style="background:#f8fafc"><td style="padding:8px">Contacted</td><td style="padding:8px;text-align:right">{stats.get('contacted', 0)}</td></tr>
  <tr><td style="padding:8px">Replied</td><td style="padding:8px;text-align:right">{stats.get('replied', 0)} ({stats.get('reply_rate', 0)}%)</td></tr>
  <tr style="background:#f8fafc"><td style="padding:8px">Demos booked</td><td style="padding:8px;text-align:right">{stats.get('demos_booked', 0)}</td></tr>
  <tr><td style="padding:8px">Closed won</td><td style="padding:8px;text-align:right">{stats.get('closed_won', 0)}</td></tr>
</table>
{narrative}
"""


if __name__ == "__main__":
    main()
