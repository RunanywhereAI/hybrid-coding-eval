"""Cost-vs-quality scatter with a Pareto frontier.

One point per (task × route × seed). Colour = route. Marker shape =
category. The Pareto frontier connects the non-dominated points
(higher quality OR lower cost than every other point).

Run from the repo root::

    python -m viz.cost_quality_pareto results/full-sweep/raw.jsonl \\
        --out results/full-sweep/charts/pareto.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo-root import dance.
_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / "pyproject.toml").is_file():
        _REPO_ROOT = _p
        break
else:  # pragma: no cover
    _REPO_ROOT = _here.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Matplotlib must be Agg-only — we never show an interactive window.
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from hybrid_arena.analysis.cost_scenarios import compute_row_cost  # noqa: E402
from hybrid_arena.core.metrics import ResultRow  # noqa: E402
from hybrid_arena.core.results import load_results  # noqa: E402

__all__ = ["plot_pareto"]


# Agent → colour, task-class → marker. Fixed so the legend is stable
# across reports. Unknown agents/categories fall back to grey + "x".
_ROUTE_COLORS = {
    "aider":          "#1f77b4",  # blue
    "opencode":       "#ff7f0e",  # orange
    "mini-swe-agent": "#2ca02c",  # green
    "cline":          "#9467bd",  # purple
}
_CATEGORY_MARKERS = {
    "puzzles":   "o",   # Exercism Python
    "refactors": "s",   # real-PR D-tasks
    "real-prs":  "^",   # SWE-bench Verified
}


def _pareto_frontier(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Lower-cost, higher-quality frontier.

    A point (c, q) is on the frontier iff no other point has c' <= c
    AND q' >= q (with at least one strict). We sort by cost asc then
    walk, keeping points whose quality strictly exceeds the running max.
    """
    if not points:
        return []
    # Sort by cost asc, then by quality desc so equal-cost points
    # collapse to the highest-quality one.
    ordered = sorted(points, key=lambda cq: (cq[0], -cq[1]))
    frontier: list[tuple[float, float]] = []
    best_q = -float("inf")
    for c, q in ordered:
        if q > best_q:
            frontier.append((c, q))
            best_q = q
    return frontier


def _quality(r: ResultRow) -> float:
    if r.quality.composite is not None:
        return float(r.quality.composite)
    if r.quality.functional_pass is not None:
        return 1.0 if r.quality.functional_pass else 0.0
    return 0.0


def plot_pareto(
    rows: list[ResultRow],
    output_path: Path | str,
    scenario: str = "openai-gpt5.5",
    title: str | None = None,
    dpi: int = 150,
) -> Path:
    """Render the Pareto scatter and save to ``output_path``. Returns the path."""
    op = Path(output_path)
    op.parent.mkdir(parents=True, exist_ok=True)

    # 1200x800 @ 150dpi = 8x5.333 inches.
    fig, ax = plt.subplots(figsize=(8.0, 5.333), dpi=dpi)

    # Plot one scatter group per (route, category) for a clean legend.
    all_points: list[tuple[float, float]] = []
    seen_routes: set[str] = set()
    seen_categories: set[str] = set()
    for route in sorted({r.route for r in rows}):
        colour = _ROUTE_COLORS.get(route, "#7f7f7f")
        for cat in sorted({r.category for r in rows if r.route == route}):
            marker = _CATEGORY_MARKERS.get(cat, "x")
            subset = [r for r in rows if r.route == route and r.category == cat]
            xs = [compute_row_cost(r, scenario) for r in subset]
            ys = [_quality(r) for r in subset]
            all_points.extend(zip(xs, ys))
            label_bits: list[str] = []
            if route not in seen_routes:
                label_bits.append(route)
                seen_routes.add(route)
            if cat not in seen_categories:
                label_bits.append(f"cat {cat}")
                seen_categories.add(cat)
            label = " / ".join(label_bits) if label_bits else None
            # Always label so downstream legend has a per-(route,cat) entry.
            ax.scatter(
                xs,
                ys,
                c=colour,
                marker=marker,
                alpha=0.75,
                s=55,
                edgecolors="white",
                linewidths=0.6,
                label=f"{route} / {cat}",
            )

    # Pareto frontier — dashed line through non-dominated points.
    frontier = _pareto_frontier(all_points)
    if frontier:
        fx = [p[0] for p in frontier]
        fy = [p[1] for p in frontier]
        ax.plot(
            fx,
            fy,
            linestyle="--",
            color="#333333",
            linewidth=1.2,
            label="Pareto frontier",
            alpha=0.9,
        )

    ax.set_xlabel(f"Cost (USD) — {scenario}")
    ax.set_ylabel("Quality (composite / pass)")
    ax.set_title(title or f"Cost vs quality — {scenario}")
    ax.grid(True, alpha=0.25)
    # Give the plot some breathing room at the bottom for x=0 rows.
    xmin = 0.0
    xmax = max((p[0] for p in all_points), default=0.0)
    if xmax > 0:
        ax.set_xlim(xmin, xmax * 1.05)
    ax.set_ylim(-0.05, 1.05)

    # De-duplicate legend entries (we set label every scatter call).
    handles, labels = ax.get_legend_handles_labels()
    uniq = list({label: handle for label, handle in zip(labels, handles)}.items())
    ax.legend(
        [h for _, h in uniq],
        [l for l, _ in uniq],
        loc="lower right",
        fontsize=8,
        framealpha=0.9,
    )

    fig.tight_layout()
    fig.savefig(op, dpi=dpi)
    plt.close(fig)
    return op


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="viz.cost_quality_pareto",
        description="Cost vs quality scatter with Pareto frontier.",
    )
    p.add_argument("raw_jsonl", type=Path, help="Path to raw.jsonl")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PNG path. Default: <raw_jsonl dir>/charts/pareto.png",
    )
    p.add_argument(
        "--scenario",
        type=str,
        default="openai-gpt5.5",
        help="Pricing scenario driving the cost axis.",
    )
    p.add_argument("--title", type=str, default=None)
    args = p.parse_args(argv)

    rows = load_results(args.raw_jsonl)
    out = args.out or (args.raw_jsonl.parent / "charts" / "pareto.png")
    path = plot_pareto(rows, out, scenario=args.scenario, title=args.title)
    print(f"wrote {path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
