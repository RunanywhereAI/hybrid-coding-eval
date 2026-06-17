"""One-shot pipeline: aggregate → bootstrap → decision matrix → charts.

Run against a sweep directory containing ``raw.jsonl``::

    python -m hybrid_arena.analysis.all results/runs/<sweep>/

Writes the following artefacts in-place:

* ``<dir>/aggregate.json`` — :func:`analysis.aggregate.aggregate_results`.
* ``<dir>/bootstrap_cis.json`` — :func:`analysis.bootstrap.bootstrap_cells_for_rows`.
* ``<dir>/decision_matrix.md`` — :func:`analysis.decision_matrix.build_decision_matrix`.
* ``<dir>/charts/pareto.png``
* ``<dir>/charts/heatmap_quality.png``
* ``<dir>/charts/heatmap_cost.png``

Safe on partial sweeps: skips cells without data, never crashes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hybrid_arena.analysis.aggregate import aggregate_results
from hybrid_arena.analysis.bootstrap import bootstrap_cells_for_rows
from hybrid_arena.analysis.cost_scenarios import PRICING_SCENARIOS
from hybrid_arena.analysis.decision_matrix import build_decision_matrix
from hybrid_arena.core.results import load_results
from hybrid_arena.viz.cost_quality_pareto import plot_pareto
from hybrid_arena.viz.decision_heatmap import plot_heatmap


def run_pipeline(
    sweep_dir: Path | str,
    scenario: str = "openai-gpt5.5",
    scenarios: list[str] | None = None,
) -> dict:
    """Run the full analysis pipeline for ``sweep_dir``.

    Returns a dict of ``{artefact_name: Path}`` for the caller's log.
    """
    d = Path(sweep_dir)
    raw = d / "raw.jsonl"
    if not raw.exists():
        raise FileNotFoundError(f"no raw.jsonl in {d}")

    if scenarios is None:
        scenarios = PRICING_SCENARIOS

    agg_path = d / "aggregate.json"
    bootstrap_path = d / "bootstrap_cis.json"
    decision_path = d / "decision_matrix.md"
    charts_dir = d / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    agg = aggregate_results(raw, agg_path, pricing_scenarios=scenarios)

    rows = load_results(raw)
    bootstrap = (
        bootstrap_cells_for_rows(rows, scenario=scenario) if rows else None
    )
    if bootstrap is not None:
        bootstrap_path.write_text(json.dumps(bootstrap, indent=2))

    build_decision_matrix(agg, bootstrap, decision_path, default_scenario=scenario)

    chart_paths: dict = {}
    if rows:
        try:
            chart_paths["pareto"] = plot_pareto(rows, charts_dir / "pareto.png", scenario=scenario)
        except Exception as exc:  # pragma: no cover — defensive
            print(f"pareto chart failed: {exc}", file=sys.stderr)
        for metric in ("quality", "cost"):
            try:
                chart_paths[f"heatmap_{metric}"] = plot_heatmap(
                    agg,
                    charts_dir / f"heatmap_{metric}.png",
                    metric=metric,
                    scenario=scenario,
                )
            except Exception as exc:  # pragma: no cover
                print(f"heatmap {metric} failed: {exc}", file=sys.stderr)
    else:
        print("no rows in sweep — skipping chart generation", file=sys.stderr)

    return {
        "aggregate": agg_path,
        "bootstrap_cis": bootstrap_path if bootstrap is not None else None,
        "decision_matrix": decision_path,
        "charts": chart_paths,
        "row_count": agg["row_count"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="hybrid_arena.analysis.all",
        description="Run the full analysis pipeline on a sweep directory.",
    )
    p.add_argument("sweep_dir", type=Path, help="Directory containing raw.jsonl")
    p.add_argument("--scenario", type=str, default="openai-gpt5.5")
    p.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="Comma-separated scenarios for per-row cost columns.",
    )
    args = p.parse_args(argv)

    scenarios = None
    if args.scenarios:
        scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    result = run_pipeline(args.sweep_dir, scenario=args.scenario, scenarios=scenarios)
    print(f"pipeline complete — {result['row_count']} rows")
    for name, path in result.items():
        if name == "charts":
            for cname, cpath in path.items():
                print(f"  chart/{cname}: {cpath}")
        elif name != "row_count":
            print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
