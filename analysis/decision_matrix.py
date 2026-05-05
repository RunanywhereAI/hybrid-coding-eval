"""Render the category × route decision matrix as Markdown.

One artefact feeds the REPORT.md's headline section. For each
(category, route) cell we show:

  * Quality — median + mean of the composite (or functional_pass rate
    when composite is unavailable).
  * Cost — median + total USD across the tasks in the cell, per the
    default pricing scenario.
  * Wall time — median wall_ms.
  * ARQGC — area-under quality-cost curve (per-category).

The "Recommended route" column picks the route with the highest
ARQGC score per category — i.e. the best quality-per-dollar inside
the shared cost budget.

CLI::

    python -m analysis.decision_matrix results/full-sweep/aggregate.json \\
        --arqgc results/full-sweep/arqgc.json \\
        --out results/full-sweep/decision_matrix.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo-root path dance so running as ``python -m analysis.decision_matrix`` works.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.arqgc import bounded_arqgc  # noqa: E402
from analysis.cost_scenarios import PRICING_SCENARIOS  # noqa: E402
from lib.pricing import fmt_usd  # noqa: E402
from lib.results import load_results  # noqa: E402

__all__ = ["build_decision_matrix"]


def _fmt_num(v, pct: bool = False, digits: int = 2) -> str:
    """Short human-readable formatter for cell values. None → em-dash."""
    if v is None:
        return "—"
    if isinstance(v, float) and (v != v):  # NaN
        return "—"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v:.{digits}f}"


def _fmt_ms(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and (v != v):
        return "—"
    return f"{int(round(float(v))):,} ms"


def _best_route_per_category(
    categories: list[str],
    routes: list[str],
    arqgc_per_cat_route: dict[str, float],
) -> dict[str, str]:
    """Return ``{category: best_route_id}`` by ARQGC. Ties broken by route order."""
    best: dict[str, str] = {}
    for cat in categories:
        candidates = [
            (route, arqgc_per_cat_route.get(f"{cat}/{route}"))
            for route in routes
        ]
        # Drop cells we don't have data for.
        scored = [(r, s) for r, s in candidates if s is not None]
        if not scored:
            continue
        # Stable: highest score first, tie-break by route id.
        scored.sort(key=lambda rs: (-rs[1], rs[0]))
        best[cat] = scored[0][0]
    return best


def build_decision_matrix(
    aggregate_json: dict,
    arqgc: dict,
    output_md: Path | str,
    default_scenario: str = "openai-gpt5.5",
    extra_scenarios: list[str] | None = None,
) -> None:
    """Write ``output_md`` with the decision-matrix Markdown.

    Parameters
    ----------
    aggregate_json
        Dict as produced by :func:`analysis.aggregate.aggregate_results`.
    arqgc
        Dict as produced by :func:`analysis.arqgc.bounded_arqgc`.
    output_md
        Path to write the Markdown file.
    default_scenario
        Which pricing scenario drives the Cost column.
    extra_scenarios
        Additional scenarios to show in the "Alternative pricing" table.
        Defaults to all :data:`PRICING_SCENARIOS` except the default.
    """
    per_cat_route: dict = aggregate_json.get("per_category_route", {})
    arqgc_cells: dict = arqgc.get("per_category_route", {})
    arqgc_routes: dict = arqgc.get("per_route", {})
    cost_cap: float = float(arqgc.get("cost_cap") or 0.0)

    categories = sorted({k.split("/")[0] for k in per_cat_route.keys()})
    routes = sorted({k.split("/")[1] for k in per_cat_route.keys()})

    if extra_scenarios is None:
        extra_scenarios = [s for s in PRICING_SCENARIOS if s != default_scenario]

    cost_col = f"cost_{default_scenario}"
    cost_median_key = f"{cost_col}_median"
    cost_total_key = f"{cost_col}_total"

    lines: list[str] = []
    lines.append("# Decision matrix — category × route")
    lines.append("")
    lines.append(
        f"_Generated from `{aggregate_json.get('source', '?')}` — "
        f"{aggregate_json.get('row_count', 0)} rows, default pricing: "
        f"**{default_scenario}**._"
    )
    lines.append("")
    if cost_cap > 0:
        lines.append(
            f"_Bounded-ARQGC cost cap: **{fmt_usd(cost_cap)}** (p90 of R1's "
            f"per-task cost × task count)._"
        )
        lines.append("")

    # ------------------------------------------------------------------ #
    # Headline table.
    # ------------------------------------------------------------------ #

    header = ["Category", *[f"{r} quality" for r in routes], *[f"{r} cost" for r in routes], *[f"{r} wall" for r in routes]]
    lines.append("## Quality × cost × wall time")
    lines.append("")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    for cat in categories:
        row_cells: list[str] = [cat]
        # Quality columns.
        for route in routes:
            cell = per_cat_route.get(f"{cat}/{route}", {})
            q = cell.get("quality_median")
            qm = cell.get("quality_mean")
            row_cells.append(f"{_fmt_num(q)} (μ {_fmt_num(qm)})")
        # Cost columns.
        for route in routes:
            cell = per_cat_route.get(f"{cat}/{route}", {})
            cm = cell.get(cost_median_key)
            ct = cell.get(cost_total_key)
            if cm is None and ct is None:
                row_cells.append("—")
            else:
                row_cells.append(
                    f"{fmt_usd(cm) if cm is not None else '—'} "
                    f"(Σ {fmt_usd(ct) if ct is not None else '—'})"
                )
        # Wall columns.
        for route in routes:
            cell = per_cat_route.get(f"{cat}/{route}", {})
            row_cells.append(_fmt_ms(cell.get("wall_ms_median")))
        lines.append("| " + " | ".join(row_cells) + " |")

    lines.append("")

    # ------------------------------------------------------------------ #
    # ARQGC + recommendation.
    # ------------------------------------------------------------------ #

    lines.append("## Bounded-ARQGC — area under quality-cost curve")
    lines.append("")
    lines.append("| Category | " + " | ".join(routes) + " | Recommended |")
    lines.append("|" + "|".join(["---"] * (len(routes) + 2)) + "|")

    best_route = _best_route_per_category(categories, routes, arqgc_cells)
    for cat in categories:
        cells = [_fmt_num(arqgc_cells.get(f"{cat}/{route}"), digits=3) for route in routes]
        lines.append("| " + " | ".join([cat, *cells, best_route.get(cat, "—")]) + " |")
    # Overall row.
    overall_cells = [_fmt_num(arqgc_routes.get(route), digits=3) for route in routes]
    lines.append("| **all** | " + " | ".join(overall_cells) + " | — |")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Alt-scenario cost table.
    # ------------------------------------------------------------------ #

    if extra_scenarios:
        lines.append("## Alternative pricing scenarios — median cost per task")
        lines.append("")
        head = ["Category/Route", default_scenario, *extra_scenarios]
        lines.append("| " + " | ".join(head) + " |")
        lines.append("|" + "|".join(["---"] * len(head)) + "|")
        for cat in categories:
            for route in routes:
                cell = per_cat_route.get(f"{cat}/{route}", {})
                costs = [cell.get(f"cost_{s}_median") for s in [default_scenario, *extra_scenarios]]
                row = [f"{cat}/{route}"] + [
                    fmt_usd(c) if c is not None else "—" for c in costs
                ]
                lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    # ------------------------------------------------------------------ #
    # Prose interpretation.
    # ------------------------------------------------------------------ #

    lines.append("## Interpretation")
    lines.append("")
    if best_route:
        by_route: dict[str, list[str]] = {}
        for cat, route in best_route.items():
            by_route.setdefault(route, []).append(cat)
        for route, cats in sorted(by_route.items()):
            cat_list = ", ".join(sorted(cats))
            lines.append(
                f"- **{route}** wins on categories {cat_list} "
                f"(highest ARQGC under the {fmt_usd(cost_cap)} budget)."
            )
    else:
        lines.append("- Not enough data to pick per-category winners yet.")

    # Totals.
    totals = aggregate_json.get("totals", {}).get("per_route", {})
    if totals:
        lines.append("")
        lines.append("### Token totals per route (across all tasks)")
        lines.append("")
        lines.append("| Route | Cloud prompt | Cloud completion | Local prompt | Local completion |")
        lines.append("|---|---:|---:|---:|---:|")
        for route in sorted(totals.keys()):
            t = totals[route]
            lines.append(
                f"| {route} | "
                f"{t.get('tokens_cloud_prompt_total', 0):,} | "
                f"{t.get('tokens_cloud_completion_total', 0):,} | "
                f"{t.get('tokens_local_prompt_total', 0):,} | "
                f"{t.get('tokens_local_completion_total', 0):,} |"
            )

    lines.append("")
    op = Path(output_md)
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text("\n".join(lines))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="analysis.decision_matrix",
        description="Render category×route decision matrix as Markdown.",
    )
    p.add_argument("aggregate_json", type=Path, help="Path to aggregate.json")
    p.add_argument(
        "--arqgc",
        type=Path,
        default=None,
        help="Path to arqgc.json. If missing, recomputed from raw.jsonl "
        "sibling of aggregate_json.",
    )
    p.add_argument(
        "--raw",
        type=Path,
        default=None,
        help="Path to raw.jsonl (used when --arqgc is not supplied).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path. Default: sibling decision_matrix.md.",
    )
    p.add_argument(
        "--scenario",
        type=str,
        default="openai-gpt5.5",
        help="Default pricing scenario (drives the Cost column).",
    )
    args = p.parse_args(argv)

    agg = json.loads(args.aggregate_json.read_text())
    if args.arqgc is not None and args.arqgc.exists():
        arqgc = json.loads(args.arqgc.read_text())
    else:
        raw = args.raw or (args.aggregate_json.parent / "raw.jsonl")
        rows = load_results(raw)
        arqgc = bounded_arqgc(rows, scenario=args.scenario)

    out_path = args.out or (args.aggregate_json.parent / "decision_matrix.md")
    build_decision_matrix(agg, arqgc, out_path, default_scenario=args.scenario)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
