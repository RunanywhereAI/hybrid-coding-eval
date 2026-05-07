"""T-15: cross-scenario repricing of the full dataset.

Reads ``results/raw.jsonl`` + all Wave 2 run dirs, writes one cost
column per pricing scenario. No inference; pure derivation from stored
tokens × pinned rates.

Outputs:
 - ``results/reprice/cost_by_scenario.csv`` — (variant, task_id, route,
   source_run) × (cost_<scenario> for every scenario).
 - ``results/reprice/summary.md`` — category × route × scenario means +
   totals.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from hybrid_coding_eval.analysis.cost_scenarios import (
    PRICING_SCENARIOS,
    compute_row_cost,
)
from hybrid_coding_eval.core.metrics import ResultRow
from hybrid_coding_eval.core.paths import repo_root
from hybrid_coding_eval.core.results import load_results


def collect_rows(root: Path) -> list[tuple[ResultRow, str]]:
    """Return ``(row, source_run)`` pairs across the MVP dataset plus
    every POST-MVP ``results/runs/NN-*/raw.jsonl``.

    ``results/raw.jsonl`` is the concatenation of runs 01–04 (the MVP
    preserved set), so merging those in again would double-count. Only
    runs 05+ are added on top.
    """
    out: list[tuple[ResultRow, str]] = []
    mvp = root / "results" / "raw.jsonl"
    for r in load_results(mvp):
        out.append((r, "mvp/raw.jsonl"))
    for run_dir in sorted((root / "results" / "runs").glob("*")):
        if not run_dir.is_dir():
            continue
        if run_dir.name.startswith(("01-", "02-", "03-", "04-")):
            continue  # already in mvp/raw.jsonl
        raw = run_dir / "raw.jsonl"
        if not raw.is_file():
            continue
        for r in load_results(raw):
            out.append((r, f"runs/{run_dir.name}"))
    return out


def _write_csv(pairs: list[tuple[ResultRow, str]], out: Path) -> None:
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["variant", "task_id", "route", "category", "source_run"]
            + [f"cost_{s}" for s in PRICING_SCENARIOS]
            + ["cloud_tokens", "local_tokens"]
        )
        for r, source_run in pairs:
            costs = [f"{compute_row_cost(r, s):.6f}" for s in PRICING_SCENARIOS]
            cloud = int(r.tokens.cloud_prompt or 0) + int(r.tokens.cloud_completion or 0)
            if cloud == 0:
                cloud = int(r.tokens.prompt or 0) + int(r.tokens.completion or 0)
            local = int(r.tokens.local_prompt or 0) + int(r.tokens.local_completion or 0)
            w.writerow(
                [
                    r.variant or "",
                    r.task_id,
                    r.route,
                    r.category,
                    source_run,
                ]
                + costs
                + [cloud, local]
            )


def _render_summary_md(pairs: list[tuple[ResultRow, str]]) -> str:
    # Means per (category, route, scenario).
    buckets: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for r, _ in pairs:
        if r.error:
            continue
        for s in PRICING_SCENARIOS:
            buckets[(r.category, r.route, s)].append(compute_row_cost(r, s))

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    cats = sorted({k[0] for k in buckets})
    routes = sorted({k[1] for k in buckets})

    lines: list[str] = []
    lines.append("# Cross-scenario re-priced summary (T-15)")
    lines.append("")
    lines.append(
        "Mean per-row USD cost under each pricing scenario. Derived from "
        "stored tokens × pinned rates in `configs/pricing/pricing_tables.json`; "
        "no inference re-run."
    )
    lines.append("")

    for s in PRICING_SCENARIOS:
        lines.append(f"## Scenario: `{s}`")
        lines.append("")
        header = "| cat \\ route | " + " | ".join(routes) + " |"
        lines.append(header)
        lines.append("|---|" + ("---:|" * len(routes)))
        for cat in cats:
            row_vals = []
            for route in routes:
                xs = buckets.get((cat, route, s), [])
                row_vals.append(f"${mean(xs):.4f}" if xs else "—")
            lines.append(f"| **{cat}** | " + " | ".join(row_vals) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reprice")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv or sys.argv[1:])

    root = repo_root()
    out_dir = args.out_dir or (root / "results" / "reprice")
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = collect_rows(root)

    csv_path = out_dir / "cost_by_scenario.csv"
    _write_csv(pairs, csv_path)
    print(f"wrote {csv_path} ({len(pairs)} rows × {len(PRICING_SCENARIOS)} scenarios)")

    md_path = out_dir / "summary.md"
    md_path.write_text(_render_summary_md(pairs), encoding="utf-8")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
