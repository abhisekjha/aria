import os
os.environ["DRY_RUN"] = "true"
os.environ["APPROVAL_SECRET"] = "test-secret-key-for-unit-tests-only"

import pytest
import time
from aria.approval.tokens import generate_token, validate_token


def test_valid_token():
    token = generate_token("prospect-123")
    assert validate_token(token, "prospect-123") is True


def test_wrong_prospect_id():
    token = generate_token("prospect-123")
    assert validate_token(token, "prospect-999") is False


def test_tampered_token():
    token = generate_token("prospect-123")
    tampered = token[:-4] + "xxxx"
    assert validate_token(tampered, "prospect-123") is False


def test_malformed_token():
    assert validate_token("not-a-real-token", "prospect-123") is False
    assert validate_token("", "prospect-123") is False
