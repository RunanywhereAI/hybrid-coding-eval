"""Orchestrator core for :mod:`bin.run-experiment` (T4.1).

The orchestrator loops over ``(task, route)`` pairs, invokes the right
runner, optionally scores the output, and appends one
:class:`lib.metrics.ResultRow` per pair to ``<out>/raw.jsonl`` *immediately*
so the sweep is resume-safe.

This module holds the benchmark-loading, resume-scan and per-pair
execution helpers. The CLI (``bin/run-experiment.py``) is kept thin.
"""

from __future__ import annotations

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


#: Which benchmark adapters contribute tasks to each task class.
#: v1.4 replaces the category-letter taxonomy (A/B/C/D/X) with three
#: task classes named for the work shape they represent:
#:   * ``puzzles``   → exercism_python (small, isolated function tasks)
#:   * ``refactors`` → real_dev (multi-file refactor / review / script tasks)
#:   * ``real-prs``  → swebench_verified (repo-level patch tasks)
#: The benchmark directory names are unchanged in this phase; Phase 2 of
#: the v1.4 cleanup renames them to match the task classes.
CATEGORY_SOURCES: dict[str, list[str]] = {
    "puzzles": ["puzzles"],
    "refactors": ["refactors"],
    "real-prs": ["real_prs"],
}

#: Valid --routes values. R6/R7/R8 are *agent-loop* routes (mini-swe-agent,
#: aider, opencode). R9/R10 (claude-code, cline) are added in parallel by
#: Agents B/C during the v1.4 cleanup; the dispatch entries for them live in
#: :func:`_runner_for` below.
ROUTES: tuple[str, ...] = ("mini-swe-agent", "aider", "opencode", "claude-code", "cline")


# --------------------------------------------------------------------------- #
# Task loading
# --------------------------------------------------------------------------- #


def load_category_tasks(
    category: str,
    smoke: bool = False,
    tasks_cap: int | None = None,
) -> list[tuple[str, Any]]:
    """Return ``[(source, task), ...]`` for a task class.

    Parameters
    ----------
    category
        One of ``"puzzles"``, ``"refactors"``, ``"real-prs"``.
    smoke
        If True, take only the first task (deterministic).
    tasks_cap
        If given, cap to the first ``tasks_cap`` tasks across all sources in
        the class.
    """
    if category not in CATEGORY_SOURCES:
        raise ValueError(f"unknown task class {category!r}")

    pairs: list[tuple[str, Any]] = []
    for source in CATEGORY_SOURCES[category]:
        if source == "real_prs":
            from hybrid_coding_eval.tasks.real_prs.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=10))
        elif source == "refactors":
            from hybrid_coding_eval.tasks.refactors.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks())
        elif source == "puzzles":
            from hybrid_coding_eval.tasks.puzzles.adapter import (
                load_tasks,
            )

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
    """One item in the planned sweep: which task, from which source, under which agent."""

    task_class: str
    source: str
    task: Any  # a task-adapter Task dataclass (duck-typed)
    agent: str

    @property
    def task_id(self) -> str:
        return getattr(self.task, "id", "<unknown>")


def build_task_plan(
    task_classes: Iterable[str],
    agents: Iterable[str],
    smoke: bool,
    tasks_cap: int | None,
    task_ids: Iterable[str] | None = None,
) -> list[TaskPlan]:
    """Enumerate ``(task_class, source, task, route)`` tuples in deterministic order.

    Order: by task class as given in ``categories``, then by task index
    within the class, then by route order as given in ``routes``.

    ``task_ids`` (optional): if provided, tasks whose ``id`` is not in this
    whitelist are dropped after loading. Useful for scoping a sweep to a
    specific set of agent-compatible tasks.
    """
    cats = list(task_classes)
    agnt = list(agents)
    id_filter = set(task_ids) if task_ids else None
    plan: list[TaskPlan] = []
    for cls in cats:
        # When task_ids is set, bypass tasks_cap at load time — the cap is
        # uniform-per-class and would slice off tasks before the whitelist
        # filter ran. Load all, then filter, then trust the whitelist as
        # the cap.
        cap_for_load = None if id_filter is not None else tasks_cap
        pairs = load_category_tasks(cls, smoke=smoke, tasks_cap=cap_for_load)
        for source, task in pairs:
            if id_filter is not None and getattr(task, "id", None) not in id_filter:
                continue
            for agent in agnt:
                plan.append(
                    TaskPlan(task_class=cls, source=source, task=task, agent=agent)
                )
    return plan


# --------------------------------------------------------------------------- #
# Resume-safety
# --------------------------------------------------------------------------- #


def pair_already_done(
    raw_path: Path,
    task_id: str,
    route: str,
    router_strategy: str | None = None,
) -> bool:
    """True iff ``raw.jsonl`` already contains a row for the triple
    ``(task_id, route, router_strategy)``.

    The strategy axis was added in v4 (R6/R7/R8) so multiple invocations
    of the same (task, route) under different strategies coexist in one
    raw.jsonl. Matching rules:

      * Search ``router_strategy`` is ``None``       → match any row.
      * Row's ``router_strategy`` is ``None``        → match (v3 rows
        predate the field; treat as wildcard for back-compat).
      * Both present                                  → exact match.
    """
    if not raw_path.exists():
        return False
    rows = load_results(raw_path)
    for r in rows:
        if r.task_id == task_id and r.route == route:
            if (
                router_strategy is None
                or r.router_strategy is None
                or r.router_strategy == router_strategy
            ):
                return True
    return False


# --------------------------------------------------------------------------- #
# Runner dispatch
# --------------------------------------------------------------------------- #


def _runner_for(agent: str) -> Callable[..., ResultRow]:
    """Dispatch an agent name to its runner. v1.4: only agent-loop routes remain."""
    if agent == "mini-swe-agent":
        from hybrid_coding_eval.agents import mini_swe

        return mini_swe.run
    if agent == "aider":
        from hybrid_coding_eval.agents import aider

        return aider.run
    if agent == "opencode":
        from hybrid_coding_eval.agents import opencode

        return opencode.run
    if agent == "claude-code":
        from hybrid_coding_eval.agents import claude_code

        return claude_code.run
    if agent == "cline":
        from hybrid_coding_eval.agents import cline

        return cline.run
    raise ValueError(f"unknown agent {agent!r}")


def _read_output_text(row: ResultRow) -> str:
    """Read the model output text that ``row.output_ref`` points at.

    Agent-loop routes (R6/R7/R8 and R9/R10) write a plain ``.txt`` with
    the cleaned final-turn content; that's the only shape we need to
    handle post-v1.4 cleanup.
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
    return p.read_text(encoding="utf-8")


def _repo_root() -> Path:
    from .paths import repo_root

    return repo_root()


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def score_row(row: ResultRow, source: str, task: Any) -> Quality | None:
    """Score ``row`` in place-ish (returns a Quality the caller must attach).

    Skips scoring and returns None for:
      - rows with ``error`` set
      - rows where the runner already produced a definitive
        ``functional_pass`` (agent-loop routes score inside their own
        Docker sandbox; re-overlaying the agent's output on a clean
        fixture would lose its work). ``Quality()`` empty (everything
        None) is treated as "not yet scored" and dispatches as usual.
    """
    if row.error:
        return None

    if row.quality is not None and row.quality.functional_pass is not None:
        return None

    model_output = _read_output_text(row)

    if source == "real_prs":
        from hybrid_coding_eval.scorers import swebench as swebench_scorer

        try:
            return swebench_scorer.score(task, model_output)
        except Exception as exc:  # pragma: no cover
            logger.warning("swebench.score failed for %s: %s", row.task_id, exc)
            return None

    if source == "real_dev":
        from hybrid_coding_eval.tasks.refactors import scorers as real_dev_scorers

        try:
            return real_dev_scorers.score(task, model_output, context={})
        except Exception as exc:  # pragma: no cover — scorer should handle its own errors
            logger.warning("real_dev.score failed for %s: %s", row.task_id, exc)
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
    router_strategy: str = "heuristic",
) -> ResultRow:
    """Execute one (task, route) pair end-to-end: runner → score → append.

    ``router_strategy`` is forwarded to every agent-loop route — they all
    consult the router proxy at each step to decide local-vs-cloud per
    call. Defaults to ``heuristic``.

    Returns the ResultRow so the caller can format a progress line.
    """
    runner = _runner_for(plan_item.agent)
    runner_kwargs: dict[str, Any] = {
        "proxy_url": proxy_url,
        "hardware_profile_ref": hardware_profile_ref,
        "output_dir": outputs_dir,
    }
    # Agent-loop routes all consult router_strategy.
    if plan_item.agent in ("mini-swe-agent", "aider", "opencode", "claude-code", "cline"):
        runner_kwargs["router_strategy"] = router_strategy
    row = runner(plan_item.task, **runner_kwargs)
    # Stamp the strategy onto the row regardless of route, so downstream
    # analysis can group by (route, router_strategy) cleanly.
    if row.router_strategy is None:
        row.router_strategy = router_strategy

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
