"""Worker module — consumes constants from ``constants.py``.

After the refactor, imports should resolve to enum members and the
string comparisons should still work (StrEnum members compare equal to
their string value).
"""

from __future__ import annotations

from constants import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    RETRY_EXPONENTIAL,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_TIMEOUT,
)


def advance(status: str) -> str:
    if status == STATUS_PENDING:
        return STATUS_QUEUED
    if status == STATUS_QUEUED:
        return STATUS_RUNNING
    if status == STATUS_RUNNING:
        return STATUS_SUCCEEDED
    return status


def is_terminal(status: str) -> bool:
    return status in (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_TIMEOUT)


def pick_retry(priority: str) -> str:
    if priority in (PRIORITY_HIGH, PRIORITY_CRITICAL):
        return RETRY_EXPONENTIAL
    if priority == PRIORITY_NORMAL:
        return RETRY_EXPONENTIAL
    return "none"
