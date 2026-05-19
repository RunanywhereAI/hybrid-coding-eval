"""Unit tests for analysis.bootstrap — Phase 4 of v1.1.

Tests are deterministic via fixed RNG seed. They exercise:

  * the metric helpers (pass_rate / cost_median / wall_median /
    cloud_fraction_mean) on hand-crafted rows
  * the cell stratification by (category, route, router_strategy)
  * the bootstrap CI bounds make sense (point estimate ∈ [lo, hi];
    lo ≤ hi; reasonable spread)
  * the schema-version contract for downstream readers
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hybrid_coding_eval.analysis.bootstrap import (
    bootstrap_aggregate,
    bootstrap_cells_for_rows,
    cell_key,
)

# --- minimal row fixtures --------------------------------------------------


@dataclass
class _Quality:
    functional_pass: bool | None = None
    composite: float | None = None


@dataclass
class _Latency:
    wall_ms: int = 0


@dataclass
class _Routing:
    total_calls: int = 0
    local_calls: int = 0
    cloud_calls: int = 0


@dataclass
class _Row:
    task_id: str
    category: str = "A"
    route: str = "R8"
    router_strategy: str | None = "heuristic"
    quality: _Quality = field(default_factory=_Quality)
    latency: _Latency = field(default_factory=_Latency)
    routing: _Routing = field(default_factory=_Routing)
    cost_usd: float = 0.0
    seeds: list[int] = field(default_factory=lambda: [42])
    error: str | None = None


def _make_rows(n: int, pass_rate: float = 0.7, cost: float = 0.10) -> list[_Row]:
    """Build n rows with a controllable pass-rate and cost."""
    out = []
    for i in range(n):
        passed = (i / n) < pass_rate
        out.append(
            _Row(
                task_id=f"t{i}",
                quality=_Quality(functional_pass=passed, composite=1.0 if passed else 0.0),
                latency=_Latency(wall_ms=1000 + i * 50),
                routing=_Routing(total_calls=10, local_calls=3, cloud_calls=7),
                cost_usd=cost,
            )
        )
    return out


# --- key + schema tests ----------------------------------------------------


def test_cell_key_stable():
    assert cell_key("A", "R8", "heuristic") == "A::R8::heuristic"
    assert cell_key("D", "R8", None) == "D::R8::none"


def test_schema_version_present_on_empty():
    """Empty rows → empty cells, still valid schema."""
    out = bootstrap_aggregate([])
    assert out["schema_version"] == "1.0"
    assert out["cells"] == {}
    assert "generated_at" in out


# --- core bootstrap behavior ----------------------------------------------


def test_bootstrap_point_estimate_matches_row_proportion():
    rows = _make_rows(20, pass_rate=0.5)  # 10/20 pass
    out = bootstrap_cells_for_rows(rows, n_resamples=200, seed=42)
    assert len(out) == 1
    cell = next(iter(out.values()))
    point = cell["pass_rate"]["point"]
    assert point is not None
    assert 0.45 <= point <= 0.55, point


def test_bootstrap_ci_contains_point_estimate():
    rows = _make_rows(20, pass_rate=0.7)
    out = bootstrap_cells_for_rows(rows, n_resamples=500, seed=42)
    cell = next(iter(out.values()))
    pr = cell["pass_rate"]
    assert pr["ci_lower"] <= pr["point"] <= pr["ci_upper"]
    # Spread should be non-trivial but bounded for n=20.
    assert pr["ci_upper"] - pr["ci_lower"] >= 0.05
    assert pr["ci_upper"] - pr["ci_lower"] <= 0.6


def test_bootstrap_stratifies_by_cell():
    rows_a_heuristic = _make_rows(15, pass_rate=0.8)
    rows_a_cascade = [
        _Row(
            task_id=f"c{i}",
            router_strategy="cascade",
            quality=_Quality(functional_pass=False, composite=0.0),
            latency=_Latency(wall_ms=2000),
            routing=_Routing(total_calls=8, local_calls=8, cloud_calls=0),
            cost_usd=0.05,
        )
        for i in range(10)
    ]
    out = bootstrap_cells_for_rows(
        rows_a_heuristic + rows_a_cascade, n_resamples=200, seed=42,
    )
    assert "A::R8::heuristic" in out
    assert "A::R8::cascade" in out
    assert out["A::R8::heuristic"]["n_rows"] == 15
    assert out["A::R8::cascade"]["n_rows"] == 10
    # cascade rows are all-fail → pass_rate ~ 0
    assert out["A::R8::cascade"]["pass_rate"]["point"] == 0.0


def test_bootstrap_cost_and_wall_medians():
    rows = []
    for i, cost in enumerate([0.01, 0.02, 0.10, 0.50, 1.00]):
        rows.append(
            _Row(
                task_id=f"t{i}",
                quality=_Quality(functional_pass=True),
                latency=_Latency(wall_ms=1000 * (i + 1)),
                routing=_Routing(total_calls=10, local_calls=5, cloud_calls=5),
                cost_usd=cost,
            )
        )
    out = bootstrap_cells_for_rows(rows, n_resamples=200, seed=42)
    cell = next(iter(out.values()))
    assert cell["cost_usd"]["point"] == 0.10  # median of [0.01, 0.02, 0.10, 0.50, 1.00]
    assert cell["wall_ms"]["point"] == 3000.0  # median of [1000, 2000, 3000, 4000, 5000]


def test_bootstrap_cloud_fraction():
    """Each row has its own cloud_fraction; cell mean averages them."""
    rows = [
        _Row(
            task_id=f"t{i}",
            quality=_Quality(functional_pass=True),
            latency=_Latency(wall_ms=1000),
            routing=_Routing(total_calls=10, local_calls=l, cloud_calls=c),
            cost_usd=0.01,
        )
        for i, (l, c) in enumerate([(0, 10), (5, 5), (10, 0)])
    ]
    out = bootstrap_cells_for_rows(rows, n_resamples=200, seed=42)
    cell = next(iter(out.values()))
    # Per-row cloud_fraction = [1.0, 0.5, 0.0] → mean = 0.5
    assert abs(cell["cloud_fraction"]["point"] - 0.5) < 1e-9


def test_bootstrap_error_rows_excluded():
    rows = _make_rows(10, pass_rate=1.0)
    rows.append(
        _Row(
            task_id="bad",
            quality=_Quality(functional_pass=None),
            error="agent_timeout_900s",
        )
    )
    out = bootstrap_cells_for_rows(rows, n_resamples=100, seed=42)
    cell = next(iter(out.values()))
    assert cell["n_rows"] == 10  # error row dropped


def test_seeds_collected_per_cell():
    rows = []
    for s in (42, 7, 13):
        rows.extend(
            _Row(task_id=f"t{i}_{s}", seeds=[s], quality=_Quality(functional_pass=True))
            for i in range(3)
        )
    out = bootstrap_cells_for_rows(rows, n_resamples=100, seed=42)
    cell = next(iter(out.values()))
    assert cell["n_seeds"] == 3
    assert sorted(cell["seeds"]) == [7, 13, 42]
