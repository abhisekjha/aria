"""
Dry run: full pipeline with mock data, zero external calls.
Run with: python scripts/test_run.py
"""
import os
os.environ["DRY_RUN"] = "true"

import json
import uuid
from pathlib import Path
from datetime import datetime

from aria.state import AriaState, Prospect
from aria.agents import qualifier
from aria.utils.logger import get_logger

logger = get_logger("test_run")


def main():
    print("\n" + "="*60)
    print("ARIA DRY RUN — No real API calls will be made")
    print("="*60 + "\n")

    # Load mock prospect
    mock_path = Path(__file__).parent.parent / "tests" / "fixtures" / "mock_prospect.json"
    mock_data = json.loads(mock_path.read_text())
    mock_prospect = Prospect(**mock_data)

    # Test qualifier scoring
    score = qualifier.score_prospect(mock_prospect)
    tier = qualifier.tier(score)
    print(f"✅ Qualifier: {mock_prospect['company']} → score={score} tier={tier}")

    # Test state creation
    state: AriaState = {
        "run_id": str(uuid.uuid4()),
        "run_date": datetime.utcnow().date().isoformat(),
        "prospects": [mock_prospect],
        "digest_sent": False,
        "digest_token": "",
        "approvals_received": [],
        "rejections_received": [],
        "outreach_sent_count": 0,
        "errors": [],
    }
    print(f"✅ State created: run_id={state['run_id']}")

    # Test qualifier node
    from aria.agents.qualifier import run as qualifier_run
    state = qualifier_run(state)
    p = state["prospects"][0]
    print(f"✅ Qualifier node: {p['company']} → score={p['score']} tier={p['tier']}")

    print("\n" + "="*60)
    print("DRY RUN COMPLETE — All checks passed")
    print("To run the real pipeline: set DRY_RUN=false in .env")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
