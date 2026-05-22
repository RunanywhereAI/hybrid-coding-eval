"""R9 — Claude Code CLI agent on Exercism / real_dev tasks.

Claude Code is Anthropic's official agentic coding CLI
(https://github.com/anthropics/claude-code). Like R7 (aider) and R8
(opencode), it operates *inside a repo*: it reads files, emits edits,
executes shell commands, and iterates. R9 wraps the ``claude -p`` one-shot
mode so the harness can drive it task-by-task.

Routing caveat (v1.4)
---------------------
The router proxy (``router/server.mjs``) exposes only the OpenAI-compat
surface ``/v1/chat/completions`` — there is **no** Anthropic-compat
``/v1/messages`` endpoint. Claude Code speaks the Anthropic Messages
protocol natively, so pointing ``ANTHROPIC_BASE_URL`` at our router will
404 on the first call. Two practical modes:

1. **Always-cloud direct** (default in v1.4): when ``router_strategy`` is
   ``"always-cloud-direct"`` or any strategy not requesting routing,
   leave ``ANTHROPIC_BASE_URL`` unset and let Claude Code call
   ``api.anthropic.com`` directly with a real ``ANTHROPIC_API_KEY``. No
   per-call routing is exercised — Claude Code measures Anthropic-cloud
   wall-clock + token cost end-to-end.

2. **Router-mediated** (experimental): set ``ANTHROPIC_BASE_URL`` to
   ``<proxy>/v1`` anyway. This will only work once the router grows an
   Anthropic-compat shim (v1.5+). For now this mode reports
   ``router_unsupported`` and falls back to mode (1) so the smoke run
   still produces a row.

What R9 does, per task:
  1. Generate a 12-hex ``bench_run_id`` + copy the task fixture into a
     per-run scratch dir.
  2. Subprocess ``claude -p <prompt> --output-format text`` with cwd =
     scratch. Permissions bypassed in the sandbox so Claude Code can
     read/write/edit/bash freely.
  3. After Claude Code exits, run pytest on the (possibly modified)
     fixture file using the host venv (fast-local path R7 also uses).
  4. Token attribution by filtering ``decisions.jsonl`` for
     ``bench_run_id`` — empty in always-cloud-direct mode because no
     calls hit the router. The bench_run_id is still emitted so that the
     v1.5+ router-mediated path attributes correctly once the
     Anthropic-compat shim lands.

Phase 2 will rename this module to ``agents/claude_code.py``; ``ROUTE``
stays ``"claude-code"`` so the public dispatch key never changes.
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

ROUTE = "claude-code"
_REPO_ROOT: Path = _resolve_repo_root()

DEFAULT_TIMEOUT_S: int = 900


def _task_slug(task_id: str) -> str:
    return task_id.replace("/", "__").replace(" ", "_")


_REAL_DEV_FIXTURES_ROOT: Path = (
    _REPO_ROOT / "src" / "hybrid_coding_eval" / "tasks" / "refactors" / "fixtures"
)


def _resolve_fixture_dir(task: Any) -> Path:
    """Return the source fixture dir for ``task`` — handles both Exercism
    (``fixture_dir`` Path) and real_dev (``fixtures_dir`` slug) shapes.
    Mirror of the helper in r7_aider.py.
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
    """Locate the canonical test file inside ``scratch``."""
    tests_attr = getattr(task, "tests", None)
    if isinstance(tests_attr, str) and tests_attr:
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
    """Copy the task fixture into ``dst``. Returns ``(test_path, editable_files)``."""
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
    if not editable:
        run_cmd = getattr(task, "run_cmd", None) or ""
        for tok in run_cmd.split():
            if tok.endswith(".py") or tok.endswith(".sh"):
                editable = [dst / tok]
                break
    return test_path, editable


def _run_tests_local(stub_dir: Path, test_path: Path) -> Quality:
    """Run pytest on the test file in the stub dir. Fast local subprocess.

    Identical to r7_aider._run_tests_local — duplicated here to keep R9
    self-contained for the eventual ``agents/claude_code.py`` rename.
    """
    venv_py = _REPO_ROOT / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else (
        shutil.which("python3") or shutil.which("python") or "python3"
    )
    try:
        proc = subprocess.run(
            [py, "-m", "pytest", "-q", str(test_path)],
            cwd=stub_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        passed = proc.returncode == 0
        return Quality(
            functional_pass=passed,
            tests_passed=1 if passed else 0,
            tests_total=1,
            composite=1.0 if passed else 0.0,
        )
    except subprocess.TimeoutExpired:
        return Quality(functional_pass=False, composite=0.0)


def _wants_router_routing(strategy: str) -> bool:
    """True iff the requested strategy expects router-mediated routing.

    ``always-cloud-direct`` (and a few synonyms) skip the router entirely
    and let Claude Code talk to api.anthropic.com directly. Everything
    else *would* like to be routed — but the router doesn't speak the
    Anthropic Messages protocol yet (v1.4), so we still bypass and log
    the limitation in ``error``.
    """
    direct = {"always-cloud-direct", "anthropic-direct", "always-cloud"}
    return strategy not in direct


def run(
    task: Any,
    *,
    proxy_url: str = "http://127.0.0.1:8787",
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    router_strategy: str = "always-cloud-direct",
    timeout_s: int = DEFAULT_TIMEOUT_S,
    **_unused: Any,
) -> ResultRow:
    """Run one task through Claude Code's ``claude -p`` one-shot CLI."""
    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r9"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    run_dir = output_dir / f"r9_{slug}_{router_strategy}"
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

    # 2. Build the prompt. Single-file Exercism stubs get a hint; multi-
    # file real_dev tasks are self-contained.
    if len(editable_files) == 1 and editable_files[0].name not in (
        "solution.py",
        "solution.sh",
    ):
        prompt = task.prompt + (
            "\n\nImplement the function(s) in the stub so that all tests in "
            f"{test_path.name} pass. Edit only the stub file."
        )
    else:
        prompt = task.prompt

    bench_run_id = generate_run_id()
    # The model_string is emitted for parity with R7/R8 even though Claude
    # Code's CLI does not accept an OpenAI-shape model id. It's recorded
    # on the row's started_at / decision-log query so the v1.5+
    # Anthropic-shim path attributes cleanly once it lands.
    _model_id_for_attribution = model_string(
        router_strategy, bench_run_id, prefix="router"
    )

    # 3. Subprocess Claude Code.
    claude_bin = shutil.which("claude") or "claude"
    cmd = [
        claude_bin,
        "-p",
        prompt,
        "--output-format",
        "text",
        # Sandbox is the per-run scratch dir; let Claude Code touch any
        # file under it.
        "--add-dir",
        str(scratch),
        # Bypass interactive permission prompts — required for non-TTY
        # one-shot mode. Safe here because cwd is an isolated scratch.
        "--permission-mode",
        "bypassPermissions",
        # Minimal mode: no hooks, plugins, CLAUDE.md auto-discovery, etc.
        # Keeps the runner reproducible across user machines.
        "--bare",
    ]

    env = os.environ.copy()
    err: str | None = None
    if _wants_router_routing(router_strategy):
        # The router doesn't speak /v1/messages yet (v1.4). Record this
        # in the error field so analysis can filter, but still run with
        # direct Anthropic API so the row isn't empty.
        err = "router_unsupported_for_claude_code_v1.4"
    # Strict-Anthropic-auth mode (per --bare): the API key must come from
    # ANTHROPIC_API_KEY (or apiKeyHelper). We pass through whatever the
    # caller has set; if absent, Claude Code will error out and we'll
    # capture that in stderr.
    if "ANTHROPIC_API_KEY" not in env:
        env["ANTHROPIC_API_KEY"] = env.get("CLAUDE_API_KEY", "")

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    proc_returncode: int | None = None
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
        proc_returncode = proc.returncode
        (run_dir / "stdout.log").write_text(proc.stdout or "", encoding="utf-8")
        (run_dir / "stderr.log").write_text(proc.stderr or "", encoding="utf-8")
        if proc.returncode != 0 and err is None:
            err = f"claude_exit_{proc.returncode}"
    except subprocess.TimeoutExpired:
        err = f"agent_timeout_{timeout_s}s"
    except FileNotFoundError:
        err = "claude_not_installed"

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)

    # 4. Score by running pytest on the (possibly modified) editable files.
    quality = _run_tests_local(scratch, test_path)

    # Save the primary edited file as the canonical output.
    answer_path = run_dir / "answer.py"
    primary = editable_files[0] if editable_files else None
    if primary and primary.exists():
        answer_path.write_text(primary.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        answer_path.write_text("", encoding="utf-8")

    # 5. Token attribution. In always-cloud-direct mode no calls hit the
    # router so attribution is empty. The fallback timestamp window query
    # still runs but won't match anything for Claude Code calls.
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
