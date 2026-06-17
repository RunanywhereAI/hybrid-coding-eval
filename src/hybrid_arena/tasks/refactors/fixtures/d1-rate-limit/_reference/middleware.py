"""Reference implementation of the sliding-window rate limiter.

Keyed by client IP. Each IP has a deque of hit-timestamps; on every
call we drop timestamps older than the window and compare the
remaining count to ``max_requests``.

Thread-safe via a single ``threading.Lock``; the stdlib HTTPServer
handles each request on its own thread once we wrap it, and tests in
the suite do fire concurrent-ish requests from the same IP.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_limited(self, ip: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._hits[ip]
            # Drop expired hits from the front.
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                return True
            q.append(now)
            return False
