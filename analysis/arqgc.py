"""Bounded-ARQGC — Area under the quality-cost curve.

Adapted from IPRBench's ``ARQGC`` aggregate score. The intuition:

  * Each route has a Pareto curve of "how much quality do you get per
    dollar?".
  * Sort rows by per-task cost ascending; plot cumulative cost (x) vs
    per-task quality (y) as a step function.
  * Integrate the curve (trapezoidal) up to a chosen cost cap — that
    area is the "quality dollars" the route delivered within the
    budget. Normalise to [0, 1] by dividing by the area of the
    hypothetical "perfect route" (quality=1 everywhere up to the cap).
  * Higher is better; 1.0 means every task passed perfectly and the
    total cost stayed under the cap.

Why *bounded*? Raw ARQGC integrates to infinity which rewards cheap-
but-slow providers unboundedly. Capping the cost axis — e.g. at the
median R1 cost — makes routes comparable on the budget you actually
care about.
"""

from __future__ import annotations

from typing import Iterable

from lib.metrics import ResultRow

from analysis.cost_scenarios import compute_row_cost

__all__ = [
    "bounded_arqgc",
    "arqgc_for_rows",
]


def _quality(r: ResultRow) -> float:
    """Quality signal: composite if set, else functional_pass as 0/1."""
    if r.quality.composite is not None:
        return float(r.quality.composite)
    if r.quality.functional_pass is not None:
        return 1.0 if r.quality.functional_pass else 0.0
    return 0.0  # unknown quality counts as 0 for ARQGC


def arqgc_for_rows(
    rows: list[ResultRow],
    scenario: str,
    cost_cap: float | None = None,
) -> float:
    """Compute ARQGC for one group of rows.

    Steps:

      1. Build (cost, quality) pairs, one per row.
      2. Sort by cost ascending.
      3. Walk cumulative cost on x-axis; quality on y-axis.
      4. Trapezoidal integration up to ``cost_cap``.
      5. Normalise by ``cost_cap`` (the area of the perfect curve).

    Edge cases:

      * Empty ``rows`` → 0.0.
      * All rows zero-cost (e.g. pure-local) → average quality. This
        is the limit as cost_cap → 0; makes the metric behave sensibly
        when a route is genuinely free.
      * ``cost_cap`` None → use the total cost of the group.
    """
    if not rows:
        return 0.0

    pairs = sorted(
        ((compute_row_cost(r, scenario), _quality(r)) for r in rows),
        key=lambda cq: cq[0],
    )

    total_cost = sum(c for c, _ in pairs)
    if cost_cap is None:
        cost_cap = total_cost

    # Degenerate: no cost axis. Return mean quality — the "free route"
    # limit. Prevents divide-by-zero and still orders routes sensibly.
    if cost_cap is None or cost_cap <= 0:
        return sum(q for _, q in pairs) / len(pairs)

    # Integrate quality as a step function of cumulative cost, clipped
    # to [0, cost_cap].
    area = 0.0
    cum = 0.0
    for cost, q in pairs:
        if cum >= cost_cap:
            break
        # This row contributes from x=cum to x=min(cum+cost, cost_cap).
        # Width is the cost spent on this task (clipped at the cap).
        span = min(cost, cost_cap - cum)
        # Step function: quality is constant over [cum, cum+span].
        area += span * q
        cum += span

    # Beyond the last row we assume quality=0 (no more tasks → no more
    # quality delivered). So if total_cost < cost_cap, the remaining
    # [total_cost, cost_cap] band contributes zero. That's intentional:
    # it penalises routes that don't even have enough work to fill the
    # budget.

    # Normalise by the perfect-quality area: quality=1 over [0, cap].
    return float(area / cost_cap)


def bounded_arqgc(
    rows: Iterable[ResultRow],
    scenario: str = "openai-gpt5.5",
    cost_cap: float | None = None,
) -> dict:
    """Compute ARQGC per route + per (category, route).

    Returns::

        {
            "scenario": "openai-gpt5.5",
            "cost_cap": 0.5,
            "per_route": {"R1": 0.87, "R2": 0.12, "R3": 0.76},
            "per_category_route": {
                "A/R1": 0.91, "A/R2": 0.2, "A/R3": 0.85, ...
            },
        }

    ``cost_cap`` default: the 90th percentile of R1's per-task cost at
    ``scenario``. This ties the budget to "the most expensive route
    we're benchmarking against" which keeps the number interpretable —
    ARQGC=0.5 means "half the quality of a perfect route running within
    the R1 budget".
    """
    rows_list = list(rows)

    # Derive a default cost cap from R1 if none supplied.
    if cost_cap is None:
        r1_costs = sorted(
            compute_row_cost(r, scenario) for r in rows_list if r.route == "R1"
        )
        if r1_costs:
            # p90 of per-task costs × number of tasks gives a "90% of R1"
            # budget across the whole task set. Fall back to sum(costs)
            # if we can't compute a percentile cleanly.
            idx = max(0, int(round(0.9 * (len(r1_costs) - 1))))
            p90 = r1_costs[idx]
            # Budget = p90 × number of tasks in the biggest per-route group.
            per_route_counts = {}
            for r in rows_list:
                per_route_counts[r.route] = per_route_counts.get(r.route, 0) + 1
            n_tasks = max(per_route_counts.values()) if per_route_counts else len(r1_costs)
            cost_cap = p90 * n_tasks
        else:
            cost_cap = 0.0

    per_route: dict[str, float] = {}
    per_cat_route: dict[str, float] = {}

    routes = sorted({r.route for r in rows_list})
    for route in routes:
        route_rows = [r for r in rows_list if r.route == route]
        per_route[route] = arqgc_for_rows(route_rows, scenario, cost_cap)

    cats = sorted({r.category for r in rows_list})
    for cat in cats:
        for route in routes:
            sub = [r for r in rows_list if r.category == cat and r.route == route]
            if not sub:
                continue
            per_cat_route[f"{cat}/{route}"] = arqgc_for_rows(sub, scenario, cost_cap)

    return {
        "scenario": scenario,
        "cost_cap": float(cost_cap),
        "per_route": per_route,
        "per_category_route": per_cat_route,
    }
