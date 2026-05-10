"""Reference tests for the rate-limit middleware.

Runs against the real HTTP server spawned in a background thread so the
end-to-end pipeline (request -> dispatch -> middleware -> handler) is
actually exercised. Uses only stdlib (``urllib.request``, ``json``,
``threading``).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

import pytest

# Make the fixture importable regardless of where pytest is invoked.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import run  # noqa: E402
from middleware import RateLimiter  # noqa: E402


def _post(url: str, body: dict, ip: str = "10.0.0.1") -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Forwarded-For": ip},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


def _get(url: str, ip: str = "10.0.0.1") -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"X-Forwarded-For": ip}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


@pytest.fixture
def server():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)
    srv, thread = run(host="127.0.0.1", port=0, rate_limiter=limiter)
    host, port = srv.server_address
    base = f"http://{host}:{port}"
    try:
        yield base, limiter
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=1)


def test_first_requests_pass(server):
    base, _ = server
    for i in range(3):
        status, body = _post(f"{base}/echo", {"i": i})
        assert status == 200, f"request #{i} should pass, got {status} {body}"
        assert body == {"echo": {"i": i}}


def test_fourth_request_is_rate_limited(server):
    base, _ = server
    for _ in range(3):
        _post(f"{base}/echo", {})
    status, body = _post(f"{base}/echo", {})
    assert status == 429, f"4th request should be 429, got {status} {body}"


def test_separate_ips_have_independent_budgets(server):
    base, _ = server
    for _ in range(3):
        _post(f"{base}/echo", {}, ip="10.0.0.1")
    status_a, _ = _post(f"{base}/echo", {}, ip="10.0.0.1")
    status_b, _ = _post(f"{base}/echo", {}, ip="10.0.0.2")
    assert status_a == 429
    assert status_b == 200


def test_health_endpoint_is_not_rate_limited(server):
    base, _ = server
    # Burn through the budget first.
    for _ in range(5):
        _post(f"{base}/echo", {})
    # /health must still be reachable.
    for _ in range(10):
        status, body = _get(f"{base}/health")
        assert status == 200
        assert body == {"ok": True}


def test_window_expiry_releases_budget():
    # Small window so the test doesn't sleep forever.
    limiter = RateLimiter(max_requests=2, window_seconds=0.4)
    srv, thread = run(host="127.0.0.1", port=0, rate_limiter=limiter)
    try:
        host, port = srv.server_address
        base = f"http://{host}:{port}"
        assert _post(f"{base}/echo", {})[0] == 200
        assert _post(f"{base}/echo", {})[0] == 200
        assert _post(f"{base}/echo", {})[0] == 429
        time.sleep(0.5)
        # Window has elapsed; calls should succeed again.
        assert _post(f"{base}/echo", {})[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=1)
