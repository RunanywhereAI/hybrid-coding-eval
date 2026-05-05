"""Tests for runners/r3_hybrid_architect.py (T2.3).

Two tests:

  1. End-to-end on a small HumanEval+ task. Verifies that the JS architect
     subprocess runs, the parsed ResultRow has route='R3', per-call backend
     attribution is present, and token splits line up with call counts.
  2. Error handling: bad proxy URL should yield an error-flavoured ResultRow
     rather than a traceback.

Both tests are skipped cleanly when the router proxy is unreachable —
architect runs take several minutes and there's nothing useful to assert
without a live proxy. Timeouts are generous because architect mode on an
M4 Max typically takes 2–10 minutes per task.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from runners._shared import load_task_by_id, proxy_health
from runners.r3_hybrid_architect import run as r3_run

PROXY_URL = os.environ.get("HYBRID_PROXY_URL", "http://127.0.0.1:8787")

# Generous architect timeout — real runs can hit 5–10 min on small HumanEval
# tasks when the local model is cold or slow. CI environments that want a
# tighter budget can set HYBRID_ARCHITECT_TIMEOUT.
_ARCHITECT_TIMEOUT_S = int(os.environ.get("HYBRID_ARCHITECT_TIMEOUT", "600"))


pytestmark = [
    pytest.mark.skipif(
        shutil.which("node") is None,
        reason="node not on PATH — architect shim needs Node.js",
    ),
]


def _skip_if_proxy_down() -> None:
    if not proxy_health(PROXY_URL, timeout_s=2.0):
        pytest.skip(f"router proxy not reachable at {PROXY_URL}")


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_r3_end_to_end_on_humaneval_task(tmp_path: Path) -> None:
    """Run R3 against the shortest HumanEval+ task in the pinned sample.

    We pick HumanEval_99 (closest_integer) because its prompt is tiny,
    which minimises architect wall time while still exercising the full
    planner → executor[s] → (optional synth) pipeline.
    """
    _skip_if_proxy_down()

    task = load_task_by_id("humaneval_plus", "HumanEval_99")

    row = r3_run(
        task,
        proxy_url=PROXY_URL,
        hardware_profile_ref="test-profile",
        output_dir=tmp_path,
        max_steps=6,
        timeout_s=_ARCHITECT_TIMEOUT_S,
    )

    # Basic shape
    assert row.route == "R3"
    assert row.task_id == "humaneval-plus/HumanEval_99"
    assert row.category == "A"
    assert row.hardware_profile_ref == "test-profile"
    assert row.output_ref  # trace file path written

    # Routing: must have at least planner + 1 step. If plan has >1 step we
    # also get a synth call, so per_call_backends can be 2 or more. The
    # acceptance criterion says >2 typically; we weaken to >=2 to remain
    # robust against single-step plans the planner sometimes emits for
    # trivial tasks.
    assert row.routing.total_calls >= 2, (
        f"expected planner + >=1 step, got per_call_backends={row.routing.per_call_backends}"
    )
    assert len(row.routing.per_call_backends) == row.routing.total_calls
    assert row.routing.local_calls + row.routing.cloud_calls == row.routing.total_calls, (
        f"local+cloud must sum to total_calls: {row.routing}"
    )

    # First entry is always the planner; planner is always-cloud by default.
    assert row.routing.per_call_backends[0].startswith("planner/"), (
        f"first call should be planner, got {row.routing.per_call_backends[0]!r}"
    )

    # Tokens: planner is cloud, so cloud tokens must be > 0. Local tokens
    # MAY be 0 if the planner+synth-only path was taken (single-step plan,
    # and the one step got routed to cloud). Whichever side is populated
    # should agree with the aggregate totals.
    assert row.tokens.cloud_prompt > 0, (
        f"planner should produce cloud prompt tokens, got {row.tokens}"
    )
    assert (row.tokens.local_prompt + row.tokens.cloud_prompt) == row.tokens.prompt
    assert (
        row.tokens.local_completion + row.tokens.cloud_completion
    ) == row.tokens.completion

    # Latency
    assert row.latency.wall_ms > 0
    assert len(row.latency.per_call_ms) == row.routing.total_calls

    # Raw artifacts exist on disk
    trace_path = Path(row.output_ref)
    assert trace_path.exists(), f"trace file missing: {trace_path}"
    assert trace_path.stat().st_size > 0
    answer_path = trace_path.with_name(trace_path.name.replace(".arch.json", ".answer.txt"))
    assert answer_path.exists(), f"answer file missing: {answer_path}"


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


def test_r3_handles_bad_proxy_gracefully(tmp_path: Path) -> None:
    """Pointing R3 at a dead proxy URL must not raise; it must return a
    ResultRow with ``routing.per_call_backends=['error/...']`` and zero
    tokens. This is how the orchestrator detects failed runs.
    """
    _skip_if_proxy_down()  # we still need node + a real proxy to be DOWN somewhere
    task = load_task_by_id("humaneval_plus", "HumanEval_99")

    # Port 1 is privileged and will not be listening — connection refused
    # path. The architect subprocess will propagate the failure via a
    # non-zero exit + stderr, which r3_run captures into the error row.
    row = r3_run(
        task,
        proxy_url="http://127.0.0.1:1",
        hardware_profile_ref="",
        output_dir=tmp_path,
        max_steps=3,
        timeout_s=30,
    )

    assert row.route == "R3"
    assert row.routing.total_calls == 0
    assert row.routing.local_calls == 0
    assert row.routing.cloud_calls == 0
    assert len(row.routing.per_call_backends) == 1
    assert row.routing.per_call_backends[0].startswith("error/"), row.routing.per_call_backends
    # Tokens zeroed
    assert row.tokens.prompt == 0
    assert row.tokens.completion == 0
    assert row.tokens.local_prompt == 0
    assert row.tokens.cloud_prompt == 0
