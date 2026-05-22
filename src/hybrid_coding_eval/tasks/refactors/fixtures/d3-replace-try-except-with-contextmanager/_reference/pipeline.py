"""Data pipeline — every try/except block replaced with the new
``suppress_and_log`` context manager. Behaviour identical: transient
failures are logged at warning level; the caller receives ``None``.
"""

from __future__ import annotations

import logging
from typing import Any

from transient import TransientError, suppress_and_log

log = logging.getLogger(__name__)


def _fetch_user(user_id: str) -> dict[str, Any]:
    raise TransientError(f"simulated fetch failure for {user_id}")


def _fetch_order(order_id: str) -> dict[str, Any]:
    return {"id": order_id, "total": 42}


def _publish(event: dict[str, Any]) -> None:
    raise TransientError("simulated publish failure")


def _write_metric(name: str, value: float) -> None:
    return None


def enrich_user(user_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    with suppress_and_log(log, "enrich_user: skipped user %s", user_id):
        result = _fetch_user(user_id)
    return result


def enrich_order(order_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    with suppress_and_log(log, "enrich_order: skipped order %s", order_id):
        result = _fetch_order(order_id)
    return result


def publish_event(event: dict[str, Any]) -> None:
    with suppress_and_log(
        log, "publish_event: failed for event %r", event.get("id")
    ):
        _publish(event)


def record_metric(name: str, value: float) -> None:
    with suppress_and_log(log, "record_metric: dropped %s=%s", name, value):
        _write_metric(name, value)


def run(user_ids: list[str], order_ids: list[str]) -> None:
    for uid in user_ids:
        enrich_user(uid)
    for oid in order_ids:
        enrich_order(oid)
    publish_event({"id": "e1"})
    record_metric("rows_processed", float(len(user_ids) + len(order_ids)))
