"""Orchestrator core for :mod:`bin.run-experiment` (T4.1).

The orchestrator loops over ``(task, route)`` pairs, invokes the right
runner, optionally scores the output, and appends one
:class:`lib.metrics.ResultRow` per pair to ``<out>/raw.jsonl`` *immediately*
so the sweep is resume-safe.

This module holds the benchmark-loading, resume-scan and per-pair
execution helpers. The CLI (``bin/run-experiment.py``) is kept thin.
"""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .metrics import Quality, ResultRow
from .results import append_row, load_results

logger = logging.getLogger(__name__)

__all__ = [
    "CATEGORY_SOURCES",
    "ROUTES",
    "TaskPlan",
    "build_task_plan",
    "load_category_tasks",
    "pair_already_done",
    "run_pair",
    "score_row",
    "timestamp_dirname",
]


#: Which benchmark adapters contribute tasks to each category letter.
#: Category A = HumanEval+ (tiny function-completion).
#: Category B = SWE-bench Verified (repo-level agentic).
#: Category C = BigCodeBench-Hard (functional) + custom_arch (judge).
CATEGORY_SOURCES: dict[str, list[str]] = {
    "A": ["humaneval_plus"],
    "B": ["swebench_verified"],
    "C": ["bigcodebench_hard", "custom_arch"],
}

#: Valid --routes values.
ROUTES: tuple[str, ...] = ("R1", "R2", "R3", "R4")


# --------------------------------------------------------------------------- #
# Task loading
# --------------------------------------------------------------------------- #


def load_category_tasks(
    category: str,
    smoke: bool = False,
    tasks_cap: int | None = None,
) -> list[tuple[str, Any]]:
    """Return ``[(source, task), ...]`` for a category.

    Parameters
    ----------
    category
        'A', 'B', or 'C'.
    smoke
        If True, take only the first task from the category (deterministic).
        When the category has multiple sources (C has two), the first source's
        first task is returned.
    tasks_cap
        If given, cap to the first ``tasks_cap`` tasks across all sources in
        the category.
    """
    if category not in CATEGORY_SOURCES:
        raise ValueError(f"unknown category {category!r}")

    pairs: list[tuple[str, Any]] = []
    for source in CATEGORY_SOURCES[category]:
        if source == "humaneval_plus":
            from benchmark.humaneval_plus.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=10))
        elif source == "swebench_verified":
            from benchmark.swebench_verified.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=10))
        elif source == "bigcodebench_hard":
            from benchmark.bigcodebench_hard.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=5))
        elif source == "custom_arch":
            from benchmark.custom_arch.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks())
        else:  # pragma: no cover — guarded by CATEGORY_SOURCES
            raise ValueError(f"unknown source {source!r}")

    if smoke:
        pairs = pairs[:1]
    elif tasks_cap is not None:
        pairs = pairs[:tasks_cap]
    return pairs


@dataclass
class TaskPlan:
    """One item in the planned sweep: which task, from which source, under which route."""

    category: str
    source: str
    task: Any  # a benchmark-adapter Task dataclass (duck-typed)
    route: str

    @property
    def task_id(self) -> str:
        return getattr(self.task, "id", "<unknown>")


def build_task_plan(
    categories: Iterable[str],
    routes: Iterable[str],
    smoke: bool,
    tasks_cap: int | None,
) -> list[TaskPlan]:
    """Enumerate ``(category, source, task, route)`` tuples in deterministic order.

    Order: by category letter, then by task index within the category, then by
    route order as given in ``routes``.
    """
    cats = list(categories)
    rts = list(routes)
    plan: list[TaskPlan] = []
    for cat in cats:
        pairs = load_category_tasks(cat, smoke=smoke, tasks_cap=tasks_cap)
        for source, task in pairs:
            for route in rts:
                plan.append(
                    TaskPlan(category=cat, source=source, task=task, route=route)
                )
    return plan


# --------------------------------------------------------------------------- #
# Resume-safety
# --------------------------------------------------------------------------- #


def pair_already_done(raw_path: Path, task_id: str, route: str) -> bool:
    """True iff ``raw.jsonl`` already contains a row for (task_id, route)."""
    if not raw_path.exists():
        return False
    rows = load_results(raw_path)
    for r in rows:
        if r.task_id == task_id and r.route == route:
            return True
    return False


# --------------------------------------------------------------------------- #
# Runner dispatch
# --------------------------------------------------------------------------- #


def _runner_for(route: str) -> Callable[..., ResultRow]:
    if route == "R1":
        from runners import r1_cloud_only

        return r1_cloud_only.run
    if route == "R2":
        from runners import r2_local_only

        return r2_local_only.run
    if route == "R3":
        from runners import r3_hybrid_architect

        return r3_hybrid_architect.run
    if route == "R4":
        from runners import r4_minion

        return r4_minion.run
    raise ValueError(f"unknown route {route!r}")


def _read_output_text(row: ResultRow) -> str:
    """Read the model output text that ``row.output_ref`` points at.

    For R1/R2 the output_ref is a plain ``.txt`` with the cleaned content.
    For R3 it's a ``.r3.arch.json`` file; the usable final answer lives in
    ``<...>.r3.answer.txt`` next to it.
    """
    ref = row.output_ref
    if not ref:
        return ""
    p = Path(ref)
    if not p.is_absolute():
        # relative to repo root
        p = _repo_root() / p
    if not p.exists():
        return ""
    if p.suffix == ".json" and p.name.endswith(".r3.arch.json"):
        answer = p.with_name(p.name.replace(".arch.json", ".answer.txt"))
        if answer.exists():
            return answer.read_text(encoding="utf-8")
        # Fall back to the trace's finalOutput.
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            return (payload.get("arch") or {}).get("finalOutput") or ""
        except Exception:  # pragma: no cover — defensive
            return ""
    return p.read_text(encoding="utf-8")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def score_row(row: ResultRow, source: str, task: Any) -> Quality | None:
    """Score ``row`` in place-ish (returns a Quality the caller must attach).

    Skips scoring and returns None for:
      - rows with ``error`` set
      - category-C ``custom_arch`` tasks (judge phase handles these)
    """
    if row.error:
        return None

    model_output = _read_output_text(row)

    if source in ("humaneval_plus", "bigcodebench_hard"):
        from scorers import functional_python

        try:
            return functional_python.score(task, model_output)
        except Exception as exc:  # pragma: no cover — scorer should handle its own errors
            logger.warning("functional_python.score failed for %s: %s", row.task_id, exc)
            return None

    if source == "swebench_verified":
        from scorers import swebench as swebench_scorer

        try:
            return swebench_scorer.score(task, model_output)
        except Exception as exc:  # pragma: no cover
            logger.warning("swebench.score failed for %s: %s", row.task_id, exc)
            return None

    if source == "custom_arch":
        # Category-C hand-curated — judge runs in T4.3. Leave quality empty.
        return None

    logger.warning("no scorer wired up for source %r", source)
    return None


# --------------------------------------------------------------------------- #
# Per-pair execution
# --------------------------------------------------------------------------- #


def run_pair(
    plan_item: TaskPlan,
    *,
    proxy_url: str,
    hardware_profile_ref: str,
    outputs_dir: Path,
    raw_path: Path,
    skip_scoring: bool,
) -> ResultRow:
    """Execute one (task, route) pair end-to-end: runner → score → append.

    Returns the ResultRow so the caller can format a progress line.
    """
    runner = _runner_for(plan_item.route)
    row = runner(
        plan_item.task,
        proxy_url=proxy_url,
        hardware_profile_ref=hardware_profile_ref,
        output_dir=outputs_dir,
    )

    if not skip_scoring:
        quality = score_row(row, plan_item.source, plan_item.task)
        if quality is not None:
            row.quality = quality

    append_row(raw_path, row)
    return row


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #


def timestamp_dirname() -> str:
    """Return ``YYYY-MM-DD_HHMMSS_<hostname-short>`` for the default --out."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    try:
        host = socket.gethostname().split(".")[0]
    except Exception:  # pragma: no cover
        host = "unknown"
    return f"{ts}_{host}"
