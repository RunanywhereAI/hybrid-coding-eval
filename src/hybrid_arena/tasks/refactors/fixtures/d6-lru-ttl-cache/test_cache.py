"""Acceptance tests for the LRUTTLCache implementation in cache.py.

The model writes cache.py; this test file is held constant.
"""

from __future__ import annotations

import time

import pytest

from cache import LRUTTLCache


# ── construction ────────────────────────────────────────────────────


def test_construct_basic():
    c = LRUTTLCache(capacity=3)
    assert c.capacity == 3
    assert len(c) == 0
    info = c.cache_info()
    assert info["hits"] == 0
    assert info["misses"] == 0
    assert info["size"] == 0


def test_construct_rejects_nonpositive_capacity():
    with pytest.raises((ValueError, AssertionError)):
        LRUTTLCache(capacity=0)
    with pytest.raises((ValueError, AssertionError)):
        LRUTTLCache(capacity=-1)


def test_construct_rejects_nonpositive_default_ttl():
    with pytest.raises((ValueError, AssertionError)):
        LRUTTLCache(capacity=3, default_ttl=0)
    with pytest.raises((ValueError, AssertionError)):
        LRUTTLCache(capacity=3, default_ttl=-1.0)


# ── basic get / set / delete ────────────────────────────────────────


def test_set_then_get():
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    assert c.get("a") == 1


def test_get_missing_returns_default():
    c = LRUTTLCache(capacity=3)
    assert c.get("missing") is None
    assert c.get("missing", default="x") == "x"


def test_delete_existing_returns_true():
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    assert c.delete("a") is True
    assert "a" not in c


def test_delete_missing_returns_false():
    c = LRUTTLCache(capacity=3)
    assert c.delete("missing") is False


def test_set_overwrites_value():
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    c.set("a", 2)
    assert c.get("a") == 2
    assert len(c) == 1


def test_contains():
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    assert "a" in c
    assert "b" not in c


def test_clear():
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    c.set("b", 2)
    c.clear()
    assert len(c) == 0
    info = c.cache_info()
    assert info["hits"] == 0
    assert info["misses"] == 0
    assert info["size"] == 0


# ── LRU eviction ────────────────────────────────────────────────────


def test_lru_eviction_when_over_capacity():
    c = LRUTTLCache(capacity=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert "a" not in c
    assert c.get("b") == 2
    assert c.get("c") == 3
    info = c.cache_info()
    assert info["evictions_lru"] == 1


def test_get_refreshes_lru_order():
    c = LRUTTLCache(capacity=2)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1  # bumps a to the front
    c.set("c", 3)
    assert "a" in c
    assert "b" not in c  # b was the actual LRU


def test_set_overwrite_refreshes_lru_order():
    c = LRUTTLCache(capacity=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("a", 11)  # refresh a
    c.set("c", 3)
    assert c.get("a") == 11
    assert "b" not in c


def test_overwrite_does_not_count_lru_eviction():
    c = LRUTTLCache(capacity=2)
    c.set("a", 1)
    c.set("a", 2)
    assert c.cache_info()["evictions_lru"] == 0


# ── TTL eviction ────────────────────────────────────────────────────


def test_ttl_eviction_on_get(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=3)
    c.set("a", 1, ttl=10)
    now[0] += 5
    assert c.get("a") == 1  # still alive
    now[0] += 6
    assert c.get("a") is None  # expired
    assert c.cache_info()["evictions_ttl"] == 1


def test_default_ttl_applied_when_set_omits_ttl(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=3, default_ttl=5.0)
    c.set("a", 1)
    now[0] += 4
    assert c.get("a") == 1
    now[0] += 2
    assert c.get("a") is None


def test_explicit_ttl_overrides_default(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=3, default_ttl=5.0)
    c.set("a", 1, ttl=20)
    now[0] += 10
    assert c.get("a") == 1


def test_no_default_ttl_means_never_expires(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    now[0] += 1_000_000
    assert c.get("a") == 1


def test_contains_evicts_expired(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=3)
    c.set("a", 1, ttl=5)
    now[0] += 10
    assert "a" not in c


def test_len_evicts_expired(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=3)
    c.set("a", 1, ttl=5)
    c.set("b", 2, ttl=100)
    now[0] += 10
    assert len(c) == 1


# ── cache_info ──────────────────────────────────────────────────────


def test_cache_info_hits_and_misses():
    c = LRUTTLCache(capacity=3)
    c.set("a", 1)
    c.get("a")  # hit
    c.get("a")  # hit
    c.get("missing")  # miss
    info = c.cache_info()
    assert info["hits"] == 2
    assert info["misses"] == 1
    assert info["size"] == 1
    assert info["capacity"] == 3


def test_cache_info_distinguishes_lru_and_ttl_evictions(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=2)
    c.set("a", 1, ttl=100)
    c.set("b", 2, ttl=100)
    c.set("c", 3, ttl=100)  # evicts "a" via LRU
    info = c.cache_info()
    assert info["evictions_lru"] == 1
    assert info["evictions_ttl"] == 0
    c.set("d", 4, ttl=2)  # capacity=2 → evicts "b" via LRU (b is LRU)
    info = c.cache_info()
    assert info["evictions_lru"] == 2
    now[0] += 5
    _ = c.get("d")  # ttl-evict d
    info = c.cache_info()
    assert info["evictions_lru"] == 2
    assert info["evictions_ttl"] >= 1


def test_expired_entry_does_not_block_capacity(monkeypatch):
    """Expired entries should not count towards capacity for new sets."""
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    c = LRUTTLCache(capacity=2)
    c.set("a", 1, ttl=5)
    c.set("b", 2, ttl=5)
    now[0] += 10  # both expired
    assert len(c) == 0
    c.set("c", 3)
    c.set("d", 4)
    assert "c" in c
    assert "d" in c
    assert len(c) == 2
