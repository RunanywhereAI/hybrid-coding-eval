"""T-17: decision matrix with Wilson 95% CIs, one grid per pricing scenario.

Inputs
------
- ``results/raw.jsonl`` — the merged dataset (180 historical + Wave 2 rows).
- ``configs/pricing/pricing_tables.json`` — via ``core.pricing``.
- ``PRICING_SCENARIOS`` from ``analysis.cost_scenarios`` (six scenarios by
  default).

Outputs
-------
- ``results/reprice/decision_matrix.md`` — one 3×4 grid (category × route)
  per scenario. Cells show pass-rate ± 95% Wilson CI, median tokens routed
  cloud/local, median cost under that scenario, median wall.
- ``results/reprice/decision_matrix.json`` — the same numbers as a single
  JSON blob for programmatic consumers (APPENDIX_SCENARIOS, charts).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from hybrid_coding_eval.analysis.cost_scenarios import (
    PRICING_SCENARIOS,
    compute_row_cost,
)
from hybrid_coding_eval.core.metrics import ResultRow
from hybrid_coding_eval.core.paths import repo_root
from hybrid_coding_eval.core.results import load_results

# --------------------------------------------------------------------------- #
# Wilson score interval for a proportion — ``k`` hits out of ``n`` trials.
# --------------------------------------------------------------------------- #


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Return ``(point, lo, hi)`` for a binomial proportion with Wilson 95% CI.

    With N=10 the normal approximation is too optimistic; Wilson gives a
    bounded, asymmetric interval that's honest at small N.
    """
    if n <= 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return (p, lo, hi)


# --------------------------------------------------------------------------- #
# Grid construction
# --------------------------------------------------------------------------- #


def _is_pass(row: ResultRow) -> bool | None:
    q = row.quality
    if q.functional_pass is True:
        return True
    if q.functional_pass is False:
        return False
    # For custom_arch rows, functional_pass is None but composite is set
    # by the judge — treat composite >= 0.5 as pass.
    if q.composite is not None:
        return q.composite >= 0.5
    return None


def _row_cloud_tokens(row: ResultRow) -> int:
    t = row.tokens
    v = int(t.cloud_prompt or 0) + int(t.cloud_completion or 0)
    if v == 0 and not int(t.local_prompt or 0) and not int(t.local_completion or 0):
        # R1 rows never populated the split — treat full total as cloud.
        v = int(t.prompt or 0) + int(t.completion or 0)
    return v


def _row_local_tokens(row: ResultRow) -> int:
    t = row.tokens
    return int(t.local_prompt or 0) + int(t.local_completion or 0)


def build_matrix(
    rows: Iterable[ResultRow],
    scenarios: list[str] | None = None,
) -> dict[str, Any]:
    """Return nested dict ``{scenario: {category: {route: cell}}}`` + index."""
    rows = list(rows)
    scenarios = scenarios or PRICING_SCENARIOS

    # Group by (scenario, category, route, variant). When the same
    # (task_id, route) appears in multiple variants, we keep them as
    # separate rows so CI counts are honest.
    matrix: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict))
    )

    for scen in scenarios:
        # Aggregate per (category, route) across all rows — one CI per
        # grid cell.
        grouped: dict[tuple[str, str], list[ResultRow]] = defaultdict(list)
        for r in rows:
            grouped[(r.category, r.route)].append(r)

        for (cat, route), rs in grouped.items():
            passes = [_is_pass(r) for r in rs]
            n = sum(1 for v in passes if v is not None)
            k = sum(1 for v in passes if v is True)
            point, lo, hi = wilson_ci(k, n)

            cloud_toks = [_row_cloud_tokens(r) for r in rs if not r.error]
            local_toks = [_row_local_tokens(r) for r in rs if not r.error]
            walls = [r.latency.wall_ms for r in rs if not r.error and r.latency.wall_ms]
            costs = [compute_row_cost(r, scen) for r in rs if not r.error]

            matrix[scen][cat][route] = {
                "n": n,
                "k": k,
                "pass_rate": point,
                "ci_low": lo,
                "ci_high": hi,
                "median_cloud_tokens": int(statistics.median(cloud_toks)) if cloud_toks else 0,
                "median_local_tokens": int(statistics.median(local_toks)) if local_toks else 0,
                "median_wall_ms": int(statistics.median(walls)) if walls else 0,
                "median_cost_usd": float(statistics.median(costs)) if costs else 0.0,
                "variants": sorted({r.variant for r in rs if r.variant}),
            }

    return {
        "scenarios": scenarios,
        "matrix": matrix,
    }


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #


def _render_md(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Multi-scenario decision matrix (T-17)")
    lines.append("")
    lines.append(
        "One 3 × 4 grid per pricing scenario. Cells carry:"
    )
    lines.append("")
    lines.append(
        "- **pass rate** — Wilson 95% CI; ``k/n`` where ``n`` is rows scored "
        "and ``k`` is passes."
    )
    lines.append("- **cloud / local tokens** — median per row in this cell.")
    lines.append("- **wall** — median wall-clock per row.")
    lines.append("- **cost** — median USD per row under the scenario's rates.")
    lines.append("")

    categories = ["A", "B", "C"]
    routes = ["R1", "R2", "R3", "R4"]

    for scen, grid in data["matrix"].items():
        lines.append(f"## Scenario: `{scen}`")
        lines.append("")
        lines.append(
            "| cat | route | pass rate (95% CI) | cloud tok | local tok | wall | $ cost |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for cat in categories:
            for route in routes:
                cell = grid.get(cat, {}).get(route)
                if not cell or not cell["n"]:
                    lines.append(f"| {cat} | {route} | _n=0_ | — | — | — | — |")
                    continue
                lines.append(
                    f"| {cat} | {route} | "
                    f"**{cell['pass_rate']:.2f}** "
                    f"({cell['ci_low']:.2f}–{cell['ci_high']:.2f}) "
                    f"*n={cell['n']}, k={cell['k']}* | "
                    f"{cell['median_cloud_tokens']:,} | "
                    f"{cell['median_local_tokens']:,} | "
                    f"{cell['median_wall_ms']:,} ms | "
                    f"${cell['median_cost_usd']:.4f} |"
                )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Generated by ``bench analyze decision-matrix``. Cost is *derived* "
        "from tokens via configs/pricing/pricing_tables.json; never stored._"
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="decision_matrix_v2")
    parser.add_argument("--raw", type=Path, default=None)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: ``results/reprice/``.",
    )
    args = parser.parse_args(argv or sys.argv[1:])

    root = repo_root()
    out_dir = args.out_dir or (root / "results" / "reprice")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.raw:
        rows = load_results(args.raw)
    else:
        # MVP's ``results/raw.jsonl`` is the concatenation of run dirs
        # 01–04, so merging them in again would double-count. Pull in
        # only post-MVP run dirs (05+) alongside the merged MVP set.
        rows = list(load_results(root / "results" / "raw.jsonl"))
        for run_dir in sorted((root / "results" / "runs").glob("*")):
            if not run_dir.is_dir():
                continue
            if run_dir.name.startswith(("01-", "02-", "03-", "04-")):
                continue  # part of MVP raw.jsonl already
            raw = run_dir / "raw.jsonl"
            if raw.is_file():
                rows.extend(load_results(raw))

    data = build_matrix(rows)

    md_path = out_dir / "decision_matrix.md"
    md_path.write_text(_render_md(data), encoding="utf-8")

    json_path = out_dir / "decision_matrix.json"
    json_path.write_text(
        json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
