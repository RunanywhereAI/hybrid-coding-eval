"""Per-cell bootstrap confidence intervals for sweep aggregates.

Attaches 95% CIs to every ``(category, route, router_strategy)`` cell
(or whatever ``stratify_by`` you ask for). Multi-seed runs
(``./bench sweep --seeds 42,7,13``) provide the resample base.

Math is deliberately simple — non-parametric bootstrap with percentile
bounds. For each cell we resample with replacement ``n_resamples`` times,
recompute the statistic on each resample, and take the ``(1-ci)/2`` and
``(1+ci)/2`` quantiles of the resample distribution.

Statistics computed per cell:

* ``pass_rate`` — fraction of rows with ``quality.functional_pass == True``
  (rows where it's ``None`` are excluded).
* ``cost_usd`` — median per-row cost under the named pricing scenario,
  computed on the fly via :func:`analysis.cost_scenarios.compute_row_cost`.
  Cost is NEVER stored on the row, so this is the only correct way to
  bootstrap it.
* ``cloud_fraction`` — Σ cloud tokens / Σ all tokens across the cell's
  rows. Token-based (the canonical definition cited in every release
  note). Falls back to ``None`` when no token data is present.
* ``wall_ms`` — median wall-clock ms per row.

Output written to ``bootstrap_cis.json``::

    {
      "schema_version": "2.0",
      "generated_at": "...",
      "n_resamples": 1000,
      "ci": 0.95,
      "scenario": "openai-gpt5.5",
      "stratify_by": ["category", "route", "router_strategy"],
      "cells": {
        "<key>": {
          "n_rows": 12, "n_seeds": 3,
          "pass_rate":      {"point": ..., "ci_lower": ..., "ci_upper": ...},
          "cost_usd":       {"point": ..., "ci_lower": ..., "ci_upper": ...},
          "cloud_fraction": {"point": ..., "ci_lower": ..., "ci_upper": ...},
          "wall_ms":        {"point": ..., "ci_lower": ..., "ci_upper": ...}
        }
      }
    }

``<key>`` is ``"::"``-joined values of the stratify fields. With the
default ``stratify_by`` it's ``"<category>::<route>::<strategy>"`` —
e.g. ``"refactors::cline::cascade"``.
"""

from __future__ import annotations

import datetime as _dt
import random
from collections.abc import Sequence
from functools import partial
from typing import Any

from hybrid_coding_eval.analysis.cost_scenarios import compute_row_cost

__all__ = ["bootstrap_aggregate", "bootstrap_cells_for_rows", "cell_key"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


_DEFAULT_STRATIFY: tuple[str, ...] = ("category", "route", "router_strategy")


def cell_key(row: Any, stratify_by: Sequence[str] = _DEFAULT_STRATIFY) -> str:
    """Stable key for a row under ``stratify_by``.

    Each field is fetched with :func:`getattr`; ``None`` becomes
    ``"none"`` so the keys remain JSON-safe.
    """
    parts: list[str] = []
    for field in stratify_by:
        val = getattr(row, field, None)
        parts.append("none" if val is None else str(val))
    return "::".join(parts)


def _row_seed(row: Any) -> int | None:
    """Extract the seed off a row in a defensive way."""
    seeds = getattr(row, "seeds", None) or getattr(row, "seed", None)
    if isinstance(seeds, list) and seeds:
        return int(seeds[0])
    if isinstance(seeds, int):
        return int(seeds)
    return None


def _pass_rate(rows: Sequence[Any]) -> float | None:
    """Fraction of rows with ``functional_pass == True``, ignoring None."""
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


def _cost_median(rows: Sequence[Any], scenario: str) -> float | None:
    """Median per-row cost in USD under ``scenario``."""
    return _median([compute_row_cost(r, scenario) for r in rows])


def _wall_median(rows: Sequence[Any]) -> float | None:
    return _median([float(getattr(r.latency, "wall_ms", 0) or 0) for r in rows])


def _cloud_fraction_tokens(rows: Sequence[Any]) -> float | None:
    """Cloud_tokens / all_tokens summed across the cell.

    This is the canonical definition used in every release-notes
    headline. Rows with zero tokens (e.g. error rows) contribute nothing.
    """
    cloud = 0
    total = 0
    for r in rows:
        tokens = getattr(r, "tokens", None)
        if tokens is None:
            continue
        cp = int(getattr(tokens, "cloud_prompt", 0) or 0)
        cc = int(getattr(tokens, "cloud_completion", 0) or 0)
        lp = int(getattr(tokens, "local_prompt", 0) or 0)
        lc = int(getattr(tokens, "local_completion", 0) or 0)
        cloud += cp + cc
        total += cp + cc + lp + lc
    if total <= 0:
        return None
    return cloud / total


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interp percentile (matches ``numpy.percentile`` default)."""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #


def _build_metric_map(scenario: str) -> dict[str, Any]:
    """Statistic functions used inside the bootstrap loop."""
    return {
        "pass_rate": _pass_rate,
        "cost_usd": partial(_cost_median, scenario=scenario),
        "cloud_fraction": _cloud_fraction_tokens,
        "wall_ms": _wall_median,
    }


def _bootstrap_one(
    rows: Sequence[Any],
    *,
    metrics: dict[str, Any],
    n_resamples: int,
    ci: float,
    rng: random.Random,
) -> dict[str, dict[str, float | None]]:
    """Resample ``rows`` ``n_resamples`` times; return per-metric CIs."""
    if not rows:
        return {m: {"point": None, "ci_lower": None, "ci_upper": None} for m in metrics}

    point_estimates = {m: fn(rows) for m, fn in metrics.items()}

    resample_dists: dict[str, list[float]] = {m: [] for m in metrics}
    n = len(rows)
    for _ in range(n_resamples):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        for m, fn in metrics.items():
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
    stratify_by: Sequence[str] = _DEFAULT_STRATIFY,
    scenario: str = "openai-gpt5.5",
    seed: int = 42,
) -> dict[str, Any]:
    """Group ``rows`` by ``stratify_by`` and compute per-cell bootstrap CIs.

    Returns the JSON-serialisable dict that downstream callers write to
    ``bootstrap_cis.json``.
    """
    rng = random.Random(seed)
    metrics_fns = _build_metric_map(scenario)

    cells: dict[str, list[Any]] = {}
    for r in rows:
        # Skip error rows (no clean signal).
        if getattr(r, "error", None):
            continue
        key = cell_key(r, stratify_by)
        cells.setdefault(key, []).append(r)

    cells_out: dict[str, dict[str, Any]] = {}
    for key, cell_rows in cells.items():
        seeds = sorted({s for s in (_row_seed(r) for r in cell_rows) if s is not None})
        bootstrap = _bootstrap_one(
            cell_rows,
            metrics=metrics_fns,
            n_resamples=n_resamples,
            ci=ci,
            rng=rng,
        )
        cells_out[key] = {
            "n_rows": len(cell_rows),
            "n_seeds": len(seeds),
            "seeds": seeds,
            **bootstrap,
        }
    return {
        "schema_version": "2.0",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "n_resamples": n_resamples,
        "ci": ci,
        "scenario": scenario,
        "stratify_by": list(stratify_by),
        "rng_seed": seed,
        "cells": cells_out,
    }


def bootstrap_aggregate(
    rows: Sequence[Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Back-compat alias for :func:`bootstrap_cells_for_rows`."""
    return bootstrap_cells_for_rows(rows, **kwargs)
