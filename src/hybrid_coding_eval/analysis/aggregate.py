"""Aggregate a ``raw.jsonl`` sweep into a single JSON artefact.

The aggregate JSON is the root document everything downstream reads:

  * ``analysis.bootstrap`` — needs per-row cost + quality (CI inputs).
  * ``analysis.decision_matrix`` — needs per-(category, route) medians.
  * ``viz.*`` — need headline tiles + totals.

Design notes:

  * Cost is *derived* per scenario — we compute ``cost_<scenario>``
    columns for every scenario in ``PRICING_SCENARIOS`` so downstream
    consumers can pick any of them without re-reading rows.
  * Medians are the primary central tendency; means are stored too for
    completeness but downstream code should prefer medians (robust to
    the occasional 60-second timeout).
  * NaN-safe: pandas' default ``skipna=True`` means rows whose quality
    is all-None (category C in practice) don't poison the aggregate.

CLI::

    python -m analysis.aggregate results/full-sweep/raw.jsonl \\
        --out results/full-sweep/aggregate.json \\
        --scenarios openai-gpt5.5,openai-gpt5-mini
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

# Make ``lib`` / ``analysis`` importable when run as a script.
_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / "pyproject.toml").is_file():
        _REPO_ROOT = _p
        break
else:  # pragma: no cover
    _REPO_ROOT = _here.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_coding_eval.analysis.cost_scenarios import (  # noqa: E402
    PRICING_SCENARIOS,
    compute_row_cost,
)
from hybrid_coding_eval.core.metrics import ResultRow  # noqa: E402
from hybrid_coding_eval.core.results import load_results  # noqa: E402

__all__ = [
    "aggregate_results",
    "rows_to_frame",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _json_safe(v):
    """JSON-ready scalar — convert NaN to ``None`` and numpy → python.

    pandas gives us ``float('nan')`` for empty groups; ``json.dumps``
    emits ``NaN`` by default which isn't valid JSON. Convert those to
    ``None`` up-front so the output is parseable by strict consumers.
    """
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    # numpy scalar types carry ``.item()`` which returns a Python native.
    try:
        return v.item()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    if isinstance(v, (int, str, bool)):
        return v
    return str(v)


def _composite_from_row(r: ResultRow) -> float:
    """Extract a scalar quality value for aggregation.

    Priority:
      1. ``quality.composite`` if set.
      2. ``quality.functional_pass`` cast to 0/1 if set.
      3. NaN.

    Rationale: functional-pass rows (HumanEval+, BigCodeBench-Hard)
    don't always populate ``composite`` but they still have a boolean
    pass/fail. Treating those as 0/1 keeps them in the quality signal.
    """
    if r.quality.composite is not None:
        return float(r.quality.composite)
    if r.quality.functional_pass is not None:
        return 1.0 if r.quality.functional_pass else 0.0
    return float("nan")


def rows_to_frame(
    rows: Iterable[ResultRow],
    scenarios: list[str] | None = None,
) -> pd.DataFrame:
    """Flatten rows into a per-row DataFrame with cost-per-scenario cols.

    Public so callers (tests, downstream scripts) can reuse the flat
    representation without repeating the scenario loop.
    """
    if scenarios is None:
        scenarios = PRICING_SCENARIOS

    records: list[dict] = []
    for r in rows:
        rec: dict = {
            "task_id": r.task_id,
            "category": r.category,
            "route": r.route,
            "prompt_tokens": int(r.tokens.prompt or 0),
            "completion_tokens": int(r.tokens.completion or 0),
            "cloud_prompt_tokens": int(r.tokens.cloud_prompt or 0),
            "cloud_completion_tokens": int(r.tokens.cloud_completion or 0),
            "local_prompt_tokens": int(r.tokens.local_prompt or 0),
            "local_completion_tokens": int(r.tokens.local_completion or 0),
            "wall_ms": int(r.latency.wall_ms or 0),
            "total_calls": int(r.routing.total_calls or 0),
            "local_calls": int(r.routing.local_calls or 0),
            "cloud_calls": int(r.routing.cloud_calls or 0),
            "quality": _composite_from_row(r),
            "functional_pass": r.quality.functional_pass,
            "error": r.error,
        }
        for s in scenarios:
            rec[f"cost_{s}"] = compute_row_cost(r, s)
        records.append(rec)

    return pd.DataFrame.from_records(records)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def _success_rate(series: pd.Series) -> float:
    """Fraction of non-None values that are truthy. All-None → NaN."""
    mask = series.notna()
    vals = series[mask]
    if len(vals) == 0:
        return float("nan")
    return float(vals.astype(bool).sum()) / float(len(vals))


def _per_cat_route_cell(
    sub: pd.DataFrame,
    scenarios: list[str],
) -> dict:
    """Stats for one (category, route) cell."""
    cell = {
        "count": int(len(sub)),
        "prompt_tokens_median": _json_safe(sub["prompt_tokens"].median()),
        "prompt_tokens_mean": _json_safe(sub["prompt_tokens"].mean()),
        "completion_tokens_median": _json_safe(sub["completion_tokens"].median()),
        "completion_tokens_mean": _json_safe(sub["completion_tokens"].mean()),
        "cloud_prompt_tokens_sum": int(sub["cloud_prompt_tokens"].sum()),
        "cloud_completion_tokens_sum": int(sub["cloud_completion_tokens"].sum()),
        "local_prompt_tokens_sum": int(sub["local_prompt_tokens"].sum()),
        "local_completion_tokens_sum": int(sub["local_completion_tokens"].sum()),
        "wall_ms_median": _json_safe(sub["wall_ms"].median()),
        "wall_ms_mean": _json_safe(sub["wall_ms"].mean()),
        "total_calls_median": _json_safe(sub["total_calls"].median()),
        "local_calls_median": _json_safe(sub["local_calls"].median()),
        "cloud_calls_median": _json_safe(sub["cloud_calls"].median()),
        "quality_median": _json_safe(sub["quality"].median()),
        "quality_mean": _json_safe(sub["quality"].mean()),
        "functional_pass_rate": _json_safe(_success_rate(sub["functional_pass"])),
        "error_rate": _json_safe(
            float(sub["error"].notna().sum()) / float(len(sub))
        ) if len(sub) else None,
    }
    for s in scenarios:
        col = f"cost_{s}"
        cell[f"cost_{s}_median"] = _json_safe(sub[col].median())
        cell[f"cost_{s}_mean"] = _json_safe(sub[col].mean())
        cell[f"cost_{s}_total"] = _json_safe(sub[col].sum())
    return cell


def aggregate_results(
    raw_jsonl: Path | str,
    output_json: Path | str | None = None,
    pricing_scenarios: list[str] | None = None,
) -> dict:
    """Load ``raw_jsonl``, compute aggregate, optionally write JSON.

    Returns the aggregate dict regardless of whether ``output_json``
    was provided.

    Handles the partial-sweep case by simply processing whatever rows
    exist — never crashes on missing cells.
    """
    if pricing_scenarios is None:
        pricing_scenarios = PRICING_SCENARIOS

    raw_path = Path(raw_jsonl)
    rows = load_results(raw_path)
    df = rows_to_frame(rows, pricing_scenarios)

    out: dict = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source": str(raw_path),
        "pricing_scenarios": list(pricing_scenarios),
        "row_count": int(len(rows)),
        "per_category_route": {},
        "per_route": {},
        "per_category": {},
        "headline": {
            "quality": {},
            "wall_ms_median": {},
        },
        "totals": {
            "tokens_cloud_prompt_total": 0,
            "tokens_cloud_completion_total": 0,
            "tokens_local_prompt_total": 0,
            "tokens_local_completion_total": 0,
        },
        "success_rate_per_route_per_category": {},
    }
    for s in pricing_scenarios:
        out["headline"][f"cost_{s}"] = {}

    if df.empty:
        # Still write the skeleton so downstream doesn't have to branch.
        if output_json is not None:
            op = Path(output_json)
            op.parent.mkdir(parents=True, exist_ok=True)
            op.write_text(json.dumps(out, indent=2))
        return out

    # Totals across all rows.
    out["totals"] = {
        "tokens_cloud_prompt_total": int(df["cloud_prompt_tokens"].sum()),
        "tokens_cloud_completion_total": int(df["cloud_completion_tokens"].sum()),
        "tokens_local_prompt_total": int(df["local_prompt_tokens"].sum()),
        "tokens_local_completion_total": int(df["local_completion_tokens"].sum()),
    }
    # Also break totals down per agent (useful for "cline uses X% of tokens locally").
    totals_per_route: dict = {}
    for route, sub in df.groupby("route", dropna=False, sort=True):
        totals_per_route[str(route)] = {
            "tokens_cloud_prompt_total": int(sub["cloud_prompt_tokens"].sum()),
            "tokens_cloud_completion_total": int(sub["cloud_completion_tokens"].sum()),
            "tokens_local_prompt_total": int(sub["local_prompt_tokens"].sum()),
            "tokens_local_completion_total": int(sub["local_completion_tokens"].sum()),
        }
        for s in pricing_scenarios:
            totals_per_route[str(route)][f"cost_{s}_total"] = _json_safe(
                sub[f"cost_{s}"].sum()
            )
    out["totals"]["per_route"] = totals_per_route

    # Per (category, route) cell.
    for (cat, route), sub in df.groupby(["category", "route"], dropna=False, sort=True):
        key = f"{cat}/{route}"
        out["per_category_route"][key] = _per_cat_route_cell(sub, pricing_scenarios)

        flat = f"{cat}_{route}"
        out["headline"]["quality"][flat] = out["per_category_route"][key]["quality_median"]
        out["headline"]["wall_ms_median"][flat] = out["per_category_route"][key]["wall_ms_median"]
        for s in pricing_scenarios:
            out["headline"][f"cost_{s}"][flat] = out["per_category_route"][key][f"cost_{s}_median"]

        out["success_rate_per_route_per_category"].setdefault(str(cat), {})[str(route)] = _json_safe(
            _success_rate(sub["functional_pass"])
        )

    # Per route (ignoring category).
    for route, sub in df.groupby("route", dropna=False, sort=True):
        out["per_route"][str(route)] = _per_cat_route_cell(sub, pricing_scenarios)

    # Per category (ignoring route).
    for cat, sub in df.groupby("category", dropna=False, sort=True):
        out["per_category"][str(cat)] = _per_cat_route_cell(sub, pricing_scenarios)

    if output_json is not None:
        op = Path(output_json)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(out, indent=2))

    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _parse_scenarios(s: str | None) -> list[str] | None:
    if not s:
        return None
    return [p.strip() for p in s.split(",") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="analysis.aggregate",
        description="Aggregate a raw.jsonl sweep into aggregate.json.",
    )
    p.add_argument("raw_jsonl", type=Path, help="Path to raw.jsonl")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path. Default: sibling aggregate.json next to raw_jsonl.",
    )
    p.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="Comma-separated scenario names (default: all five).",
    )
    args = p.parse_args(argv)

    out_path = args.out or (args.raw_jsonl.parent / "aggregate.json")
    scenarios = _parse_scenarios(args.scenarios)
    agg = aggregate_results(args.raw_jsonl, out_path, scenarios)

    print(
        f"aggregated {agg['row_count']} rows → {out_path} "
        f"({len(agg['per_category_route'])} category/route cells)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
