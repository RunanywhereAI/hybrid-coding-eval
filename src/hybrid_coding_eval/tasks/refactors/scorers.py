"""Scorers for Category-D (real-developer) tasks.

Dispatches on ``task.shape`` to one of five implementations:

- **D1** (small feature) — overlay the model's extracted source on the
  fixture tree, run the task's pytest file in the functional sandbox,
  report ``functional_pass`` + ``tests_passed`` / ``tests_total``.
- **D2** (bug fix) — would grade a unified diff against the upstream
  repo using :mod:`hybrid_coding_eval.scorers.swebench`. The existing
  scorer hard-codes the HF SWE-bench Verified dataset, but our D2 tasks
  reference bug IDs that are NOT in that dataset (e.g. ``pallets__click-3298``).
  Until a small repo-clone + reference-test harness lands, D2 returns
  ``Quality(functional_pass=None)`` so the row survives the sweep without
  being miscounted as a failure. See the long comment in :func:`_score_d2`.
- **D3** (refactor) / **D4** (code review) — historically judged by
  ``scorers.llm_judge.judge_pairwise`` against the gold exemplar under
  ``fixtures/<slug>/_reference/``. ``llm_judge`` was deleted in v1.4 as
  part of the agentic cleanup, so these branches now return an
  unknown :class:`Quality` and are effectively deferred until a
  replacement scoring path lands.
- **D5** (script) — overlay the model's extracted script into the
  fixture tree under the task's expected filename (``solution.py`` or
  ``solution.sh``), then run the task's pytest file (which in turn
  invokes the model's script with the right stdin / args and diffs
  stdout against ``expected.txt``).

All heavy lifting lives in the existing scorer
:mod:`hybrid_coding_eval.scorers.functional_python` and the sandbox
:mod:`hybrid_coding_eval.core.sandbox`. This module is a thin shape
dispatcher + fixture-overlay helper.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from hybrid_coding_eval.core.metrics import Quality
from hybrid_coding_eval.core.sandbox import run_in_sandbox
from hybrid_coding_eval.scorers.functional_python import (
    DEFAULT_IMAGE,
    extract_python_code,
)
from hybrid_coding_eval.scorers.functional_python import (
    _parse_pytest_summary as _parse_pytest_summary,  # re-use
)

from .adapter import Task

logger = logging.getLogger(__name__)

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"
_REFERENCE_SUBDIR = "_reference"

# Sandbox resource caps for real_dev tasks. D1/D5 tests can spin up a
# stdlib HTTPServer or shell out to bash, so we bump pids and memory
# modestly above the functional_python defaults.
_SANDBOX_MEMORY_MB = 1024
_SANDBOX_PIDS = 256
_SANDBOX_TIMEOUT_S = 90


# --------------------------------------------------------------------------- #
# Fixture materialization helpers
# --------------------------------------------------------------------------- #


def _iter_fixture_files(
    fixtures_dir: Path, *, exclude_subdir: str | None = _REFERENCE_SUBDIR
) -> list[tuple[str, str]]:
    """Return ``[(relpath, content), ...]`` for every file under
    ``fixtures_dir``, skipping any path that begins with ``exclude_subdir``
    and the usual housekeeping files.

    Binary files (non-UTF-8) are skipped with a log line — none of the
    current real_dev fixtures are binary.
    """
    if not fixtures_dir.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for child in sorted(fixtures_dir.rglob("*")):
        if not child.is_file():
            continue
        rel = child.relative_to(fixtures_dir)
        parts = rel.parts
        if exclude_subdir and parts and parts[0] == exclude_subdir:
            continue
        if child.name == ".gitkeep":
            continue
        try:
            contents = child.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.info(
                "skipping non-UTF8 fixture file %s: %s", child, exc
            )
            continue
        out.append((rel.as_posix(), contents))
    return out


def _list_reference_targets(fixtures_dir: Path) -> list[str]:
    """Paths (relative to ``fixtures_dir``) of files the model is meant to
    produce. Derived from the ``_reference/`` subdir structure.
    """
    ref = fixtures_dir / _REFERENCE_SUBDIR
    if not ref.is_dir():
        return []
    targets: list[str] = []
    for child in sorted(ref.rglob("*")):
        if not child.is_file() or child.name == ".gitkeep":
            continue
        # Flatten: a file at ``_reference/retry.py`` maps to ``retry.py``
        # in the task root. We assume no subdirs inside _reference for
        # now — no D1/D5 task uses them.
        targets.append(child.relative_to(ref).as_posix())
    return targets


# ---------------------------------------------------------------------------
# Fenced-block parsing (per-filename)
# ---------------------------------------------------------------------------


# Capture ``### filename.ext`` or ``# filename.ext`` or ``**filename.ext**``
# or ``File: filename.ext`` labels immediately preceding a fenced block. We
# scan forward from the label to the next ``` ``` ``` fence.
_LABEL_BEFORE_FENCE_RE = re.compile(
    r"""(?:^|\n)\s*              # line start
        (?:                      # one of the supported label shapes:
            (?:\#{1,6}\s+)                   # ## heading
          | (?:\*\*)                         # **filename**
          | (?:File:\s*)                     # File: foo.py
          | (?:```\w*\s*)                    # ```py:foo.py (we'll re-trim)
        )?
        (?P<name>[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)   # looks like a filename
        \*{0,2}                  # optional trailing **
        \s*\n                    # newline
        (?:[^`]*?)               # possibly more prose
        ```(?P<lang>[A-Za-z0-9_+-]*)\s*\n
        (?P<body>.*?)
        \n```""",
    re.DOTALL | re.VERBOSE,
)

# Generic fenced-block regex (fallback when no filename labels are present).
_FENCE_RE = re.compile(
    r"```(?P<lang>[A-Za-z0-9_+-]*)\s*\n(?P<body>.*?)\n```",
    re.DOTALL,
)


def _extract_labeled_fences(text: str) -> dict[str, str]:
    """Return ``{filename: body}`` for each fenced block preceded by a
    filename-looking label.

    Multiple blocks for the same filename are concatenated in appearance
    order, so a model that emits imports + body in two fences for the same
    file still produces a single coherent content string.
    """
    out: dict[str, str] = {}
    for m in _LABEL_BEFORE_FENCE_RE.finditer(text):
        name = m.group("name").strip()
        body = m.group("body")
        if name in out:
            out[name] = out[name].rstrip() + "\n\n" + body + "\n"
        else:
            out[name] = body + ("\n" if not body.endswith("\n") else "")
    return out


def _extract_files_for_targets(
    model_output: str, targets: list[str]
) -> dict[str, str]:
    """Map the model's output onto the expected target filenames.

    Strategy:

    1. If labeled fences exist, match them by basename (case-insensitive)
       against ``targets``. Models sometimes say ``### src/retry.py``
       when the target is just ``retry.py`` — matching on basename is
       more forgiving.
    2. For any target that stayed unmapped AND there is exactly one
       unused fenced block, assign that block.
    3. For any single-target task (``len(targets) == 1``), fall through
       to :func:`extract_python_code` which handles plain prose-around-code
       too.

    Returns ``{target_relpath: content}`` with at most one entry per
    target. Entries whose body is empty are dropped so the caller can
    tell the model produced nothing.
    """
    if not targets:
        return {}

    labeled = _extract_labeled_fences(model_output)

    out: dict[str, str] = {}
    used_labels: set[str] = set()

    # (1) basename match for labeled fences.
    target_by_basename: dict[str, str] = {}
    for tgt in targets:
        target_by_basename.setdefault(Path(tgt).name.lower(), tgt)

    for label, body in labeled.items():
        tgt = target_by_basename.get(Path(label).name.lower())
        if tgt is not None and tgt not in out and body.strip():
            out[tgt] = body if body.endswith("\n") else body + "\n"
            used_labels.add(label)

    # (2) single-target fallback via extract_python_code — this handles
    # prose-only responses and un-labeled fences uniformly.
    unmapped = [t for t in targets if t not in out]
    if len(targets) == 1 and unmapped:
        body = extract_python_code(model_output)
        if body.strip():
            out[targets[0]] = body if body.endswith("\n") else body + "\n"
    elif unmapped and labeled:
        # Multi-target task with labeled fences — try to fill each missing
        # target from any leftover un-used fence, in order of appearance.
        leftover = [
            (k, v) for k, v in labeled.items() if k not in used_labels
        ]
        for tgt, (_, body) in zip(unmapped, leftover):
            if body.strip():
                out[tgt] = body if body.endswith("\n") else body + "\n"
    elif unmapped and not labeled:
        # No labels and multiple targets — best-effort: bundle the
        # extracted code into the first target. Models that emit a single
        # block for a multi-file task will fail the other tests, which is
        # the right signal.
        body = extract_python_code(model_output)
        if body.strip() and unmapped:
            out[unmapped[0]] = body if body.endswith("\n") else body + "\n"

    return out


# ---------------------------------------------------------------------------
# Pytest-in-sandbox runner
# ---------------------------------------------------------------------------


def _zero_quality(tests_total_guess: int = 0) -> Quality:
    return Quality(
        functional_pass=False,
        tests_passed=0,
        tests_total=tests_total_guess,
        composite=0.0,
    )


def _unknown_quality() -> Quality:
    return Quality(
        functional_pass=None,
        tests_passed=None,
        tests_total=None,
        composite=None,
    )


def _run_pytest_in_sandbox(
    files: dict[str, str],
    test_rel: str,
    *,
    timeout_s: int = _SANDBOX_TIMEOUT_S,
    image: str = DEFAULT_IMAGE,
) -> Quality:
    """Run ``pytest <test_rel>`` inside the functional_python sandbox image
    with ``files`` mounted at ``/workspace``. Returns a scored :class:`Quality`.

    ``test_rel`` must be a path relative to the workdir. Everything in
    ``files`` is visible to pytest during collection and run.
    """
    test_cmd = [
        "python",
        "-m",
        "pytest",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        test_rel,
    ]
    try:
        result = run_in_sandbox(
            files=files,
            test_cmd=test_cmd,
            timeout_s=timeout_s,
            image=image,
            memory_mb=_SANDBOX_MEMORY_MB,
            pids_limit=_SANDBOX_PIDS,
            network="none",
        )
    except RuntimeError as exc:
        # Docker unavailable — return ``None`` quality so aggregators see
        # "not graded" rather than "model failed".
        logger.warning("real_dev scorer: sandbox unavailable: %s", exc)
        return _unknown_quality()

    passed, total = _parse_pytest_summary(result.stdout, result.stderr)

    if total == 0:
        logger.info(
            "real_dev scorer: no tests collected (stderr tail=%r)",
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


# ---------------------------------------------------------------------------
# D1 — small feature
# ---------------------------------------------------------------------------


def _score_d1(task: Task, model_output: str) -> Quality:
    if not task.fixtures_dir or not task.tests:
        logger.warning("D1 task %s missing fixtures_dir/tests", task.id)
        return _zero_quality()

    fixtures_dir = _FIXTURES_ROOT / task.fixtures_dir
    starter = _iter_fixture_files(fixtures_dir)
    if not starter:
        logger.warning("D1 task %s has empty fixtures dir", task.id)
        return _zero_quality()

    targets = _list_reference_targets(fixtures_dir)
    overlays = _extract_files_for_targets(model_output, targets)
    if not overlays:
        logger.info("D1 task %s: model produced no usable code", task.id)
        return _zero_quality()

    files: dict[str, str] = dict(starter)
    for tgt, body in overlays.items():
        files[tgt] = body

    # ``task.tests`` is a path relative to fixtures/ (e.g.
    # ``d1-rate-limit/test_rate_limit.py``); strip the leading slug so
    # the in-sandbox relative path is just ``test_rate_limit.py``.
    test_rel = _strip_fixture_prefix(task.tests, task.fixtures_dir)
    return _run_pytest_in_sandbox(files, test_rel)


# ---------------------------------------------------------------------------
# D2 — bug fix (see long comment below)
# ---------------------------------------------------------------------------


def _score_d2(task: Task, model_output: str) -> Quality:
    """Scoring is deferred. See block comment.

    TODO(P2.x): Integrate a swebench-compatible harness that can apply a
    unified diff to an arbitrary ``(repo, base_commit)`` pair and run the
    task's reference test (``task.tests`` which lives under
    ``fixtures/<slug>/_reference/``). The existing
    :mod:`hybrid_coding_eval.scorers.swebench` path hard-codes
    ``princeton-nlp/SWE-bench_Verified`` as the dataset, so it can only
    grade instance IDs registered there. Our D2 task IDs (e.g.
    ``pallets__click-3298``) reference real GitHub issues but are NOT in
    that HF dataset, so the existing harness would refuse them.

    Until that work lands, D2 returns an ``all-None`` :class:`Quality`:
    functional_pass is ``None`` rather than ``False`` so aggregators see
    "not graded" and don't count D2 as a miss against the model. The
    model's produced diff is still written to disk by the runner, so
    post-hoc rescoring is straightforward once the harness is ready.
    """
    del task, model_output  # deliberately unused; see docstring.
    return Quality(
        functional_pass=None,
        tests_passed=None,
        tests_total=None,
        composite=None,
    )


# ---------------------------------------------------------------------------
# D5 — script
# ---------------------------------------------------------------------------


def _score_d5(task: Task, model_output: str) -> Quality:
    if not task.fixtures_dir or not task.tests:
        logger.warning("D5 task %s missing fixtures_dir/tests", task.id)
        return _zero_quality()

    fixtures_dir = _FIXTURES_ROOT / task.fixtures_dir
    starter = _iter_fixture_files(fixtures_dir)
    if not starter:
        logger.warning("D5 task %s has empty fixtures dir", task.id)
        return _zero_quality()

    targets = _list_reference_targets(fixtures_dir)
    overlays = _extract_files_for_targets(model_output, targets)
    if not overlays:
        logger.info("D5 task %s: model produced no usable code", task.id)
        return _zero_quality()

    files: dict[str, str] = dict(starter)
    for tgt, body in overlays.items():
        files[tgt] = body

    test_rel = _strip_fixture_prefix(task.tests, task.fixtures_dir)
    return _run_pytest_in_sandbox(files, test_rel)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _strip_fixture_prefix(test_path: str, fixtures_dir: str) -> str:
    """Turn ``d1-rate-limit/test_rate_limit.py`` into ``test_rate_limit.py``
    when ``fixtures_dir == 'd1-rate-limit'`` so pytest resolves the file
    relative to the mounted workdir.
    """
    prefix = fixtures_dir.rstrip("/") + "/"
    if test_path.startswith(prefix):
        return test_path[len(prefix):]
    return test_path


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def score(
    task: Task, model_output: str, *, context: dict | None = None
) -> Quality:
    """Dispatch on ``task.shape`` to a per-shape scorer.

    ``context`` is reserved for future judge-model overrides; currently
    unused.
    """
    del context  # reserved for future per-row overrides.
    if task.shape == "D1":
        return _score_d1(task, model_output)
    if task.shape == "D2":
        return _score_d2(task, model_output)
    if task.shape in ("D3", "D4"):
        # v1.4: llm_judge was deleted as part of the agentic cleanup, so
        # D3 (refactor) and D4 (code-review) scoring is deferred — the
        # row records an all-None Quality and aggregators see "not graded"
        # rather than miscounting as a failure.
        logger.warning(
            "%s task %s: scoring deferred (llm_judge removed in v1.4)",
            task.shape,
            task.id,
        )
        return _unknown_quality()
    if task.shape == "D5":
        return _score_d5(task, model_output)
    if task.shape == "D6":
        # D6 hard-refactors use the same overlay+pytest path as D1/D5.
        # They differ only in the complexity calibration of the
        # fixture + test suite, not in scoring shape.
        return _score_d1(task, model_output)
    # Shouldn't reach here — the adapter rejects unknown shapes.
    raise ValueError(f"unknown shape {task.shape!r}")


__all__ = ["score"]

# Convenience re-exports so downstream tests / callers can inspect the
# internal helpers without reaching into a private namespace.
_ = Any  # keep the `Any` import referenced for typing consumers.
