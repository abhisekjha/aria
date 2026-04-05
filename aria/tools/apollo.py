import httpx
import uuid
from typing import List, Optional
from aria.config import Config
from aria.state import Prospect, make_empty_prospect
from aria.utils.logger import get_logger
from aria.utils.rate_limiter import apollo_limiter

logger = get_logger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"

# ICP search parameters
APOLLO_TITLES = [
    "Deductions Manager",
    "Director of Deductions",
    "VP Finance",
    "Director of Trade Finance",
    "Controller",
    "Trade Finance Manager",
    "VP Trade Marketing",
]

APOLLO_INDUSTRY_IDS = [
    "5567cd4773696439b10b0000",  # Food & Beverages
    "5567cd4773696439b10b0001",  # Consumer Goods
    "5567cd4773696439b10b0002",  # Health & Beauty
]


def search_prospects(page: int = 1, per_page: int = 10) -> List[Prospect]:
    """
    Search Apollo.io for CPG prospects matching ICP.
    Returns list of raw Prospect objects (not yet enriched or scored).
    Never raises — returns empty list on any error.
    """
    if Config.DRY_RUN:
        logger.info("[APOLLO] DRY_RUN=true — skipping real Apollo call")
        return []

    apollo_limiter.wait()

    try:
        headers = {"X-Api-Key": Config.APOLLO_API_KEY, "Content-Type": "application/json"}
        payload = {
            "person_titles": APOLLO_TITLES,
            "organization_industry_tag_ids": APOLLO_INDUSTRY_IDS,
            "organization_num_employees_ranges": ["100,2000"],
            "per_page": per_page,
            "page": page,
        }

        resp = httpx.post(
            f"{APOLLO_BASE}/mixed_people/search",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        prospects = []
        for person in data.get("people", []):
            p = _map_apollo_person(person)
            if p:
                prospects.append(p)

        logger.info(f"[APOLLO] Found {len(prospects)} prospects on page {page}")
        return prospects

    except Exception as e:
        logger.error(f"[APOLLO] search failed: {e}")
        return []


def reveal_email(person_id: str) -> Optional[str]:
    """
    Reveal email for a specific Apollo person (costs 1 credit).
    Only call if email not already in search results.
    """
    if Config.DRY_RUN:
        return None

    apollo_limiter.wait()

    try:
        headers = {"X-Api-Key": Config.APOLLO_API_KEY, "Content-Type": "application/json"}
        resp = httpx.post(
            f"{APOLLO_BASE}/people/match",
            headers=headers,
            json={"id": person_id, "reveal_personal_emails": False},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("person", {}).get("email")
    except Exception as e:
        logger.error(f"[APOLLO] reveal_email failed for {person_id}: {e}")
        return None


def _map_apollo_person(person: dict) -> Optional[Prospect]:
    """Map raw Apollo person object to Prospect TypedDict."""
    try:
        email = person.get("email", "")
        # Skip if no email — not useful without contact info
        if not email:
            return None

        org = person.get("organization", {}) or {}
        p = make_empty_prospect()
        p["id"] = str(uuid.uuid4())
        p["first_name"] = person.get("first_name", "")
        p["last_name"] = person.get("last_name", "")
        p["title"] = person.get("title", "")
        p["email"] = email
        p["linkedin_url"] = person.get("linkedin_url", "")
        p["company"] = org.get("name", "")
        p["company_domain"] = (org.get("website_url", "") or "").replace("https://", "").replace("http://", "").rstrip("/")
        p["company_headcount"] = str(org.get("estimated_num_employees", "unknown"))

        # Revenue estimate from Apollo
        rev = org.get("estimated_annual_revenue") or org.get("annual_revenue_printed", "")
        p["company_revenue_estimate"] = str(rev) if rev else "unknown"

        return p
    except Exception as e:
        logger.error(f"[APOLLO] _map_apollo_person failed: {e}")
        return None
