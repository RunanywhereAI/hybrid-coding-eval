"""Category × route heatmap.

Rows = task categories (``puzzles`` / ``refactors``). Columns = routes
(``aider`` / ``opencode`` / ``mini-swe-agent`` / ``cline``). Each cell is
annotated with the numeric value of the chosen metric.

CLI::

    python -m hybrid_arena.viz.decision_heatmap \\
        results/runs/<sweep>/aggregate.json \\
        --metric quality \\
        --out results/runs/<sweep>/charts/heatmap_quality.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

__all__ = ["plot_heatmap"]


_SUPPORTED_METRICS = ("quality", "cost", "cost_total", "wall_ms")


def _build_grid(
    aggregate_json: dict,
    metric: str,
    scenario: str,
) -> tuple[list[str], list[str], np.ndarray]:
    """Return (categories, routes, matrix) for the chosen metric."""
    per_cat_route: dict = aggregate_json.get("per_category_route", {})
    categories = sorted({k.split("/")[0] for k in per_cat_route.keys()})
    routes = sorted({k.split("/")[1] for k in per_cat_route.keys()})

    matrix = np.full((len(categories), len(routes)), np.nan, dtype=float)

    for i, cat in enumerate(categories):
        for j, route in enumerate(routes):
            cell = per_cat_route.get(f"{cat}/{route}", {})
            if metric == "quality":
                v = cell.get("quality_median")
            elif metric == "cost":
                v = cell.get(f"cost_{scenario}_median")
            elif metric == "cost_total":
                v = cell.get(f"cost_{scenario}_total")
            elif metric == "wall_ms":
                v = cell.get("wall_ms_median")
            else:
                raise ValueError(
                    f"unknown metric {metric!r} (expected one of {_SUPPORTED_METRICS})"
                )
            if v is None:
                matrix[i, j] = np.nan
            else:
                matrix[i, j] = float(v)
    return categories, routes, matrix


def _annotate_value(v: float, metric: str) -> str:
    if np.isnan(v):
        return "—"
    if metric == "quality":
        return f"{v:.2f}"
    if metric in ("cost", "cost_total"):
        if v == 0:
            return "$0"
        if v < 0.01:
            return f"${v:.4f}"
        if v < 1:
            return f"${v:.3f}"
        return f"${v:.2f}"
    if metric == "wall_ms":
        return f"{int(round(v)):,}ms"
    return f"{v:.3f}"


def plot_heatmap(
    aggregate_json: dict,
    output_path: Path | str,
    *,
    metric: str = "quality",
    scenario: str = "openai-gpt5.5",
    dpi: int = 150,
) -> Path:
    """Render the heatmap. Returns the output path."""
    if metric not in _SUPPORTED_METRICS:
        raise ValueError(f"unknown metric {metric!r} (expected one of {_SUPPORTED_METRICS})")

    op = Path(output_path)
    op.parent.mkdir(parents=True, exist_ok=True)

    categories, routes, matrix = _build_grid(aggregate_json, metric, scenario)

    fig, ax = plt.subplots(
        figsize=(
            max(5, 1.6 * len(routes) + 2),
            max(3, 1.1 * len(categories) + 1.5),
        ),
        dpi=dpi,
    )

    # Higher = better for quality, lower = better for cost/wall.
    cmap = "YlGn" if metric == "quality" else "YlOrRd"

    finite = matrix[np.isfinite(matrix)]
    vmin = float(finite.min()) if finite.size else 0.0
    vmax = float(finite.max()) if finite.size else 1.0
    if vmin == vmax:
        vmax = vmin + 1e-9  # avoid zero-range colormap

    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    ax.set_xticks(range(len(routes)))
    ax.set_xticklabels(routes)
    ax.set_yticks(range(len(categories)))
    ax.set_yticklabels(categories)
    ax.set_xlabel("Route")
    ax.set_ylabel("Category")

    pretty = {
        "quality": "Quality (median)",
        "cost": f"Cost per task (median, {scenario})",
        "cost_total": f"Cost total ({scenario})",
        "wall_ms": "Wall time (median ms)",
    }[metric]
    ax.set_title(pretty)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            if not np.isfinite(val):
                colour = "#666666"
                text = "—"
            else:
                norm = (val - vmin) / (vmax - vmin) if vmax > vmin else 0.0
                colour = "white" if norm > 0.6 else "black"
                text = _annotate_value(val, metric)
            ax.text(j, i, text, ha="center", va="center", color=colour, fontsize=10)

    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(op, dpi=dpi)
    plt.close(fig)
    return op


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="hybrid_arena.viz.decision_heatmap",
        description="Category × route heatmap of a chosen metric.",
    )
    p.add_argument("aggregate_json", type=Path, help="Path to aggregate.json")
    p.add_argument(
        "--metric",
        choices=_SUPPORTED_METRICS,
        default="quality",
        help="Which number to plot in each cell.",
    )
    p.add_argument(
        "--scenario",
        type=str,
        default="openai-gpt5.5",
        help="Pricing scenario (used for cost metrics).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PNG path. Default: <aggregate dir>/charts/heatmap_<metric>.png",
    )
    args = p.parse_args(argv)

    agg = json.loads(args.aggregate_json.read_text())
    out = args.out or (args.aggregate_json.parent / "charts" / f"heatmap_{args.metric}.png")
    path = plot_heatmap(agg, out, metric=args.metric, scenario=args.scenario)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
