"""Smoke tests for :mod:`viz.cost_quality_pareto` and :mod:`viz.decision_heatmap`.

We only verify each script produces a non-zero PNG given a 10-row synthetic
fixture. Visual correctness of matplotlib output is out of scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hybrid_arena.analysis.aggregate import aggregate_results
from hybrid_arena.core.metrics import (
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_arena.core.results import append_row
from hybrid_arena.viz.cost_quality_pareto import plot_pareto
from hybrid_arena.viz.decision_heatmap import plot_heatmap


def _mk_row(
    task_id: str,
    category: str,
    route: str,
    composite: float,
    cloud_prompt: int = 0,
    cloud_completion: int = 0,
    local_prompt: int = 0,
    local_completion: int = 0,
) -> ResultRow:
    return ResultRow(
        task_id=task_id,
        category=category,
        route=route,
        hardware_profile_ref="hw",
        tokens=TokenUsage(
            prompt=cloud_prompt + local_prompt,
            completion=cloud_completion + local_completion,
            cloud_prompt=cloud_prompt,
            cloud_completion=cloud_completion,
            local_prompt=local_prompt,
            local_completion=local_completion,
        ),
        latency=Latency(wall_ms=1000, per_call_ms=[1000]),
        quality=Quality(composite=composite, functional_pass=composite > 0.5),
        routing=Routing(
            total_calls=1, local_calls=0, cloud_calls=1, per_call_backends=["x"]
        ),
        output_ref="out.txt",
    )


def _make_fixture(tmp_path: Path):
    rows = []
    configs = [
        ("puzzles", "aider", 0.9, 1000, 500, 0, 0),
        ("puzzles", "aider", 0.85, 1200, 400, 0, 0),
        ("puzzles", "opencode", 0.5, 0, 0, 1000, 500),
        ("puzzles", "opencode", 0.55, 0, 0, 1100, 550),
        ("puzzles", "cline", 0.8, 500, 250, 500, 250),
        ("refactors", "aider", 0.7, 2000, 1000, 0, 0),
        ("refactors", "aider", 0.75, 1800, 900, 0, 0),
        ("refactors", "opencode", 0.6, 0, 0, 2000, 1000),
        ("refactors", "cline", 0.72, 1000, 500, 1000, 500),
        ("refactors", "cline", 0.78, 1200, 600, 800, 400),
    ]
    for i, (cat, route, q, cp, cc, lp, lc) in enumerate(configs):
        rows.append(_mk_row(f"t{i}", cat, route, q, cp, cc, lp, lc))

    raw_path = tmp_path / "raw.jsonl"
    for r in rows:
        append_row(raw_path, r)
    agg = aggregate_results(raw_path, tmp_path / "aggregate.json")
    return rows, agg


def test_pareto_png_is_created_non_empty(tmp_path: Path):
    rows, _ = _make_fixture(tmp_path)
    out = tmp_path / "charts" / "pareto.png"
    plot_pareto(rows, out, scenario="openai-gpt5.5")
    assert out.exists()
    assert out.stat().st_size > 1000


def test_heatmap_quality_png(tmp_path: Path):
    _, agg = _make_fixture(tmp_path)
    out = tmp_path / "charts" / "heatmap_quality.png"
    plot_heatmap(agg, out, metric="quality")
    assert out.exists()
    assert out.stat().st_size > 1000


def test_heatmap_cost_png(tmp_path: Path):
    _, agg = _make_fixture(tmp_path)
    out = tmp_path / "charts" / "heatmap_cost.png"
    plot_heatmap(agg, out, metric="cost", scenario="openai-gpt5.5")
    assert out.exists()
    assert out.stat().st_size > 1000


def test_heatmap_unknown_metric_raises(tmp_path: Path):
    _, agg = _make_fixture(tmp_path)
    out = tmp_path / "charts" / "heatmap_bad.png"
    with pytest.raises(ValueError):
        plot_heatmap(agg, out, metric="bogus")
