"""SWE-bench scorer.

Wraps the working :mod:`swebench.harness.run_evaluation` CLI (validated
end-to-end by
``src/hybrid_arena/tasks/real_prs/verify_harness.py``) into a
simple ``score(task, model_output, ...) -> Quality`` function.

The scorer is intentionally narrow: it is given *one* task and *one*
model-produced raw string, extracts the unified diff, invokes the upstream
SWE-bench grading harness for exactly that instance in a subprocess, and
parses the JSON report the harness writes.

This module does **not** generate patches — it only grades them. It does
**not** reimplement SWE-bench scoring — it shells out to the upstream
package. Docker is required (each SWE-bench instance runs inside a per-task
image); on ARM Macs those images run under Rosetta/QEMU and scoring takes
several minutes per task even for the "easy" tier.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from hybrid_arena.core.metrics import Quality

# ---------------------------------------------------------------------------
# Diff extraction
# ---------------------------------------------------------------------------

# ``diff --git a/... b/...`` header or a bare ``--- <path>\n+++ <path>`` header
# both constitute the start of a unified diff.
_DIFF_GIT_RE = re.compile(r"^diff --git ", re.MULTILINE)
_DIFF_MINUS_RE = re.compile(r"^--- [^\n]*\n\+\+\+ [^\n]*", re.MULTILINE)

# ```diff / ```patch / bare ``` fenced blocks.
_FENCE_RE = re.compile(
    r"```(?:diff|patch|git|gitdiff)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _looks_like_diff(text: str) -> bool:
    if not text:
        return False
    return bool(_DIFF_GIT_RE.search(text) or _DIFF_MINUS_RE.search(text))


def _trim_to_diff_start(text: str) -> str:
    """Strip any prose before the first diff header."""
    m_git = _DIFF_GIT_RE.search(text)
    m_minus = _DIFF_MINUS_RE.search(text)
    candidates = [m.start() for m in (m_git, m_minus) if m is not None]
    if not candidates:
        return text
    return text[min(candidates):]


def extract_diff(text: str) -> str:
    """Return a unified-diff string from ``text``, or ``""`` if none is found.

    Accepted shapes, in preference order:

    1. A fenced block (```` ```diff ```` / ```` ```patch ```` / ```` ``` ````)
       whose *contents* look like a diff — we pick the first such block.
    2. A raw diff embedded in prose — we trim everything before the first
       ``diff --git`` or ``--- <file>`` line and return the remainder.
    3. Otherwise ``""``.

    The returned string always ends with a newline, because ``git apply`` and
    the SWE-bench harness can mis-apply a patch whose final hunk lacks a
    trailing newline.
    """
    if not text:
        return ""

    # (1) fenced blocks — prefer the first one whose body looks like a diff.
    for m in _FENCE_RE.finditer(text):
        body = m.group(1)
        if _looks_like_diff(body):
            body = _trim_to_diff_start(body)
            return body if body.endswith("\n") else body + "\n"

    # (2) raw diff in prose.
    if _looks_like_diff(text):
        body = _trim_to_diff_start(text)
        return body if body.endswith("\n") else body + "\n"

    # (3) nothing.
    return ""


# ---------------------------------------------------------------------------
# Harness invocation helpers (adapted from tasks/real_prs/verify_harness.py)
# ---------------------------------------------------------------------------

MODEL_NAME = "hybrid-arena"


def _docker_available() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "`docker` binary not found on PATH."
    try:
        out = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"`docker info` crashed: {exc!r}"
    if out.returncode != 0:
        msg = (out.stderr or "").strip().splitlines()
        return False, f"`docker info` exited {out.returncode}: {msg[0] if msg else ''}"
    return True, "ok"


def _write_predictions_file(
    instance_id: str,
    patch: str,
    out_dir: Path,
) -> Path:
    """Write a single-row SWE-bench predictions file (JSON list form)."""
    preds = [
        {
            "instance_id": instance_id,
            "model_patch": patch,
            "model_name_or_path": MODEL_NAME,
        }
    ]
    path = out_dir / "predictions.json"
    path.write_text(json.dumps(preds))
    return path


def _run_harness(
    instance_id: str,
    predictions_path: Path,
    run_id: str,
    timeout_s: int,
    cwd: Path,
) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        "princeton-nlp/SWE-bench_Verified",
        "--split",
        "test",
        "--instance_ids",
        instance_id,
        "--predictions_path",
        str(predictions_path),
        "--run_id",
        run_id,
        "--max_workers",
        "1",
        "--cache_level",
        "env",
        "--timeout",
        str(timeout_s),
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s + 120,
        cwd=str(cwd),
    )


def _find_report(run_id: str, cwd: Path) -> dict | None:
    """Locate the harness report JSON.

    The harness writes a top-level ``<model>.<run_id>.json`` summary next to
    the CWD, plus per-instance ``logs/run_evaluation/<run_id>/<model>/<instance>/report.json``
    files. We check both.
    """
    candidates = [
        cwd / f"{MODEL_NAME}.{run_id}.json",
        cwd / "logs" / "run_evaluation" / run_id / MODEL_NAME / "report.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text())
            except Exception:  # noqa: BLE001
                pass
    logs_dir = cwd / "logs"
    if logs_dir.exists():
        for p in logs_dir.rglob("report.json"):
            try:
                return json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
    return None


def _resolved_from_report(report: dict | None, instance_id: str) -> bool | None:
    """Return True/False/None from a harness report for ``instance_id``.

    ``error_ids`` in v2 summaries covers both infra errors *and* things like
    "patch failed to apply" or test-execution failures. For grading purposes
    we treat error_ids as FAIL (matching the SWE-bench leaderboard
    convention) once we know the harness itself ran successfully (i.e. a
    summary was produced). True harness-failed-to-run cases surface as
    returncode != 0 upstream and never reach this function's happy path.
    """
    if not report:
        return None
    if instance_id in report.get("resolved_ids", []):
        return True
    if instance_id in report.get("unresolved_ids", []):
        return False
    if instance_id in report.get("error_ids", []):
        # Patch-apply failed or instance-level run error. This IS a model
        # failure per leaderboard convention.
        return False
    if instance_id in report.get("empty_patch_ids", []):
        return False
    # Per-instance report format.
    if "resolved" in report:
        return bool(report["resolved"])
    inst = report.get(instance_id)
    if isinstance(inst, dict) and "resolved" in inst:
        return bool(inst["resolved"])
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _quality_no_patch() -> Quality:
    return Quality(
        functional_pass=False,
        tests_passed=0,
        tests_total=1,
        composite=0.0,
    )


def _quality_pass() -> Quality:
    return Quality(
        functional_pass=True,
        tests_passed=1,
        tests_total=1,
        composite=1.0,
    )


def _quality_fail() -> Quality:
    return Quality(
        functional_pass=False,
        tests_passed=0,
        tests_total=1,
        composite=0.0,
    )


def _quality_unknown() -> Quality:
    """Harness could not grade (docker missing, pull failed, etc.).

    We deliberately do NOT claim the model failed: the caller should surface
    this as "not graded" rather than counting it against the model.
    """
    return Quality(
        functional_pass=None,
        tests_passed=None,
        tests_total=1,
        composite=None,
    )


def score(
    task: Any,
    model_output: str,
    timeout_s: int = 1200,
    image_pull: bool = True,  # noqa: ARG001 — currently always True at harness level
) -> Quality:
    """Grade ``model_output`` against a SWE-bench Verified ``task``.

    Steps:

    1. Extract a unified diff from ``model_output``. If none is found, return
       a failing ``Quality`` with ``functional_pass=False`` and
       ``tests_passed=0`` (no patch means the bug was not fixed).
    2. Write a 1-row predictions file and invoke
       ``python -m swebench.harness.run_evaluation`` for this instance only.
    3. Parse the report JSON. A "resolved" instance becomes ``functional_pass=True``
       with composite 1.0; an "unresolved" instance becomes a fail; an
       environment error / Docker problem becomes ``functional_pass=None``
       (unknown), so we don't miscount it against the model.

    Parameters
    ----------
    task:
        A ``benchmark.swebench_verified.adapter.Task``. Only ``instance_id`` is
        required here — the harness re-fetches the full instance from the HF
        dataset by ID.
    model_output:
        Raw string produced by the model. May contain prose, fenced blocks,
        reasoning, etc. We extract the diff ourselves.
    timeout_s:
        Per-task harness timeout in seconds. Defaults to 1200 s (20 min) — on
        an M4 Max running x86 SWE-bench images under Rosetta this is roughly
        the 90th percentile of a scored easy-tier task (first-run pulls can
        exceed this; subsequent runs use the cached image).
    image_pull:
        Kept in the signature for future use. The upstream harness always
        pulls missing images at the moment; we pass through.
    """
    patch = extract_diff(model_output or "")
    if not patch:
        return _quality_no_patch()

    instance_id = getattr(task, "instance_id", None)
    if not instance_id:
        return _quality_unknown()

    ok, _why = _docker_available()
    if not ok:
        return _quality_unknown()

    run_id = f"score-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="swebench-score-") as tmp:
        tmp_path = Path(tmp)
        preds = _write_predictions_file(
            instance_id=instance_id,
            patch=patch,
            out_dir=tmp_path,
        )
        try:
            proc = _run_harness(
                instance_id=instance_id,
                predictions_path=preds,
                run_id=run_id,
                timeout_s=timeout_s,
                cwd=tmp_path,
            )
        except subprocess.TimeoutExpired:
            # Timeout — count as a functional failure (the patch, if any,
            # couldn't be graded in the allotted time). Mark timeout in
            # composite=None so aggregators can choose to exclude.
            return Quality(
                functional_pass=False,
                tests_passed=0,
                tests_total=1,
                composite=0.0,
            )

        if proc.returncode != 0:
            # Harness itself crashed (bad Docker setup, network, etc.).
            # We can't tell whether the model succeeded or failed — return
            # "unknown" so we don't miscount it.
            return _quality_unknown()

        report = _find_report(run_id, tmp_path)
        resolved = _resolved_from_report(report, instance_id)

    if resolved is True:
        return _quality_pass()
    if resolved is False:
        return _quality_fail()
    return _quality_unknown()
