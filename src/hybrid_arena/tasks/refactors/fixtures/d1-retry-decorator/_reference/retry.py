"""Reference retry decorator with exponential backoff."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable


def retry(
    *,
    retry_on: tuple[type[BaseException], ...],
    max_attempts: int,
    base_delay: float,
    sleep: Callable[[float], None] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    _sleep = sleep if sleep is not None else time.sleep

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            delay = base_delay
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except retry_on as exc:  # retryable
                    last_exc = exc
                    if attempt == max_attempts - 1:
                        break
                    _sleep(delay)
                    delay *= 2
            assert last_exc is not None  # loop entered at least once
            raise last_exc

        return wrapper

    return decorator
