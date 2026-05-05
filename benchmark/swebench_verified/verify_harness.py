#!/usr/bin/env python3
"""End-to-end sanity check of the SWE-bench scoring harness.

This script is intentionally *not* part of the pytest suite: it requires
Docker and will pull a ~500 MB per-task image from Docker Hub. Run it manually
after setting up Docker to confirm the scoring path works before wiring it
into the main eval loop (T3.2).

What it does:

1. Loads the first task from ``load_tasks(n=10, seed=42, difficulty='easy')``.
2. Runs ``swebench.harness.run_evaluation`` with an EMPTY patch — asserts the
   harness reports FAIL (sanity: the tests should require the fix).
3. Runs the same harness with the task's GOLD patch — asserts PASS.
4. On any Docker / platform failure, prints a clear diagnostic and exits 2 so
   a caller can distinguish "harness rejected by environment" from "harness
   ran but graded incorrectly".

On Apple Silicon (M1–M4): the SWE-bench images are x86_64 and run under
Rosetta/QEMU emulation. Each image pull is slow and each evaluation is slow
(expect tens of minutes per task on a first run). If the harness takes longer
than ``--timeout``, the script exits with the "environment can't run" path.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow running as a standalone script (``python benchmark/swebench_verified/verify_harness.py``)
# by ensuring the repo root is on sys.path before the intra-repo import.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmark.swebench_verified.adapter import load_tasks  # noqa: E402


EXIT_OK = 0
EXIT_GRADING_MISMATCH = 1
EXIT_ENV_UNAVAILABLE = 2


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
        return False, f"`docker info` exited {out.returncode}: {out.stderr.strip()[:500]}"
    return True, out.stdout.splitlines()[0] if out.stdout else "ok"


def _write_predictions_file(
    instance_id: str,
    patch: str,
    model_name: str,
    out_dir: Path,
) -> Path:
    """Write a SWE-bench-harness-compatible predictions.json with a single row."""
    preds = [
        {
            "instance_id": instance_id,
            "model_patch": patch,
            "model_name_or_path": model_name,
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
    """Invoke ``python -m swebench.harness.run_evaluation`` as a subprocess."""
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


def _find_report(run_id: str, model_name: str, cwd: Path) -> dict | None:
    """The harness writes ``<model>/<run_id>/<instance>/report.json`` per instance
    and a top-level summary. We look for the top-level summary first, then
    fall back to per-instance reports."""
    for candidate in (
        cwd / f"{model_name}.{run_id}.json",
        cwd / "logs" / "run_evaluation" / run_id / model_name / "report.json",
    ):
        if candidate.exists():
            try:
                return json.loads(candidate.read_text())
            except Exception:  # noqa: BLE001
                pass
    # Fallback: search for any report.json under logs/.
    for p in (cwd / "logs").rglob("report.json"):
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
    return None


def _summary_passed(report: dict | None, instance_id: str) -> bool | None:
    """Return True if the harness says this instance was resolved, False if not,
    None if we can't tell."""
    if not report:
        return None
    if instance_id in report.get("resolved_ids", []):
        return True
    if instance_id in report.get("unresolved_ids", []):
        return False
    if instance_id in report.get("error_ids", []):
        return False
    # Per-instance report format.
    if "resolved" in report:
        return bool(report["resolved"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Per-run timeout in seconds (default: 1800 = 30 min).",
    )
    parser.add_argument(
        "--skip-empty",
        action="store_true",
        help="Skip the empty-patch FAIL check (save one image pull).",
    )
    args = parser.parse_args()

    print(f"[verify_harness] platform: {platform.system()} {platform.machine()}")
    if platform.machine().lower() in {"arm64", "aarch64"}:
        print(
            "[verify_harness] NOTE: running on ARM. SWE-bench images are x86_64; "
            "they will run under Rosetta/QEMU and be SLOW. "
            "Expect tens of minutes even for the easy tier."
        )

    ok, why = _docker_available()
    if not ok:
        print(f"[verify_harness] Docker unavailable: {why}")
        print("[verify_harness] Cannot run the SWE-bench grading harness without Docker.")
        print("[verify_harness] Install Docker Desktop and re-run. For CI, use x86 Linux.")
        return EXIT_ENV_UNAVAILABLE
    print(f"[verify_harness] docker: {why}")

    tasks = load_tasks(n=10, seed=42, difficulty="easy")
    task = tasks[0]
    print(f"[verify_harness] target task: {task.instance_id} ({task.repo})")
    print(f"[verify_harness] expected_patch length: {len(task.expected_patch)} chars")

    with tempfile.TemporaryDirectory(prefix="swebench-verify-") as tmp:
        tmp_path = Path(tmp)
        model_name = "verify_harness"
        overall_pass: bool | None = None
        overall_fail: bool | None = None

        # ---- Step 1: empty patch should FAIL ---------------------------------
        if not args.skip_empty:
            print("[verify_harness] step 1/2: empty-patch run (should FAIL)...")
            preds = _write_predictions_file(
                instance_id=task.instance_id,
                patch="",
                model_name=model_name,
                out_dir=tmp_path,
            )
            try:
                proc = _run_harness(
                    instance_id=task.instance_id,
                    predictions_path=preds,
                    run_id="empty",
                    timeout_s=args.timeout,
                    cwd=tmp_path,
                )
            except subprocess.TimeoutExpired:
                print(
                    f"[verify_harness] empty-patch run exceeded "
                    f"{args.timeout}s — Docker image pull or Rosetta emulation "
                    "is too slow in this environment."
                )
                print(
                    "[verify_harness] Harness environment unavailable. "
                    "Scoring verified on x86 Linux only."
                )
                return EXIT_ENV_UNAVAILABLE
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout).splitlines()[-40:]
                print(f"[verify_harness] harness exited {proc.returncode}:")
                for line in tail:
                    print(f"    {line}")
                print("[verify_harness] Harness could not run in this environment.")
                return EXIT_ENV_UNAVAILABLE
            report = _find_report("empty", model_name, tmp_path)
            overall_fail = _summary_passed(report, task.instance_id)
            print(f"[verify_harness] empty-patch resolved={overall_fail}")
            if overall_fail is True:
                print("[verify_harness] UNEXPECTED: empty patch was graded PASS.")
                return EXIT_GRADING_MISMATCH

        # ---- Step 2: gold patch should PASS ----------------------------------
        print("[verify_harness] step 2/2: gold-patch run (should PASS)...")
        preds = _write_predictions_file(
            instance_id=task.instance_id,
            patch=task.expected_patch,
            model_name=model_name,
            out_dir=tmp_path,
        )
        try:
            proc = _run_harness(
                instance_id=task.instance_id,
                predictions_path=preds,
                run_id="gold",
                timeout_s=args.timeout,
                cwd=tmp_path,
            )
        except subprocess.TimeoutExpired:
            print(
                f"[verify_harness] gold-patch run exceeded {args.timeout}s. "
                "Environment cannot run the harness in reasonable time."
            )
            return EXIT_ENV_UNAVAILABLE
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).splitlines()[-40:]
            print(f"[verify_harness] harness exited {proc.returncode}:")
            for line in tail:
                print(f"    {line}")
            return EXIT_ENV_UNAVAILABLE
        report = _find_report("gold", model_name, tmp_path)
        overall_pass = _summary_passed(report, task.instance_id)
        print(f"[verify_harness] gold-patch resolved={overall_pass}")

        if overall_pass is not True:
            print("[verify_harness] UNEXPECTED: gold patch was NOT graded PASS.")
            return EXIT_GRADING_MISMATCH

    print("[verify_harness] OK: empty=FAIL, gold=PASS. Harness works end-to-end.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
