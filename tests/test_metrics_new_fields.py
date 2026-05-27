"""T-08: new Optional metadata fields on :class:`ResultRow`.

Covers:
 - historical row (no new fields) round-trips via ``from_dict``/``to_dict``.
 - a row populated with all new fields round-trips without losing them.
 - the existing 180-row dataset at ``results/raw.jsonl`` still parses
   cleanly after the field addition.
"""

from __future__ import annotations

import json
from pathlib import Path

from hybrid_coding_eval.core.metrics import (
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_coding_eval.core.results import load_results

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _base_row(**overrides) -> ResultRow:
    row = ResultRow(
        task_id="humaneval-plus/HumanEval_0",
        category="A",
        route="R1",
        hardware_profile_ref="test-profile",
        tokens=TokenUsage(prompt=10, completion=20),
        latency=Latency(wall_ms=100, per_call_ms=[100]),
        quality=Quality(functional_pass=True, composite=1.0),
        routing=Routing(total_calls=1, local_calls=0, cloud_calls=1),
        output_ref="out.txt",
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def test_historical_row_still_round_trips():
    """A row without any of the new fields populates them to None."""
    row = _base_row()
    d = row.to_dict()
    # All new fields present but None on a default row.
    for key in (
        "variant",
        "cloud_model_id",
        "local_model_id",
        "router_classifier_model_id",
        "router_strategy",
        "seed",
        "config_sha",
    ):
        assert key in d
        assert d[key] is None
    back = ResultRow.from_dict(d)
    assert back == row


def test_new_fields_survive_round_trip():
    row = _base_row(
        variant="r4-cachedA",
        cloud_model_id="gpt-5.5",
        local_model_id="gemma4:31b",
        router_classifier_model_id="qwen3:0.6b",
        router_strategy="heuristic",
        seed=42,
        config_sha="abc123" * 10 + "abcd",
    )
    d = row.to_dict()
    back = ResultRow.from_dict(d)
    assert back.variant == "r4-cachedA"
    assert back.cloud_model_id == "gpt-5.5"
    assert back.local_model_id == "gemma4:31b"
    assert back.router_classifier_model_id == "qwen3:0.6b"
    assert back.router_strategy == "heuristic"
    assert back.seed == 42
    assert back.config_sha == "abc123" * 10 + "abcd"


def test_historical_dataset_still_loads():
    """Every row in the committed 180-row dataset must still parse."""
    raw = _REPO_ROOT / "results" / "raw.jsonl"
    rows = load_results(raw)
    assert len(rows) == 180, f"expected 180 rows, got {len(rows)}"
    # Representative checks — every row has the required non-optional
    # fields, and the new optional ones default to None (or whatever the
    # historical data had, e.g. ``variant`` was added post-hoc and is
    # present on every row).
    for r in rows:
        assert r.task_id
        assert r.route in {"R1", "R2", "R3", "R4"}


def test_raw_jsonl_unknown_keys_are_tolerated(tmp_path):
    """from_dict silently drops unknown keys — forward-compatibility."""
    payload = {
        "task_id": "t",
        "category": "A",
        "route": "R1",
        "hardware_profile_ref": "hw",
        "tokens": {"prompt": 1, "completion": 1},
        "latency": {"wall_ms": 1},
        "quality": {},
        "routing": {"total_calls": 1, "local_calls": 0, "cloud_calls": 1},
        "output_ref": "out.txt",
        "some_future_field_we_dont_know_yet": 42,
    }
    row = ResultRow.from_dict(payload)
    assert row.task_id == "t"
    assert "some_future_field_we_dont_know_yet" not in row.to_dict()


def test_raw_jsonl_preserves_variant_field():
    """Historical rows use ``variant`` — confirm it's loaded into the
    dataclass attribute now that the field is declared."""
    raw = _REPO_ROOT / "results" / "raw.jsonl"
    with raw.open() as fh:
        first = json.loads(fh.readline())
    assert "variant" in first, "sample historical row must have variant"
    row = ResultRow.from_dict(first)
    assert row.variant == first["variant"]
