"""R5 — Stanford DevMinion-style hybrid runner (Aider-style review loop).

Wraps ``vendor/minions/minions/minion_code.py`` (MIT-licensed). The
DevMinion protocol follows an architect/editor review loop:

  1. Cloud supervisor generates a development *runbook* (list of steps).
  2. For each step, the local worker implements it, then the cloud
     supervisor reviews. If the review says "request_edits" the worker
     retries with feedback, up to ``max_edit_rounds`` times per step.
  3. After all steps complete, cloud conducts a final integration review.

Both clients are ``minions.clients.openai.OpenAIClient`` instances
pointed at our router proxy on ``:8787`` — the same OpenAIClient-via-proxy
trick R4 uses. The OpenAI-compatible API keeps the proxy as the single
place where routing decisions, cost accounting, and backend selection
happen.

- supervisor → ``model=router/always-cloud`` → gpt-5.5 via OpenAI.
- worker     → ``model=router/always-local`` → qwen/devstral via Ollama.

Public API matches R1/R2/R3/R4: ``run(task, ...) -> ResultRow``. Rows
get ``route="R5"`` and the same tokens/latency/quality/routing shape as
the other runners, so the orchestrator + analysis pipeline don't need
changes.

Scope: R5 supports the same categories as R4 (primarily SWE-bench
Verified, category B). DevMinion is designed for greenfield software
projects, but for SWE-bench we frame the task as "implement a patch
that fixes the problem statement" and extract the final code from the
workspace. For non-SWE tasks (A/C) the prompt is passed as ``task``
with an empty requirements string.

# TODO: extract shared helper — large portions of the monkey-patch /
# client-bootstrap code are copied from r4_minion.py. A later pass
# should lift `_resilient_extract_json`, the minions-vendor sys.path
# tricks, and the stubbing of Together/Gemini into a shared
# ``runners._minions_shim`` module.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the vendored Minion library importable. It expects to be on
# ``sys.path`` at the ``vendor/minions`` level — i.e. the directory that
# contains the ``minions/`` package.
try:
    from hybrid_coding_eval.core.paths import repo_root as _resolve_repo_root
    _REPO_ROOT = _resolve_repo_root()
except ModuleNotFoundError:  # pragma: no cover — during migration
    _here = Path(__file__).resolve()
    for _p in (_here, *_here.parents):
        if (_p / "pyproject.toml").is_file():
            _REPO_ROOT = _p
            break
    else:
        _REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_REPO_ROOT))
_MINIONS_VENDOR = _REPO_ROOT / "vendor" / "minions"
_MINIONS_LEGACY = _REPO_ROOT / "EXTERNAL" / "minions"
_MINIONS_DIR = _MINIONS_VENDOR if _MINIONS_VENDOR.exists() else _MINIONS_LEGACY
sys.path.insert(0, str(_MINIONS_DIR))

# ---------------------------------------------------------------------------
# Reuse the r4_minion bootstrap.
#
# Importing ``hybrid_coding_eval.runners.r4_minion`` has a side effect: it
# patches ``minions.minion._extract_json`` with a resilient parser, stubs
# Together/Gemini/Sambanova clients, and registers ``minions.clients.openai``
# et al. in ``sys.modules``. We piggy-back on that bootstrap so R5 doesn't
# duplicate the work and so we don't double-patch a module shared with R4.
# ---------------------------------------------------------------------------
from hybrid_coding_eval.runners import r4_minion as _r4  # noqa: E402, F401

# Now that ``minions.clients`` is populated with the stub classes plus
# ``OpenAIClient``, and ``minions.usage`` / ``minions.clients.openai`` /
# ``minions.clients.base`` are in ``sys.modules``, we can import the
# DevMinion module. Like ``minions.minion``, the ``minion_code`` module
# has its own ``_extract_json`` that we need to patch too.
import importlib.util as _iu  # noqa: E402

_DEV_MODNAME = "minions.minion_code"
if _DEV_MODNAME not in sys.modules:
    _spec = _iu.spec_from_file_location(
        _DEV_MODNAME, _MINIONS_DIR / "minions" / "minion_code.py"
    )
    _mod = _iu.module_from_spec(_spec)
    sys.modules[_DEV_MODNAME] = _mod
    _spec.loader.exec_module(_mod)
_minion_code_mod = sys.modules[_DEV_MODNAME]

# Patch DevMinion's JSON extractor with R4's resilient version. Also rebind
# the module-level ``json`` symbol to the same ``_JsonProxy`` R4 installed
# on ``minion`` — this makes ``json.loads`` inside minion_code call sites
# route through our resilient loader without mutating the global
# :mod:`json` module.
_minion_code_mod._extract_json = _r4._resilient_extract_json
_minion_code_mod.json = _r4._minion_mod.json

from minions.minion_code import DevMinion  # noqa: E402
from minions.clients.openai import OpenAIClient  # noqa: E402

from hybrid_coding_eval.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)

ROUTE = "R5"
PROXY_URL = "http://127.0.0.1:8787"
CLOUD_MODEL = "router/always-cloud"
LOCAL_MODEL = "router/always-local"


def _ensure_v1(base: str) -> str:
    """Normalise the proxy base URL to include ``/v1`` for the OpenAI SDK."""
    base = (base or "").rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _task_slug(task_id: str) -> str:
    return task_id.replace("/", "__").replace(" ", "_")


def _load_dotenv_once() -> None:
    """Populate ``os.environ`` from the repo-root ``.env``. Minimal parser."""
    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    if "OPENAI_API_KEY" not in os.environ and os.environ.get("OPEN_AI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPEN_AI_API_KEY"]


def _devminion_inputs(task: Any) -> tuple[str, str]:
    """Build ``(task, requirements)`` for DevMinion's ``__call__``.

    DevMinion's signature is ``(task: str, requirements: str = "", ...)``.
    Unlike Minion (which takes ``task`` + ``context: list[str]``), DevMinion
    wants a single natural-language task description plus a free-form
    requirements string.
    """
    from hybrid_coding_eval.runners._shared import task_prompt

    prompt = task_prompt(task)
    tid = task.id
    if tid.startswith("swebench-verified/"):
        ps = getattr(task, "problem_statement", "") or ""
        repo = getattr(task, "repo", "?")
        base_commit = getattr(task, "base_commit", "?")
        task_desc = (
            "Produce a unified diff patch that resolves the following "
            "problem statement from the repository. The final deliverable "
            "is a single ```diff ... ``` code block that applies cleanly "
            "with `git apply`."
        )
        requirements = (
            f"Repository: {repo}\n"
            f"Base commit: {base_commit}\n\n"
            f"Problem statement:\n{ps}"
        )
        return task_desc, requirements
    # Fallback for non-SWE tasks: prompt text as the task; empty requirements.
    return prompt, ""


def _aggregate_calls(result: dict[str, Any]) -> tuple[int, int, list[str]]:
    """Walk DevMinion's return dict to count cloud + local calls.

    DevMinion issues:
      - 1 cloud call to generate the runbook
      - For each step: attempts x (1 local impl + 1 cloud review)
      - 1 cloud call for the final integration review

    Return (cloud_calls, local_calls, per_call_backends).
    """
    cloud_calls = 0
    local_calls = 0
    backends: list[str] = []

    session_log = (result or {}).get("session_log") or {}
    # Runbook generation is always a cloud call if it happened (runbook is set).
    if session_log.get("runbook"):
        cloud_calls += 1
        backends.append("gpt-5.5")

    steps_completed = session_log.get("steps_completed") or []
    for step_result in steps_completed:
        attempts = (step_result or {}).get("attempts") or []
        for attempt in attempts:
            # One local implementation per attempt.
            if attempt.get("local_response") is not None:
                local_calls += 1
                backends.append(LOCAL_MODEL)
            # One cloud review per attempt.
            if attempt.get("review_decision") is not None:
                cloud_calls += 1
                backends.append("gpt-5.5")

    # Final integration review (cloud) if we made it that far.
    if session_log.get("final_assessment") is not None:
        cloud_calls += 1
        backends.append("gpt-5.5")

    return cloud_calls, local_calls, backends


def _gather_final_output(result: dict[str, Any], workspace_dir: Path) -> str:
    """Build a text blob representing the DevMinion final output.

    DevMinion builds code files in a workspace directory. For observability
    we concatenate file paths + contents and append the final-assessment
    summary so a SWE-bench or LLM-judge scorer can inspect the deliverable.
    """
    lines: list[str] = []
    final = (result or {}).get("final_assessment") or {}
    if isinstance(final, dict) and final:
        lines.append("=== FINAL ASSESSMENT ===")
        lines.append(json.dumps(final, indent=2, ensure_ascii=False))
        lines.append("")

    # Dump workspace files.
    if workspace_dir.exists():
        lines.append("=== WORKSPACE FILES ===")
        for p in sorted(workspace_dir.rglob("*")):
            if not p.is_file():
                continue
            # Skip internal dirs the WorkspaceManager creates.
            if ".backups" in p.parts:
                continue
            try:
                rel = p.relative_to(workspace_dir)
            except ValueError:
                rel = p
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                content = "<binary or unreadable>"
            lines.append(f"\n--- {rel} ---")
            lines.append(content)
    return "\n".join(lines).strip() + "\n"


def run(
    task: Any,
    proxy_url: str = PROXY_URL,
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    max_edit_rounds: int = 3,
    timeout_s: int = 1200,  # noqa: ARG001
) -> ResultRow:
    """Execute one task through the hybrid-DevMinion route."""
    _load_dotenv_once()

    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r5"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    out_path = output_dir / f"{slug}_R5.txt"
    workspace_dir = output_dir / f"{slug}_R5_workspace"
    log_dir = output_dir / f"{slug}_R5_logs"
    try:
        output_ref = str(out_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        output_ref = str(out_path.resolve())

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")
    base_url = _ensure_v1(proxy_url)
    # GPT-5.5 is a reasoning model — the proxy echoes back ``gpt-5.5-*``
    # regardless of the client-side ``model_name`` we use. DevMinion issues
    # runbook / review calls with ``response_format={'type': 'json_object'}``,
    # where the reasoning-token budget is counted against max_completion_tokens.
    # A 4000-token budget (what R4's ``Minion`` supervisor uses) empties
    # into reasoning alone and returns zero content. Bump to 16000 so
    # reasoning + JSON both fit.
    supervisor = OpenAIClient(
        model_name=CLOUD_MODEL,
        api_key=api_key,
        base_url=base_url,
        max_tokens=16000,
    )
    worker = OpenAIClient(
        model_name=LOCAL_MODEL,
        api_key=api_key,
        base_url=base_url,
        max_tokens=4000,
        local=True,  # tells the library to return the 3-tuple shape
    )

    devminion = DevMinion(
        local_client=worker,
        remote_client=supervisor,
        workspace_dir=str(workspace_dir),
        max_edit_rounds=max_edit_rounds,
        log_dir=str(log_dir),
        backup_enabled=False,  # no need to version backups during a sweep
    )

    dm_task, dm_requirements = _devminion_inputs(task)
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    result: dict[str, Any] | None = None
    err_msg: str | None = None
    try:
        result = devminion(
            task=dm_task,
            requirements=dm_requirements,
            logging_id=slug,
        )
    except Exception as exc:  # noqa: BLE001
        # DevMinion's JSON parse path is fragile on SWE-bench diffs. When
        # the resilient parser can't recover, surface the failure as a
        # skipped row rather than a crash. Keep whatever partial usage
        # the clients already recorded on ``devminion``.
        err_msg = f"devminion_error: {type(exc).__name__}: {str(exc)[:200]}"

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    if result is None:
        out_path.write_text(f"[R5 ERROR] {err_msg}\n", encoding="utf-8")
        return ResultRow(
            task_id=task.id,
            category=getattr(task, "category", "?"),
            route=ROUTE,
            hardware_profile_ref=hardware_profile_ref,
            tokens=TokenUsage(),
            latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
            quality=Quality(),
            routing=Routing(total_calls=0, local_calls=0, cloud_calls=0),
            output_ref=output_ref,
            started_at=started_at,
            finished_at=finished_at,
            error=err_msg,
        )

    # Aggregate usage. DevMinion returns Usage dataclasses from minions.usage.
    remote_usage = result.get("remote_usage")
    local_usage = result.get("local_usage")
    r_prompt = getattr(remote_usage, "prompt_tokens", 0) or 0
    r_comp = getattr(remote_usage, "completion_tokens", 0) or 0
    l_prompt = getattr(local_usage, "prompt_tokens", 0) or 0
    l_comp = getattr(local_usage, "completion_tokens", 0) or 0

    cloud_calls, local_calls, backends = _aggregate_calls(result)

    # Write a human-readable summary of the deliverable (for scorers).
    final_text = _gather_final_output(result, workspace_dir)
    out_path.write_text(final_text, encoding="utf-8")

    return ResultRow(
        task_id=task.id,
        category=getattr(task, "category", "?"),
        route=ROUTE,
        hardware_profile_ref=hardware_profile_ref,
        tokens=TokenUsage(
            prompt=r_prompt + l_prompt,
            completion=r_comp + l_comp,
            cached=0,
            reasoning=0,
            local_prompt=l_prompt,
            local_completion=l_comp,
            cloud_prompt=r_prompt,
            cloud_completion=r_comp,
        ),
        latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
        quality=Quality(),
        routing=Routing(
            total_calls=cloud_calls + local_calls,
            local_calls=local_calls,
            cloud_calls=cloud_calls,
            per_call_backends=backends,
        ),
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
        error=None,
    )


def main() -> int:
    import argparse

    from hybrid_coding_eval.benchmarks.swebench_verified import adapter as swe_adapter

    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", help="specific SWE-bench task id (else first)")
    ap.add_argument("--out", default="results/r5")
    args = ap.parse_args()

    tasks = {t.id: t for t in swe_adapter.load_tasks(n=10, seed=42)}
    if args.task_id:
        task = tasks[args.task_id]
    else:
        task = next(iter(tasks.values()))
    row = run(task, output_dir=Path(args.out))
    print(json.dumps({
        "task_id": row.task_id,
        "route": row.route,
        "tokens": row.tokens.__dict__,
        "wall_ms": row.latency.wall_ms,
        "output_ref": row.output_ref,
        "error": row.error,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
