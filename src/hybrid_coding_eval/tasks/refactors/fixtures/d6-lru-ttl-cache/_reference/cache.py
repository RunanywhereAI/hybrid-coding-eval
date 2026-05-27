"""Reference implementation of LRUTTLCache."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class LRUTTLCache:
    def __init__(self, capacity: int, default_ttl: float | None = None) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if default_ttl is not None and default_ttl <= 0:
            raise ValueError("default_ttl must be positive or None")
        self.capacity = capacity
        self.default_ttl = default_ttl
        # key -> (value, expiry_monotonic_or_None)
        self._data: OrderedDict[Any, tuple[Any, float | None]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions_lru = 0
        self._evictions_ttl = 0

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _expired(self, expiry: float | None) -> bool:
        return expiry is not None and self._now() >= expiry

    def _purge_expired(self) -> None:
        dead_keys = [k for k, (_, exp) in self._data.items() if self._expired(exp)]
        for k in dead_keys:
            del self._data[k]
            self._evictions_ttl += 1

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        chosen_ttl = self.default_ttl if ttl is None else ttl
        if chosen_ttl is not None and chosen_ttl <= 0:
            raise ValueError("ttl must be positive or None")
        expiry = self._now() + chosen_ttl if chosen_ttl is not None else None
        if key in self._data:
            self._data.move_to_end(key)
            self._data[key] = (value, expiry)
            return
        self._data[key] = (value, expiry)
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)
            self._evictions_lru += 1

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            self._misses += 1
            return default
        value, expiry = self._data[key]
        if self._expired(expiry):
            del self._data[key]
            self._evictions_ttl += 1
            self._misses += 1
            return default
        self._data.move_to_end(key)
        self._hits += 1
        return value

    def delete(self, key: Any) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def __contains__(self, key: Any) -> bool:
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        if self._expired(expiry):
            del self._data[key]
            self._evictions_ttl += 1
            return False
        return True

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._data)

    def cache_info(self) -> dict:
        self._purge_expired()
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions_lru": self._evictions_lru,
            "evictions_ttl": self._evictions_ttl,
            "size": len(self._data),
            "capacity": self.capacity,
        }

    def clear(self) -> None:
        self._data.clear()
        self._hits = 0
        self._misses = 0
        self._evictions_lru = 0
        self._evictions_ttl = 0
