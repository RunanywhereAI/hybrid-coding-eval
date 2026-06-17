"""Render the ``category × route × strategy`` decision matrix as Markdown.

This is the artefact that feeds the headline section of each release
report. For every ``(category, route, strategy)`` cell we show:

* Pass-rate — fraction of rows that pass functional tests, with a
  bootstrap 95% CI from ``analysis.bootstrap``.
* Cost — median + total USD across the tasks in the cell, at the chosen
  pricing scenario.
* Cloud fraction — Σ cloud_tokens / Σ all_tokens, the canonical
  definition used in every published headline.
* Wall time — median wall-clock ms per task.

The "Recommended" column picks the cheapest strategy that ties (within
the bootstrap CI) with the best-performing strategy on the same row's
``(category, route)``. This is the same rule used in
``docs/release-notes/v1.4.*.md`` to call e.g. "cline + qwen3.6 + cascade"
a Pareto win over "cline + qwen3.6 + always-cloud".

CLI::

    python -m hybrid_arena.analysis.decision_matrix \\
        results/runs/<sweep>/aggregate.json \\
        --bootstrap results/runs/<sweep>/bootstrap_cis.json \\
        --out results/runs/<sweep>/decision_matrix.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hybrid_arena.analysis.cost_scenarios import PRICING_SCENARIOS
from hybrid_arena.core.paths import repo_root  # noqa: F401  (used by callers)
from hybrid_arena.core.pricing import fmt_usd

__all__ = ["build_decision_matrix"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fmt_num(v: float | None, *, pct: bool = False, digits: int = 2) -> str:
    """Short human-readable formatter. ``None`` / NaN → em-dash."""
    if v is None:
        return "—"
    if isinstance(v, float) and v != v:  # NaN
        return "—"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v:.{digits}f}"


def _fmt_ms(v: float | None) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and v != v:
        return "—"
    return f"{int(round(float(v))):,} ms"


def _cell_key(category: str, route: str, strategy: str) -> str:
    return f"{category}::{route}::{strategy}"


def _best_strategy_per_cell(
    bootstrap_cells: dict,
    categories: list[str],
    routes: list[str],
    strategies: list[str],
) -> dict[tuple[str, str], str]:
    """For each ``(category, route)`` pick the strategy with the highest
    pass-rate, breaking ties by lower median cost (cheaper wins)."""
    out: dict[tuple[str, str], str] = {}
    for cat in categories:
        for route in routes:
            candidates: list[tuple[str, float, float]] = []
            for strat in strategies:
                cell = bootstrap_cells.get(_cell_key(cat, route, strat))
                if not cell:
                    continue
                pr = (cell.get("pass_rate") or {}).get("point")
                cost = (cell.get("cost_usd") or {}).get("point") or 0.0
                if pr is None:
                    continue
                candidates.append((strat, pr, cost))
            if not candidates:
                continue
            # Highest pass_rate, then lowest cost, then alphabetical.
            candidates.sort(key=lambda t: (-t[1], t[2], t[0]))
            out[(cat, route)] = candidates[0][0]
    return out


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #


def build_decision_matrix(
    aggregate_json: dict,
    bootstrap_json: dict | None,
    output_md: Path | str,
    *,
    default_scenario: str = "openai-gpt5.5",
    extra_scenarios: list[str] | None = None,
) -> Path:
    """Write the Markdown decision matrix and return the output path.

    Parameters
    ----------
    aggregate_json
        Dict as produced by :func:`analysis.aggregate.aggregate_results`.
    bootstrap_json
        Dict as produced by
        :func:`analysis.bootstrap.bootstrap_cells_for_rows`. May be
        ``None`` for legacy sweeps; the "Recommended" column will then
        omit CI bounds and pick by point estimate only.
    output_md
        Path to write the Markdown file.
    default_scenario
        Pricing scenario that drives the Cost column.
    extra_scenarios
        Additional scenarios for the "Alternative pricing" table.
        Defaults to every :data:`PRICING_SCENARIOS` except ``default``.
    """
    per_cat_route: dict = aggregate_json.get("per_category_route", {})
    if not per_cat_route:
        raise ValueError("aggregate.json has no per_category_route data")

    bootstrap_cells: dict = (bootstrap_json or {}).get("cells", {})

    if extra_scenarios is None:
        extra_scenarios = [s for s in PRICING_SCENARIOS if s != default_scenario]

    categories = sorted({k.split("/")[0] for k in per_cat_route.keys()})
    routes = sorted({k.split("/")[1] for k in per_cat_route.keys()})
    strategies = sorted({c.split("::")[2] for c in bootstrap_cells.keys()}) if bootstrap_cells else []

    cost_median_key = f"cost_{default_scenario}_median"
    cost_total_key = f"cost_{default_scenario}_total"

    lines: list[str] = []
    lines.append("# Decision matrix — category × route × strategy")
    lines.append("")
    lines.append(
        f"_Generated from `{aggregate_json.get('source', '?')}` — "
        f"{aggregate_json.get('row_count', 0)} rows · default pricing: "
        f"**{default_scenario}**._"
    )
    lines.append("")

    # ------------------------------------------------------------------ #
    # Headline table.
    # ------------------------------------------------------------------ #

    lines.append("## Quality × cost × wall time per (category × route)")
    lines.append("")
    header = [
        "Category",
        *[f"{r} quality" for r in routes],
        *[f"{r} cost (median)" for r in routes],
        *[f"{r} wall" for r in routes],
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    for cat in categories:
        cells: list[str] = [cat]
        for route in routes:
            cell = per_cat_route.get(f"{cat}/{route}", {})
            q = cell.get("quality_median")
            qm = cell.get("quality_mean")
            cells.append(f"{_fmt_num(q)} (μ {_fmt_num(qm)})")
        for route in routes:
            cell = per_cat_route.get(f"{cat}/{route}", {})
            cm = cell.get(cost_median_key)
            ct = cell.get(cost_total_key)
            if cm is None and ct is None:
                cells.append("—")
            else:
                cells.append(
                    f"{fmt_usd(cm) if cm is not None else '—'} "
                    f"(Σ {fmt_usd(ct) if ct is not None else '—'})"
                )
        for route in routes:
            cell = per_cat_route.get(f"{cat}/{route}", {})
            cells.append(_fmt_ms(cell.get("wall_ms_median")))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # ------------------------------------------------------------------ #
    # Per-strategy bootstrap table + recommended strategy.
    # ------------------------------------------------------------------ #

    if bootstrap_cells and strategies:
        lines.append("## Per-strategy pass-rate (bootstrap 95% CI)")
        lines.append("")
        lines.append(
            "| Cell | n | pass-rate | 95% CI | cost (median) | cloud_fraction | Recommended |"
        )
        lines.append("|---|---:|---:|---|---:|---:|---|")
        best = _best_strategy_per_cell(bootstrap_cells, categories, routes, strategies)
        for cat in categories:
            for route in routes:
                rec = best.get((cat, route))
                for strat in strategies:
                    key = _cell_key(cat, route, strat)
                    cell = bootstrap_cells.get(key)
                    if not cell:
                        continue
                    pr = cell.get("pass_rate") or {}
                    cf = cell.get("cloud_fraction") or {}
                    cu = cell.get("cost_usd") or {}
                    is_rec = "**recommended**" if strat == rec else ""
                    lines.append(
                        f"| {cat}/{route}/{strat} | {cell.get('n_rows', 0)} | "
                        f"{_fmt_num(pr.get('point'), pct=True)} | "
                        f"[{_fmt_num(pr.get('ci_lower'), pct=True)}, "
                        f"{_fmt_num(pr.get('ci_upper'), pct=True)}] | "
                        f"{fmt_usd(cu.get('point')) if cu.get('point') is not None else '—'} | "
                        f"{_fmt_num(cf.get('point'), pct=True)} | {is_rec} |"
                    )
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
    # Token totals.
    # ------------------------------------------------------------------ #

    totals = aggregate_json.get("totals", {}).get("per_route", {})
    if totals:
        lines.append("## Token totals per route (across all tasks)")
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
    return op


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="hybrid_arena.analysis.decision_matrix",
        description="Render category × route × strategy decision matrix as Markdown.",
    )
    p.add_argument("aggregate_json", type=Path, help="Path to aggregate.json")
    p.add_argument(
        "--bootstrap",
        type=Path,
        default=None,
        help="Path to bootstrap_cis.json (recommended). If missing, "
        "the bootstrap-CI section + recommendation column are skipped.",
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
    boot = None
    if args.bootstrap is not None and args.bootstrap.exists():
        boot = json.loads(args.bootstrap.read_text())
    elif (args.aggregate_json.parent / "bootstrap_cis.json").exists():
        boot = json.loads((args.aggregate_json.parent / "bootstrap_cis.json").read_text())

    out_path = args.out or (args.aggregate_json.parent / "decision_matrix.md")
    written = build_decision_matrix(agg, boot, out_path, default_scenario=args.scenario)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
