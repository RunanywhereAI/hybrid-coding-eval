"""Stdlib HTTP app with a single ``POST /users`` endpoint.

Today the handler accepts any JSON body. You need to add schema
validation per the prompt: reject bodies that don't include
``name: str`` and ``age: int >= 0`` with HTTP 422, returning a
structured error that tells the client which field failed.

The validator itself lives in ``validate.py`` (currently a stub).
``/users`` should call ``validate_user(body)`` — if it returns a
non-empty list of error dicts, respond 422; otherwise respond 200
with ``{"created": body}``.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from validate import validate_user


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - stdlib signature
        if self.path != "/users":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid json"})
            return

        errors = validate_user(body)
        if errors:
            self._send_json(422, {"errors": errors})
            return
        self._send_json(200, {"created": body})


def run(host: str = "127.0.0.1", port: int = 0):
    server = HTTPServer((host, port), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
