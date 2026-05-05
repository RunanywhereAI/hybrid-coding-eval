"""Tests for :mod:`scorers.swebench`.

Two tiers:

* **Fast** (unit tests for :func:`extract_diff`) — always run, no Docker.
* **Slow** (end-to-end against the SWE-bench harness) — gated by
  ``@pytest.mark.slow`` and skipped automatically if Docker is unavailable.
  On an Apple-Silicon Mac these tests can take 10+ minutes each on the first
  run because the per-instance Docker image must be pulled under
  Rosetta/QEMU.

Run fast tests only:

    pytest tests/test_swebench_scorer.py -v -m "not slow"

Run the end-to-end suite:

    pytest tests/test_swebench_scorer.py -v -m slow
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from scorers.swebench import extract_diff, score


# ---------------------------------------------------------------------------
# Fast tests — pure function, no Docker.
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """diff --git a/foo.py b/foo.py
index abc123..def456 100644
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,3 @@
 def foo():
-    return 1
+    return 2
"""


def test_extract_diff_raw() -> None:
    got = extract_diff(SAMPLE_DIFF)
    assert "diff --git a/foo.py b/foo.py" in got
    assert got.endswith("\n")


def test_extract_diff_raw_with_prose_prefix() -> None:
    wrapped = "Here is my patch:\n\n" + SAMPLE_DIFF + "\n\nHope this helps!"
    got = extract_diff(wrapped)
    assert got.startswith("diff --git a/foo.py b/foo.py")
    # The trailing prose should not survive — we trim at the diff header,
    # but we still accept text after the last hunk because unified diffs
    # don't have an explicit end marker. The important thing is that the
    # diff itself survives intact.
    assert "@@ -1,3 +1,3 @@" in got


def test_extract_diff_fenced_diff_language() -> None:
    wrapped = "```diff\n" + SAMPLE_DIFF + "```\n"
    got = extract_diff(wrapped)
    assert got.startswith("diff --git a/foo.py b/foo.py")
    assert "```" not in got


def test_extract_diff_fenced_patch_language() -> None:
    wrapped = "```patch\n" + SAMPLE_DIFF + "```\n"
    got = extract_diff(wrapped)
    assert got.startswith("diff --git a/foo.py b/foo.py")


def test_extract_diff_fenced_no_language() -> None:
    wrapped = "Apply this:\n\n```\n" + SAMPLE_DIFF + "```\n"
    got = extract_diff(wrapped)
    assert got.startswith("diff --git a/foo.py b/foo.py")


def test_extract_diff_minus_plus_only() -> None:
    minimal = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n"
    got = extract_diff(minimal)
    assert got.startswith("--- a/foo.py")
    assert got.endswith("\n")


def test_extract_diff_empty_returns_empty() -> None:
    assert extract_diff("") == ""


def test_extract_diff_prose_only_returns_empty() -> None:
    assert extract_diff("Sorry, I can't help with that.") == ""
    assert extract_diff("Here's some Python:\n```python\nprint('hi')\n```\n") == ""


def test_extract_diff_picks_first_fenced_diff_block() -> None:
    other = "```python\nprint('hi')\n```\n"
    combined = other + "\nand here is the fix:\n\n```diff\n" + SAMPLE_DIFF + "```\n"
    got = extract_diff(combined)
    assert got.startswith("diff --git a/foo.py b/foo.py")


def test_score_empty_output_returns_fail_without_docker() -> None:
    # No diff → scorer short-circuits and never touches Docker.
    class _FakeTask:
        instance_id = "astropy__astropy-000"

    q = score(_FakeTask(), model_output="")
    assert q.functional_pass is False
    assert q.tests_passed == 0
    assert q.tests_total == 1
    assert q.composite == 0.0


def test_score_prose_only_output_returns_fail_without_docker() -> None:
    class _FakeTask:
        instance_id = "astropy__astropy-000"

    q = score(_FakeTask(), model_output="I don't know how to fix this.")
    assert q.functional_pass is False
    assert q.tests_passed == 0


# ---------------------------------------------------------------------------
# Slow tests — real SWE-bench harness.
# ---------------------------------------------------------------------------

def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
    except Exception:  # noqa: BLE001
        return False
    return proc.returncode == 0


docker_required = pytest.mark.skipif(
    not _docker_up(),
    reason="Docker not available — the SWE-bench grading harness cannot run.",
)


@pytest.fixture(scope="module")
def one_task():
    from benchmark.swebench_verified.adapter import load_tasks

    tasks = load_tasks(n=10, seed=42, difficulty="easy")
    return tasks[0]


@pytest.mark.slow
@docker_required
def test_gold_patch_is_graded_pass(one_task) -> None:
    """Sanity: the task's own gold patch must be graded PASS."""
    q = score(one_task, model_output=one_task.expected_patch, timeout_s=1800)
    # functional_pass=None means harness env-failed; give a useful diagnostic.
    assert q.functional_pass is not None, (
        "Scorer returned functional_pass=None — harness could not grade this task. "
        "Check docker + first-time image pull time."
    )
    assert q.functional_pass is True, (
        f"Gold patch was not graded PASS. Quality={q}"
    )
    assert q.tests_passed == 1
    assert q.tests_total == 1


@pytest.mark.slow
def test_empty_output_is_fail_without_invoking_harness(one_task) -> None:
    """Empty model output never reaches the harness; it should short-circuit."""
    q = score(one_task, model_output="")
    assert q.functional_pass is False
    assert q.tests_passed == 0


@pytest.mark.slow
@docker_required
def test_fenced_gold_patch_is_extracted_and_passes(one_task) -> None:
    """A gold patch wrapped in a ```diff fence should still score PASS."""
    wrapped = (
        "Here's the fix:\n\n"
        "```diff\n"
        f"{one_task.expected_patch}"
        "```\n"
    )
    q = score(one_task, model_output=wrapped, timeout_s=1800)
    assert q.functional_pass is not None, (
        "Scorer returned functional_pass=None — harness could not grade this task."
    )
    assert q.functional_pass is True, (
        f"Fenced gold patch was not graded PASS. Quality={q}"
    )
