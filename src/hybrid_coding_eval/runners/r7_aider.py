"""R7 — Aider in architect/editor mode on Exercism Python tasks.

**EXPERIMENTAL in v1.1.** R7 is in the tree as the apples-to-apples Aider
runner but is NOT exercised in the v1.1 canonical sweep — v1.1 focuses
entirely on R8 (opencode). R7 rides free on shared refactors:
correlation-id token attribution + the new agent-aware `heuristic`
strategy. Full polish (Docker scoring for pytest, more fixtures) lands
in v1.2.

Aider is a CLI coding assistant that operates *inside a repo*: read files,
emit diffs, run tests, iterate. The architect/editor mode splits the
work into two model calls per turn (architect proposes, editor patches),
which is exactly the kind of routing-friendly call mix that this
benchmark wants to measure.

What R7 does, per task:
  1. Generate a 12-hex ``bench_run_id`` + copy the task fixture into a
     per-run scratch dir.
  2. Subprocess ``aider --architect`` with both architect-model and
     editor-model pointed at this repo's proxy on :8787 under
     ``router/<strategy>/run-<id>``. Aider uses LiteLLM internally and
     respects ``OPENAI_API_BASE``.
  3. After Aider exits, run pytest on the modified files.
  4. Reconstruct token attribution by filtering decisions.jsonl on
     ``bench_run_id`` (primary) / timestamp window (fallback).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hybrid_coding_eval.core.metrics import (
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_coding_eval.core.paths import repo_root as _resolve_repo_root
from hybrid_coding_eval.runners._agent_attribution import (
    attribute_from_decisions_log,
    generate_run_id,
    model_string,
)

__all__ = ["run", "ROUTE"]

ROUTE = "R7"
_REPO_ROOT: Path = _resolve_repo_root()

DEFAULT_TIMEOUT_S: int = 600


def _task_slug(task_id: str) -> str:
    return task_id.replace("/", "__").replace(" ", "_")


_REAL_DEV_FIXTURES_ROOT: Path = (
    _REPO_ROOT / "src" / "hybrid_coding_eval" / "benchmarks" / "real_dev" / "fixtures"
)


def _resolve_fixture_dir(task: Any) -> Path:
    """Return the source fixture dir for ``task`` — handles both Exercism
    (``fixture_dir`` Path) and real_dev (``fixtures_dir`` slug) shapes.
    """
    fixture_dir = getattr(task, "fixture_dir", None)
    if isinstance(fixture_dir, Path) and fixture_dir.is_dir():
        return fixture_dir
    slug = getattr(task, "fixtures_dir", None)
    if isinstance(slug, str) and slug:
        candidate = _REAL_DEV_FIXTURES_ROOT / slug
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"task {getattr(task, 'id', '?')!r}: no fixture_dir (Path) or fixtures_dir (slug)"
    )


def _find_test_path(scratch: Path, task: Any) -> Path | None:
    """Locate the canonical test file inside ``scratch``.

    Order:
      1. If ``task.tests`` is set (real_dev shape: ``<slug>/test_*.py`` or
         ``<slug>/_reference/test_*.py``), strip the leading slug and resolve
         under scratch.
      2. Exercism shape: ``*_test.py`` next to the stub.
      3. Generic: ``test_*.py`` or ``*_test.py`` anywhere in scratch.
    """
    tests_attr = getattr(task, "tests", None)
    if isinstance(tests_attr, str) and tests_attr:
        # task.tests is "<slug>/test_x.py" relative to fixtures/. Strip slug.
        parts = tests_attr.split("/", 1)
        rel = parts[1] if len(parts) == 2 else tests_attr
        candidate = scratch / rel
        if candidate.exists():
            return candidate
    for p in scratch.glob("*_test.py"):
        return p
    for p in scratch.rglob("test_*.py"):
        return p
    for p in scratch.rglob("*_test.py"):
        return p
    return None


def _copy_fixture(task: Any, dst: Path) -> tuple[Path, list[Path]]:
    """Copy the task fixture into ``dst``. Returns ``(test_path, editable_files)``.

    ``editable_files`` is the list of non-test .py files in the top level of
    the fixture — these get passed to aider as the working set. For Exercism
    that's typically one stub; for real_dev D1 it can be several.
    """
    src = _resolve_fixture_dir(task)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    test_path = _find_test_path(dst, task)
    if test_path is None:
        raise FileNotFoundError(f"no test file found in {dst}")
    editable = [
        p for p in dst.glob("*.py")
        if not p.name.endswith("_test.py") and not p.name.startswith("test_")
    ]
    # D5 tasks have solution.py / solution.sh that may not exist yet at copy
    # time — aider needs to CREATE them. Add the bare filename as a hint.
    if not editable:
        run_cmd = getattr(task, "run_cmd", None) or ""
        # crude: pick the first .py / .sh token from the run_cmd
        for tok in run_cmd.split():
            if tok.endswith(".py") or tok.endswith(".sh"):
                editable = [dst / tok]
                break
    return test_path, editable


def _run_tests_local(stub_dir: Path, test_path: Path) -> Quality:
    """Run pytest on the test file in the stub dir. Fast local subprocess
    (no Docker overhead for this lightweight case).

    Prefer the repo's .venv/bin/python (which has pytest installed) over
    the first python3 on PATH — system pythons usually lack pytest.
    """
    venv_py = _REPO_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else (shutil.which("python3") or shutil.which("python") or "python3")
    try:
        proc = subprocess.run(
            [py, "-m", "pytest", "-q", str(test_path)],
            cwd=stub_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        # pytest exit 0 = pass; 1 = test failures; >1 = setup error
        passed = proc.returncode == 0
        # Try to parse the "<X passed>" / "<Y failed>" line for fine-grained
        # counts; not strictly required.
        tail = (proc.stdout or "")[-400:]
        tests_passed = 0
        tests_total = 0
        for tok in tail.split():
            if tok.endswith("passed,") or tok == "passed":
                # crude — find preceding int
                pass
        return Quality(
            functional_pass=passed,
            tests_passed=tests_passed if tests_passed else (1 if passed else 0),
            tests_total=tests_total if tests_total else 1,
            composite=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        return Quality(functional_pass=False, composite=0.0)


def run(
    task: Any,
    *,
    proxy_url: str = "http://127.0.0.1:8787",
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    router_strategy: str = "heuristic",
    timeout_s: int = DEFAULT_TIMEOUT_S,
    **_unused: Any,
) -> ResultRow:
    """Run one Exercism Python task through Aider's architect mode."""
    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r7"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    run_dir = output_dir / f"r7_{slug}_{router_strategy}"
    scratch = run_dir / "scratch"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy fixture so the run is isolated.
    try:
        test_path, editable_files = _copy_fixture(task, scratch)
    except Exception as exc:
        return ResultRow(
            task_id=task.id,
            category=getattr(task, "category", "A"),
            route=ROUTE,
            hardware_profile_ref=hardware_profile_ref,
            tokens=TokenUsage(),
            latency=Latency(wall_ms=0, per_call_ms=[]),
            quality=Quality(),
            routing=Routing(total_calls=0, local_calls=0, cloud_calls=0),
            output_ref="",
            error=f"fixture_copy_failed: {exc}",
            router_strategy=router_strategy,
        )

    # 2. Build the prompt. For Exercism we add a hint about the stub file;
    # for real_dev (D1/D5) tasks the prompt is self-contained.
    if len(editable_files) == 1 and editable_files[0].name not in ("solution.py", "solution.sh"):
        # Single-file Exercism stub.
        prompt = task.prompt + (
            "\n\nImplement the function(s) in the stub so that all tests in "
            f"{test_path.name} pass. Edit only the stub file."
        )
    else:
        # Multi-file real_dev task: prompt is self-contained.
        prompt = task.prompt

    bench_run_id = generate_run_id()
    api_base = proxy_url.rstrip("/") + "/v1"
    model_id = model_string(router_strategy, bench_run_id, prefix="openai/router")

    # 3. Subprocess Aider. Prefer .venv/bin/aider when present (./bench
    # setup installs aider into the repo's venv); fall back to PATH.
    _venv_aider = _REPO_ROOT / ".venv" / "bin" / "aider"
    aider_bin = str(_venv_aider) if _venv_aider.exists() else (shutil.which("aider") or "aider")
    cmd = [
        aider_bin,
        "--architect",
        "--model",
        model_id,
        "--editor-model",
        model_id,
        "--openai-api-base",
        api_base,
        "--openai-api-key",
        "bench-eval-key",
        "--no-git",
        "--yes-always",
        "--no-show-model-warnings",
        "--no-check-update",
        "--no-stream",
        "--no-pretty",
        "--message",
        prompt,
        *[str(p.name) for p in editable_files],  # all editable files (relative to cwd = scratch)
    ]

    env = os.environ.copy()
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "bench-eval-key")
    env["OPENAI_API_BASE"] = api_base

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    err: str | None = None
    try:
        proc = subprocess.run(
            cmd,
            cwd=scratch,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        (run_dir / "stdout.log").write_text(proc.stdout or "", encoding="utf-8")
        (run_dir / "stderr.log").write_text(proc.stderr or "", encoding="utf-8")
        if proc.returncode != 0 and "Tokens:" not in (proc.stdout or ""):
            # Aider sometimes exits non-zero on edit-format issues but still
            # writes a valid modified file. We tolerate that.
            err = f"aider_exit_{proc.returncode}"
    except subprocess.TimeoutExpired:
        err = f"agent_timeout_{timeout_s}s"
    except FileNotFoundError:
        err = "aider_not_installed"

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)

    # 4. Score by running pytest on the (possibly modified) editable files.
    quality = _run_tests_local(scratch, test_path)

    # Save the primary edited file as the canonical output. For multi-file
    # tasks we save the first editable file; the full scratch dir stays
    # under outputs/ for inspection.
    answer_path = run_dir / "answer.py"
    primary = editable_files[0] if editable_files else None
    if primary and primary.exists():
        answer_path.write_text(primary.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        answer_path.write_text("", encoding="utf-8")

    # 5. Token attribution (primary: bench_run_id; fallback: timestamp window).
    tokens, routing = attribute_from_decisions_log(
        run_id=bench_run_id,
        strategy=router_strategy,
        started_at=started_at,
        finished_at=finished_at,
    )

    try:
        output_ref = str(answer_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        output_ref = str(answer_path.resolve())

    return ResultRow(
        task_id=task.id,
        category=getattr(task, "category", "A"),
        route=ROUTE,
        hardware_profile_ref=hardware_profile_ref,
        tokens=tokens,
        latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
        quality=quality,
        routing=routing,
        output_ref=output_ref,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        error=err,
        router_strategy=router_strategy,
    )
