import hmac
import hashlib
import time
from aria.config import Config

TOKEN_TTL_SECONDS = 8 * 60 * 60  # 8 hours


def generate_token(prospect_id: str) -> str:
    """Generate a signed, time-limited HMAC token for prospect approval."""
    timestamp = int(time.time())
    message = f"{prospect_id}:{timestamp}"
    signature = hmac.new(
        Config.APPROVAL_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{timestamp}:{signature}"


def validate_token(token: str, prospect_id: str) -> bool:
    """
    Validate an approval token.
    Returns True if valid, not expired, and correctly signed.
    """
    try:
        parts = token.split(":")
        if len(parts) != 2:
            return False

        timestamp_str, signature = parts
        timestamp = int(timestamp_str)

        # Check expiry
        if time.time() - timestamp > TOKEN_TTL_SECONDS:
            return False

        # Verify signature
        message = f"{prospect_id}:{timestamp_str}"
        expected = hmac.new(
            Config.APPROVAL_SECRET.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    except Exception:
        return False
