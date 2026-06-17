"""Unit tests for :mod:`hybrid_arena.analysis.bootstrap`.

Deterministic via fixed RNG seed. Exercises:

* the per-metric helpers (pass_rate, cost_median via real pricing,
  cloud_fraction via token sums, wall_median).
* cell stratification by the default ``(category, route, router_strategy)``
  axis and by a custom ``stratify_by``.
* CI sanity: ``ci_lower ≤ point ≤ ci_upper``.
* schema-version contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hybrid_arena.analysis.bootstrap import (
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
class _Tokens:
    prompt: int = 0
    completion: int = 0
    cached: int = 0
    local_prompt: int = 0
    local_completion: int = 0
    cloud_prompt: int = 0
    cloud_completion: int = 0


@dataclass
class _Row:
    task_id: str
    category: str = "puzzles"
    route: str = "aider"
    router_strategy: str | None = "heuristic"
    quality: _Quality = field(default_factory=_Quality)
    latency: _Latency = field(default_factory=_Latency)
    routing: _Routing = field(default_factory=_Routing)
    tokens: _Tokens = field(default_factory=_Tokens)
    seed: int | None = 42
    error: str | None = None


def _make_rows(
    n: int,
    pass_rate: float = 0.7,
    cloud_tokens: int = 100,
    local_tokens: int = 0,
) -> list[_Row]:
    """Build n rows with controllable pass-rate + token split."""
    out: list[_Row] = []
    for i in range(n):
        passed = (i / n) < pass_rate
        out.append(
            _Row(
                task_id=f"t{i}",
                quality=_Quality(functional_pass=passed, composite=1.0 if passed else 0.0),
                latency=_Latency(wall_ms=1000 + i * 50),
                routing=_Routing(total_calls=10, local_calls=3, cloud_calls=7),
                tokens=_Tokens(
                    cloud_prompt=cloud_tokens, cloud_completion=cloud_tokens // 4,
                    local_prompt=local_tokens, local_completion=local_tokens // 4,
                ),
            )
        )
    return out


# --- key + schema tests ----------------------------------------------------


def test_cell_key_default_axis():
    r = _Row(task_id="t0", category="puzzles", route="aider", router_strategy="heuristic")
    assert cell_key(r) == "puzzles::aider::heuristic"


def test_cell_key_custom_axis():
    r = _Row(task_id="t0", category="refactors", route="cline")
    assert cell_key(r, ("route", "category")) == "cline::refactors"


def test_cell_key_none_router_strategy():
    r = _Row(task_id="t0", router_strategy=None)
    assert cell_key(r).endswith("::none")


def test_schema_version_present_on_empty():
    """Empty rows → empty cells, still valid schema."""
    out = bootstrap_aggregate([])
    assert out["schema_version"] == "2.0"
    assert out["cells"] == {}
    assert "generated_at" in out
    assert out["scenario"] == "openai-gpt5.5"


# --- core bootstrap behavior ----------------------------------------------


def test_bootstrap_point_estimate_matches_row_proportion():
    rows = _make_rows(20, pass_rate=0.5)
    out = bootstrap_cells_for_rows(rows, n_resamples=200, seed=42)
    cells = out["cells"]
    assert len(cells) == 1
    cell = next(iter(cells.values()))
    point = cell["pass_rate"]["point"]
    assert point is not None
    assert 0.45 <= point <= 0.55, point


def test_bootstrap_ci_contains_point_estimate():
    rows = _make_rows(20, pass_rate=0.7)
    out = bootstrap_cells_for_rows(rows, n_resamples=500, seed=42)
    cell = next(iter(out["cells"].values()))
    pr = cell["pass_rate"]
    assert pr["ci_lower"] <= pr["point"] <= pr["ci_upper"]
    # Spread should be non-trivial but bounded for n=20.
    assert pr["ci_upper"] - pr["ci_lower"] >= 0.05
    assert pr["ci_upper"] - pr["ci_lower"] <= 0.6


def test_bootstrap_stratifies_by_cell():
    rows_a = _make_rows(15, pass_rate=0.8)
    rows_b = [
        _Row(
            task_id=f"c{i}",
            router_strategy="cascade",
            quality=_Quality(functional_pass=False),
            latency=_Latency(wall_ms=2000),
            routing=_Routing(total_calls=8, local_calls=8, cloud_calls=0),
            tokens=_Tokens(local_prompt=200, local_completion=50),
        )
        for i in range(10)
    ]
    out = bootstrap_cells_for_rows(rows_a + rows_b, n_resamples=200, seed=42)
    cells = out["cells"]
    assert "puzzles::aider::heuristic" in cells
    assert "puzzles::aider::cascade" in cells
    assert cells["puzzles::aider::heuristic"]["n_rows"] == 15
    assert cells["puzzles::aider::cascade"]["n_rows"] == 10
    assert cells["puzzles::aider::cascade"]["pass_rate"]["point"] == 0.0


def test_bootstrap_cost_uses_pricing_table():
    """cost_usd is computed via core.pricing — verify the point estimate
    is non-zero for a cloud-heavy row and zero for a local-only row."""
    cloud_row = _Row(
        task_id="cloud",
        router_strategy="always-cloud",
        quality=_Quality(functional_pass=True),
        tokens=_Tokens(prompt=1000, completion=200, cloud_prompt=1000, cloud_completion=200),
    )
    local_row = _Row(
        task_id="local",
        router_strategy="always-local",
        quality=_Quality(functional_pass=True),
        tokens=_Tokens(prompt=1000, completion=200, local_prompt=1000, local_completion=200),
    )
    out = bootstrap_cells_for_rows(
        [cloud_row, cloud_row, local_row, local_row], n_resamples=100, seed=42,
    )
    cloud_cell = out["cells"]["puzzles::aider::always-cloud"]
    local_cell = out["cells"]["puzzles::aider::always-local"]
    assert cloud_cell["cost_usd"]["point"] > 0
    assert local_cell["cost_usd"]["point"] == 0.0


def test_bootstrap_cloud_fraction_token_based():
    """cloud_fraction is Σ cloud_tokens / Σ all_tokens — the canonical
    definition used in every release headline."""
    rows = [
        _Row(
            task_id=f"t{i}",
            quality=_Quality(functional_pass=True),
            tokens=_Tokens(cloud_prompt=cp, local_prompt=lp),
        )
        for i, (cp, lp) in enumerate([(100, 0), (50, 50), (0, 100)])
    ]
    out = bootstrap_cells_for_rows(rows, n_resamples=200, seed=42)
    cell = next(iter(out["cells"].values()))
    # Σ cloud = 150, Σ all = 300 → 0.5
    assert abs(cell["cloud_fraction"]["point"] - 0.5) < 1e-9


def test_bootstrap_error_rows_excluded():
    rows = _make_rows(10, pass_rate=1.0)
    rows.append(
        _Row(task_id="bad", quality=_Quality(functional_pass=None), error="agent_timeout_900s"),
    )
    out = bootstrap_cells_for_rows(rows, n_resamples=100, seed=42)
    cell = next(iter(out["cells"].values()))
    assert cell["n_rows"] == 10


def test_seeds_collected_per_cell():
    rows: list[_Row] = []
    for s in (42, 7, 13):
        rows.extend(
            _Row(task_id=f"t{i}_{s}", seed=s, quality=_Quality(functional_pass=True))
            for i in range(3)
        )
    out = bootstrap_cells_for_rows(rows, n_resamples=100, seed=42)
    cell = next(iter(out["cells"].values()))
    assert cell["n_seeds"] == 3
    assert sorted(cell["seeds"]) == [7, 13, 42]
