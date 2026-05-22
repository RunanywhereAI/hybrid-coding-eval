"""Rate-limit middleware — TO BE IMPLEMENTED.

Implement a sliding-window ``RateLimiter`` class with the interface
below. See the prompt and ``test_rate_limit.py`` for acceptance.
"""

from __future__ import annotations


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP.

    The caller constructs one instance shared across all requests and
    asks ``is_limited(ip)`` on every request. Returning ``True`` means
    the request should be rejected with HTTP 429.

    No external dependencies. In-memory state only.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # TODO: initialise the per-IP bookkeeping structure.

    def is_limited(self, ip: str) -> bool:
        """Return True if ``ip`` has exceeded ``max_requests`` in the
        last ``window_seconds``. Must also record this call as a hit
        so subsequent calls in the window count it.
        """
        # TODO: implement the sliding-window check.
        raise NotImplementedError
