"""Status / priority / sink / retry / severity string enums.

Every bag-of-literals in the old ``constants.py`` is now a ``StrEnum``
class. Values match the old literals byte-for-byte so persisted records
and serialized payloads keep round-tripping unchanged.
"""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Sink(StrEnum):
    S3 = "s3"
    GCS = "gcs"
    LOCAL = "local"
    HTTP = "http"


class RetryStrategy(StrEnum):
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
