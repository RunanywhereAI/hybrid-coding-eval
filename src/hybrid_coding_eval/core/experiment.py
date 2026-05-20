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
#: Category D = real_dev (real-developer tasks, 5 shapes D1-D5).
CATEGORY_SOURCES: dict[str, list[str]] = {
    "A": ["humaneval_plus"],
    "B": ["swebench_verified"],
    "C": ["bigcodebench_hard", "custom_arch"],
    "D": ["real_dev"],
    # Category X is the agent-benchmark sweep. X = ``exercism_python`` for R7
    # (single-language polyglot subset). SWE-bench Verified for R6 is loaded
    # via the existing "B" path; real_dev D1+D5 for R8 via "D".
    "X": ["exercism_python"],
}

#: Valid --routes values. R6/R7/R8 are *agent-loop* routes (mini-swe-agent,
#: aider, opencode) added in v4. They differ from R1-R5 in that they wrap an
#: external coding-agent process and let it drive multi-turn tool use; only
#: the routing of each LLM call (per-strategy) is this repo's concern.
ROUTES: tuple[str, ...] = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8")


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
            from hybrid_coding_eval.benchmarks.humaneval_plus.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=10))
        elif source == "swebench_verified":
            from hybrid_coding_eval.benchmarks.swebench_verified.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=10))
        elif source == "bigcodebench_hard":
            from hybrid_coding_eval.benchmarks.bigcodebench_hard.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks(n=5))
        elif source == "custom_arch":
            from hybrid_coding_eval.benchmarks.custom_arch.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks())
        elif source == "real_dev":
            from hybrid_coding_eval.benchmarks.real_dev.adapter import load_tasks

            pairs.extend((source, t) for t in load_tasks())
        elif source == "exercism_python":
            from hybrid_coding_eval.benchmarks.exercism_python.adapter import (
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
    task_ids: Iterable[str] | None = None,
) -> list[TaskPlan]:
    """Enumerate ``(category, source, task, route)`` tuples in deterministic order.

    Order: by category letter, then by task index within the category, then by
    route order as given in ``routes``.

    ``task_ids`` (optional): if provided, tasks whose ``id`` is not in this
    whitelist are dropped after loading. Useful for scoping a sweep to a
    specific set of R7-compatible D1+D5 tasks (v1.3+).
    """
    cats = list(categories)
    rts = list(routes)
    id_filter = set(task_ids) if task_ids else None
    plan: list[TaskPlan] = []
    for cat in cats:
        # When task_ids is set, bypass tasks_cap at load time — the cap is
        # uniform-per-category and would slice off tasks before the
        # whitelist filter ran (v1.3 expanded sweep wants 8 D-tasks but
        # real_dev has 20 total, so cap=8 picks arbitrary 8 most of which
        # aren't in the whitelist). Load all, then filter, then trust the
        # whitelist as the cap.
        cap_for_load = None if id_filter is not None else tasks_cap
        pairs = load_category_tasks(cat, smoke=smoke, tasks_cap=cap_for_load)
        for source, task in pairs:
            if id_filter is not None and getattr(task, "id", None) not in id_filter:
                continue
            for route in rts:
                plan.append(
                    TaskPlan(category=cat, source=source, task=task, route=route)
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


def _runner_for(route: str) -> Callable[..., ResultRow]:
    if route == "R1":
        from hybrid_coding_eval.runners import r1_cloud_only

        return r1_cloud_only.run
    if route == "R2":
        from hybrid_coding_eval.runners import r2_local_only

        return r2_local_only.run
    if route == "R3":
        from hybrid_coding_eval.runners import r3_hybrid_architect

        return r3_hybrid_architect.run
    if route == "R4":
        from hybrid_coding_eval.runners import r4_minion

        return r4_minion.run
    if route == "R5":
        from hybrid_coding_eval.runners import r5_devminion

        return r5_devminion.run
    if route == "R6":
        from hybrid_coding_eval.runners import r6_mini_swe_agent

        return r6_mini_swe_agent.run
    if route == "R7":
        from hybrid_coding_eval.runners import r7_aider

        return r7_aider.run
    if route == "R8":
        from hybrid_coding_eval.runners import r8_opencode

        return r8_opencode.run
    if route in ("R10", "cline"):
        from hybrid_coding_eval.runners import r10_cline

        return r10_cline.run
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
    from .paths import repo_root

    return repo_root()


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def score_row(row: ResultRow, source: str, task: Any) -> Quality | None:
    """Score ``row`` in place-ish (returns a Quality the caller must attach).

    Skips scoring and returns None for:
      - rows with ``error`` set
      - category-C ``custom_arch`` tasks (judge phase handles these)
      - rows where the runner already produced a definitive
        ``functional_pass`` (agentic R6/R7/R8 score inside their own
        Docker sandbox; re-overlaying the agent's output on a clean
        fixture would lose its work). ``Quality()`` empty (everything
        None) is treated as "not yet scored" and dispatches as usual.
    """
    if row.error:
        return None

    if row.quality is not None and row.quality.functional_pass is not None:
        return None

    model_output = _read_output_text(row)

    if source in ("humaneval_plus", "bigcodebench_hard"):
        from hybrid_coding_eval.scorers import functional_python

        try:
            return functional_python.score(task, model_output)
        except Exception as exc:  # pragma: no cover — scorer should handle its own errors
            logger.warning("functional_python.score failed for %s: %s", row.task_id, exc)
            return None

    if source == "swebench_verified":
        from hybrid_coding_eval.scorers import swebench as swebench_scorer

        try:
            return swebench_scorer.score(task, model_output)
        except Exception as exc:  # pragma: no cover
            logger.warning("swebench.score failed for %s: %s", row.task_id, exc)
            return None

    if source == "custom_arch":
        # Category-C hand-curated — judge runs in T4.3. Leave quality empty.
        return None

    if source == "real_dev":
        # Category-D scoring (P2.1). Stub currently returns all-None Quality;
        # we still call it so the dispatch wires up end-to-end today.
        from hybrid_coding_eval.benchmarks.real_dev import scorers as real_dev_scorers

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

    ``router_strategy`` is forwarded only to R3, which is the one route
    that actually consults a router-strategy at each step. R1/R2 force
    cloud/local by design; R4/R5 hardwire backends to roles. The kwarg
    defaults to ``heuristic`` to preserve v3 sweep semantics on routes
    that never landed in v3 with anything else.

    Returns the ResultRow so the caller can format a progress line.
    """
    runner = _runner_for(plan_item.route)
    runner_kwargs: dict[str, Any] = {
        "proxy_url": proxy_url,
        "hardware_profile_ref": hardware_profile_ref,
        "output_dir": outputs_dir,
    }
    # R3 and agent-loop routes R6/R7/R8 all consult router_strategy.
    if plan_item.route in ("R3", "R6", "R7", "R8"):
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
