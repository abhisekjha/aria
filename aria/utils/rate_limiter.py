import time
import threading
from collections import defaultdict
from aria.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter. Thread-safe.
    Usage:
        limiter = RateLimiter(max_calls=10, period=60)  # 10 calls per minute
        limiter.wait()  # blocks until a token is available
    """

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period  # seconds
        self._lock = threading.Lock()
        self._calls = []

    def wait(self) -> None:
        """Block until we're within the rate limit, then consume a token."""
        with self._lock:
            now = time.time()
            # Remove calls outside the window
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) >= self.max_calls:
                # Sleep until oldest call falls outside window
                sleep_time = self.period - (now - self._calls[0]) + 0.01
                logger.info(f"[RATE_LIMITER] Sleeping {sleep_time:.1f}s (limit: {self.max_calls}/{self.period}s)")
                time.sleep(sleep_time)
                self._calls = [t for t in self._calls if time.time() - t < self.period]

            self._calls.append(time.time())


# Pre-configured limiters for each external API
apollo_limiter = RateLimiter(max_calls=10, period=60)       # 10 req/min
airtable_limiter = RateLimiter(max_calls=5, period=1)       # 5 req/sec
gmail_send_limiter = RateLimiter(max_calls=20, period=60)   # 20 emails/min
web_search_limiter = RateLimiter(max_calls=5, period=10)    # 5 searches/10s
anthropic_limiter = RateLimiter(max_calls=50, period=60)    # 50 req/min
