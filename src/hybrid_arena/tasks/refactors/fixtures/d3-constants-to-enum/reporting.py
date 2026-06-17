"""Reporting module — another consumer."""

from __future__ import annotations

from constants import (
    SEVERITY_ERROR,
    SEVERITY_WARN,
    SINK_GCS,
    SINK_LOCAL,
    SINK_S3,
    STATUS_CANCELLED,
    STATUS_FAILED,
)


def classify_outcome(status: str) -> str:
    if status == STATUS_FAILED:
        return SEVERITY_ERROR
    if status == STATUS_CANCELLED:
        return SEVERITY_WARN
    return "info"


def is_cloud_sink(sink: str) -> bool:
    return sink in (SINK_S3, SINK_GCS)


def is_local_sink(sink: str) -> bool:
    return sink == SINK_LOCAL
