"""Round-trip tests for :class:`ResultRow` and its optional metadata fields.

These tests cover the JSONL serialisation surface — the on-disk
``raw.jsonl`` format. Unknown keys must be tolerated (forward-compat)
and the optional metadata fields (``variant``, ``cloud_model_id``,
``local_model_id``, ``router_classifier_model_id``, ``router_strategy``,
``seed``, ``config_sha``) must survive a round trip.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from hybrid_arena.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)


def _base_row(**overrides) -> ResultRow:
    row = ResultRow(
        task_id="exercism-python/grep",
        category="puzzles",
        route="aider",
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


def test_default_row_emits_all_metadata_fields_as_none():
    row = _base_row()
    d = row.to_dict()
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


def test_metadata_fields_survive_round_trip():
    row = _base_row(
        variant="canonical",
        cloud_model_id="gpt-5.5",
        local_model_id="gemma4:31b",
        router_classifier_model_id="qwen3:0.6b",
        router_strategy="heuristic",
        seed=42,
        config_sha="abc123" * 10 + "abcd",
    )
    d = row.to_dict()
    back = ResultRow.from_dict(d)
    assert back.variant == "canonical"
    assert back.cloud_model_id == "gpt-5.5"
    assert back.local_model_id == "gemma4:31b"
    assert back.router_classifier_model_id == "qwen3:0.6b"
    assert back.router_strategy == "heuristic"
    assert back.seed == 42
    assert back.config_sha == "abc123" * 10 + "abcd"


def test_unknown_keys_are_dropped_on_load():
    """from_dict silently drops unknown keys — forward-compatibility."""
    payload = {
        "task_id": "t",
        "category": "puzzles",
        "route": "aider",
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
