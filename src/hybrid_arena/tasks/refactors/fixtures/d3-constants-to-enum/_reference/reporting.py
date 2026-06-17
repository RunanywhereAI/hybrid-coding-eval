"""Reporting module — enum-based comparisons."""

from __future__ import annotations

from constants import JobStatus, Severity, Sink


def classify_outcome(status: str) -> Severity:
    if status == JobStatus.FAILED:
        return Severity.ERROR
    if status == JobStatus.CANCELLED:
        return Severity.WARN
    return Severity.INFO


def is_cloud_sink(sink: str) -> bool:
    return sink in (Sink.S3, Sink.GCS)


def is_local_sink(sink: str) -> bool:
    return sink == Sink.LOCAL
