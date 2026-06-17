"""Shared agent-runner attribution helpers.

Each agent runner generates a short ``bench_run_id`` per ``(task, route,
strategy)`` call, embeds it in the model field sent to the router proxy
(``router/<strategy>/run-<id>``), and the proxy echoes it into every
``router/logs/decisions.jsonl`` row. Attribution back into ``TokenUsage``
+ ``Routing`` filters on that id, eliminating any timestamp-window race
when two strategy=heuristic runs overlap.

Fallback: agents (e.g. opencode) that can't embed the ``bench_run_id``
in the model field — opencode rejects unknown model ids — fall back to
strategy + timestamp window matching. Used **only if no primary rows
are found**.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from hybrid_arena.core.metrics import Routing, TokenUsage
from hybrid_arena.core.paths import repo_root as _repo_root

__all__ = [
    "generate_run_id",
    "model_string",
    "attribute_from_decisions_log",
]

_REPO_ROOT: Path = _repo_root()
_DECISIONS_PATH: Path = _REPO_ROOT / "router" / "logs" / "decisions.jsonl"


def generate_run_id() -> str:
    """A 12-hex correlation id for one ``(task, route, strategy)`` call."""
    return uuid.uuid4().hex[:12]


def model_string(strategy: str, run_id: str | None = None, *, prefix: str = "router") -> str:
    """Build the model field the router proxy parses.

    Shapes::

        router/<strategy>                   # no run id (legacy / cross-tool)
        router/<strategy>/run-<run_id>      # primary path for v1.1+

    The ``prefix`` argument lets callers use ``openai/router`` (LiteLLM
    custom-provider style) when needed.
    """
    base = f"{prefix}/{strategy}"
    if run_id:
        return f"{base}/run-{run_id}"
    return base


def attribute_from_decisions_log(
    *,
    run_id: str,
    strategy: str,
    started_at: datetime,
    finished_at: datetime,
    decisions_path: Path | None = None,
) -> tuple[TokenUsage, Routing]:
    """Slice ``decisions.jsonl`` and aggregate ``TokenUsage`` + ``Routing``.

    Primary: rows where ``bench_run_id == run_id``.
    Fallback: rows where ``strategy`` matches AND ``ts`` is in
    ``[started_at, finished_at]`` — only consulted if zero primary rows
    are found. The fallback exists so logs predating the run-id field
    (or third-party clients that didn't add the suffix) still attribute.
    """
    path = decisions_path or _DECISIONS_PATH
    if not path.exists():
        return TokenUsage(), Routing(total_calls=0, local_calls=0, cloud_calls=0)

    primary_rows: list[dict] = []
    fallback_rows: list[dict] = []
    start_iso = started_at.isoformat()
    end_iso = finished_at.isoformat()

    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row_run_id = d.get("bench_run_id")
                if row_run_id == run_id:
                    primary_rows.append(d)
                    continue
                # Fallback candidate: same strategy + ts in window.
                if d.get("strategy") != strategy:
                    continue
                ts = d.get("ts") or ""
                if start_iso <= ts <= end_iso:
                    fallback_rows.append(d)
    except OSError:
        pass

    rows = primary_rows if primary_rows else fallback_rows
    return _aggregate_rows(rows)


def _aggregate_rows(rows: list[dict]) -> tuple[TokenUsage, Routing]:
    local_prompt = local_completion = cloud_prompt = cloud_completion = 0
    cached = reasoning = 0
    total_calls = local_calls = cloud_calls = 0
    backends: list[str] = []

    for d in rows:
        total_calls += 1
        choice = d.get("choice") or "?"
        backend = d.get("backend") or d.get("backendModel") or d.get("backend_model") or choice
        backends.append(f"call_{total_calls}/{choice}/{backend}")
        usage = d.get("usage") or {}
        p_in = int(usage.get("prompt_tokens") or 0)
        p_out = int(usage.get("completion_tokens") or 0)
        p_cached = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
        p_reasoning = int(((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)
        cached += p_cached
        reasoning += p_reasoning
        if choice == "cloud":
            cloud_prompt += p_in
            cloud_completion += p_out
            cloud_calls += 1
        else:
            local_prompt += p_in
            local_completion += p_out
            local_calls += 1

    tokens = TokenUsage(
        prompt=local_prompt + cloud_prompt,
        completion=local_completion + cloud_completion,
        cached=cached,
        reasoning=reasoning,
        local_prompt=local_prompt,
        local_completion=local_completion,
        cloud_prompt=cloud_prompt,
        cloud_completion=cloud_completion,
    )
    routing = Routing(
        total_calls=total_calls,
        local_calls=local_calls,
        cloud_calls=cloud_calls,
        per_call_backends=backends,
    )
    return tokens, routing
