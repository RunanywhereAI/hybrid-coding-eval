"""Price the same ``raw.jsonl`` under multiple pricing scenarios.

The eval harness stores tokens, never cost (see ``PLAN.md`` §7). That
lets us answer questions like *"what would this sweep have cost on
gpt-5-mini?"* long after the fact — by re-running the pricing formula
against the stored token counts.

A *scenario* is a human-readable name (e.g. ``openai-gpt5.5``) that
:mod:`hybrid_arena.core.results` maps to a pricing-table key.
This module adds two
small utilities on top of that:

  * :func:`compute_row_cost` — single-row cost under one scenario.
  * :func:`compute_scenario_costs` — tidy DataFrame with one cost column
    per scenario so callers can diff them trivially.

Local tokens always cost $0 (priced against the ``__local__`` pseudo-
model). Cloud tokens cost whatever the scenario says.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from hybrid_arena.core.metrics import ResultRow
from hybrid_arena.core.pricing import compute_cost
from hybrid_arena.core.results import PRICING_SCENARIOS as _NAMED_SCENARIOS

__all__ = [
    "PRICING_SCENARIOS",
    "compute_row_cost",
    "compute_scenario_costs",
]


# Scenarios surfaced by the report. Kept small on purpose — the full
# registry lives in ``core.results.PRICING_SCENARIOS``. These five span
# "current default cloud route" → "cheap cloud" → "alternative frontier"
# and are what the decision matrix / Pareto charts iterate over.
PRICING_SCENARIOS: list[str] = [
    "openai-gpt5.5",              # current default cloud route
    "openai-gpt5",                # ~40% cheaper cloud (same vendor)
    "openai-gpt5-mini",           # cheap cloud
    "anthropic-claude-opus-4.7",  # alternative frontier
    "anthropic-claude-sonnet-4.6",  # alternative mid-tier
]


def _scenario_to_model_id(scenario: str) -> str:
    """Scenario name → pricing-table key.

    Falls back to the raw string so callers can drop a model id in
    directly (handy for ad-hoc what-ifs).
    """
    return _NAMED_SCENARIOS.get(scenario, scenario)


def compute_row_cost(row: ResultRow, scenario: str) -> float:
    """USD for one row under ``scenario``.

    Rules (identical to :func:`core.results._row_cost_usd` but re-stated
    here so this module is self-contained):

      * ``local_*`` tokens are priced at ``__local__`` (always $0).
      * ``cloud_*`` tokens are priced at the scenario model.
      * If neither ``local_*`` nor ``cloud_*`` are set, fall back to
        treating ``prompt`` / ``completion`` as cloud (defensive default).
      * Cached tokens are subtracted from the cloud-prompt side and
        re-charged at ``cache_read``.
    """
    tokens = row.tokens

    cloud_prompt = int(tokens.cloud_prompt or 0)
    cloud_completion = int(tokens.cloud_completion or 0)
    local_prompt = int(tokens.local_prompt or 0)
    local_completion = int(tokens.local_completion or 0)

    if (
        cloud_prompt == 0
        and cloud_completion == 0
        and local_prompt == 0
        and local_completion == 0
    ):
        cloud_prompt = int(tokens.prompt or 0)
        cloud_completion = int(tokens.completion or 0)

    cached = int(tokens.cached or 0)
    cloud_cached = min(cached, cloud_prompt)

    cloud_cost = compute_cost(
        _scenario_to_model_id(scenario),
        {
            "prompt_tokens": cloud_prompt,
            "completion_tokens": cloud_completion,
            "prompt_tokens_details": {"cached_tokens": cloud_cached},
        },
    )["usd"]

    local_cost = compute_cost(
        "__local__",
        {
            "prompt_tokens": local_prompt,
            "completion_tokens": local_completion,
        },
    )["usd"]

    return float(cloud_cost + local_cost)


def compute_scenario_costs(
    rows: Iterable[ResultRow],
    scenarios: list[str] | None = None,
) -> pd.DataFrame:
    """Return one row per input row with one cost column per scenario.

    Columns:

      * ``task_id``, ``category``, ``route`` — identifying keys.
      * ``cost_<scenario>`` — USD under each scenario.

    Handy for the Pareto scatter (pick any scenario column for x-axis)
    and for "price the same dataset N ways" tables in the report.
    """
    if scenarios is None:
        scenarios = PRICING_SCENARIOS

    records: list[dict] = []
    for r in rows:
        rec: dict = {
            "task_id": r.task_id,
            "category": r.category,
            "route": r.route,
        }
        for s in scenarios:
            rec[f"cost_{s}"] = compute_row_cost(r, s)
        records.append(rec)
    return pd.DataFrame.from_records(records)
