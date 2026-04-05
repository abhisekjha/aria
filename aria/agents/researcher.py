import json
from pathlib import Path
from typing import List
import anthropic

from aria.state import AriaState, Prospect
from aria.tools.web_search import web_search, web_fetch
from aria.config import Config
from aria.utils.logger import get_logger, log_agent_start, log_agent_end
from aria.utils.rate_limiter import anthropic_limiter

logger = get_logger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "research.txt"
_client: anthropic.Anthropic = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _client


def run(state: AriaState) -> AriaState:
    """
    Researcher node: enriches each prospect with company intelligence.
    Runs in sequence (not parallel) to respect rate limits.
    """
    log_agent_start(logger, "researcher", len(state["prospects"]))

    enriched = []
    for prospect in state["prospects"]:
        try:
            p = _enrich(prospect)
            enriched.append(p)
        except Exception as e:
            logger.error(f"[RESEARCHER] Failed to enrich {prospect.get('company')}: {e}")
            state["errors"].append(f"researcher:{prospect.get('company')}: {e}")
            enriched.append(prospect)  # Keep original, don't drop

    # Filter out disqualified
    active = [p for p in enriched if not p["disqualified"]]
    disqualified = [p for p in enriched if p["disqualified"]]

    logger.info(f"[RESEARCHER] {len(active)} active, {len(disqualified)} disqualified")
    log_agent_end(logger, "researcher", len(active))

    return {**state, "prospects": active}


def _enrich(prospect: Prospect) -> Prospect:
    """Run research for a single prospect. Returns enriched Prospect."""
    company = prospect["company"]
    domain = prospect["company_domain"]
    logger.info(f"[RESEARCHER] Researching {company}")

    # Gather raw research data
    context_parts = []

    results = web_search(f"{company} CPG retailers sells to Walmart Target")
    if results:
        context_parts.append("Search results (retailers):\n" + "\n".join(
            f"- {r['title']}: {r['snippet']}" for r in results[:3]
        ))

    results2 = web_search(f"{company} annual revenue trade spend CPG")
    if results2:
        context_parts.append("Search results (revenue):\n" + "\n".join(
            f"- {r['title']}: {r['snippet']}" for r in results2[:3]
        ))

    results3 = web_search(f"site:linkedin.com/jobs {company} deductions manager trade finance")
    if results3:
        context_parts.append("Job search results:\n" + "\n".join(
            f"- {r['title']}: {r['snippet']}" for r in results3[:3]
        ))

    results4 = web_search(f"{company} 2025 2026 news trade promotion")
    if results4:
        context_parts.append("Recent news:\n" + "\n".join(
            f"- {r['title']}: {r['snippet']}" for r in results4[:3]
        ))

    if domain:
        homepage = web_fetch(f"https://{domain}", max_chars=2000)
        if homepage:
            context_parts.append(f"Homepage content:\n{homepage}")

    context = "\n\n".join(context_parts) if context_parts else "No data found."

    # Call Claude Haiku (cheap) for analysis
    prompt = _load_prompt().format(
        company=company,
        domain=domain,
        title=prospect["title"],
        context=context,
    )

    anthropic_limiter.wait()
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            logger.error(f"[RESEARCHER] Could not parse JSON for {company}: {raw[:100]}")
            return prospect

    # Apply enrichment to prospect
    p = dict(prospect)
    p["retailers"] = data.get("retailers", [])
    p["company_revenue_estimate"] = data.get("revenue_confirmed", prospect["company_revenue_estimate"])
    p["tpm_software_detected"] = data.get("tpm_software_detected", False)
    p["job_signal"] = data.get("job_signal", False)
    p["recent_news"] = data.get("recent_news")
    p["personalization_hook"] = data.get("personalization_hook")
    p["pain_angle"] = data.get("pain_angle", "")
    p["disqualified"] = data.get("disqualify", False)
    p["disqualify_reason"] = data.get("disqualify_reason")
    p["research_summary"] = _build_summary(p)

    logger.info(
        f"[RESEARCHER] {company} — retailers={p['retailers']} "
        f"job_signal={p['job_signal']} disqualified={p['disqualified']}"
    )

    return Prospect(**p)


def _build_summary(p: dict) -> str:
    retailers_str = ", ".join(p["retailers"]) if p["retailers"] else "unknown retailers"
    summary = f"{p['company']} ({p['company_revenue_estimate']}) sells to {retailers_str}."
    if p.get("job_signal"):
        summary += " Active deductions/trade finance job posting — signals backlog pain."
    if p.get("recent_news"):
        summary += f" Recent: {p['recent_news']}"
    return summary


def _load_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text()
    return _DEFAULT_PROMPT


_DEFAULT_PROMPT = """
You are researching a CPG company as a potential sales prospect for Auralix,
a trade promotion deduction management platform.

Company: {company}
Website: {domain}
Contact title: {title}

Research data collected:
{context}

Return ONLY a valid JSON object with exactly these fields:
{{
  "retailers": ["list of retailers they sell to — only confirmed, not assumed"],
  "revenue_confirmed": "$XM-$YM or unknown",
  "tpm_software_detected": false,
  "job_signal": false,
  "recent_news": "one sentence or null",
  "personalization_hook": "one specific recent fact for outreach, or null",
  "pain_angle": "one sentence — the strongest deduction pain angle for this prospect",
  "disqualify": false,
  "disqualify_reason": null
}}

Set disqualify=true if: already uses SAP TPM/Salesforce TPM/UpClear,
revenue under $20M or over $1B, or pure private label company.
Return ONLY the JSON. No preamble, no markdown.
"""
