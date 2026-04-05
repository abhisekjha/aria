from aria.state import AriaState, Prospect
from aria.utils.logger import get_logger, log_agent_start, log_agent_end

logger = get_logger(__name__)


def run(state: AriaState) -> AriaState:
    """
    Qualifier node: scores each prospect 0-100 and segments into hot/warm/cold.
    Purely deterministic — no Claude call needed.
    """
    log_agent_start(logger, "qualifier", len(state["prospects"]))

    scored = []
    for p in state["prospects"]:
        p = dict(p)
        p["score"] = score_prospect(p)
        p["tier"] = tier(p["score"])
        scored.append(Prospect(**p))
        logger.info(f"[QUALIFIER] {p['company']} — {p['first_name']} {p['last_name']} score={p['score']} tier={p['tier']}")

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    hot = [p for p in scored if p["tier"] == "hot"]
    warm = [p for p in scored if p["tier"] == "warm"]
    cold = [p for p in scored if p["tier"] == "cold"]

    logger.info(f"[QUALIFIER] hot={len(hot)} warm={len(warm)} cold={len(cold)}")
    log_agent_end(logger, "qualifier", len(scored))

    return {**state, "prospects": scored}


def score_prospect(p: dict) -> int:
    score = 0

    # Retailer signals (max 25)
    high_volume = ["walmart", "target", "costco", "kroger"]
    retailer_matches = sum(
        1 for r in p.get("retailers", [])
        if any(h in r.lower() for h in high_volume)
    )
    score += min(retailer_matches * 12, 25)

    # Revenue fit (max 20)
    revenue = p.get("company_revenue_estimate", "unknown")
    if any(x in revenue for x in ["$50M", "$100M", "$200M"]):
        score += 20
    elif any(x in revenue for x in ["$20M", "$500M"]):
        score += 10
    elif "unknown" in revenue:
        score += 5

    # Title match (max 15)
    title = p.get("title", "").lower()
    if "deduction" in title:
        score += 15
    elif "trade finance" in title or "vp finance" in title:
        score += 12
    elif "controller" in title or "trade marketing" in title:
        score += 8

    # Buying signals (max 15)
    if p.get("job_signal"):
        score += 10
    if p.get("recent_news"):
        score += 5

    # Personalization bonus
    if p.get("personalization_hook"):
        score += 5

    # Hard disqualifiers
    if p.get("tpm_software_detected"):
        score -= 30

    return max(0, min(100, score))


def tier(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"
