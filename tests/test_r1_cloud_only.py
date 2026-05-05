"""Tests for :mod:`runners.r1_cloud_only` (T2.1).

Three scenarios:

  1. End-to-end happy path against a live proxy — one HumanEval+ task.
  2. Error handling — dead proxy URL must return a row with ``error`` set
     and tokens zeroed, never raise.
  3. Cost derivation — tokens from a successful run price > $0 through
     :func:`lib.pricing.compute_cost`.

The happy-path and cost tests are skipped when the router proxy on
127.0.0.1:8787 isn't reachable. The error-handling test always runs
(it *wants* a dead endpoint).
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmark.humaneval_plus.adapter import load_tasks  # noqa: E402
from lib.pricing import compute_cost  # noqa: E402
from runners.r1_cloud_only import ROUTE, ROUTER_MODEL, build_prompt, run  # noqa: E402


PROXY_URL = "http://127.0.0.1:8787"


def _proxy_reachable(url: str = PROXY_URL, timeout_s: float = 2.0) -> bool:
    """True iff ``GET {url}/health`` responds 2xx within the timeout."""
    try:
        resp = httpx.get(url.rstrip("/") + "/health", timeout=timeout_s)
    except httpx.HTTPError:
        return False
    return resp.status_code < 300


requires_proxy = pytest.mark.skipif(
    not _proxy_reachable(),
    reason=f"router proxy at {PROXY_URL} not reachable — skipping live tests",
)


@pytest.fixture(scope="module")
def humaneval_task():
    """First HumanEval+ task from the pinned jsonl (no network)."""
    tasks = load_tasks()
    assert tasks, "humaneval_plus tasks.jsonl is empty — run the adapter first"
    return tasks[0]


# --------------------------------------------------------------------------- #
# 1. Happy-path end-to-end
# --------------------------------------------------------------------------- #


@requires_proxy
def test_run_happy_path_humaneval(tmp_path, humaneval_task):
    row = run(
        humaneval_task,
        proxy_url=PROXY_URL,
        hardware_profile_ref="test-hw",
        output_dir=tmp_path,
        # Keep max_tokens small — we only care that it succeeds, not that it
        # produces a correct solution (scorer is a different task).
        max_tokens=1000,
        timeout_s=120,
    )

    assert row.error is None, f"runner reported error: {row.error}"
    assert row.route == ROUTE == "R1"
    assert row.task_id == humaneval_task.id
    assert row.category == humaneval_task.category

    # Tokens — headers always populate at least prompt+completion.
    assert row.tokens.cloud_prompt > 0, "cloud_prompt must be populated"
    assert row.tokens.cloud_completion > 0, "cloud_completion must be populated"
    # R1 spends zero local tokens by definition.
    assert row.tokens.local_prompt == 0
    assert row.tokens.local_completion == 0

    # Latency
    assert row.latency.wall_ms > 0
    assert row.latency.per_call_ms == [row.latency.wall_ms]

    # Routing bookkeeping.
    assert row.routing.total_calls == 1
    assert row.routing.local_calls == 0
    assert row.routing.cloud_calls == 1
    assert row.routing.per_call_backends and row.routing.per_call_backends[0]

    # Output file must exist and have non-empty content.
    out_file = Path(row.output_ref)
    if not out_file.is_absolute():
        out_file = _REPO_ROOT / out_file
    assert out_file.exists(), f"raw answer not saved to {out_file}"
    text = out_file.read_text(encoding="utf-8")
    assert text.strip(), "saved answer was empty"
    # Banner must have been stripped.
    assert not text.startswith("[router] ")


# --------------------------------------------------------------------------- #
# 2. Error handling — dead port
# --------------------------------------------------------------------------- #


def test_run_dead_proxy_returns_error_row(tmp_path, humaneval_task):
    # Port 1 is reserved; nothing ever binds to it. A connect attempt
    # fails immediately on every OS we care about.
    dead_url = "http://127.0.0.1:1"
    row = run(
        humaneval_task,
        proxy_url=dead_url,
        output_dir=tmp_path,
        timeout_s=3,
    )
    assert row.error is not None, "expected error field populated on proxy failure"
    assert row.route == ROUTE == "R1"
    assert row.tokens.cloud_prompt == 0
    assert row.tokens.cloud_completion == 0
    assert row.tokens.prompt == 0
    assert row.quality.functional_pass is None
    assert row.quality.composite is None
    # Sidecar file should still be written with an error marker.
    out_file = Path(row.output_ref)
    if not out_file.is_absolute():
        out_file = _REPO_ROOT / out_file
    assert out_file.exists()
    assert "[R1 ERROR]" in out_file.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 3. Cost derivable from tokens + backend echo
# --------------------------------------------------------------------------- #


@requires_proxy
def test_cost_derivable_from_row(tmp_path, humaneval_task):
    row = run(
        humaneval_task,
        proxy_url=PROXY_URL,
        output_dir=tmp_path,
        max_tokens=800,
        timeout_s=120,
    )
    assert row.error is None

    backend = row.routing.per_call_backends[0]
    cost = compute_cost(
        backend,
        {
            "prompt_tokens": row.tokens.cloud_prompt,
            "completion_tokens": row.tokens.cloud_completion,
            "prompt_tokens_details": {"cached_tokens": row.tokens.cached},
        },
    )
    assert cost["usd"] > 0, (
        f"expected positive cost, got {cost['usd']} (backend={backend!r}, "
        f"missing={cost['missing']})"
    )


# --------------------------------------------------------------------------- #
# Lightweight unit tests (no proxy needed)
# --------------------------------------------------------------------------- #


def test_build_prompt_humaneval(humaneval_task):
    prompt = build_prompt(humaneval_task)
    assert humaneval_task.prompt in prompt
    assert "Complete" in prompt  # instruction header is present


def test_router_model_constant():
    # Sanity: the pseudo-model name must match what the router expects
    # so the cloud-only strategy actually fires.
    assert ROUTER_MODEL == "router/always-cloud"
