from typing import List
from aria.state import AriaState, Prospect
from aria.tools.apollo import search_prospects
from aria.tools.airtable import get_all_prospect_emails
from aria.config import Config
from aria.utils.logger import get_logger, log_agent_start, log_agent_end

logger = get_logger(__name__)


def run(state: AriaState) -> AriaState:
    """
    Prospector node: finds new CPG prospects via Apollo.io.
    Deduplicates against existing Airtable records.
    Updates state with new prospects.
    """
    log_agent_start(logger, "prospector")

    try:
        # Get existing emails to deduplicate
        existing_emails = set(get_all_prospect_emails())
        logger.info(f"[PROSPECTOR] {len(existing_emails)} existing prospects in CRM")

        # Fetch from Apollo
        raw_prospects = search_prospects(page=1, per_page=Config.MAX_PROSPECTS_PER_DAY)

        # Deduplicate
        new_prospects: List[Prospect] = []
        for p in raw_prospects:
            if p["email"] and p["email"].lower() not in existing_emails:
                new_prospects.append(p)
                existing_emails.add(p["email"].lower())
            else:
                logger.info(f"[PROSPECTOR] Skipping duplicate: {p['email']}")

        logger.info(f"[PROSPECTOR] {len(new_prospects)} new unique prospects found")
        log_agent_end(logger, "prospector", len(new_prospects))

        return {**state, "prospects": new_prospects}

    except Exception as e:
        logger.error(f"[PROSPECTOR] Unexpected error: {e}")
        state["errors"].append(f"prospector: {e}")
        return {**state, "prospects": []}
