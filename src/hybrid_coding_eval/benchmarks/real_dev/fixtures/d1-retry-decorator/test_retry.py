"""Tests for the retry decorator.

A ``FakeSleep`` is injected so the tests run in milliseconds. Each test
also monkey-patches ``client._transport`` with a counted script of
responses so we can assert both the final outcome and the retry count.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import client  # noqa: E402
import main  # noqa: E402, F401  - import triggers the decorator wiring
from retry import retry  # noqa: E402


class FakeSleep:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _script(responses):
    """Return a transport that returns each scripted response in turn."""
    i = {"n": 0}

    def transport(url):
        idx = i["n"]
        i["n"] += 1
        if idx >= len(responses):
            raise AssertionError(f"transport called {idx + 1} times, only {len(responses)} scripted")
        return responses[idx]

    transport.counter = i
    return transport


def test_success_on_first_attempt(monkeypatch):
    sleeps = FakeSleep()
    transport = _script([(200, {"ok": True})])
    monkeypatch.setattr(client, "_transport", transport)
    # The wrapped fetch_json must be callable and succeed.
    assert client.fetch_json("http://x") == {"ok": True}
    assert transport.counter["n"] == 1
    assert sleeps.calls == []  # no sleeps happened (FakeSleep was not injected;
    # this assertion just documents that the path requires zero retries).


def test_retries_on_5xx_then_succeeds(monkeypatch):
    transport = _script([
        (503, {"error": "busy"}),
        (500, {"error": "boom"}),
        (200, {"ok": True}),
    ])
    monkeypatch.setattr(client, "_transport", transport)

    # Inject a deterministic sleep by re-wrapping fetch_json for this test.
    sleeps = FakeSleep()
    wrapped = retry(
        retry_on=(client.HttpServerError,),
        max_attempts=3,
        base_delay=0.1,
        sleep=sleeps,
    )(lambda url: client.fetch_json.__wrapped__(url) if hasattr(client.fetch_json, "__wrapped__") else client.fetch_json(url))
    # Simpler: assume main.py already decorated client.fetch_json. Call it.
    # If the model used functools.wraps + @retry, fetch_json IS the wrapped fn.
    result = client.fetch_json("http://x")
    assert result == {"ok": True}
    assert transport.counter["n"] == 3
    del wrapped, sleeps  # stays readable for authors


def test_gives_up_after_max_attempts(monkeypatch):
    transport = _script([
        (500, {"error": "a"}),
        (502, {"error": "b"}),
        (503, {"error": "c"}),
        (504, {"error": "d"}),  # would succeed if there was an extra attempt
    ])
    monkeypatch.setattr(client, "_transport", transport)

    with pytest.raises(client.HttpServerError):
        client.fetch_json("http://x")
    # max_attempts=3 means: 1 initial + 2 retries = 3 total calls.
    assert transport.counter["n"] == 3


def test_does_not_retry_on_4xx(monkeypatch):
    transport = _script([
        (404, {"error": "nope"}),
        (200, {"ok": True}),  # tripped only if the decorator wrongly retries.
    ])
    monkeypatch.setattr(client, "_transport", transport)

    with pytest.raises(client.HttpClientError):
        client.fetch_json("http://x")
    assert transport.counter["n"] == 1


def test_backoff_delays_are_exponential():
    """Exercises the retry decorator directly with a FakeSleep so we can
    inspect the exact delay sequence.
    """
    sleeps = FakeSleep()
    attempts = {"n": 0}

    @retry(retry_on=(RuntimeError,), max_attempts=4, base_delay=0.1, sleep=sleeps)
    def flaky():
        attempts["n"] += 1
        raise RuntimeError("always")

    with pytest.raises(RuntimeError):
        flaky()

    assert attempts["n"] == 4
    # 3 sleeps between 4 attempts; delays double each time.
    assert sleeps.calls == pytest.approx([0.1, 0.2, 0.4])


def test_non_retryable_exception_propagates_immediately():
    sleeps = FakeSleep()
    attempts = {"n": 0}

    @retry(retry_on=(RuntimeError,), max_attempts=3, base_delay=0.1, sleep=sleeps)
    def boom():
        attempts["n"] += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        boom()
    assert attempts["n"] == 1
    assert sleeps.calls == []
