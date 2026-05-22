"""Retry decorator — TO BE IMPLEMENTED.

Implement a decorator ``retry`` with the signature documented below.
See the prompt and ``test_retry.py`` for acceptance criteria.
"""

from __future__ import annotations

from typing import Any, Callable


def retry(
    *,
    retry_on: tuple[type[BaseException], ...],
    max_attempts: int,
    base_delay: float,
    sleep: Callable[[float], None] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return a decorator that retries the wrapped callable.

    Parameters
    ----------
    retry_on
        Exception classes that trigger a retry. Anything else propagates.
    max_attempts
        Total attempts including the first. ``3`` means: initial call +
        up to 2 retries.
    base_delay
        First-retry delay in seconds. Subsequent retries double it
        (exponential backoff): ``base_delay``, ``base_delay * 2``,
        ``base_delay * 4``, ...
    sleep
        Sleep function; defaults to ``time.sleep``. Tests inject a
        counting fake so they can run fast.

    Returns
    -------
    A decorator. The wrapped function re-raises the last exception if
    every attempt fails.
    """
    raise NotImplementedError
