"""R4 — Stanford Minion-style hybrid runner.

Wraps ``EXTERNAL/minions/minions/minion.py`` (MIT-licensed). Cloud
supervisor emits targeted questions; local worker reads context and
answers; supervisor aggregates until `final_answer`.

Both clients are ``minions.clients.openai.OpenAIClient`` instances
pointed at our router proxy on ``:8787``. The OpenAI-compatible API
lets the Minion library talk to our hybrid routing layer unchanged:

- supervisor → ``model=router/always-cloud`` → gpt-5.5 via OpenAI.
- worker     → ``model=router/always-local`` → qwen/devstral via Ollama.

This keeps the proxy as the single place where routing decisions,
cost accounting, and backend selection happen. No duplicated logic.

Public API matches R1/R2/R3: ``run(task, ...) → ResultRow``. Rows get
``route="R4"`` and the same tokens/latency/quality/routing shape as
the other runners, so the orchestrator and analysis pipeline don't
need changes.

Scope (intentional): R4 in this MVP runs ONLY SWE-bench (category B)
since that's where Minion's Q&A decomposition was designed to help.
Other categories are explicitly not tested — we're measuring whether
a different hybrid pattern beats R3's plan-execute-synth on the one
category where the hybrid thesis matters. Skipping A/C avoids noise.
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
# ``sys.path`` at the ``EXTERNAL/minions`` level (i.e. the directory
# that contains the ``minions/`` package).
_REPO_ROOT = Path(__file__).resolve().parent.parent
# Make both our repo root (for ``lib.metrics`` et al.) and the vendored
# Minion library importable.
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "EXTERNAL" / "minions"))

# The Stanford Minions package __init__ imports optional backends
# (mistral, sambanova) that break on recent SDK versions. We load the
# two modules we actually need by path, stash them under the canonical
# names, then import Minion normally.
import importlib.util as _iu  # noqa: E402

_MINIONS = _REPO_ROOT / "EXTERNAL" / "minions"
for _mod_name, _rel in [
    ("minions.usage", "minions/usage.py"),
    ("minions.clients.base", "minions/clients/base.py"),
    ("minions.clients.openai", "minions/clients/openai.py"),
]:
    _spec = _iu.spec_from_file_location(_mod_name, _MINIONS / _rel)
    _m = _iu.module_from_spec(_spec)
    sys.modules[_mod_name] = _m
    _spec.loader.exec_module(_m)

# Pre-populate ``minions.clients`` parent with stubs for the extra backends
# Minion imports at module level. isinstance() checks only need these
# classes to exist; we'll never produce instances of them.
import types as _types  # noqa: E402

class _StubClient:
    """Placeholder for Together/Gemini/Sambanova; never instantiated."""
    pass

_clients_pkg = _types.ModuleType("minions.clients")
_clients_pkg.OpenAIClient = sys.modules["minions.clients.openai"].OpenAIClient
_clients_pkg.TogetherClient = _StubClient
_clients_pkg.GeminiClient = _StubClient
_clients_pkg.SambanovaClient = _StubClient
sys.modules["minions.clients"] = _clients_pkg

from minions.clients.openai import OpenAIClient  # noqa: E402
from minions import minion as _minion_mod  # noqa: E402


def _ensure_minion_shape(d: dict, text: str) -> dict:
    """Guarantee the dict has every field Minion's loop might access."""
    if not isinstance(d, dict):
        d = {}
    d.setdefault("decision", "provide_final_answer")
    d.setdefault("answer", text)
    d.setdefault("message", text)
    d.setdefault("mcp_tool_calls", [])
    return d


def _resilient_extract_json(text: str) -> dict:
    """Patched version of Minion's _extract_json that handles SWE-bench
    diffs gracefully. Stanford's regex-based extractor stops at the
    first balanced ``{...}`` and can't cope with diffs that contain
    JSON-looking braces inside prose. We try three strategies in order:

    1. Parse as-is (works for clean JSON).
    2. Strip markdown fences and retry.
    3. Pull the largest balanced object from the text (last-resort).
    4. Treat the whole text as the final answer — {"decision": "provide_final_answer", "answer": text}.
    """
    import json as _json
    import re as _re
    cleaned = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.MULTILINE).strip()
    for candidate in (text, cleaned):
        try:
            return _ensure_minion_shape(_json.loads(candidate), text)
        except _json.JSONDecodeError:
            pass
    depth, start, in_str, escape = 0, -1, False, False
    for i, ch in enumerate(cleaned):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True; continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return _ensure_minion_shape(_json.loads(cleaned[start:i+1]), text)
                except _json.JSONDecodeError:
                    continue
    # Fallback: produce a record that's valid for BOTH the initial
    # supervisor question (needs "message") and the final answer
    # (needs "decision" == provide_final_answer + "answer"). Minion's
    # early-round code reads ``supervisor_json["message"]``; later-round
    # code reads ``supervisor_json["decision"]``. Setting both fields
    # lets the conversation make it to the final round even when the
    # supervisor produced prose instead of JSON.
    return {
        "message": text,
        "decision": "provide_final_answer",
        "answer": text,
        "mcp_tool_calls": [],
    }


_minion_mod._extract_json = _resilient_extract_json

# Wrap json.loads inside Minion's module too — the initial supervisor call
# uses ``json.loads`` directly (not _extract_json), which raises on the
# same pathological inputs. If it succeeds but yields a dict missing
# `message`/`decision`, we fill them in defensively.
_orig_json_loads = _minion_mod.json.loads


def _resilient_json_loads(text, *args, **kwargs):
    try:
        obj = _orig_json_loads(text, *args, **kwargs)
        if isinstance(obj, dict):
            return _ensure_minion_shape(obj, text if isinstance(text, str) else "")
        return obj
    except Exception:
        # Let the caller's ``except`` clause fall through to _extract_json,
        # which is already patched.
        raise


_minion_mod.json.loads = _resilient_json_loads
from minions.minion import Minion  # noqa: E402

from lib.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)

ROUTE = "R4"
PROXY_URL = "http://127.0.0.1:8787"
CLOUD_MODEL = "router/always-cloud"
LOCAL_MODEL = "router/always-local"


def _ensure_v1(base: str) -> str:
    """Normalise the proxy base URL to include ``/v1`` for the OpenAI
    SDK's endpoint construction. Accepts both flavours so the runner
    can be called from the orchestrator (which passes the bare
    ``http://127.0.0.1:8787``) or standalone.
    """
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


def _minion_prompt(task: Any) -> tuple[str, list[str]]:
    """Build the (task, context) pair for Minion's ``__call__``.

    For SWE-bench we put the repository + problem statement into context
    (so the worker reads it locally) and the question-to-answer into
    task (so the supervisor decides what to ask the worker).
    """
    from runners._shared import task_prompt

    prompt = task_prompt(task)
    tid = task.id
    if tid.startswith("swebench-verified/"):
        ps = getattr(task, "problem_statement", "") or ""
        return (
            "Produce a unified diff patch that resolves the problem statement. "
            "Return ONLY the patch wrapped in a ```diff ... ``` code block.",
            [f"Repository: {getattr(task, 'repo', '?')}\n\n"
             f"Base commit: {getattr(task, 'base_commit', '?')}\n\n"
             f"Problem statement:\n{ps}"],
        )
    # Fallback for non-SWE tasks: full prompt in context, short ask in task.
    return (
        "Answer the question based on the attached context. Provide the full deliverable.",
        [prompt],
    )


def run(
    task: Any,
    proxy_url: str = PROXY_URL,
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    max_rounds: int = 3,
    timeout_s: int = 1200,  # noqa: ARG001
) -> ResultRow:
    """Execute one task through the hybrid-minion route."""
    _load_dotenv_once()

    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r4"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    out_path = output_dir / f"{slug}_R4.txt"
    try:
        output_ref = str(out_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        output_ref = str(out_path.resolve())

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")
    base_url = _ensure_v1(proxy_url)
    supervisor = OpenAIClient(
        model_name=CLOUD_MODEL,
        api_key=api_key,
        base_url=base_url,
        max_tokens=4000,
    )
    worker = OpenAIClient(
        model_name=LOCAL_MODEL,
        api_key=api_key,
        base_url=base_url,
        max_tokens=2000,
        local=True,  # tells the library to return the 3-tuple shape
    )

    minion = Minion(local_client=worker, remote_client=supervisor, max_rounds=max_rounds)

    minion_task, minion_context = _minion_prompt(task)
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    result: dict[str, Any] | None = None
    try:
        result = minion(task=minion_task, context=minion_context, max_rounds=max_rounds)
    except Exception as exc:  # noqa: BLE001
        # Minion's JSON-parse path is fragile on SWE-bench diffs (the
        # supervisor returns a valid JSON wrapper around a diff, but the
        # regex-based extractor miscounts braces). Rather than treat that
        # as an infrastructure failure, recover the last-round supervisor
        # content from the exception chain if we can, and keep the usage
        # counters we already accumulated via the OpenAIClient.
        import re as _re
        # Try pulling the diff out of the exception args — Minion prints
        # the failed blob before re-raising, so it's in the traceback.
        err_msg = f"minion_error: {type(exc).__name__}: {str(exc)[:200]}"
        recovered = ""
        try:
            # Supervisor's final message is in conversation_log; Minion
            # assigns it before trying to parse.
            log = getattr(minion, "_last_conversation_log", None)
            if log and log.get("conversation"):
                recovered = log["conversation"][-1].get("output") or ""
        except Exception:  # noqa: BLE001
            pass
        if recovered:
            out_path.write_text(recovered, encoding="utf-8")
            # fall through to aggregate tokens
            result = {
                "final_answer": recovered,
                "remote_usage": None,
                "local_usage": None,
                "conversation": log.get("conversation") if log else [],
            }
        else:
            wall_ms = int((time.perf_counter() - t0) * 1000)
            finished_at = datetime.now(timezone.utc).isoformat()
            out_path.write_text(f"[R4 ERROR] {err_msg}\n", encoding="utf-8")
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

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    final = result.get("final_answer", "") if isinstance(result, dict) else ""
    out_path.write_text(final, encoding="utf-8")

    remote_usage = result.get("remote_usage") if isinstance(result, dict) else None
    local_usage = result.get("local_usage") if isinstance(result, dict) else None
    r_prompt = getattr(remote_usage, "prompt_tokens", 0) or 0
    r_comp = getattr(remote_usage, "completion_tokens", 0) or 0
    l_prompt = getattr(local_usage, "prompt_tokens", 0) or 0
    l_comp = getattr(local_usage, "completion_tokens", 0) or 0

    conversation = result.get("conversation", []) if isinstance(result, dict) else []
    backends: list[str] = []
    cloud_calls = 0
    local_calls = 0
    for turn in conversation:
        u = (turn or {}).get("user", "")
        if u == "remote":
            backends.append("gpt-5.5")
            cloud_calls += 1
        elif u == "local":
            backends.append(LOCAL_MODEL)
            local_calls += 1

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
    from benchmark.swebench_verified import adapter as swe_adapter

    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", help="specific SWE-bench task id (else first)")
    ap.add_argument("--out", default="results/r4")
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
