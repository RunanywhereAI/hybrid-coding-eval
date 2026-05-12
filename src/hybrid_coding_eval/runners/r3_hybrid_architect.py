"""R3 — hybrid architect runner.

Subprocess-calls ``runners/_architect_runner.mjs`` which, in turn, imports
``runArchitect()`` from ``router/agentic/architect-core.mjs``. The JS side
does the full architect pipeline against the local router proxy:

  1. PLANNER  — always cloud (``router/always-cloud``) — decomposes the task.
  2. EXECUTOR — per-step, ``router/heuristic`` (or ``always-local``/
     ``always-cloud`` when the planner's ``router_hint`` forces it).
  3. SYNTH    — ``router/heuristic`` in practice almost always lands on cloud.

This runner parses the JS output and builds a :class:`ResultRow` whose
token counts are split into ``local_*`` vs ``cloud_*`` based on each
call's ``routerChoice``. ``routing.per_call_backends`` preserves the
full attribution chain (``planner/cloud`` → ``step_1/local`` →
``step_2/cloud`` → ... → ``synth/cloud``).

CLI:

    python -m runners.r3_hybrid_architect \\
        --task-source humaneval_plus \\
        --task-id HumanEval_99 \\
        --out /tmp/r3_test/

Per PLAN.md §7, the ResultRow's cost is NEVER persisted. The JS side's
``totals.hybridCostUsd`` is returned in the metadata field only for
cross-check purposes (the aggregator re-derives cost from tokens).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hybrid_coding_eval.core.metrics import Latency, Quality, ResultRow, Routing, TokenUsage
from hybrid_coding_eval.core.results import append_row

try:
    from hybrid_coding_eval.core.paths import repo_root as _repo_root
except ModuleNotFoundError:  # pragma: no cover — during migration
    def _repo_root() -> Path:
        here = Path(__file__).resolve()
        for parent in (here, *here.parents):
            if (parent / "pyproject.toml").is_file():
                return parent
        raise RuntimeError("repo_root not resolvable")

from ._shared import REPO_ROOT, load_task_by_id, task_prompt

logger = logging.getLogger(__name__)

# Node subprocess shim lives at router/pipelines/architect/runner.mjs (moved
# from runners/_architect_runner.mjs in T-03 so Node files stay under
# router/, not mixed into the Python package tree).
_ARCHITECT_SHIM = _repo_root() / "router" / "pipelines" / "architect" / "runner.mjs"
_ROUTE = "R3"


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #


def _usage_get(u: dict[str, Any] | None, key: str) -> int:
    if not u:
        return 0
    v = u.get(key)
    return int(v) if isinstance(v, (int, float)) else 0


def _cached_from_usage(u: dict[str, Any] | None) -> int:
    if not u:
        return 0
    d = u.get("prompt_tokens_details") or {}
    v = d.get("cached_tokens")
    return int(v) if isinstance(v, (int, float)) else 0


def _reasoning_from_usage(u: dict[str, Any] | None) -> int:
    if not u:
        return 0
    d = u.get("completion_tokens_details") or {}
    v = d.get("reasoning_tokens")
    return int(v) if isinstance(v, (int, float)) else 0


def _attribute_call(
    role: str,
    router_choice: str,
    router_backend: str,
    usage: dict[str, Any] | None,
    tokens: TokenUsage,
    per_call_backends: list[str],
    per_call_ms: list[int],
    elapsed_ms: int,
    total_calls_counter: dict[str, int],
) -> None:
    """Fold one call (planner / step_i / synth) into the running totals.

    ``role`` is the short tag written into ``per_call_backends`` (e.g.
    ``"planner"`` or ``"step_3"``). ``router_choice`` is the authoritative
    local-vs-cloud label emitted by the proxy for this call (``"local"``,
    ``"cloud"``, or ``"error"``).
    """
    prompt = _usage_get(usage, "prompt_tokens")
    completion = _usage_get(usage, "completion_tokens")
    cached = _cached_from_usage(usage)
    reasoning = _reasoning_from_usage(usage)

    tokens.prompt += prompt
    tokens.completion += completion
    tokens.cached += cached
    tokens.reasoning += reasoning

    if router_choice == "local":
        tokens.local_prompt += prompt
        tokens.local_completion += completion
        total_calls_counter["local"] += 1
    elif router_choice == "cloud":
        tokens.cloud_prompt += prompt
        tokens.cloud_completion += completion
        total_calls_counter["cloud"] += 1
    else:
        # "error" or unknown — still record the attempt, just don't attribute
        # its tokens to either side (they'll be 0 anyway on an error path).
        total_calls_counter["other"] += 1

    per_call_backends.append(f"{role}/{router_choice}/{router_backend}")
    per_call_ms.append(int(elapsed_ms or 0))
    total_calls_counter["total"] += 1


def _build_result_row(
    task_id: str,
    category: str,
    hardware_profile_ref: str,
    wall_ms: int,
    arch: dict[str, Any],
    output_ref: str,
    started_at: str,
    finished_at: str,
) -> ResultRow:
    """Turn the JS architect run's JSON into a ResultRow.

    ``arch`` is the parsed stdout from ``_architect_runner.mjs``.
    """
    tokens = TokenUsage()
    per_call_backends: list[str] = []
    per_call_ms: list[int] = []
    counter = {"total": 0, "local": 0, "cloud": 0, "other": 0}

    planner = arch.get("plannerResult")
    if planner:
        _attribute_call(
            role="planner",
            router_choice=planner.get("routerChoice") or "?",
            router_backend=planner.get("routerBackend") or "?",
            usage=planner.get("usage"),
            tokens=tokens,
            per_call_backends=per_call_backends,
            per_call_ms=per_call_ms,
            elapsed_ms=planner.get("elapsed") or 0,
            total_calls_counter=counter,
        )

    for r in arch.get("stepResults") or []:
        idx = (r.get("step") or {}).get("index") or "?"
        _attribute_call(
            role=f"step_{idx}",
            router_choice=r.get("routerChoice") or "?",
            router_backend=r.get("routerBackend") or "?",
            usage=r.get("usage"),
            tokens=tokens,
            per_call_backends=per_call_backends,
            per_call_ms=per_call_ms,
            elapsed_ms=r.get("elapsed") or 0,
            total_calls_counter=counter,
        )

    synth = arch.get("synth")
    if synth:
        _attribute_call(
            role="synth",
            router_choice=synth.get("routerChoice") or "?",
            router_backend=synth.get("routerBackend") or "?",
            usage=synth.get("usage"),
            tokens=tokens,
            per_call_backends=per_call_backends,
            per_call_ms=per_call_ms,
            elapsed_ms=synth.get("elapsed") or 0,
            total_calls_counter=counter,
        )

    routing = Routing(
        total_calls=counter["total"],
        local_calls=counter["local"],
        cloud_calls=counter["cloud"],
        per_call_backends=per_call_backends,
    )
    latency = Latency(wall_ms=wall_ms, per_call_ms=per_call_ms)
    # Quality is populated by the scorer downstream. Leave all fields None.
    quality = Quality()

    return ResultRow(
        task_id=task_id,
        category=category,
        route=_ROUTE,
        hardware_profile_ref=hardware_profile_ref,
        tokens=tokens,
        latency=latency,
        quality=quality,
        routing=routing,
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
    )


# --------------------------------------------------------------------------- #
# Subprocess driver
# --------------------------------------------------------------------------- #


def _invoke_architect(
    task_text: str,
    proxy_url: str,
    max_steps: int,
    timeout_s: int,
    router_strategy: str = "heuristic",
) -> tuple[dict[str, Any], int, str | None]:
    """Run the JS shim. Returns ``(parsed_stdout, wall_ms, error_or_None)``.

    ``router_strategy`` controls the model id passed to the architect's
    executor and synthesizer steps (``router/<strategy>``). Defaults to
    ``heuristic`` to preserve v3 sweep semantics. Valid values match the
    7 strategies in ``router/strategies.mjs``.

    Errors from the subprocess are surfaced as the 3rd element rather than
    raised — the caller wraps them into an error-flavoured ResultRow.
    """
    if not _ARCHITECT_SHIM.exists():
        return {}, 0, f"architect shim not found at {_ARCHITECT_SHIM}"

    stdin_payload = json.dumps(
        {
            "task": task_text,
            "proxy": proxy_url,
            "maxSteps": max_steps,
            "executor": f"router/{router_strategy}",
            "synthesizer": f"router/{router_strategy}",
        }
    )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["node", str(_ARCHITECT_SHIM)],
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        wall_ms = int((time.monotonic() - t0) * 1000)
        return {}, wall_ms, f"architect subprocess timed out after {timeout_s}s: {exc}"
    except FileNotFoundError as exc:
        wall_ms = int((time.monotonic() - t0) * 1000)
        return {}, wall_ms, f"node not found on PATH: {exc}"
    wall_ms = int((time.monotonic() - t0) * 1000)

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip().splitlines()[-5:]
        return {}, wall_ms, (
            f"architect subprocess exited {proc.returncode}: "
            + " | ".join(stderr_tail)
        )

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        head = (proc.stdout or "")[:200]
        return {}, wall_ms, f"architect subprocess returned non-JSON stdout ({exc}): {head!r}"

    return parsed, wall_ms, None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def run(
    task: Any,
    proxy_url: str = "http://127.0.0.1:8787",
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    max_steps: int = 10,
    timeout_s: int = 1800,
    router_strategy: str = "heuristic",
) -> ResultRow:
    """Invoke the JS architect via subprocess and build a ResultRow.

    ``task`` is a benchmark-adapter dataclass (HumanEval+ / SWE-bench /
    BigCodeBench-Hard / Custom-Arch). The single user-facing prompt is
    constructed via :func:`_shared.task_prompt`, then handed to the
    architect which decomposes it internally.

    ``output_dir`` — if given, the raw JSON trace from the JS runner and
    the final-answer text are written there; the row's ``output_ref``
    points at the directory.

    Errors are captured as an error-flavoured ResultRow (route='R3',
    tokens zeroed, ``routing.per_call_backends=['error/<msg>']``) rather
    than raised — the orchestrator wants the whole sweep to complete
    even if one task fails.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    prompt = task_prompt(task)

    arch, wall_ms, err = _invoke_architect(
        task_text=prompt,
        proxy_url=proxy_url,
        max_steps=max_steps,
        timeout_s=timeout_s,
        router_strategy=router_strategy,
    )
    finished_at = datetime.now(timezone.utc).isoformat()

    task_id = getattr(task, "id", "<unknown>")
    category = getattr(task, "category", "?")

    # Persist raw output for later inspection / scoring.
    output_ref = ""
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_id = task_id.replace("/", "__")
        trace_path = out_dir / f"{safe_id}.r3.arch.json"
        answer_path = out_dir / f"{safe_id}.r3.answer.txt"
        trace_payload = {
            "task_id": task_id,
            "prompt": prompt,
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_ms": wall_ms,
            "error": err,
            "arch": arch,
        }
        trace_path.write_text(
            json.dumps(trace_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        answer_path.write_text(
            arch.get("finalOutput") or (f"[R3 error] {err}" if err else ""),
            encoding="utf-8",
        )
        output_ref = str(trace_path)

    if err:
        logger.warning("R3 failed for %s: %s", task_id, err)
        return ResultRow(
            task_id=task_id,
            category=category,
            route=_ROUTE,
            hardware_profile_ref=hardware_profile_ref,
            tokens=TokenUsage(),
            latency=Latency(wall_ms=wall_ms, per_call_ms=[]),
            quality=Quality(),
            routing=Routing(
                total_calls=0,
                local_calls=0,
                cloud_calls=0,
                per_call_backends=[f"error/{err[:200]}"],
            ),
            output_ref=output_ref,
            started_at=started_at,
            finished_at=finished_at,
            error=err,
        )

    return _build_result_row(
        task_id=task_id,
        category=category,
        hardware_profile_ref=hardware_profile_ref,
        wall_ms=wall_ms,
        arch=arch,
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="r3_hybrid_architect",
        description="Run the R3 hybrid-architect route on a single task.",
    )
    p.add_argument("--task-source", required=True, choices=[
        "humaneval_plus", "swebench_verified", "bigcodebench_hard", "custom_arch",
    ])
    p.add_argument("--task-id", required=True, help="e.g. HumanEval_99")
    p.add_argument("--proxy-url", default="http://127.0.0.1:8787")
    p.add_argument("--out", type=Path, default=None,
                   help="Directory for the raw architect trace + final answer.")
    p.add_argument("--hardware-profile-ref", default="",
                   help="Manifest path / hash — passed through into the ResultRow.")
    p.add_argument("--max-steps", type=int, default=10)
    p.add_argument("--timeout-s", type=int, default=1800)
    p.add_argument("--jsonl", type=Path, default=None,
                   help="If set, append the ResultRow to this JSONL file.")
    args = p.parse_args(argv)

    task = load_task_by_id(args.task_source, args.task_id)
    row = run(
        task,
        proxy_url=args.proxy_url,
        hardware_profile_ref=args.hardware_profile_ref,
        output_dir=args.out,
        max_steps=args.max_steps,
        timeout_s=args.timeout_s,
    )

    if args.jsonl:
        append_row(args.jsonl, row)

    json.dump(asdict(row), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
