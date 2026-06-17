"""Tests for :mod:`analysis.aggregate` and :mod:`analysis.cost_scenarios`.

Scope:

  * Synthetic 5-row dataset → aggregate shape matches the spec.
  * Multi-scenario cost: swapping scenarios changes the cost column.
  * Partial-sweep robustness: empty / sparse data doesn't crash.
  * JSON round-trip: output is valid JSON (no raw NaN).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_arena.analysis.aggregate import aggregate_results, rows_to_frame  # noqa: E402
from hybrid_arena.analysis.cost_scenarios import (  # noqa: E402
    PRICING_SCENARIOS,
    compute_row_cost,
    compute_scenario_costs,
)
from hybrid_arena.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_arena.core.results import append_row  # noqa: E402


def _mk_row(
    *,
    task_id: str,
    category: str = "puzzles",
    route: str = "aider",
    prompt: int = 1000,
    completion: int = 500,
    local_prompt: int = 0,
    local_completion: int = 0,
    cloud_prompt: int = 0,
    cloud_completion: int = 0,
    wall_ms: int = 1000,
    composite: float | None = 0.8,
    functional_pass: bool | None = True,
) -> ResultRow:
    return ResultRow(
        task_id=task_id,
        category=category,
        route=route,
        hardware_profile_ref="hw",
        tokens=TokenUsage(
            prompt=prompt,
            completion=completion,
            local_prompt=local_prompt,
            local_completion=local_completion,
            cloud_prompt=cloud_prompt,
            cloud_completion=cloud_completion,
        ),
        latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
        quality=Quality(
            composite=composite,
            functional_pass=functional_pass,
        ),
        routing=Routing(
            total_calls=1,
            local_calls=0 if cloud_completion else 1,
            cloud_calls=1 if cloud_completion or not local_completion else 0,
            per_call_backends=["x"],
        ),
        output_ref="out.txt",
    )


def _write_rows(path: Path, rows: list[ResultRow]) -> None:
    for r in rows:
        append_row(path, r)


def test_compute_row_cost_pure_cloud_and_local():
    cloud = _mk_row(
        task_id="c",
        prompt=1000,
        completion=500,
        cloud_prompt=1000,
        cloud_completion=500,
    )
    # gpt-5.5 rates: 5/M input, 30/M output → 0.005 + 0.015 = 0.020
    assert math.isclose(
        compute_row_cost(cloud, "openai-gpt5.5"), 0.020, abs_tol=1e-12
    )
    # gpt-5-mini is cheaper: exact rate depends on pricing_tables.json.
    # Just assert it's strictly lower than gpt-5.5.
    assert compute_row_cost(cloud, "openai-gpt5-mini") < compute_row_cost(
        cloud, "openai-gpt5.5"
    )

    local = _mk_row(
        task_id="l",
        local_prompt=1000,
        local_completion=500,
    )
    assert compute_row_cost(local, "openai-gpt5.5") == 0.0
    assert compute_row_cost(local, "anthropic-claude-opus-4.7") == 0.0


def test_compute_scenario_costs_swaps_column_per_scenario():
    rows = [
        _mk_row(task_id="a", route="aider", cloud_prompt=1000, cloud_completion=500),
        _mk_row(task_id="b", route="opencode", local_prompt=1000, local_completion=500, composite=0.5),
    ]
    df = compute_scenario_costs(rows, ["openai-gpt5.5", "openai-gpt5-mini"])
    assert list(df.columns) == [
        "task_id",
        "category",
        "route",
        "cost_openai-gpt5.5",
        "cost_openai-gpt5-mini",
    ]
    # Cloud row should have non-zero cost, local row zero cost.
    assert float(df.loc[df["task_id"] == "a", "cost_openai-gpt5.5"].iloc[0]) > 0
    assert float(df.loc[df["task_id"] == "b", "cost_openai-gpt5.5"].iloc[0]) == 0.0
    # gpt5-mini cheaper than gpt5.5 for the same tokens.
    mini = float(df.loc[df["task_id"] == "a", "cost_openai-gpt5-mini"].iloc[0])
    full = float(df.loc[df["task_id"] == "a", "cost_openai-gpt5.5"].iloc[0])
    assert mini < full


def test_aggregate_results_shape_and_headline(tmp_path: Path):
    """5 rows across 2 task-classes × 2 agents → check the JSON shape."""
    rows = [
        _mk_row(task_id="t1", category="puzzles",   route="aider",    cloud_prompt=1000, cloud_completion=500, composite=1.0, functional_pass=True),
        _mk_row(task_id="t2", category="puzzles",   route="aider",    cloud_prompt=1200, cloud_completion=400, composite=0.9, functional_pass=True),
        _mk_row(task_id="t3", category="puzzles",   route="opencode", local_prompt=1000, local_completion=500, composite=0.4, functional_pass=False),
        _mk_row(task_id="t4", category="refactors", route="aider",    cloud_prompt=2000, cloud_completion=800, composite=0.7, functional_pass=True),
        _mk_row(task_id="t5", category="refactors", route="opencode", local_prompt=1500, local_completion=500, composite=0.5, functional_pass=False),
    ]
    path = tmp_path / "raw.jsonl"
    _write_rows(path, rows)

    out_path = tmp_path / "aggregate.json"
    agg = aggregate_results(path, out_path)

    assert agg["row_count"] == 5
    assert agg["source"].endswith("raw.jsonl")
    assert set(agg["per_category_route"].keys()) == {
        "puzzles/aider",
        "puzzles/opencode",
        "refactors/aider",
        "refactors/opencode",
    }

    puzzles_aider = agg["per_category_route"]["puzzles/aider"]
    assert puzzles_aider["count"] == 2
    # Quality median of [1.0, 0.9] = 0.95.
    assert math.isclose(puzzles_aider["quality_median"], 0.95)
    # Cost columns present and positive for the cloud cell.
    for s in PRICING_SCENARIOS:
        assert f"cost_{s}_median" in puzzles_aider
        assert f"cost_{s}_total" in puzzles_aider
        assert puzzles_aider[f"cost_{s}_total"] > 0

    # puzzles/opencode is pure-local → zero cost regardless of scenario.
    puzzles_opencode = agg["per_category_route"]["puzzles/opencode"]
    for s in PRICING_SCENARIOS:
        assert puzzles_opencode[f"cost_{s}_total"] == 0.0

    # Headline has flat keys like "puzzles_aider".
    assert "puzzles_aider" in agg["headline"]["quality"]
    assert "puzzles_aider" in agg["headline"]["cost_openai-gpt5.5"]

    # Totals per route.
    per_route = agg["totals"]["per_route"]
    assert set(per_route.keys()) == {"aider", "opencode"}
    assert per_route["aider"]["tokens_cloud_prompt_total"] == 1000 + 1200 + 2000
    assert per_route["opencode"]["tokens_local_prompt_total"] == 1000 + 1500

    # Success rate per route per category.
    srr = agg["success_rate_per_route_per_category"]
    assert srr["puzzles"]["aider"] == 1.0
    assert srr["puzzles"]["opencode"] == 0.0
    assert srr["refactors"]["aider"] == 1.0

    # Output file exists and parses as JSON (no raw NaN).
    raw_out = out_path.read_text()
    parsed = json.loads(raw_out)
    assert parsed["row_count"] == 5


def test_aggregate_results_handles_empty_input(tmp_path: Path):
    """Empty raw.jsonl → skeleton output with zero rows, no crash."""
    path = tmp_path / "raw.jsonl"
    path.write_text("")
    out = tmp_path / "agg.json"
    agg = aggregate_results(path, out)
    assert agg["row_count"] == 0
    assert agg["per_category_route"] == {}
    # JSON is valid.
    json.loads(out.read_text())


def test_aggregate_results_none_composite_becomes_null(tmp_path: Path):
    """Rows with no composite (e.g. judge-only tasks) serialise as JSON null."""
    rows = [
        _mk_row(task_id="c1", category="refactors", route="cline", composite=None, functional_pass=None),
        _mk_row(task_id="c2", category="refactors", route="cline", composite=None, functional_pass=None),
    ]
    path = tmp_path / "raw.jsonl"
    _write_rows(path, rows)
    out = tmp_path / "agg.json"
    agg = aggregate_results(path, out)
    cell = agg["per_category_route"]["refactors/cline"]
    assert cell["quality_median"] is None  # NaN → None
    parsed = json.loads(out.read_text())
    assert parsed["per_category_route"]["refactors/cline"]["quality_median"] is None


def test_rows_to_frame_includes_all_scenario_columns():
    rows = [_mk_row(task_id="t", cloud_prompt=100, cloud_completion=50)]
    df = rows_to_frame(rows, ["openai-gpt5.5", "openai-gpt5-mini"])
    assert "cost_openai-gpt5.5" in df.columns
    assert "cost_openai-gpt5-mini" in df.columns
