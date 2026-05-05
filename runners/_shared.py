"""Shared helpers for the R1/R2/R3 runners.

Kept deliberately small — this file only owns:

* :func:`task_prompt` — build the single user-facing prompt string for any
  benchmark task, so R1 (cloud-only), R2 (local-only), and R3 (architect
  mode) all send the *same* prompt and comparisons are apples-to-apples.
* :func:`proxy_health` — quick check that the router proxy is up. Tests
  use this to ``pytest.skip`` cleanly when the router isn't running.
* :func:`load_task_by_id` — adapter-agnostic task loader used by the
  per-runner CLIs.

T2.1 (R1) and T2.2 (R2) are being built in parallel by sibling agents;
this module may be extended by whichever runner lands first. Keep the
public surface stable.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
#
# Design: every task category gets a prompt that asks for the deliverable in
# a shape the scorers can parse. For HumanEval+/BigCodeBench-Hard, scorers
# want *just the function body/module*. For SWE-bench, scorers want a unified
# diff patch. For Category C (architecture/reasoning), scorers want prose.
#
# Architect mode (R3) receives the same prompt and decomposes it internally;
# that keeps R1 vs R3 comparisons clean (same input, different strategy).


_HUMANEVAL_TEMPLATE = """\
You are given a Python function stub. Complete it so that every docstring
example passes and all reasonable edge cases are handled.

Return ONLY a single Python code block containing the COMPLETE function
definition (including the `def` line). Do not include any explanation,
tests, or prose outside the code block.

{prompt}
"""

_BIGCODEBENCH_TEMPLATE = """\
Implement the Python function described below. Use the standard-library
or third-party imports listed in the prompt; do not invent new ones.

Return ONLY a single Python code block containing the COMPLETE function
definition. Do not include tests, example calls, or prose outside the
code block.

{prompt}
"""

_SWEBENCH_TEMPLATE = """\
You are fixing a bug in an open-source repository. The repository is
`{repo}` at commit `{base_commit}`.

Problem statement:
{problem_statement}

{hints_block}Produce a unified `diff` patch that, when applied with
`git apply`, resolves the problem. The patch MUST:

  * start each file block with `diff --git a/<path> b/<path>`;
  * include `---`/`+++` headers with correct paths;
  * contain valid `@@` hunk headers;
  * modify only the files necessary to fix the issue.

Return ONLY the patch inside a single ```diff ... ``` code block. No
prose before or after.
"""

_CUSTOM_ARCH_TEMPLATE = """\
{context}

TASK:
{prompt}

Write a clear, well-structured answer. Use headings and bullet points
where they improve readability. Be specific — cite concrete trade-offs,
edge cases, and failure modes rather than giving generic advice.
"""


def task_prompt(task: Any) -> str:
    """Build the single user prompt string for ``task``.

    ``task`` is a dataclass from one of the four benchmark adapters; we
    duck-type on category + fields rather than importing every adapter
    eagerly.
    """
    cat = getattr(task, "category", None)
    # HumanEval+ (category A) — task.prompt is a stub with docstring.
    if cat == "A":
        return _HUMANEVAL_TEMPLATE.format(prompt=task.prompt)
    # BigCodeBench-Hard (category C). Adapter exposes `instruct_prompt` +
    # `complete_prompt`; we prefer instruct (richer) with complete as a
    # fallback. `task.prompt` does NOT exist on this adapter.
    tid = getattr(task, "id", "") or ""
    if tid.startswith("bigcodebench-hard/"):
        prompt = (
            getattr(task, "instruct_prompt", None)
            or getattr(task, "complete_prompt", None)
            or ""
        )
        return _BIGCODEBENCH_TEMPLATE.format(prompt=prompt)
    # Custom arch (category C, id prefix custom-arch/). Has `context` + `prompt`.
    if tid.startswith("custom-arch/") or hasattr(task, "rubric"):
        return _CUSTOM_ARCH_TEMPLATE.format(
            context=getattr(task, "context", "") or "",
            prompt=task.prompt,
        )
    # SWE-bench Verified (category B). Has `problem_statement`, `repo`,
    # `base_commit`, and optionally `hints_text`.
    if cat == "B" or hasattr(task, "problem_statement"):
        hints = (getattr(task, "hints_text", "") or "").strip()
        hints_block = f"Maintainer hints:\n{hints}\n\n" if hints else ""
        return _SWEBENCH_TEMPLATE.format(
            repo=task.repo,
            base_commit=task.base_commit,
            problem_statement=task.problem_statement,
            hints_block=hints_block,
        )
    # Fallback: treat as a bare prompt string.
    return getattr(task, "prompt", str(task))


# --------------------------------------------------------------------------- #
# Proxy health
# --------------------------------------------------------------------------- #


def proxy_health(proxy_url: str, timeout_s: float = 2.0) -> bool:
    """Return True iff the router proxy at ``proxy_url`` answers on ``/v1/models``.

    Never raises — any error is collapsed to False so tests can skip
    cleanly without a traceback.
    """
    url = proxy_url.rstrip("/") + "/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            if resp.status != 200:
                return False
            body = resp.read()
            d = json.loads(body)
            return isinstance(d, dict) and d.get("object") == "list"
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False


# --------------------------------------------------------------------------- #
# Adapter-agnostic task loader (used by CLI entrypoints)
# --------------------------------------------------------------------------- #


def load_task_by_id(task_source: str, task_id: str) -> Any:
    """Look up a single task across the four benchmark adapters.

    ``task_source`` is one of: ``humaneval_plus``, ``swebench_verified``,
    ``bigcodebench_hard``, ``custom_arch``. ``task_id`` is the short
    per-dataset id (e.g. ``HumanEval_99`` for HumanEval+). The namespace
    prefix is added automatically.
    """
    if task_source == "humaneval_plus":
        from benchmark.humaneval_plus.adapter import load_tasks as loader

        ns = "humaneval-plus/"
    elif task_source == "swebench_verified":
        from benchmark.swebench_verified.adapter import load_tasks as loader

        ns = "swebench-verified/"
    elif task_source == "bigcodebench_hard":
        from benchmark.bigcodebench_hard.adapter import load_tasks as loader

        ns = "bigcodebench-hard/"
    elif task_source == "custom_arch":
        from benchmark.custom_arch.adapter import load_tasks as loader

        ns = "custom-arch/"
    else:
        raise ValueError(f"unknown task_source: {task_source!r}")

    tasks = loader()
    want_full = task_id if task_id.startswith(ns) else ns + task_id
    for t in tasks:
        if t.id == want_full:
            return t
    raise KeyError(
        f"task {task_id!r} not found in {task_source}. "
        f"Available: {[t.id for t in tasks][:5]}..."
    )


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parent.parent
