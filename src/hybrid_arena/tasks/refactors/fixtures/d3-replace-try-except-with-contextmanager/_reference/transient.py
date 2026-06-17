"""Context manager that swallows a specific exception and logs it.

Replaces the repeated ``try: ... except TransientError as exc: log.warning(...)``
pattern that used to live at every call-site.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator


class TransientError(RuntimeError):
    """Raised for temporary failures that should be logged but not crash."""


@contextmanager
def suppress_and_log(
    logger: logging.Logger, message: str, *args: object
) -> Iterator[None]:
    """Suppress :class:`TransientError` raised inside the block and log a
    warning with ``message % args``. The triggering exception is appended
    to the log record as a final ``(%s)`` placeholder.
    """
    try:
        yield
    except TransientError as exc:
        # Append the exception to the user-provided message format so
        # callers can carry their own structured context.
        logger.warning(message + " (%s)", *args, exc)
