"""R10 — Cline coding-agent CLI on Exercism Python / real-dev fixtures.

**EXPERIMENTAL in v1.4.** R10 is the third agent-loop runner alongside R7
(aider) and R8 (opencode). Cline (https://github.com/cline/cline) is an
open-source coding agent. The 3.0.9 release ships a real ``cline`` CLI
binary (npm-installed) that can be driven from a subprocess for headless
benchmark runs.

Cline 3.0.9 invocation (verified via integration smoke against the router):

    cline -P ollama -m router/<strategy>/run-<bench_run_id>            \\
          -c <scratch_dir> --auto-approve true --json -t <timeout_s>   \\
          "<prompt>"

Notes / gotchas:
  * The provider id is passed via ``-P``. The router presents an
    Ollama-style endpoint (``/v1`` with OpenAI-compat schema). The
    actual base URL for the ``ollama`` provider is stored in
    ``~/.cline/data/settings/providers.json`` — it is NOT a CLI flag.
    ``bench setup`` writes that file in Phase 1.5b; this runner just
    drives the CLI.
  * ``-m`` carries the model id verbatim through to the router; the
    router's ``runIdMatch`` regex extracts ``run-<id>`` and writes
    ``bench_run_id`` into ``decisions.jsonl`` for attribution.
  * ``--json`` requests stream-json output. We capture the stream to
    ``stdout.log`` for forensic inspection; the final task-completion
    event isn't required for scoring (pytest on the scratch dir gives
    the ground-truth pass/fail).
  * Earlier code in this file used fictional flags (``run`` subcommand,
    ``--task``, ``--provider openai-compatible``, ``--base-url``,
    ``--non-interactive``, ``--yes``, ``--file``). None of those exist
    in cline 3.0.9.

What R10 does, per task:
  1. Generate a 12-hex ``bench_run_id`` + copy the task fixture into a
     per-run scratch dir (shared helper with R7).
  2. Subprocess ``cline -P ollama -m router/<strategy>/run-<id>`` with
     ``cwd`` and ``-c`` set to the scratch dir so file edits happen
     there.
  3. Run pytest on the (modified) fixture for a local pass/fail.
  4. Reconstruct token attribution by filtering decisions.jsonl on
     ``bench_run_id`` (primary) / timestamp window (fallback).

If ``cline`` is not on PATH the runner returns a ResultRow with
``error="cline_not_installed"`` rather than raising — mirrors the
graceful path R7 takes when ``aider`` is missing. Phase 2 will rename
this file to ``agents/cline.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hybrid_coding_eval.agents.aider import (
    _copy_fixture,
    _resolve_fixture_dir,  # noqa: F401 — re-exported for compatibility
    _run_tests_local,
)
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

ROUTE = "cline"
_REPO_ROOT: Path = _resolve_repo_root()

DEFAULT_TIMEOUT_S: int = 900

# Default fallback path. cline 3.0.9 ships via npm and lands here on macOS
# Homebrew installs; ``shutil.which("cline")`` is the primary lookup.
_CLINE_FALLBACK_PATH: str = "/opt/homebrew/bin/cline"


def _task_slug(task_id: str) -> str:
    return task_id.replace("/", "__").replace(" ", "_")


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
    """Run one task through the Cline coding-agent CLI."""
    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r10"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    run_dir = output_dir / f"r10_{slug}_{router_strategy}"
    scratch = run_dir / "scratch"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy fixture so the run is isolated. Reuses R7's helper which
    # handles both Exercism (``fixture_dir`` Path) and real_dev
    # (``fixtures_dir`` slug) shapes.
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

    # 2. Build the prompt. Same shape as R7: single-file Exercism stub
    # gets a hint about the stub filename; multi-file real_dev tasks
    # rely on the task's self-contained prompt. Cline has no ``--file``
    # flag, so the only way to scope its working set is to (a) cwd into
    # the scratch dir, and (b) name the target file in the prompt.
    if len(editable_files) == 1 and editable_files[0].name not in (
        "solution.py",
        "solution.sh",
    ):
        prompt = task.prompt + (
            "\n\nImplement the function(s) in "
            f"`{editable_files[0].name}` so that all tests in "
            f"`{test_path.name}` pass. Edit only that file."
        )
    elif editable_files:
        file_list = ", ".join(f"`{p.name}`" for p in editable_files)
        prompt = task.prompt + (
            f"\n\nEdit the following file(s) so the tests in "
            f"`{test_path.name}` pass: {file_list}."
        )
    else:
        prompt = task.prompt

    bench_run_id = generate_run_id()
    # Cline doesn't accept a base-URL flag; the per-provider base URL
    # lives in ``~/.cline/data/settings/providers.json`` (written by
    # ``bench setup``). The ``router/<strategy>/run-<id>`` model id is
    # forwarded transparently through to the router proxy.
    model_id = model_string(router_strategy, bench_run_id, prefix="router")

    # 3. Subprocess Cline. Prefer ``cline`` on PATH (npm-installed
    # globally on macOS Homebrew); fall back to the canonical Homebrew
    # path. If neither exists the FileNotFoundError below converts to
    # a ``cline_not_installed`` ResultRow.
    cline_bin = shutil.which("cline") or _CLINE_FALLBACK_PATH

    cmd = [
        cline_bin,
        "-P", "ollama",
        "-m", model_id,
        "-c", str(scratch),
        "--auto-approve", "true",
        "--json",
        "-t", str(timeout_s),
        prompt,  # positional, last arg
    ]

    # Keep a clean env copy. We deliberately do NOT set
    # OPENAI_API_KEY/OPENAI_API_BASE/CLINE_API_KEY/CLINE_API_BASE — they
    # have no effect on cline 3.0.9 (base URL is configured via
    # providers.json, and the router accepts any key). Leaving real
    # secrets out of subprocess env is the safer default.
    env = os.environ.copy()

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
            # Cline sometimes exits non-zero when the task is judged
            # "incomplete" but it still wrote a file — let the pytest
            # step decide pass/fail rather than gating on this.
            err = f"cline_exit_{proc.returncode}"
    except subprocess.TimeoutExpired:
        err = f"agent_timeout_{timeout_s}s"
    except FileNotFoundError:
        err = "cline_not_installed"

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)

    # 4. Score by running pytest on the (possibly modified) editable files.
    # When cline isn't installed there's no point running tests on the
    # untouched fixture — return an empty quality.
    if err == "cline_not_installed":
        quality = Quality()
    else:
        quality = _run_tests_local(scratch, test_path)

    # Save the primary edited file as the canonical output. For multi-file
    # tasks we snapshot the first editable file; the full scratch dir
    # stays under outputs/ for inspection.
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
