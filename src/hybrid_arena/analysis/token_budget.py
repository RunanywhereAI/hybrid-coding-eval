"""P0.1: token-first analysis view — "where did this task spend its tokens?"

For each ``(task_id, route, variant)`` tuple we compute:

  * the prompt / completion split on both the local and cloud sides,
  * aggregate totals,
  * the **cloud fraction** — what share of tokens actually left the
    laptop,
  * cost under each headline pricing scenario, derived from the same
    stored tokens (no inference re-run).

This makes "for this task, X% of tokens went local ($0), Y% went cloud,
and here is what that costs under 6 pricing scenarios" the central data
view of the report, rather than the existing per-cell aggregates in
:mod:`hybrid_arena.analysis.token_share` or the per-row
scenario-pivoted CSV in :mod:`hybrid_arena.analysis.reprice`.

Outputs (via the CLI wrapper ``./arena token-budget``):

  * ``reports/TOKEN_BUDGET.md`` — human-readable tables.
  * ``reports/token_budget.csv`` — tidy one-row-per-run frame for
    downstream joins in the report generator.

Cost derivation goes through
:func:`hybrid_arena.analysis.cost_scenarios.compute_row_cost` so
this module never duplicates the pricing formula.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from hybrid_arena.analysis.cost_scenarios import compute_row_cost
from hybrid_arena.core.metrics import ResultRow

__all__ = [
    "HEADLINE_SCENARIOS",
    "compute_token_budget",
    "render_markdown",
    "render_csv",
]


# The 6 headline scenarios surfaced in the token-budget view. Kept here
# (in addition to the 5 in ``cost_scenarios.PRICING_SCENARIOS``) because
# this view deliberately surfaces a Claude Haiku line as the "cheap
# cloud alternative" for the Anthropic column.
HEADLINE_SCENARIOS: list[str] = [
    "openai-gpt5.5",
    "openai-gpt5",
    "openai-gpt5-mini",
    "anthropic-claude-opus-4.7",
    "anthropic-claude-sonnet-4.6",
    "anthropic-claude-haiku-4.5",
]


# --------------------------------------------------------------------------- #
# Token-split helpers
# --------------------------------------------------------------------------- #


def _row_tokens_split(row: ResultRow) -> tuple[int, int, int, int]:
    """Return ``(prompt_local, completion_local, prompt_cloud,
    completion_cloud)`` for one row.

    Mirrors the fallback used by :func:`compute_row_cost`: when neither
    a local nor cloud split is populated (defensive default), the
    aggregate ``tokens.prompt`` / ``tokens.completion`` are treated as
    cloud so the cloud-fraction computation stays consistent with the
    per-row cost.
    """
    t = row.tokens
    local_prompt = int(t.local_prompt or 0)
    local_completion = int(t.local_completion or 0)
    cloud_prompt = int(t.cloud_prompt or 0)
    cloud_completion = int(t.cloud_completion or 0)
    if (
        local_prompt == 0
        and local_completion == 0
        and cloud_prompt == 0
        and cloud_completion == 0
    ):
        cloud_prompt = int(t.prompt or 0)
        cloud_completion = int(t.completion or 0)
    return local_prompt, local_completion, cloud_prompt, cloud_completion


# --------------------------------------------------------------------------- #
# Public: compute_token_budget
# --------------------------------------------------------------------------- #


def compute_token_budget(
    rows_iterable: Iterable[ResultRow],
    scenarios: list[str],
) -> pd.DataFrame:
    """Return one row per ``(task_id, route, variant)`` with tokens,
    cloud fraction, and cost columns — one per scenario.

    The returned DataFrame preserves input order and length: every input
    row corresponds to exactly one output row, even when ``row.error``
    is set (those rows have zero tokens and zero cost — they still count
    as "runs attempted").
    """
    records: list[dict] = []
    for r in rows_iterable:
        prompt_local, completion_local, prompt_cloud, completion_cloud = (
            _row_tokens_split(r)
        )
        total_local = prompt_local + completion_local
        total_cloud = prompt_cloud + completion_cloud
        total = total_local + total_cloud
        cloud_fraction = (total_cloud / total) if total > 0 else 0.0

        rec: dict = {
            "task_id": r.task_id,
            "category": r.category,
            "route": r.route,
            "variant": r.variant,
            "prompt_local": prompt_local,
            "completion_local": completion_local,
            "prompt_cloud": prompt_cloud,
            "completion_cloud": completion_cloud,
            "total_local": total_local,
            "total_cloud": total_cloud,
            "total": total,
            "cloud_fraction": cloud_fraction,
            "functional_pass": r.quality.functional_pass,
            "composite": r.quality.composite,
        }
        for s in scenarios:
            rec[f"cost_{s}_usd"] = compute_row_cost(r, s)
        records.append(rec)
    return pd.DataFrame.from_records(records)


# --------------------------------------------------------------------------- #
# Render helpers
# --------------------------------------------------------------------------- #


def _band_label(cf: float) -> str:
    """Bucket a cloud_fraction into one of four equal-width bands."""
    if cf < 0.25:
        return "0-25%"
    if cf < 0.50:
        return "25-50%"
    if cf < 0.75:
        return "50-75%"
    return "75-100%"


_BAND_ORDER = ["0-25%", "25-50%", "50-75%", "75-100%"]


def _top_local_efficient(df: pd.DataFrame, scenarios: list[str], n: int = 10) -> str:
    passing = df[df["functional_pass"] == True]  # noqa: E712
    if passing.empty:
        return "_No passing rows in the dataset._\n"
    top = passing.sort_values(
        by=["cloud_fraction", "total"], ascending=[True, True]
    ).head(n)

    lines: list[str] = []
    header_cells = ["task_id", "route", "variant", "cat", "cloud_frac", "tokens"]
    for s in scenarios:
        header_cells.append(f"${s}")
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("|" + ("---|" * len(header_cells)))
    for _, row in top.iterrows():
        cells = [
            str(row["task_id"]),
            str(row["route"]),
            str(row["variant"] or ""),
            str(row["category"]),
            f"{row['cloud_fraction']:.0%}",
            f"{int(row['total']):,}",
        ]
        for s in scenarios:
            cells.append(f"${row[f'cost_{s}_usd']:.4f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _median_by_cat_route(df: pd.DataFrame, scenarios: list[str]) -> str:
    if df.empty:
        return "_No rows in dataset._\n"
    groups = df.groupby(["category", "route"], dropna=False, sort=True)

    lines: list[str] = []
    header = ["cat", "route", "n_rows", "median_cloud_frac", "pass_rate"]
    for s in scenarios:
        header.append(f"med_${s}")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + ("---|" * len(header)))

    for (cat, route), g in groups:
        n_rows = len(g)
        median_cf = float(g["cloud_fraction"].median())
        pass_mask = g["functional_pass"].notna()
        pass_vals = g.loc[pass_mask, "functional_pass"]
        pass_rate = (
            float(pass_vals.astype(bool).sum()) / float(len(pass_vals))
            if len(pass_vals) > 0
            else float("nan")
        )
        cells = [
            str(cat),
            str(route),
            str(n_rows),
            f"{median_cf:.0%}",
            ("—" if pass_rate != pass_rate else f"{pass_rate:.0%}"),
        ]
        for s in scenarios:
            med = float(g[f"cost_{s}_usd"].median())
            cells.append(f"${med:.4f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _decision_matrix(df: pd.DataFrame, primary_scenario: str) -> str:
    if df.empty:
        return "_No rows in dataset._\n"
    cost_col = f"cost_{primary_scenario}_usd"
    df = df.copy()
    df["__band__"] = df["cloud_fraction"].apply(_band_label)

    lines: list[str] = []
    lines.append(
        f"| cloud_fraction band | n_tasks | pass_rate | mean ${primary_scenario}/task |"
    )
    lines.append("|---|---:|---:|---:|")
    for band in _BAND_ORDER:
        g = df[df["__band__"] == band]
        n = len(g)
        if n == 0:
            lines.append(f"| {band} | 0 | — | — |")
            continue
        pass_mask = g["functional_pass"].notna()
        pass_vals = g.loc[pass_mask, "functional_pass"]
        pass_rate = (
            float(pass_vals.astype(bool).sum()) / float(len(pass_vals))
            if len(pass_vals) > 0
            else float("nan")
        )
        mean_cost = float(g[cost_col].mean())
        pr = "—" if pass_rate != pass_rate else f"{pass_rate:.0%}"
        lines.append(f"| {band} | {n} | {pr} | ${mean_cost:.4f} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Public: render_markdown / render_csv
# --------------------------------------------------------------------------- #


def render_markdown(
    df: pd.DataFrame,
    scenarios: list[str],
    out_path: Path,
    *,
    source: str = "results/raw.jsonl",
    primary_scenario: str = "openai-gpt5.5",
) -> None:
    """Write a markdown rendering of the token budget to ``out_path``.

    The output is deliberately short (<200 lines) and readable as plain
    text — three tables plus a header that states where the numbers
    came from and the derivation contract.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts: list[str] = []
    parts.append("# Token budget — where the tokens went")
    parts.append("")
    parts.append(
        f"Generated from `{source}` at `{timestamp}`; cost is derived from "
        "tokens at read time using `configs/pricing/pricing_tables.json`."
    )
    parts.append("")
    parts.append(
        "Every row below is one `(task_id, route, variant)` run from the "
        "committed dataset. `cloud_fraction` is the share of prompt+completion "
        "tokens that left the laptop; local tokens cost $0 by construction. "
        "`cost_<scenario>_usd` is re-derived from the stored tokens against "
        "the pinned pricing table, so the same dataset can be re-priced under "
        "any scenario without re-running inference."
    )
    parts.append("")
    parts.append(f"**Scenarios surfaced:** {', '.join(f'`{s}`' for s in scenarios)}")
    parts.append("")

    parts.append("## 1. Top-10 most-local-efficient passing tasks")
    parts.append("")
    parts.append(
        "Rows where `functional_pass = True`, sorted by `cloud_fraction` "
        "ascending (ties broken by fewer total tokens). These are the tasks "
        "the laptop actually solved mostly on its own — the routing wins."
    )
    parts.append("")
    parts.append(_top_local_efficient(df, scenarios, n=10))

    parts.append("## 2. Per-(category, route) median table")
    parts.append("")
    parts.append(
        "One row per `(category, route)` cell. `median_cloud_frac` is the "
        "median across the runs in that cell; `pass_rate` ignores rows where "
        "`functional_pass` is null; each `med_$<scenario>` column is the "
        "median per-run cost under that scenario."
    )
    parts.append("")
    parts.append(_median_by_cat_route(df, scenarios))

    parts.append(f"## 3. Decision matrix — cloud_fraction bands (costed under `{primary_scenario}`)")
    parts.append("")
    parts.append(
        "Bucket every run by its `cloud_fraction` into 4 equal-width bands, "
        "then report how many tasks land in each band, their pass rate, and "
        "the mean USD cost under the primary pricing scenario."
    )
    parts.append("")
    parts.append(_decision_matrix(df, primary_scenario))

    parts.append("---")
    parts.append("")
    parts.append(
        f"_n_rows={len(df)} | scenarios={len(scenarios)} | "
        "derivation: tokens × pinned pricing_tables.json (sha256 pinned in "
        "`hybrid_arena.core.pricing.PRICING_META`)._"
    )
    parts.append("")

    out_path.write_text("\n".join(parts), encoding="utf-8")


def render_csv(df: pd.DataFrame, out_path: Path) -> None:
    """Write the token-budget DataFrame to ``out_path`` as CSV.

    Uses ``csv.writer`` directly so ``None`` values come out as empty
    cells (pandas' default is ``""`` via ``to_csv`` which matches but
    we're explicit about the contract here)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(df.columns)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        for _, row in df.iterrows():
            out_row: list[str] = []
            for col in columns:
                v = row[col]
                if v is None or (isinstance(v, float) and v != v):
                    out_row.append("")
                elif isinstance(v, bool):
                    out_row.append("true" if v else "false")
                elif isinstance(v, float):
                    out_row.append(f"{v:.6f}")
                else:
                    out_row.append(str(v))
            w.writerow(out_row)
