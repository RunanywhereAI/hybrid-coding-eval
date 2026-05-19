"""Per-cell bootstrap confidence intervals for sweep aggregates.

Used by Phase 4 of the v1.1 plan to attach 95% CIs to every published
``(category, route, router_strategy)`` cell. Multi-seed runs (``./bench
sweep --seeds 42,7,13``) provide the resample base.

The math is deliberately simple — non-parametric bootstrap with
percentile bounds. For each cell we resample with replacement
``n_resamples`` times, recompute the statistic on each resample, and
take the (1-ci)/2 and (1+ci)/2 quantiles of the resample distribution.

Stratification key is configurable but defaults to
``(category, route, router_strategy)`` — i.e., seeds are pooled inside
each cell so the CI captures inter-seed variance.

Statistics computed per cell:
  * ``pass_rate``        — fraction of rows with ``quality.functional_pass``
                           equal to True. Excludes rows where it's None.
  * ``cost_usd``         — median ``cost_usd`` per row (pre-summed by
                           the upstream pricing pipeline).
  * ``cloud_fraction``   — mean of ``routing.cloud_calls /
                           routing.total_calls`` (skips rows where
                           total_calls == 0).
  * ``wall_ms``          — median ``latency.wall_ms``.

Output shape (written to ``bootstrap_cis.json``)::

    {
      "schema_version": "1.0",
      "generated_at": "...",
      "n_resamples": 1000,
      "ci": 0.95,
      "stratify_by": ["category", "route", "router_strategy"],
      "cells": {
        "<key>": {
          "n_rows": 12, "n_seeds": 3,
          "pass_rate":     {"point": ..., "ci_lower": ..., "ci_upper": ...},
          "cost_usd":      {"point": ..., "ci_lower": ..., "ci_upper": ...},
          "cloud_fraction":{"point": ..., "ci_lower": ..., "ci_upper": ...},
          "wall_ms":       {"point": ..., "ci_lower": ..., "ci_upper": ...},
        },
        ...
      }
    }

``<key>`` is the tuple joined with "::". e.g. ``"A::R8::heuristic"``.
"""

from __future__ import annotations

import datetime as _dt
import random
from collections.abc import Sequence
from typing import Any

__all__ = ["bootstrap_aggregate", "bootstrap_cells_for_rows", "cell_key"]


def cell_key(category: str, route: str, router_strategy: str | None) -> str:
    """Stable key for a ``(category, route, router_strategy)`` triple."""
    return f"{category}::{route}::{router_strategy or 'none'}"


def _row_seed(row: Any) -> int | None:
    """Extract the seed off a row in a defensive way."""
    seeds = getattr(row, "seeds", None) or getattr(row, "seed", None)
    if isinstance(seeds, list) and seeds:
        return int(seeds[0])
    if isinstance(seeds, int):
        return int(seeds)
    return None


def _pass_rate(rows: Sequence[Any]) -> float | None:
    """Fraction of rows with functional_pass == True, ignoring None."""
    measured = [
        bool(r.quality.functional_pass)
        for r in rows
        if getattr(r.quality, "functional_pass", None) is not None
    ]
    if not measured:
        return None
    return sum(measured) / len(measured)


def _median(values: Sequence[float]) -> float | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    cleaned = sorted(cleaned)
    n = len(cleaned)
    mid = n // 2
    if n % 2 == 1:
        return float(cleaned[mid])
    return float((cleaned[mid - 1] + cleaned[mid]) / 2)


def _cost_median(rows: Sequence[Any]) -> float | None:
    return _median([float(getattr(r, "cost_usd", 0.0) or 0.0) for r in rows])


def _wall_median(rows: Sequence[Any]) -> float | None:
    return _median([float(getattr(r.latency, "wall_ms", 0) or 0) for r in rows])


def _cloud_fraction_mean(rows: Sequence[Any]) -> float | None:
    fractions: list[float] = []
    for r in rows:
        total = getattr(r.routing, "total_calls", 0) or 0
        if total <= 0:
            continue
        cloud = getattr(r.routing, "cloud_calls", 0) or 0
        fractions.append(cloud / total)
    if not fractions:
        return None
    return sum(fractions) / len(fractions)


# Function-name → statistic function map. The bootstrap loop applies
# each one to the resampled rows.
_METRICS: dict[str, Any] = {
    "pass_rate": _pass_rate,
    "cost_usd": _cost_median,
    "cloud_fraction": _cloud_fraction_mean,
    "wall_ms": _wall_median,
}


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interp percentile (matches numpy.percentile's default)."""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _bootstrap_one(
    rows: Sequence[Any],
    *,
    n_resamples: int,
    ci: float,
    rng: random.Random,
) -> dict[str, dict[str, float | None]]:
    """Resample ``rows`` ``n_resamples`` times; return per-metric CIs."""
    if not rows:
        return {m: {"point": None, "ci_lower": None, "ci_upper": None} for m in _METRICS}

    point_estimates = {m: fn(rows) for m, fn in _METRICS.items()}

    resample_dists: dict[str, list[float]] = {m: [] for m in _METRICS}
    n = len(rows)
    for _ in range(n_resamples):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        for m, fn in _METRICS.items():
            v = fn(sample)
            if v is not None:
                resample_dists[m].append(float(v))

    q_lo = (1 - ci) / 2
    q_hi = 1 - q_lo
    out: dict[str, dict[str, float | None]] = {}
    for m, point in point_estimates.items():
        dist = sorted(resample_dists[m])
        if not dist:
            out[m] = {"point": point, "ci_lower": None, "ci_upper": None}
            continue
        out[m] = {
            "point": point,
            "ci_lower": _percentile(dist, q_lo),
            "ci_upper": _percentile(dist, q_hi),
        }
    return out


def bootstrap_cells_for_rows(
    rows: Sequence[Any],
    *,
    n_resamples: int = 1000,
    ci: float = 0.95,
    stratify_by: tuple[str, ...] = ("category", "route", "router_strategy"),
    seed: int = 42,
) -> dict[str, dict[str, Any]]:
    """Group ``rows`` by ``stratify_by`` and compute per-cell bootstrap CIs."""
    rng = random.Random(seed)
    cells: dict[str, list[Any]] = {}
    for r in rows:
        # Skip error rows (no clean signal).
        if getattr(r, "error", None):
            continue
        category = getattr(r, "category", None)
        route = getattr(r, "route", None)
        router_strategy = getattr(r, "router_strategy", None)
        key = cell_key(category, route, router_strategy)
        cells.setdefault(key, []).append(r)

    out: dict[str, dict[str, Any]] = {}
    for key, cell_rows in cells.items():
        seeds = sorted({s for s in (_row_seed(r) for r in cell_rows) if s is not None})
        metrics = _bootstrap_one(
            cell_rows, n_resamples=n_resamples, ci=ci, rng=rng,
        )
        out[key] = {
            "n_rows": len(cell_rows),
            "n_seeds": len(seeds),
            "seeds": seeds,
            **metrics,
        }
    return out


def bootstrap_aggregate(
    rows: Sequence[Any],
    *,
    n_resamples: int = 1000,
    ci: float = 0.95,
    stratify_by: tuple[str, ...] = ("category", "route", "router_strategy"),
    seed: int = 42,
) -> dict[str, Any]:
    """Top-level entry point used by ``analysis.all.run_pipeline``.

    Returns a JSON-serializable dict with a ``schema_version`` header
    plus the per-cell payload.
    """
    cells = bootstrap_cells_for_rows(
        rows,
        n_resamples=n_resamples,
        ci=ci,
        stratify_by=stratify_by,
        seed=seed,
    )
    return {
        "schema_version": "1.0",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "n_resamples": n_resamples,
        "ci": ci,
        "stratify_by": list(stratify_by),
        "rng_seed": seed,
        "cells": cells,
    }
