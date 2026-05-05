"""One-shot pipeline: aggregate → arqgc → decision matrix → charts.

Run against a sweep directory containing ``raw.jsonl``::

    python -m analysis.all results/full-sweep/

Writes the following artefacts in-place:

  * ``<dir>/aggregate.json`` — :func:`analysis.aggregate.aggregate_results`.
  * ``<dir>/arqgc.json`` — :func:`analysis.arqgc.bounded_arqgc`.
  * ``<dir>/decision_matrix.md``
  * ``<dir>/charts/pareto.png``
  * ``<dir>/charts/heatmap_quality.png``
  * ``<dir>/charts/heatmap_cost.png``
  * ``<dir>/charts/heatmap_arqgc.png``

Safe on partial sweeps: skips cells without data, never crashes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from analysis.aggregate import aggregate_results  # noqa: E402
from analysis.arqgc import bounded_arqgc  # noqa: E402
from analysis.cost_scenarios import PRICING_SCENARIOS  # noqa: E402
from analysis.decision_matrix import build_decision_matrix  # noqa: E402
from lib.results import load_results  # noqa: E402
from viz.cost_quality_pareto import plot_pareto  # noqa: E402
from viz.decision_heatmap import plot_heatmap  # noqa: E402


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
    arqgc_path = d / "arqgc.json"
    decision_path = d / "decision_matrix.md"
    charts_dir = d / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Aggregate.
    agg = aggregate_results(raw, agg_path, pricing_scenarios=scenarios)

    # 2. ARQGC (need the rows again — cheap to reload).
    rows = load_results(raw)
    arqgc = bounded_arqgc(rows, scenario=scenario)
    arqgc_path.write_text(json.dumps(arqgc, indent=2))

    # 3. Decision matrix.
    build_decision_matrix(agg, arqgc, decision_path, default_scenario=scenario)

    # 4. Charts — don't crash the pipeline if one chart fails.
    chart_paths: dict = {}
    if rows:
        try:
            chart_paths["pareto"] = plot_pareto(rows, charts_dir / "pareto.png", scenario=scenario)
        except Exception as e:  # pragma: no cover — defensive.
            print(f"pareto chart failed: {e}", file=sys.stderr)
        for metric in ("quality", "cost", "arqgc"):
            try:
                chart_paths[f"heatmap_{metric}"] = plot_heatmap(
                    agg,
                    charts_dir / f"heatmap_{metric}.png",
                    metric=metric,
                    scenario=scenario,
                    arqgc=arqgc if metric == "arqgc" else None,
                )
            except Exception as e:  # pragma: no cover
                print(f"heatmap {metric} failed: {e}", file=sys.stderr)
    else:
        print("no rows in sweep — skipping chart generation", file=sys.stderr)

    return {
        "aggregate": agg_path,
        "arqgc": arqgc_path,
        "decision_matrix": decision_path,
        "charts": chart_paths,
        "row_count": agg["row_count"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="analysis.all",
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
