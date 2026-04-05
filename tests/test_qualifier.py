import os
os.environ["DRY_RUN"] = "true"

import json
import pytest
from pathlib import Path
from aria.agents.qualifier import score_prospect, tier, run
from aria.state import AriaState, Prospect
import uuid
from datetime import datetime


@pytest.fixture
def mock_prospect() -> Prospect:
    path = Path(__file__).parent / "fixtures" / "mock_prospect.json"
    return Prospect(**json.loads(path.read_text()))


@pytest.fixture
def base_state(mock_prospect) -> AriaState:
    return AriaState(
        run_id=str(uuid.uuid4()),
        run_date=datetime.utcnow().date().isoformat(),
        prospects=[mock_prospect],
        digest_sent=False,
        digest_token="",
        approvals_received=[],
        rejections_received=[],
        outreach_sent_count=0,
        errors=[],
    )


def test_score_hot_prospect(mock_prospect):
    """Mock prospect (Walmart+Target+Kroger, deductions title, job signal) should score high."""
    score = score_prospect(mock_prospect)
    assert score >= 70, f"Expected hot score >= 70, got {score}"


def test_tier_hot():
    assert tier(75) == "hot"
    assert tier(70) == "hot"


def test_tier_warm():
    assert tier(60) == "warm"
    assert tier(40) == "warm"


def test_tier_cold():
    assert tier(39) == "cold"
    assert tier(0) == "cold"


def test_disqualifier_reduces_score():
    p = {
        "retailers": ["Walmart"],
        "company_revenue_estimate": "$100M-$200M",
        "title": "Deductions Manager",
        "job_signal": True,
        "recent_news": "Some news",
        "personalization_hook": "Some hook",
        "tpm_software_detected": True,  # disqualifier
    }
    score = score_prospect(p)
    assert score < 70, f"TPM software detected should lower score below hot, got {score}"


def test_qualifier_node_scores_and_sorts(base_state):
    """Qualifier node should set score, tier, and sort by score."""
    result = run(base_state)
    assert len(result["prospects"]) == 1
    p = result["prospects"][0]
    assert p["score"] > 0
    assert p["tier"] in ("hot", "warm", "cold")
