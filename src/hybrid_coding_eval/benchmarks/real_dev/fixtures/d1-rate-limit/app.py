"""Tiny stdlib HTTP app exposing /health and /echo.

The server is built on ``http.server.BaseHTTPRequestHandler`` so the
fixture stays dependency-free. ``make_app(rate_limit=...)`` returns a
handler class with the rate-limit middleware applied (once you've
implemented it in ``middleware.py``).

Call sites
----------
* The request pipeline is a single function ``dispatch(handler)`` that
  (optionally) runs the rate-limit check, then routes to the endpoint.
* ``/health`` must NEVER be rate-limited.
* ``/echo`` (POST) echoes the body and IS rate-limited.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from middleware import RateLimiter


def make_app(rate_limiter: RateLimiter | None = None):
    """Return a handler class wired up with the given rate limiter.

    The handler exposes two endpoints:

    - ``GET /health``  — never rate-limited; returns ``{"ok": true}``.
    - ``POST /echo``   — rate-limited; echoes the request body.
    """

    class Handler(BaseHTTPRequestHandler):
        # Silence the per-request stderr log line — noisy under pytest.
        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            return

        def _client_ip(self) -> str:
            # client_address is (host, port). Tests set the Host via
            # an ``X-Forwarded-For`` header so one TCP client can
            # masquerade as many IPs.
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                return xff.split(",")[0].strip()
            return self.client_address[0]

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - stdlib signature
            if self.path == "/health":
                # Health endpoint is explicitly exempt from rate-limiting.
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802 - stdlib signature
            if self.path == "/echo":
                # Rate-limit check goes here. The middleware should
                # return True when the caller is over the limit.
                if rate_limiter is not None and rate_limiter.is_limited(self._client_ip()):
                    self._send_json(429, {"error": "rate limited"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "invalid json"})
                    return
                self._send_json(200, {"echo": body})
                return
            self._send_json(404, {"error": "not found"})

    return Handler


def run(host: str = "127.0.0.1", port: int = 0, rate_limiter: RateLimiter | None = None):
    """Start the server in a background thread. Returns ``(server, thread)``."""
    handler = make_app(rate_limiter=rate_limiter)
    server = HTTPServer((host, port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
