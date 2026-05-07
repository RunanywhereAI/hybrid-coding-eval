"""Tests for runners/r2_local_only.py (T2.2).

Three tests:

1. End-to-end: one HumanEval+ task → route='R2', local_* > 0, cloud_* == 0,
   quality fields all None, output file saved.
2. Cost-is-zero: :func:`lib.pricing.compute_cost` applied to the row's
   per_call_backends[0] (an Ollama-style colon-suffixed model id) yields
   ``usd == 0``.
3. Error handling: a bad proxy URL produces a graceful ``ResultRow`` with
   ``error`` populated — no exception escapes the runner.

Tests 1 and 2 skip cleanly when the router proxy at ``http://127.0.0.1:8787``
isn't reachable. Test 3 runs unconditionally; it deliberately targets a
non-existent port.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hybrid_coding_eval.benchmarks.humaneval_plus.adapter import load_tasks
from hybrid_coding_eval.core.pricing import compute_cost
from hybrid_coding_eval.runners import r2_local_only

PROXY_URL = "http://127.0.0.1:8787"


def _proxy_up(url: str = PROXY_URL, timeout_s: float = 2.0) -> bool:
    """Cheap liveness probe for the router. Any failure → False."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=timeout_s) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


requires_proxy = pytest.mark.skipif(
    not _proxy_up(), reason=f"router proxy at {PROXY_URL} not reachable"
)


# --------------------------------------------------------------------------- #
# Test 1 — end-to-end
# --------------------------------------------------------------------------- #


@requires_proxy
def test_end_to_end_humaneval(tmp_path: Path) -> None:
    """Run one HumanEval+ task through the local-only route and check the
    resulting ResultRow shape + output artefact."""
    tasks = load_tasks()
    assert tasks, "humaneval_plus adapter returned no tasks"
    task = tasks[0]

    row = r2_local_only.run(
        task,
        proxy_url=PROXY_URL,
        output_dir=tmp_path,
        # Keep this small — tests need to finish fast even on mid-tier hardware.
        max_tokens=512,
        temperature=0.0,
        timeout_s=240,
    )

    # If the local backend was down we'll get a non-None error; don't let
    # that hide everything — report it explicitly.
    assert row.error is None, f"unexpected runner error: {row.error}"

    assert row.route == "R2"
    assert row.task_id == task.id
    assert row.category == task.category

    # Tokens: local side populated, cloud side zero.
    assert row.tokens.local_prompt > 0, "expected local_prompt > 0"
    assert row.tokens.local_completion > 0, "expected local_completion > 0"
    assert row.tokens.cloud_prompt == 0
    assert row.tokens.cloud_completion == 0

    # Quality: runner does not score; all fields must be None.
    assert row.quality.functional_pass is None
    assert row.quality.tests_passed is None
    assert row.quality.tests_total is None
    assert row.quality.judge_win_rate is None
    assert row.quality.composite is None

    # Routing: single local call.
    assert row.routing.total_calls == 1
    assert row.routing.local_calls == 1
    assert row.routing.cloud_calls == 0
    assert len(row.routing.per_call_backends) == 1
    assert row.routing.per_call_backends[0], "backend id must be non-empty"

    # Output artefact saved to the expected path.
    slug = task.id.replace("/", "__")
    out_file = tmp_path / f"{slug}_R2.txt"
    assert out_file.exists(), f"expected output file at {out_file}"
    assert out_file.stat().st_size > 0, "output file should not be empty"


# --------------------------------------------------------------------------- #
# Test 2 — cost for a local row is $0
# --------------------------------------------------------------------------- #


@requires_proxy
def test_cost_is_zero_for_local_row(tmp_path: Path) -> None:
    """Whether we price by the echoed backend id (colon-convention → local
    bucket in ``lib.pricing``) or by the sentinel ``__local__`` key, the
    computed USD for an R2 row must be exactly 0."""
    tasks = load_tasks()
    task = tasks[0]
    row = r2_local_only.run(
        task,
        proxy_url=PROXY_URL,
        output_dir=tmp_path,
        max_tokens=256,
        temperature=0.0,
        timeout_s=240,
    )
    assert row.error is None, f"unexpected runner error: {row.error}"
    backend = row.routing.per_call_backends[0]
    assert backend, "backend id missing from routing.per_call_backends"

    usage = {
        "prompt_tokens": row.tokens.local_prompt,
        "completion_tokens": row.tokens.local_completion,
        "prompt_tokens_details": {"cached_tokens": row.tokens.cached},
        "completion_tokens_details": {"reasoning_tokens": row.tokens.reasoning},
    }

    # Price by the echoed backend id. Ollama model ids use the
    # colon-convention (``qwen3.6:27b-coding-mxfp8``), which
    # ``normalise_model_id`` maps to the ``__local__`` bucket.
    cost_via_backend = compute_cost(backend, usage)
    assert cost_via_backend["usd"] == 0, (
        f"expected 0 USD via backend={backend!r}, got {cost_via_backend}"
    )

    # Belt-and-braces: also price by the explicit ``__local__`` sentinel.
    cost_via_sentinel = compute_cost("__local__", usage)
    assert cost_via_sentinel["usd"] == 0


# --------------------------------------------------------------------------- #
# Test 3 — graceful error on bad proxy URL
# --------------------------------------------------------------------------- #


def test_bad_proxy_url_is_graceful(tmp_path: Path) -> None:
    """Point the runner at a port that's definitely closed. We expect a
    ResultRow with ``error`` populated — not an exception escaping."""
    tasks = load_tasks()
    task = tasks[0]

    row = r2_local_only.run(
        task,
        proxy_url="http://127.0.0.1:1",  # reserved port, always refuses.
        output_dir=tmp_path,
        max_tokens=256,
        temperature=0.0,
        timeout_s=5,
    )

    assert row.route == "R2"
    assert row.task_id == task.id
    assert row.error is not None
    assert "proxy_unreachable" in row.error or "proxy_status_" in row.error

    # Tokens must all be zero on an error row.
    assert row.tokens.prompt == 0
    assert row.tokens.completion == 0
    assert row.tokens.local_prompt == 0
    assert row.tokens.local_completion == 0
    assert row.tokens.cloud_prompt == 0
    assert row.tokens.cloud_completion == 0

    # Routing still reflects the intended shape (single local call attempted).
    assert row.routing.total_calls == 1
    assert row.routing.local_calls == 1
    assert row.routing.cloud_calls == 0

    # Sidecar file with the error exists.
    slug = task.id.replace("/", "__")
    out_file = tmp_path / f"{slug}_R2.txt"
    assert out_file.exists()
    assert "[R2 ERROR]" in out_file.read_text(encoding="utf-8")
