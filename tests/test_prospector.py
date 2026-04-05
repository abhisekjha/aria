import os
os.environ["DRY_RUN"] = "true"

import json
import pytest
from pathlib import Path
from aria.agents.prospector import run
from aria.state import AriaState
import uuid
from datetime import datetime


@pytest.fixture
def base_state() -> AriaState:
    return AriaState(
        run_id=str(uuid.uuid4()),
        run_date=datetime.utcnow().date().isoformat(),
        prospects=[],
        digest_sent=False,
        digest_token="",
        approvals_received=[],
        rejections_received=[],
        outreach_sent_count=0,
        errors=[],
    )


def test_prospector_dry_run(base_state):
    """In dry run mode, prospector returns empty list without crashing."""
    result = run(base_state)
    assert "prospects" in result
    assert isinstance(result["prospects"], list)
    assert len(result["prospects"]) == 0  # DRY_RUN=true → no Apollo calls


def test_prospector_preserves_state(base_state):
    """Prospector should not lose other state fields."""
    result = run(base_state)
    assert result["run_id"] == base_state["run_id"]
    assert result["errors"] == []
