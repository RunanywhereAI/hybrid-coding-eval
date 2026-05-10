"""Tiny HTTP client used across the app.

``_transport`` is indirected so tests can swap in a counting mock. You
MUST keep calling ``_transport(url)`` from ``fetch_json`` — the tests
rely on it being the one and only network boundary.

Errors:

- 4xx responses raise ``HttpClientError`` (do NOT retry).
- 5xx responses raise ``HttpServerError`` (DO retry).
- Transport-level exceptions propagate (treat as retry-worthy too).

Your job: add the ``retry`` decorator (defined in ``retry.py``) to
``fetch_json`` with the policy described in the prompt.
"""

from __future__ import annotations

from typing import Any


class HttpClientError(Exception):
    """Raised for 4xx responses. Do not retry."""

    def __init__(self, status: int, message: str = ""):
        super().__init__(f"{status}: {message}")
        self.status = status


class HttpServerError(Exception):
    """Raised for 5xx responses. Callers SHOULD retry."""

    def __init__(self, status: int, message: str = ""):
        super().__init__(f"{status}: {message}")
        self.status = status


def _transport(url: str) -> tuple[int, dict[str, Any]]:
    """The one and only network entry point. Tests monkey-patch this.

    Real production would use ``httpx.get(url).raise_for_status()`` or
    equivalent. Here the default implementation is deliberately broken
    so nobody accidentally calls a real URL during tests.
    """
    raise RuntimeError(
        "_transport was not patched. Tests must inject a fake transport."
    )


def fetch_json(url: str) -> dict[str, Any]:
    """Return the JSON body at ``url`` as a dict.

    Classifies the transport result:

    - 2xx -> return the body.
    - 4xx -> raise ``HttpClientError`` (no retry).
    - 5xx -> raise ``HttpServerError`` (retry per decorator policy).
    """
    status, body = _transport(url)
    if 200 <= status < 300:
        return body
    if 400 <= status < 500:
        raise HttpClientError(status, body.get("error", "") if isinstance(body, dict) else "")
    if 500 <= status < 600:
        raise HttpServerError(status, body.get("error", "") if isinstance(body, dict) else "")
    raise RuntimeError(f"unexpected status {status}")
