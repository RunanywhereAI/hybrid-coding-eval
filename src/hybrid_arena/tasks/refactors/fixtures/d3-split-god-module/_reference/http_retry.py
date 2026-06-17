"""HTTP retry helpers: generic ``retry_call`` and a convenience GET."""

from __future__ import annotations

import time
from typing import Any, Callable

_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF = 0.25


def retry_call(
    fn: Callable[[], Any],
    *,
    retries: int = _DEFAULT_RETRIES,
    backoff: float = _DEFAULT_BACKOFF,
    exc: type[BaseException] = Exception,
) -> Any:
    """Call ``fn()`` with exponential back-off on ``exc``."""
    attempt = 0
    while True:
        try:
            return fn()
        except exc:
            attempt += 1
            if attempt > retries:
                raise
            time.sleep(backoff * (2 ** (attempt - 1)))


def http_get_with_retry(url: str, *, retries: int = _DEFAULT_RETRIES) -> str:
    import urllib.request

    def _do() -> str:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            return resp.read().decode("utf-8")

    return retry_call(_do, retries=retries)
