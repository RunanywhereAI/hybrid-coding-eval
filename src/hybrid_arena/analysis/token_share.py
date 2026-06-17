"""T-16: token-economics report — where the dollars went, per route × category.

For each route × category we compute:
 - total cloud tokens (Σ across rows in the cell)
 - total local tokens
 - routing-efficiency ratio: local / (local + cloud)
 - under the primary pricing scenario: dollar share attributable to
   cloud vs local ($0 by construction for local)

Output: ``results/reprice/token_share.md``.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from hybrid_arena.analysis.cost_scenarios import compute_row_cost
from hybrid_arena.core.metrics import ResultRow
from hybrid_arena.core.paths import repo_root
from hybrid_arena.core.results import load_results


def _cloud_tokens(r: ResultRow) -> int:
    t = r.tokens
    v = int(t.cloud_prompt or 0) + int(t.cloud_completion or 0)
    if v == 0 and int(t.local_prompt or 0) == 0 and int(t.local_completion or 0) == 0:
        v = int(t.prompt or 0) + int(t.completion or 0)
    return v


def _local_tokens(r: ResultRow) -> int:
    t = r.tokens
    return int(t.local_prompt or 0) + int(t.local_completion or 0)


def _collect_all(root: Path) -> list[ResultRow]:
    # MVP raw.jsonl = concatenation of runs 01–04. Avoid double-counting
    # by only pulling in the new (post-MVP) run dirs on top of MVP.
    rows: list[ResultRow] = []
    rows.extend(load_results(root / "results" / "raw.jsonl"))
    for run_dir in sorted((root / "results" / "runs").glob("*")):
        if not run_dir.is_dir():
            continue
        if run_dir.name.startswith(("01-", "02-", "03-", "04-")):
            continue
        raw = run_dir / "raw.jsonl"
        if raw.is_file():
            rows.extend(load_results(raw))
    return rows


def _render(rows: list[ResultRow], scenario: str = "openai-gpt5.5") -> str:
    # Bucket by (route, category).
    buckets: dict[tuple[str, str], list[ResultRow]] = defaultdict(list)
    for r in rows:
        buckets[(r.route, r.category)].append(r)

    lines: list[str] = []
    lines.append("# Token-economics split — where the dollars went (T-16)")
    lines.append("")
    lines.append(
        "Totals across **every row** in the committed dataset — both the MVP "
        "180-row sweep (`results/raw.jsonl`) and every post-reorg run under "
        "`results/runs/NN-*/raw.jsonl`."
    )
    lines.append("")
    lines.append(
        f"Dollar columns priced under `{scenario}` using "
        "`configs/pricing/pricing_tables.json`. Local tokens cost **$0** by "
        "construction (laptop electricity / hardware amortisation excluded)."
    )
    lines.append("")
    lines.append(
        "| route | cat | N | Σ cloud tokens | Σ local tokens | routed local | Σ $ cost | $ / row |"
    )
    lines.append(
        "|---|---|---:|---:|---:|---:|---:|---:|"
    )

    route_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0.0])
    # route → [n_rows, total_cloud, total_local, total_cost]

    for (route, cat), rs in sorted(buckets.items()):
        valid = [r for r in rs if not r.error]
        n = len(valid)
        total_cloud = sum(_cloud_tokens(r) for r in valid)
        total_local = sum(_local_tokens(r) for r in valid)
        total_all = total_cloud + total_local
        ratio = (total_local / total_all) if total_all else 0.0
        total_cost = sum(compute_row_cost(r, scenario) for r in valid)
        per_row = (total_cost / n) if n else 0.0
        lines.append(
            f"| **{route}** | {cat} | {n} | {total_cloud:,} | {total_local:,} | "
            f"{ratio:.0%} | ${total_cost:.4f} | ${per_row:.4f} |"
        )
        agg = route_totals[route]
        agg[0] += n
        agg[1] += total_cloud
        agg[2] += total_local
        agg[3] += total_cost

    lines.append("")
    lines.append("### Per-route totals (across all categories)")
    lines.append("")
    lines.append("| route | N | Σ cloud tokens | Σ local tokens | routed local | Σ $ cost |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for route, (n, cloud, local, cost) in sorted(route_totals.items()):
        total_all = cloud + local
        ratio = (local / total_all) if total_all else 0.0
        lines.append(
            f"| **{route}** | {n} | {cloud:,} | {local:,} | "
            f"{ratio:.0%} | ${cost:.4f} |"
        )
    lines.append("")

    lines.append("### What to read from this")
    lines.append("")
    lines.append(
        "- `always-cloud` rows are pure cloud (local = 0). Any nonzero "
        "local on those rows is a routing bug."
    )
    lines.append(
        "- `always-local` rows are pure local (cloud = 0). The dollar "
        "cost column is always $0 — the cost baseline."
    )
    lines.append(
        "- Hybrid strategies (`heuristic`, `cascade`, `phase-aware`, "
        "`llm-classifier`, `embedding-knn`, `rules`) split work between "
        "local and cloud. The *routed local* percentage is the strategy's "
        "ability to offload work onto local hardware — 100 % means every "
        "call went local, 0 % means every call went cloud."
    )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="token_share")
    parser.add_argument("--scenario", default="openai-gpt5.5")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv or sys.argv[1:])

    root = repo_root()
    out = args.out or (root / "results" / "reprice" / "token_share.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = _collect_all(root)
    out.write_text(_render(rows, args.scenario), encoding="utf-8")
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
