"""Reference token-bucket rate limiter."""

from __future__ import annotations

import threading
import time


class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")
        self.capacity = capacity
        self.refill_rate = refill_rate
        # key -> (tokens, last_refill_time)
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _refill_one(self, key: str) -> tuple[float, float]:
        now = self._now()
        tokens, last = self._state.get(key, (float(self.capacity), now))
        elapsed = max(0.0, now - last)
        tokens = min(self.capacity, tokens + elapsed * self.refill_rate)
        self._state[key] = (tokens, now)
        return tokens, now

    def allow(self, key: str, tokens: int = 1) -> bool:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        if tokens > self.capacity:
            return False
        with self._lock:
            current, now = self._refill_one(key)
            if current >= tokens:
                self._state[key] = (current - tokens, now)
                return True
            return False

    def available(self, key: str) -> float:
        with self._lock:
            current, _ = self._refill_one(key)
            return current

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._state.clear()
            else:
                self._state.pop(key, None)
