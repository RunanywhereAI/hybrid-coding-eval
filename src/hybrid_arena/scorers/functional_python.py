"""Functional Python scorer.

Given a model-generated answer and a task, verify whether the generated
code actually passes the task's authored tests.

The scorer runs pytest inside the ephemeral Docker sandbox from
:mod:`hybrid_arena.core.sandbox` (``network=none``, memory + pids
caps, wall-clock timeout) so untrusted model output can't touch the host.

Public API
----------

``score(task, model_output, timeout_s=60, image=None) -> Quality``

- Extracts Python source from ``model_output`` (handles raw code,
  ```python fences, bare ``` fences, surrounding prose, and multiple
  fences).
- Assembles ``solution.py`` + a per-task ``test_solution.py``.
- Runs pytest in a sandbox, parses the summary line, and returns a
  :class:`hybrid_arena.core.metrics.Quality` with
  ``functional_pass``, ``tests_passed``/``tests_total``, and ``composite``.

Image strategy
--------------

Prefer ``hybrid-eval-python:latest`` — a custom image (see
``scorers/Dockerfile.functional_python``) with pytest + the union of
third-party libs used by our task samples pre-installed. This is
required because the sandbox runs with ``network=none`` so we can't
pip-install anything at test time.

If that image isn't available the caller can pass ``image=...`` to
override; we'll also transparently fall back to ``python:3.11-slim``
with a ``unittest``-only command, which is enough for HumanEval+ but
will fail BigCodeBench-Hard tasks that need numpy/pandas/etc.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from hybrid_arena.core.metrics import Quality
from hybrid_arena.core.sandbox import run_in_sandbox

logger = logging.getLogger(__name__)


# Default image with pytest + all libs baked in. Built from
# scorers/Dockerfile.functional_python.
DEFAULT_IMAGE = "hybrid-eval-python:latest"

# Fallback image when the custom one isn't built. Has no pytest and no
# third-party libs; suitable only for pure-stdlib HumanEval+ tasks, and
# even then we have to use unittest.
_FALLBACK_IMAGE = "python:3.11-slim"


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


# Match fenced code blocks. Captures the optional language tag and the
# body. Non-greedy over the body so back-to-back fences don't merge.
_FENCE_RE = re.compile(
    r"```([A-Za-z0-9_+-]*)\s*\n(.*?)\n```",
    re.DOTALL,
)


def extract_python_code(model_output: str) -> str:
    """Extract Python source from a raw model response.

    Handles, in priority order:

    1. One or more triple-backtick fenced blocks. Python-tagged blocks
       are preferred; if none are tagged python/py but untagged fences
       exist, those are used. When multiple python blocks are present
       we concatenate them (models sometimes emit helper + main in
       separate fences).
    2. No fences → treat the entire message as code.
    3. Nothing that looks like code → return ``""`` so the caller can
       record a functional failure.

    We do *not* attempt to prune prose that sits outside fences; those
    are dropped by virtue of us only returning the fenced content.
    """
    if model_output is None:
        return ""
    if not model_output.strip():
        return ""

    # Fence search runs on the original text so offsets/indentation
    # inside the fences survive unchanged.
    matches = _FENCE_RE.findall(model_output)
    if not matches:
        # No fences at all — assume the whole thing is code. Preserve
        # *leading* indentation: HumanEval+ canonical solutions are
        # function bodies indented under the prompt; stripping the
        # leading whitespace would re-anchor ``def`` at column 0 and
        # defeat ``_looks_like_body_only``.
        return model_output.rstrip() + "\n"

    python_tags = {"python", "py", "python3"}
    tagged = [body for lang, body in matches if lang.lower() in python_tags]
    untagged = [body for lang, body in matches if lang == ""]

    if tagged:
        chunks = tagged
    elif untagged:
        chunks = untagged
    else:
        # Fences exist but all have non-python language tags (e.g. ```sh).
        # Fall back to treating the whole message as code.
        return model_output

    # Put the largest block first — models sometimes emit a tiny example
    # fence before the real solution, or vice versa. Largest-first makes
    # `from solution import X` find the intended symbol; the others are
    # appended in original order for helpers.
    ordered = sorted(enumerate(chunks), key=lambda p: (-len(p[1]), p[0]))
    primary = ordered[0][1]
    rest = [chunks[i] for i, _ in sorted(ordered[1:], key=lambda p: p[0])]

    joined = primary
    for block in rest:
        joined = joined.rstrip() + "\n\n" + block
    return joined


# ---------------------------------------------------------------------------
# Task-type detection + harness assembly
# ---------------------------------------------------------------------------


def _task_kind(task: Any) -> str:
    """Return ``'humaneval'`` or ``'bigcodebench'`` based on task shape."""
    # HumanEval+ Task has ``tests``; BigCodeBench-Hard Task has ``test``.
    if hasattr(task, "tests") and getattr(task, "tests"):
        return "humaneval"
    if hasattr(task, "test") and getattr(task, "test"):
        return "bigcodebench"
    raise ValueError(
        "Task does not look like HumanEval+ or BigCodeBench-Hard "
        "(missing `tests` / `test` attribute)."
    )


def _humaneval_prelude(task: Any) -> str:
    """For HumanEval+, the canonical solution is just the function body
    (indented under the prompt's ``def ...:``). If the model returns only
    a body, we need to prepend the prompt so the result is a real module.
    We detect this heuristically: if the extracted code has no top-level
    ``def`` / ``class`` matching the entry point and starts with indented
    lines, we assume body-only and prepend ``task.prompt``."""
    return task.prompt


def _looks_like_body_only(code: str, entry_point: str) -> bool:
    """Heuristic: the code is just an indented function body, not a full
    module. True if there's no unindented ``def <entry_point>`` anywhere."""
    if not code.strip():
        return True
    # Quick path: any line starting with ``def <entry_point>`` (no indent)?
    for line in code.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(f"def {entry_point}") and line == stripped:
            return False
    return True


def _build_humaneval_harness(task: Any, solution_code: str) -> dict[str, str]:
    """Assemble files for a HumanEval+ task.

    HumanEval+ tests are shaped like::

        def check(candidate):
            assert candidate("10") == 10, "Test 1"
            ...

    We run them by calling ``check(<entry_point>)`` from a pytest test
    function. One model submission → one pytest test → one pass/fail row.
    """
    if _looks_like_body_only(solution_code, task.entry_point):
        # Model returned body only; prepend the prompt (which includes
        # ``def <entry_point>(...):`` and the docstring).
        full_solution = task.prompt.rstrip() + "\n" + solution_code + "\n"
    else:
        full_solution = solution_code + "\n"

    tests_src = task.tests

    test_harness = (
        "from solution import " + task.entry_point + "\n"
        "\n"
        + tests_src
        + "\n\n"
        "def test_check():\n"
        "    check(" + task.entry_point + ")\n"
    )

    return {
        "solution.py": full_solution,
        "test_solution.py": test_harness,
    }


def _build_bigcodebench_harness(task: Any, solution_code: str) -> dict[str, str]:
    """Assemble files for a BigCodeBench-Hard task.

    BCB tests are typically ``unittest.TestCase`` classes and reference
    the function directly (``task_func(...)``). The canonical solution
    is a body under a signature in ``complete_prompt``; model outputs
    usually include the full signature. We handle both by checking for
    a top-level ``def task.entry_point`` and, if absent, prepending the
    complete prompt (which contains the signature + imports).
    """
    if _looks_like_body_only(solution_code, task.entry_point):
        full_solution = task.metadata.get("complete_prompt") or getattr(
            task, "complete_prompt", ""
        )
        if not full_solution:
            # Fall back: no prompt to prepend, use code as-is.
            full_solution = solution_code
        else:
            full_solution = full_solution.rstrip() + "\n" + solution_code + "\n"
    else:
        full_solution = solution_code + "\n"

    # BCB tests import nothing from the module: they use the symbol as a
    # bare name. We prepend a wildcard import and dependency imports.
    test_harness = (
        "from solution import *  # noqa: F401,F403\n"
        "from solution import " + task.entry_point + "  # noqa: F401\n"
        "\n" + task.test + "\n"
    )

    return {
        "solution.py": full_solution,
        "test_solution.py": test_harness,
    }


# ---------------------------------------------------------------------------
# pytest output parsing
# ---------------------------------------------------------------------------


# pytest prints a summary like::
#   =========== 3 passed, 1 failed, 2 errors in 0.42s ===========
# or
#   =========== 5 passed in 0.42s ==========
# or when collection fails entirely:
#   =========== no tests ran in 0.01s ===========
_SUMMARY_COUNT_RE = re.compile(
    r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)",
)


def _parse_pytest_summary(stdout: str, stderr: str) -> tuple[int, int]:
    """Return ``(tests_passed, tests_total)`` parsed from pytest output.

    Looks at the last summary line containing ``passed`` / ``failed`` /
    ``errors``. Returns ``(0, 0)`` if no summary is found (caller treats
    that as a collection failure → 0 passed out of the expected N).
    """
    blob = (stdout or "") + "\n" + (stderr or "")
    passed = failed = errors = xfailed = xpassed = skipped = 0
    found = False
    # Scan all matches; pytest can print per-line status too. The summary
    # line aggregates them, but multiple matches don't hurt — we just
    # prefer the last lines of output which contain the final tally.
    # To that end, work on the tail only.
    tail = blob[-4096:]
    for m in _SUMMARY_COUNT_RE.finditer(tail):
        found = True
        n = int(m.group(1))
        kind = m.group(2).rstrip("s")  # "errors" -> "error"
        if kind == "passed":
            passed = max(passed, n)
        elif kind == "failed":
            failed = max(failed, n)
        elif kind == "error":
            errors = max(errors, n)
        elif kind == "xfailed":
            xfailed = max(xfailed, n)
        elif kind == "xpassed":
            xpassed = max(xpassed, n)
        elif kind == "skipped":
            skipped = max(skipped, n)

    if not found:
        return (0, 0)

    total = passed + failed + errors + xfailed + xpassed + skipped
    return (passed, total)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _zero_quality(tests_total_guess: int = 0) -> Quality:
    return Quality(
        functional_pass=False,
        tests_passed=0,
        tests_total=tests_total_guess,
        composite=0.0,
    )


def score(
    task: Any,
    model_output: str,
    timeout_s: int = 60,
    image: str | None = None,
    memory_mb: int = 1024,
    pids_limit: int = 256,
) -> Quality:
    """Score a model response against a task's authored tests.

    Parameters
    ----------
    task:
        A task object from ``benchmark.humaneval_plus.adapter.Task`` or
        ``benchmark.bigcodebench_hard.adapter.Task``. Duck-typed.
    model_output:
        Raw model response. May contain markdown prose, fenced code
        blocks, or bare code.
    timeout_s:
        Wall-clock timeout for the pytest run inside the sandbox.
    image:
        Override the sandbox Docker image. Default:
        ``hybrid-eval-python:latest`` (see
        ``scorers/Dockerfile.functional_python``).
    memory_mb:
        Memory cap passed through to ``core.sandbox.run_in_sandbox``.
        Defaults to 1 GB, higher than the sandbox default to
        accommodate numpy/pandas/matplotlib in BigCodeBench-Hard.
    pids_limit:
        Process cap passed through to the sandbox.

    Returns
    -------
    Quality
        ``functional_pass`` is ``True`` iff ``tests_passed == tests_total``
        *and* ``tests_total > 0``. ``composite`` is
        ``tests_passed / tests_total`` (0.0 when total==0).
    """
    kind = _task_kind(task)
    solution_code = extract_python_code(model_output)

    if not solution_code.strip():
        logger.info(
            "score: empty code extraction for task id=%s kind=%s",
            getattr(task, "id", "<unknown>"),
            kind,
        )
        return _zero_quality()

    if kind == "humaneval":
        files = _build_humaneval_harness(task, solution_code)
    else:
        files = _build_bigcodebench_harness(task, solution_code)

    chosen_image = image or DEFAULT_IMAGE

    # ``pytest-timeout`` installed in the custom image; we also pass the
    # wall-clock timeout at the sandbox layer as a hard floor.
    test_cmd = [
        "python",
        "-m",
        "pytest",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "test_solution.py",
    ]

    try:
        result = run_in_sandbox(
            files=files,
            test_cmd=test_cmd,
            timeout_s=timeout_s,
            image=chosen_image,
            memory_mb=memory_mb,
            pids_limit=pids_limit,
            network="none",
        )
    except RuntimeError as exc:
        # Docker not available / image pull failure. Surface as a failed
        # score rather than crashing the orchestrator.
        logger.warning(
            "score: sandbox unavailable for task id=%s: %s",
            getattr(task, "id", "<unknown>"),
            exc,
        )
        return _zero_quality()

    passed, total = _parse_pytest_summary(result.stdout, result.stderr)

    if total == 0:
        # Likely a collection error (import failed, syntax error in
        # solution, etc.). Record it as a hard failure with the task
        # name in the log for forensics.
        logger.info(
            "score: no tests collected for task id=%s stderr_tail=%s",
            getattr(task, "id", "<unknown>"),
            (result.stderr or "")[-400:],
        )
        return _zero_quality()

    functional_pass = (passed == total) and result.passed and not result.timed_out
    composite = passed / total if total > 0 else 0.0

    return Quality(
        functional_pass=bool(functional_pass),
        tests_passed=passed,
        tests_total=total,
        composite=composite,
    )


__all__ = ["score", "extract_python_code", "DEFAULT_IMAGE"]
