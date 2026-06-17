"""Worker module — enum-based comparisons. ``StrEnum`` members compare
equal to their underlying string value, so any persisted ``"pending"``
still matches ``JobStatus.PENDING``.
"""

from __future__ import annotations

from constants import JobStatus, Priority, RetryStrategy


def advance(status: str) -> str:
    if status == JobStatus.PENDING:
        return JobStatus.QUEUED
    if status == JobStatus.QUEUED:
        return JobStatus.RUNNING
    if status == JobStatus.RUNNING:
        return JobStatus.SUCCEEDED
    return status


def is_terminal(status: str) -> bool:
    return status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMEOUT)


def pick_retry(priority: str) -> str:
    if priority in (Priority.HIGH, Priority.CRITICAL):
        return RetryStrategy.EXPONENTIAL
    if priority == Priority.NORMAL:
        return RetryStrategy.EXPONENTIAL
    return RetryStrategy.NONE
