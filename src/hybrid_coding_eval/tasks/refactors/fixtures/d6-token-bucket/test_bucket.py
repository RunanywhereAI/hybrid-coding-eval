"""Acceptance tests for the multi-key token-bucket rate limiter."""

from __future__ import annotations

import time

import pytest

from bucket import TokenBucket


# ── construction ────────────────────────────────────────────────────


def test_construct_rejects_nonpositive_capacity():
    with pytest.raises((ValueError, AssertionError)):
        TokenBucket(capacity=0, refill_rate=1.0)
    with pytest.raises((ValueError, AssertionError)):
        TokenBucket(capacity=-1, refill_rate=1.0)


def test_construct_rejects_nonpositive_refill_rate():
    with pytest.raises((ValueError, AssertionError)):
        TokenBucket(capacity=5, refill_rate=0)
    with pytest.raises((ValueError, AssertionError)):
        TokenBucket(capacity=5, refill_rate=-1.0)


# ── starts full ─────────────────────────────────────────────────────


def test_new_key_starts_at_full_capacity(monkeypatch):
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    b = TokenBucket(capacity=5, refill_rate=1.0)
    assert b.available("k") == pytest.approx(5.0)


# ── burst then deny ─────────────────────────────────────────────────


def test_burst_exhaust_then_deny(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=3, refill_rate=1.0)
    for _ in range(3):
        assert b.allow("k") is True
    assert b.allow("k") is False


def test_request_larger_than_capacity_denied():
    b = TokenBucket(capacity=3, refill_rate=1.0)
    assert b.allow("k", tokens=5) is False


def test_request_nonpositive_tokens_rejected():
    b = TokenBucket(capacity=3, refill_rate=1.0)
    with pytest.raises((ValueError, AssertionError)):
        b.allow("k", tokens=0)
    with pytest.raises((ValueError, AssertionError)):
        b.allow("k", tokens=-1)


# ── refill over time ────────────────────────────────────────────────


def test_refill_at_rate(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=5, refill_rate=2.0)  # 2 tokens / sec
    for _ in range(5):
        b.allow("k")
    assert b.available("k") == pytest.approx(0.0, abs=1e-6)
    now[0] += 1.0  # +2 tokens
    assert b.available("k") == pytest.approx(2.0, abs=1e-6)
    now[0] += 2.0  # +4 → caps at 5
    assert b.available("k") == pytest.approx(5.0, abs=1e-6)


def test_refill_does_not_exceed_capacity(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=3, refill_rate=10.0)
    now[0] += 1_000_000
    assert b.available("k") == pytest.approx(3.0, abs=1e-6)


def test_partial_refill_allows_partial_burst(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=4, refill_rate=2.0)
    for _ in range(4):
        b.allow("k")
    now[0] += 1.5  # +3 tokens, capped at 4 → 3 available
    assert b.allow("k", tokens=3) is True
    assert b.allow("k") is False


# ── multi-key isolation ─────────────────────────────────────────────


def test_keys_are_independent(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=2, refill_rate=1.0)
    assert b.allow("alice") is True
    assert b.allow("alice") is True
    assert b.allow("alice") is False
    assert b.allow("bob") is True  # bob unaffected
    assert b.allow("bob") is True
    assert b.allow("bob") is False


def test_reset_one_key(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=3, refill_rate=1.0)
    for _ in range(3):
        b.allow("k")
    assert b.allow("k") is False
    b.reset("k")
    assert b.allow("k") is True
    assert b.allow("k") is True


def test_reset_all_keys(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=2, refill_rate=1.0)
    b.allow("a")
    b.allow("a")
    b.allow("b")
    b.allow("b")
    b.reset()
    assert b.allow("a") is True
    assert b.allow("b") is True


# ── floating-point refill is correct under repeated lazy refills ────


def test_repeated_available_is_idempotent(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=10, refill_rate=1.0)
    for _ in range(10):
        b.allow("k")
    now[0] += 5
    a1 = b.available("k")
    a2 = b.available("k")
    a3 = b.available("k")
    assert a1 == pytest.approx(a2)
    assert a2 == pytest.approx(a3)
    assert a1 == pytest.approx(5.0, abs=1e-6)


def test_allow_consumes_only_when_granted(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    b = TokenBucket(capacity=2, refill_rate=1.0)
    assert b.allow("k") is True
    assert b.allow("k") is True
    bal_before = b.available("k")
    assert b.allow("k", tokens=5) is False  # denied (too many)
    bal_after = b.available("k")
    assert bal_after == pytest.approx(bal_before, abs=1e-6)
    assert b.allow("k") is False  # still empty
    assert bal_after == pytest.approx(b.available("k"), abs=1e-6)
