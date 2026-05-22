"""Data pipeline — four call-sites each repeat the same try/except dance:
catch ``TransientError`` and log a warning, letting everything else
propagate. Refactor target: replace the repeated blocks with a single
``@contextmanager`` named ``suppress_and_log`` (or similar) so the four
call-sites each become a ``with suppress_and_log(log, "...")`` block.

Behaviour must be preserved exactly.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class TransientError(RuntimeError):
    """Raised for temporary failures that should be logged but not crash."""


def _fetch_user(user_id: str) -> dict[str, Any]:
    raise TransientError(f"simulated fetch failure for {user_id}")


def _fetch_order(order_id: str) -> dict[str, Any]:
    return {"id": order_id, "total": 42}


def _publish(event: dict[str, Any]) -> None:
    raise TransientError("simulated publish failure")


def _write_metric(name: str, value: float) -> None:
    return None


def enrich_user(user_id: str) -> dict[str, Any] | None:
    try:
        return _fetch_user(user_id)
    except TransientError as exc:
        log.warning("enrich_user: skipped user %s (%s)", user_id, exc)
        return None


def enrich_order(order_id: str) -> dict[str, Any] | None:
    try:
        return _fetch_order(order_id)
    except TransientError as exc:
        log.warning("enrich_order: skipped order %s (%s)", order_id, exc)
        return None


def publish_event(event: dict[str, Any]) -> None:
    try:
        _publish(event)
    except TransientError as exc:
        log.warning("publish_event: failed for event %r (%s)", event.get("id"), exc)


def record_metric(name: str, value: float) -> None:
    try:
        _write_metric(name, value)
    except TransientError as exc:
        log.warning("record_metric: dropped %s=%s (%s)", name, value, exc)


def run(user_ids: list[str], order_ids: list[str]) -> None:
    for uid in user_ids:
        enrich_user(uid)
    for oid in order_ids:
        enrich_order(oid)
    publish_event({"id": "e1"})
    record_metric("rows_processed", float(len(user_ids) + len(order_ids)))
