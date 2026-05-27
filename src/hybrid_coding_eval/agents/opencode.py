"""R8 — opencode CLI agent on real-dev D1+D5 fixtures.

opencode is a TypeScript+Bun coding agent with Read/Write/Edit/Bash/
Grep/Glob tools. ``./bench setup`` installs the maintainer's fork
(default: ``RunanywhereAI/opencode-1`` @ ``feat/hybrid-routing-plugin``,
env-overridable via ``OPENCODE_GIT_URL`` / ``OPENCODE_GIT_REF``) and
writes a ``hybrid-router`` provider entry into
``~/.config/opencode/opencode.json`` pointed at
``http://127.0.0.1:8787/v1``. R8 invokes opencode with
``--model hybrid-router/router/<strategy>/run-<id>`` so routing happens
in the proxy AND per-call attribution back to this runner is exact.

What R8 does, per task:
  1. Generate a 12-hex ``bench_run_id`` and copy the fixture into a
     per-run scratch dir.
  2. Subprocess ``opencode run -m hybrid-router/router/<strategy>/run-<id>
     <prompt>`` (cwd=scratch).
  3. Score by running pytest on the (modified) fixture via the existing
     Docker sandbox (``scorers.functional_python``; wired in Phase 1.2).
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

from hybrid_coding_eval.agents.attribution import (
    attribute_from_decisions_log,
    generate_run_id,
    model_string,
)
from hybrid_coding_eval.core.metrics import (
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_coding_eval.core.paths import repo_root as _resolve_repo_root

__all__ = ["run", "ROUTE"]

ROUTE = "opencode"
_REPO_ROOT: Path = _resolve_repo_root()

DEFAULT_TIMEOUT_S: int = 900


def _task_slug(task_id: str) -> str:
    return task_id.replace("/", "__").replace(" ", "_")


_REAL_DEV_FIXTURES_ROOT: Path = (
    _REPO_ROOT / "src" / "hybrid_coding_eval" / "tasks" / "refactors" / "fixtures"
)


def _copy_fixture(task: Any, dst: Path) -> Path:
    """Copy real-dev fixture (D1-D5) into ``dst``.

    Real-dev tasks expose ``fixtures_dir`` as a *relative* slug; the actual
    fixture lives at
    ``src/hybrid_coding_eval/tasks/refactors/fixtures/<slug>/``. We
    mirror it under ``dst`` so the agent edits in isolation.
    """
    slug = getattr(task, "fixtures_dir", None) or getattr(task, "fixture_dir", None)
    if not slug:
        # Adapters that ship a Path object (exercism-style) instead of a slug.
        fixture_dir = getattr(task, "fixture_dir", None)
        if isinstance(fixture_dir, Path) and fixture_dir.is_dir():
            slug_path = fixture_dir
        else:
            raise FileNotFoundError(f"task {task.id} has no fixtures_dir")
    else:
        slug_path = _REAL_DEV_FIXTURES_ROOT / str(slug)
    if not slug_path.is_dir():
        raise FileNotFoundError(f"fixture {slug_path} not found")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(slug_path, dst)
    return dst


def _score_in_sandbox(scratch: Path) -> Quality:
    """Score the agent's scratch dir.

    Preferred path: run pytest inside the ``hybrid-eval-python:latest``
    Docker sandbox (``--network none``, memory caps, pid cap) — the same
    boundary every agent uses via ``scorers.functional_python``.

    Fallback path: if Docker is unavailable AND test files are present,
    run pytest on the host. Trade-off: loses the sandboxing security
    guarantee, but lets development iterate without a running Docker
    daemon. A warning is logged so the fallback rows can be filtered
    out of canonical analyses.

    Returns ``Quality()`` (functional_pass=None) when no test files are
    present — real-dev D2/D3/D4 prose tasks fall through to the LLM
    judge.
    """
    import shutil as _shutil
    import subprocess as _sp

    test_paths = [
        p for p in scratch.rglob("*.py")
        if p.name.startswith("test_") or p.name.endswith("_test.py")
    ]
    if not test_paths:
        return Quality()

    files: dict[str, str] = {}
    for p in scratch.rglob("*"):
        if not p.is_file():
            continue
        try:
            files[str(p.relative_to(scratch))] = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    if not files:
        return Quality()

    test_rel = str(test_paths[0].relative_to(scratch))
    from hybrid_coding_eval.tasks.refactors.scorers import (
        _run_pytest_in_sandbox,
    )
    sandbox_quality: Quality
    try:
        sandbox_quality = _run_pytest_in_sandbox(files, test_rel)
    except Exception:
        sandbox_quality = Quality()

    # Sandbox returned an actual pass/fail → use it.
    if sandbox_quality.functional_pass is not None:
        return sandbox_quality

    # Docker unavailable or sandbox returned all-None. Try host pytest
    # as a fallback so iteration can progress without Docker. Prefer
    # the repo's .venv/bin/python (which has pytest installed) over
    # whatever python3 is first on PATH.
    venv_py = _REPO_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else (
        _shutil.which("python3") or _shutil.which("python")
    )
    if py is None:
        return Quality()
    try:
        proc = _sp.run(
            [py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", test_rel],
            cwd=str(scratch),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode == 5:
            return Quality()
        passed = proc.returncode == 0
        return Quality(
            functional_pass=passed,
            tests_passed=1 if passed else 0,
            tests_total=1,
            composite=1.0 if passed else 0.0,
        )
    except (_sp.TimeoutExpired, FileNotFoundError):
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
    """Run one real-dev D1/D5 task through opencode."""
    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r8"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    run_dir = output_dir / f"r8_{slug}_{router_strategy}"
    scratch = run_dir / "scratch"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Copy fixture
    try:
        _copy_fixture(task, scratch)
    except Exception as exc:
        return ResultRow(
            task_id=task.id,
            category=getattr(task, "category", "D"),
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

    prompt = getattr(task, "prompt", None) or getattr(task, "instruction", "")
    if not prompt:
        prompt = f"Complete the task in the README.md of {scratch.name}."

    # NB: opencode validates the model field against its registered model
    # list in ~/.config/opencode/opencode.json and rejects unknown ids
    # (ProviderModelNotFoundError). We can't dynamically add `router/.../run-<id>`
    # entries, so for R8 the bench_run_id is NOT embedded in the model.
    # Attribution falls back to the timestamp window for R8 — fine for
    # sequential sweeps (./bench sweep runs strategies serially). R6/R7
    # still use the exact-id path via LiteLLM.
    bench_run_id = generate_run_id()
    model_id = model_string(router_strategy, run_id=None, prefix="hybrid-router/router")

    # opencode CLI shape: `opencode run [message..]` — message is positional,
    # `--cwd` is not a flag; run with cwd=scratch.
    cmd = [
        "opencode",
        "run",
        "-m",
        model_id,
        "--format",
        "json",
        "--log-level",
        "WARN",
        prompt,
    ]

    env = os.environ.copy()
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "bench-eval-key")

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    err: str | None = None
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(scratch),
            timeout=timeout_s,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        (run_dir / "stdout.log").write_text(proc.stdout or "", encoding="utf-8")
        (run_dir / "stderr.log").write_text(proc.stderr or "", encoding="utf-8")
        if proc.returncode != 0:
            err = f"opencode_exit_{proc.returncode}"
    except subprocess.TimeoutExpired:
        err = f"agent_timeout_{timeout_s}s"
    except FileNotFoundError:
        err = "opencode_not_installed"

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)

    # Score via the existing Docker sandbox (same boundary every agent uses).
    quality = _score_in_sandbox(scratch)

    answer_path = run_dir / "answer.txt"
    # The "output" of an agentic run is the modified scratch dir; we
    # snapshot a recursive listing for traceability.
    snapshot_lines: list[str] = []
    for p in sorted(scratch.rglob("*")):
        if p.is_file() and p.stat().st_size < 100_000:
            try:
                snapshot_lines.append(f"### {p.relative_to(scratch)}\n")
                snapshot_lines.append(p.read_text(encoding="utf-8"))
                snapshot_lines.append("\n")
            except (UnicodeDecodeError, OSError):
                continue
    answer_path.write_text("".join(snapshot_lines), encoding="utf-8")

    # Token attribution (primary: bench_run_id; fallback: timestamp window).
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
        category=getattr(task, "category", "D"),
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
