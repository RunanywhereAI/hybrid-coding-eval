"""JSONL IO + aggregation helpers for ``ResultRow`` records.

Raw experiment output lives in ``results/*.jsonl`` — one row per
(task × route × seed). This module provides:

  * :func:`append_row` — atomic JSONL append (single ``write()`` of a
    newline-terminated UTF-8 line, so a mid-run crash never leaves a
    half-written record).
  * :func:`load_results` — skip-on-parse-error reader, returning a
    ``list[ResultRow]``.
  * :func:`aggregate_by` — pandas ``groupby`` with *derived* costs: the
    per-scenario USD is computed on the fly from the token counts +
    :mod:`hybrid_arena.core.pricing` tables, never stored. Same ``raw.jsonl`` can be
    re-priced under any scenario by swapping ``pricing_scenario``.

Design constraint from the plan: **cost is never persisted**. Every
cost-like column in the aggregated DataFrame is a function of
``(tokens, scenario)`` only.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .metrics import ResultRow, TokenUsage
from .pricing import compute_cost

__all__ = [
    "PRICING_SCENARIOS",
    "append_row",
    "load_results",
    "aggregate_by",
]


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Scenario → pricing-table key map
# --------------------------------------------------------------------------- #
#
# A *scenario* is a human-readable name for "what cloud model should the
# cloud_* tokens be priced at?". The mapping lives here rather than in the
# pricing tables so eval consumers can add their own scenarios without
# touching the shared ``pricing_tables.json``. Each value is a model id that
# ``core.pricing.normalise_model_id`` knows how to resolve.
PRICING_SCENARIOS: dict[str, str] = {
    "openai-gpt5.5": "gpt-5.5",
    "openai-gpt5.5-pro": "gpt-5.5-pro",
    "openai-gpt5": "gpt-5",
    "openai-gpt5-mini": "gpt-5-mini",
    "openai-gpt5-nano": "gpt-5-nano",
    "openai-gpt4o": "gpt-4o",
    "openai-gpt4o-mini": "gpt-4o-mini",
    "anthropic-claude-opus-4.7": "claude-opus-4-7",
    "anthropic-claude-sonnet-4.6": "claude-sonnet-4-6",
    "anthropic-claude-haiku-4.5": "claude-haiku-4-5",
}


def _resolve_scenario(scenario: str) -> str:
    """Scenario name → model id usable with ``compute_cost``.

    Falls back to the raw ``scenario`` string so callers can pass a model
    id directly if they don't want to register a named scenario.
    """
    return PRICING_SCENARIOS.get(scenario, scenario)


# --------------------------------------------------------------------------- #
# JSONL IO
# --------------------------------------------------------------------------- #


def append_row(path: Path | str, row: ResultRow) -> None:
    """Atomically append one ``ResultRow`` to ``path`` as a JSONL line.

    Atomicity strategy: we serialise the row + trailing ``\\n`` into a
    single ``bytes`` object and do **one** ``os.write()`` call on an
    ``O_APPEND | O_WRONLY | O_CREAT`` fd. On POSIX, writes ≤ ``PIPE_BUF``
    to an append-mode file are atomic w.r.t. concurrent writers, and
    crucially the write either lands fully or not at all — no half-line.

    Large rows may exceed ``PIPE_BUF`` (typically 4 KB); we still do one
    ``write`` call so the kernel sees the payload as a single unit. In
    practice a ``ResultRow`` JSON is a few hundred bytes.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(row), ensure_ascii=False, separators=(",", ":")) + "\n"
    data = payload.encode("utf-8")
    fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        # Single write — kernel treats append-mode write as atomic up to
        # PIPE_BUF. For larger payloads it's still a single syscall, so
        # nothing interleaves with another writer's line.
        n = os.write(fd, data)
        if n != len(data):  # pragma: no cover — short writes on regular
            # files are vanishingly rare but handle them anyway.
            while n < len(data):
                n += os.write(fd, data[n:])
    finally:
        os.close(fd)


def load_results(path: Path | str) -> list[ResultRow]:
    """Read a JSONL file into a ``list[ResultRow]``.

    Empty lines are silently skipped. Lines that fail JSON parsing or
    ``ResultRow.from_dict`` are logged as warnings and dropped — we'd
    rather lose one bad row than abort loading a whole sweep.
    """
    p = Path(path)
    if not p.exists():
        return []
    out: list[ResultRow] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(ResultRow.from_dict(d))
            except (json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
                logger.warning(
                    "skipping unparseable line %d of %s: %s", lineno, p, exc
                )
                continue
    return out


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def _row_cost_usd(tokens: TokenUsage, scenario: str) -> float:
    """Compute per-row USD under ``scenario``.

    Rules (per PLAN.md §7):

      * ``local_*`` tokens cost $0 (priced against ``__local__``).
      * ``cloud_*`` tokens cost per ``scenario``.
      * If both ``local_*`` and ``cloud_*`` are zero on this row, fall
        back to treating ``tokens.prompt`` / ``tokens.completion`` as
        cloud (defensive default for never-set-split rows).
      * ``cached`` tokens are subtracted from the *cloud* prompt side
        and re-charged at the ``cache_read`` rate. (Local has no cache
        rate that isn't zero, so the distinction doesn't matter there.)
    """
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
        # No split provided — fall back to treating the aggregate totals
        # as cloud (defensive default).
        cloud_prompt = int(tokens.prompt or 0)
        cloud_completion = int(tokens.completion or 0)

    cached = int(tokens.cached or 0)
    # Assume ``cached`` applies to the cloud side (local provides no
    # real cache discount — its rate is 0 anyway).
    cloud_cached = min(cached, cloud_prompt)

    model_key = _resolve_scenario(scenario)

    cloud_cost = compute_cost(
        model_key,
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


def _rows_to_frame(rows: Iterable[ResultRow], scenario: str) -> pd.DataFrame:
    """Flatten an iterable of ResultRows into a per-row DataFrame whose
    columns are exactly those needed by ``aggregate_by``.

    Extracted so the aggregation logic stays readable.
    """
    records: list[dict[str, Any]] = []
    for r in rows:
        records.append(
            {
                "task_id": r.task_id,
                "category": r.category,
                "route": r.route,
                "hardware_profile_ref": r.hardware_profile_ref,
                "prompt_tokens": int(r.tokens.prompt or 0),
                "completion_tokens": int(r.tokens.completion or 0),
                "local_prompt_tokens": int(r.tokens.local_prompt or 0),
                "local_completion_tokens": int(r.tokens.local_completion or 0),
                "cloud_prompt_tokens": int(r.tokens.cloud_prompt or 0),
                "cloud_completion_tokens": int(r.tokens.cloud_completion or 0),
                "wall_ms": int(r.latency.wall_ms or 0),
                "total_calls": int(r.routing.total_calls or 0),
                "local_calls": int(r.routing.local_calls or 0),
                "cloud_calls": int(r.routing.cloud_calls or 0),
                "quality_composite": (
                    float(r.quality.composite)
                    if r.quality.composite is not None
                    else float("nan")
                ),
                # Store functional_pass as a nullable object column so
                # None stays distinct from False.
                "functional_pass": r.quality.functional_pass,
                "cost_usd": _row_cost_usd(r.tokens, scenario),
            }
        )
    return pd.DataFrame.from_records(records)


def _functional_pass_rate(series: pd.Series) -> float:
    """Fraction of non-None values that are truthy. All-None → NaN."""
    mask = series.notna()
    vals = series[mask]
    if len(vals) == 0:
        return float("nan")
    return float((vals.astype(bool)).sum()) / float(len(vals))


def aggregate_by(
    rows: Iterable[ResultRow],
    keys: list[str],
    pricing_scenario: str = "openai-gpt5.5",
) -> pd.DataFrame:
    """Group ``rows`` by ``keys`` and return aggregated stats.

    See module docstring for the column list. Costs are *derived* from
    the pricing table each call — never read from the rows.
    """
    if not keys:
        raise ValueError("aggregate_by requires at least one key field")

    rows_list = list(rows)
    df = _rows_to_frame(rows_list, pricing_scenario)

    # Column names for the derived cost so different scenarios live in
    # separate columns when callers chain multiple aggregations.
    cost_mean_col = f"cost_usd_{pricing_scenario}_mean"
    cost_median_col = f"cost_usd_{pricing_scenario}_median"

    if df.empty:
        # Return an empty frame with the right shape rather than crash.
        cols = [
            *keys,
            "count",
            "prompt_tokens_median",
            "prompt_tokens_mean",
            "completion_tokens_median",
            "completion_tokens_mean",
            "local_prompt_tokens_sum",
            "cloud_prompt_tokens_sum",
            "local_completion_tokens_sum",
            "cloud_completion_tokens_sum",
            "wall_ms_median",
            "wall_ms_mean",
            "total_calls_median",
            "local_calls_median",
            "cloud_calls_median",
            "quality_composite_mean",
            "quality_composite_median",
            "functional_pass_rate",
            cost_mean_col,
            cost_median_col,
        ]
        return pd.DataFrame(columns=cols)

    missing = [k for k in keys if k not in df.columns]
    if missing:
        raise KeyError(f"unknown key field(s): {missing!r}")

    grouped = df.groupby(keys, dropna=False, sort=True)

    agg = grouped.agg(
        count=("task_id", "size"),
        prompt_tokens_median=("prompt_tokens", "median"),
        prompt_tokens_mean=("prompt_tokens", "mean"),
        completion_tokens_median=("completion_tokens", "median"),
        completion_tokens_mean=("completion_tokens", "mean"),
        local_prompt_tokens_sum=("local_prompt_tokens", "sum"),
        cloud_prompt_tokens_sum=("cloud_prompt_tokens", "sum"),
        local_completion_tokens_sum=("local_completion_tokens", "sum"),
        cloud_completion_tokens_sum=("cloud_completion_tokens", "sum"),
        wall_ms_median=("wall_ms", "median"),
        wall_ms_mean=("wall_ms", "mean"),
        total_calls_median=("total_calls", "median"),
        local_calls_median=("local_calls", "median"),
        cloud_calls_median=("cloud_calls", "median"),
        quality_composite_mean=("quality_composite", "mean"),
        quality_composite_median=("quality_composite", "median"),
        functional_pass_rate=("functional_pass", _functional_pass_rate),
        **{
            cost_mean_col: ("cost_usd", "mean"),
            cost_median_col: ("cost_usd", "median"),
        },
    ).reset_index()

    # Cast integer-typed columns to ``Int64`` (nullable int) so the
    # DataFrame reads naturally — e.g. ``count`` as ``5`` not ``5.0``.
    int_cols = [
        "count",
        "prompt_tokens_median",
        "prompt_tokens_mean",
        "completion_tokens_median",
        "completion_tokens_mean",
        "local_prompt_tokens_sum",
        "cloud_prompt_tokens_sum",
        "local_completion_tokens_sum",
        "cloud_completion_tokens_sum",
        "wall_ms_median",
        "wall_ms_mean",
        "total_calls_median",
        "local_calls_median",
        "cloud_calls_median",
    ]
    for col in int_cols:
        # ``round`` before cast so means like 1234.7 become 1235 rather
        # than getting truncated.
        agg[col] = agg[col].round().astype("Int64")

    return agg
