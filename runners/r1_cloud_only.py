"""R1 cloud-only runner (T2.1).

Executes a single benchmark task through the local router proxy with
``model="router/always-cloud"`` so *all* tokens are spent against the
cloud backend. Emits a :class:`lib.metrics.ResultRow` with
``route="R1"``, ``local_*`` tokens zeroed, and the raw model answer
persisted next to the results file as ``<task_id>_R1.txt``.

Design notes
------------
- The runner is deliberately benchmark-agnostic: it inspects the ``Task``
  dataclass via duck-typing (``hasattr``) and builds the prompt with a
  per-benchmark adapter function. That keeps the cross-benchmark
  comparison honest — R1 and R3 see the **same prompt bytes**.
- Token counts come from the router's ``X-Tokens-*`` response headers
  (source of truth — populated by ``router/server.mjs``
  ``jsonThrough``). We fall back to ``response.usage`` if headers are
  missing.
- Errors (proxy 5xx, connection refused, timeout, malformed body) do
  NOT raise; they emit a row with ``error=`` set, zeroed tokens, and no
  ``quality`` fields. The orchestrator in T4.1 treats these as skipped
  runs. The rationale for adding an ``error`` field to ``ResultRow``
  rather than a sidecar file is that the downstream aggregation reads
  the JSONL and flowing the error through the same record keeps
  schema-based filtering trivial (``rows = [r for r in rows if not
  r.error]``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the repo root importable when this file is run as a script
# (``python -m runners.r1_cloud_only`` handles this automatically, but
# running the file directly shouldn't crash either).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402

from lib.metrics import Latency, Quality, ResultRow, Routing, TokenUsage  # noqa: E402
from lib.results import append_row  # noqa: E402

__all__ = ["run", "build_prompt", "ROUTE", "ROUTER_MODEL"]

#: Route label persisted into ``ResultRow.route``.
ROUTE = "R1"

#: Pseudo-model name the router treats as "force cloud, no routing".
ROUTER_MODEL = "router/always-cloud"

#: Banner prefix the router prepends to the first content chunk when
#: ``ROUTER_BANNER=1``. We strip it from the saved output so the file
#: contains only the model's actual answer.
_BANNER_PREFIX = "[router] "


def _task_slug(task_id: str) -> str:
    """Turn ``"humaneval-plus/HumanEval_42"`` into ``"humaneval-plus__HumanEval_42"``
    so the filename is filesystem-safe on every OS."""
    return task_id.replace("/", "__").replace(" ", "_")


def _strip_banner(text: str) -> str:
    """Remove the ``[router] …`` banner line the proxy prepends to the
    first content chunk. The banner always ends with ``\\n\\n``.

    No-op if the banner is disabled (``ROUTER_BANNER=0``) or the
    response didn't start with it (e.g. some error envelope)."""
    if not text.startswith(_BANNER_PREFIX):
        return text
    # Banner is one line terminated by "\n\n"; conservatively take
    # everything after the first double-newline.
    idx = text.find("\n\n")
    if idx == -1:
        return text
    return text[idx + 2 :]


# --------------------------------------------------------------------------- #
# Per-benchmark prompt adapters
# --------------------------------------------------------------------------- #


def _prompt_for_humaneval_plus(task: Any) -> str:
    """HumanEval+ prompt is already self-contained (signature + docstring).

    We add a short instruction so the model returns a complete
    implementation rather than, say, just a snippet or commentary."""
    return (
        "Complete the following Python function. "
        "Return only the full function definition — no prose, no tests.\n\n"
        f"{task.prompt}"
    )


def _prompt_for_bigcodebench_hard(task: Any) -> str:
    """BigCodeBench ships an ``instruct_prompt`` field that's already
    formatted as a natural-language instruction. Use it verbatim."""
    return task.instruct_prompt


def _prompt_for_swebench(task: Any) -> str:
    """SWE-bench Verified is a repo-level task; the cloud-only route
    doesn't give the model file-system access. For the MVP we ask for a
    unified diff and let the scorer (T3.2) apply it via mini-swe-agent.

    The prompt shape is intentionally the same as what R3 will use so
    the comparison is apples-to-apples."""
    return (
        "You are fixing a GitHub issue.\n"
        f"Repo: {task.repo}\n"
        f"Base commit: {task.base_commit}\n\n"
        f"Issue:\n{task.problem_statement}\n\n"
        "Return ONLY a unified diff patch (starting with `diff --git`) "
        "that fixes the issue. No explanation, no code fences, just the "
        "patch body."
    )


def _prompt_for_custom_arch(task: Any) -> str:
    """Category-C tasks carry a ready-to-send ``prompt`` field plus an
    optional ``context`` block. Concatenate them with a separator."""
    prompt = task.prompt
    context = getattr(task, "context", "") or ""
    if context:
        return f"{prompt}\n\nContext:\n{context}"
    return prompt


def build_prompt(task: Any) -> str:
    """Dispatch to the right per-benchmark prompt builder.

    Duck-typed on the ``Task`` shape: HumanEval+ has ``prompt`` + ``tests``,
    BigCodeBench has ``instruct_prompt``, SWE-bench has
    ``problem_statement`` + ``base_commit``, custom-arch has ``prompt`` +
    ``rubric``.
    """
    if hasattr(task, "problem_statement") and hasattr(task, "base_commit"):
        return _prompt_for_swebench(task)
    if hasattr(task, "instruct_prompt"):
        return _prompt_for_bigcodebench_hard(task)
    if hasattr(task, "rubric"):
        return _prompt_for_custom_arch(task)
    if hasattr(task, "prompt"):
        return _prompt_for_humaneval_plus(task)
    raise TypeError(
        f"don't know how to build a prompt for task type {type(task).__name__!r}"
    )


# --------------------------------------------------------------------------- #
# Core runner
# --------------------------------------------------------------------------- #


def _header_int(headers: httpx.Headers, name: str, default: int = 0) -> int:
    """Pull an integer X-* header with a safe fallback."""
    raw = headers.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _tokens_from_response(
    headers: httpx.Headers, body: dict[str, Any]
) -> tuple[int, int, int, int]:
    """Return (prompt, completion, cached, reasoning).

    Prefer X-* headers (set by the router, cross-backend stable); fall
    back to ``usage`` on the response body."""
    usage = body.get("usage") or {}
    prompt = _header_int(headers, "X-Tokens-Prompt", int(usage.get("prompt_tokens") or 0))
    completion = _header_int(
        headers, "X-Tokens-Completion", int(usage.get("completion_tokens") or 0)
    )
    # ``cached`` and ``reasoning`` live under nested ``*_details`` dicts
    # in the OpenAI schema; headers are the easier source.
    cached_fallback = int(
        ((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    )
    reasoning_fallback = int(
        ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0
    )
    cached = _header_int(headers, "X-Tokens-Cached", cached_fallback)
    reasoning = _header_int(headers, "X-Tokens-Reasoning", reasoning_fallback)
    return prompt, completion, cached, reasoning


def _extract_content(body: dict[str, Any]) -> str:
    """Pull the assistant message text out of the OpenAI chat response."""
    choices = body.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    # Some backends return content as a list of parts (vision-style);
    # fold them to a single string.
    if isinstance(content, list):
        return "".join(
            (part.get("text") or "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return ""


def _empty_row(
    *,
    task: Any,
    hardware_profile_ref: str,
    output_ref: str,
    error: str,
    wall_ms: int,
    started_at: str,
    finished_at: str,
) -> ResultRow:
    """Construct an error row with everything zeroed out."""
    return ResultRow(
        task_id=task.id,
        category=getattr(task, "category", "?"),
        route=ROUTE,
        hardware_profile_ref=hardware_profile_ref,
        tokens=TokenUsage(),
        latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms] if wall_ms else []),
        quality=Quality(),  # all-None by design
        routing=Routing(
            total_calls=1, local_calls=0, cloud_calls=1, per_call_backends=[]
        ),
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
        error=error,
    )


def run(
    task: Any,
    proxy_url: str = "http://127.0.0.1:8787",
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    max_tokens: int = 8000,
    temperature: float = 0.3,
    timeout_s: int = 600,
) -> ResultRow:
    """Execute one task through the cloud-only route.

    Parameters
    ----------
    task
        A ``Task`` dataclass from any of the four benchmark adapters.
        Duck-typed — we only read ``id``, ``category`` and a
        benchmark-specific prompt field.
    proxy_url
        Base URL of ``router/server.mjs`` (no trailing ``/``).
    hardware_profile_ref
        Opaque identifier linking this row to the environment manifest
        recorded for this run (``env-manifest.json#hash``).
    output_dir
        Where to persist the raw model answer. Defaults to
        ``./results/r1/`` next to the repo root.
    max_tokens, temperature, timeout_s
        Forwarded to the upstream proxy request.

    Returns
    -------
    ResultRow
        Populated with ``route="R1"``, cloud_* tokens, wall-clock
        latency and a single ``per_call_backends`` entry holding the
        backend model id the proxy reported back via
        ``X-Router-Backend-Model-Echo``.
    """
    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r1"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    out_path = output_dir / f"{slug}_R1.txt"
    # ``output_ref`` is repo-relative when the file is under the repo
    # (keeps JSONL diff-able across machines); otherwise fall back to
    # the absolute path (e.g. when tests write into pytest's tmp_path).
    try:
        output_ref = str(out_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        output_ref = str(out_path.resolve())

    prompt = build_prompt(task)
    payload = {
        "model": ROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    url = proxy_url.rstrip("/") + "/v1/chat/completions"
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    try:
        resp = httpx.post(url, json=payload, timeout=timeout_s)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.RequestError) as exc:
        wall_ms = int((time.perf_counter() - t0) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()
        err_msg = f"proxy_unreachable: {type(exc).__name__}: {exc}"
        # Write a sidecar so manual debugging still has breadcrumbs.
        out_path.write_text(f"[R1 ERROR] {err_msg}\n", encoding="utf-8")
        print(f"[r1_cloud_only] WARN {task.id}: {err_msg}", file=sys.stderr)
        return _empty_row(
            task=task,
            hardware_profile_ref=hardware_profile_ref,
            output_ref=output_ref,
            error=err_msg,
            wall_ms=wall_ms,
            started_at=started_at,
            finished_at=finished_at,
        )

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    if resp.status_code >= 300:
        err_msg = f"proxy_status_{resp.status_code}: {resp.text[:300]}"
        out_path.write_text(f"[R1 ERROR] {err_msg}\n", encoding="utf-8")
        print(f"[r1_cloud_only] WARN {task.id}: {err_msg}", file=sys.stderr)
        return _empty_row(
            task=task,
            hardware_profile_ref=hardware_profile_ref,
            output_ref=output_ref,
            error=err_msg,
            wall_ms=wall_ms,
            started_at=started_at,
            finished_at=finished_at,
        )

    try:
        body = resp.json()
    except ValueError as exc:
        err_msg = f"proxy_bad_json: {exc}"
        out_path.write_text(f"[R1 ERROR] {err_msg}\n", encoding="utf-8")
        print(f"[r1_cloud_only] WARN {task.id}: {err_msg}", file=sys.stderr)
        return _empty_row(
            task=task,
            hardware_profile_ref=hardware_profile_ref,
            output_ref=output_ref,
            error=err_msg,
            wall_ms=wall_ms,
            started_at=started_at,
            finished_at=finished_at,
        )

    prompt_tok, completion_tok, cached_tok, reasoning_tok = _tokens_from_response(
        resp.headers, body
    )

    content = _extract_content(body)
    content_clean = _strip_banner(content)
    out_path.write_text(content_clean, encoding="utf-8")

    # Backend the cloud call actually landed on — preferring the echoed
    # model id from the upstream response (handles OpenAI's dated
    # variants like ``gpt-5.5-2026-04-23``).
    backend_echo = resp.headers.get("X-Router-Backend-Model-Echo") or resp.headers.get(
        "X-Router-Backend"
    ) or body.get("model") or ""

    row = ResultRow(
        task_id=task.id,
        category=getattr(task, "category", "?"),
        route=ROUTE,
        hardware_profile_ref=hardware_profile_ref,
        tokens=TokenUsage(
            prompt=prompt_tok,
            completion=completion_tok,
            cached=cached_tok,
            reasoning=reasoning_tok,
            local_prompt=0,
            local_completion=0,
            cloud_prompt=prompt_tok,
            cloud_completion=completion_tok,
        ),
        latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
        quality=Quality(),  # scorer fills this later
        routing=Routing(
            total_calls=1,
            local_calls=0,
            cloud_calls=1,
            per_call_backends=[backend_echo],
        ),
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
        error=None,
    )
    return row


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _load_task(source: str, task_id: str) -> Any:
    """Look up one task by id from the requested benchmark adapter."""
    if source == "humaneval_plus":
        from benchmark.humaneval_plus.adapter import load_tasks

        tasks = load_tasks()
    elif source == "swebench_verified":
        from benchmark.swebench_verified.adapter import load_tasks

        tasks = load_tasks()
    elif source == "bigcodebench_hard":
        from benchmark.bigcodebench_hard.adapter import load_tasks

        tasks = load_tasks()
    elif source == "custom_arch":
        from benchmark.custom_arch.adapter import load_tasks

        tasks = load_tasks()
    else:
        raise ValueError(f"unknown --task-source {source!r}")

    # Accept either the namespaced id ("humaneval-plus/HumanEval_42") or
    # the bare upstream id ("HumanEval_42"). The former wins.
    for t in tasks:
        if t.id == task_id:
            return t
    for t in tasks:
        if t.id.split("/")[-1] == task_id:
            return t
    raise KeyError(
        f"no task with id {task_id!r} in {source!r} "
        f"(available: {[t.id for t in tasks][:5]}…)"
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m runners.r1_cloud_only",
        description="R1 cloud-only single-shot runner (hybrid-coding-eval T2.1)",
    )
    ap.add_argument(
        "--task-source",
        required=True,
        choices=[
            "humaneval_plus",
            "swebench_verified",
            "bigcodebench_hard",
            "custom_arch",
        ],
    )
    ap.add_argument("--task-id", required=True)
    ap.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for the raw answer + results.jsonl",
    )
    ap.add_argument("--proxy-url", default="http://127.0.0.1:8787")
    ap.add_argument("--hardware-profile-ref", default="")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--timeout-s", type=int, default=600)
    args = ap.parse_args(argv)

    task = _load_task(args.task_source, args.task_id)
    row = run(
        task,
        proxy_url=args.proxy_url,
        hardware_profile_ref=args.hardware_profile_ref,
        output_dir=args.out,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        timeout_s=args.timeout_s,
    )

    results_path = Path(args.out) / "results.jsonl"
    append_row(results_path, row)

    # Print a one-line summary for humans + a JSON line for machines.
    summary = {
        "task_id": row.task_id,
        "route": row.route,
        "error": row.error,
        "tokens": {
            "cloud_prompt": row.tokens.cloud_prompt,
            "cloud_completion": row.tokens.cloud_completion,
            "cached": row.tokens.cached,
            "reasoning": row.tokens.reasoning,
        },
        "wall_ms": row.latency.wall_ms,
        "backend": row.routing.per_call_backends,
        "output_ref": row.output_ref,
        "results_jsonl": str(results_path),
    }
    print(json.dumps(summary, indent=2))
    return 0 if not row.error else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
