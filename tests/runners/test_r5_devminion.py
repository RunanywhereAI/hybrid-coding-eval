"""Unit tests for :mod:`hybrid_coding_eval.runners.r5_devminion` (R5).

These tests verify the import-time side effects (monkey-patches, stubbed
clients, vendored-library path tricks) and the plain-function helpers
without spinning up the router proxy or calling any model. A full
end-to-end run is exercised by the smoke config at
``configs/variants/_smoke-r5.yaml``.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_module_imports_and_exposes_run_and_route() -> None:
    """R5 module is importable and exposes the run() and ROUTE symbols."""
    from hybrid_coding_eval.runners import r5_devminion

    assert r5_devminion.ROUTE == "R5"
    assert callable(r5_devminion.run)

    # run() must accept the same keyword surface as the other runners so
    # the orchestrator in core.experiment._runner_for can call it uniformly.
    sig = inspect.signature(r5_devminion.run)
    for kw in ("proxy_url", "hardware_profile_ref", "output_dir"):
        assert kw in sig.parameters, f"run() missing kw-only arg {kw!r}"


def test_devminion_extract_json_is_patched() -> None:
    """Both vendored Minion modules should share the resilient extractor.

    R5 reuses R4's monkey-patch by importing r4_minion at module-load
    time. Once both are in ``sys.modules`` the ``_extract_json`` names
    inside ``minions.minion`` AND ``minions.minion_code`` must both point
    at the resilient parser from r4.
    """
    # Trigger the import chain.
    from hybrid_coding_eval.runners import r4_minion, r5_devminion  # noqa: F401
    from minions import minion as _minion
    from minions import minion_code as _minion_code

    resilient = r4_minion._resilient_extract_json
    assert _minion._extract_json is resilient
    assert _minion_code._extract_json is resilient

    # The json proxy lets Minion-internal ``json.loads`` go through the
    # resilient path without mutating the real ``json`` module.
    assert _minion.json is _minion_code.json


def test_json_proxy_leaves_real_json_unmodified() -> None:
    """The ``_JsonProxy`` installed on minion modules must not mutate the
    global :mod:`json` module. Regression test for the subtle bug R4
    called out in its own source comments.
    """
    from hybrid_coding_eval.runners import r4_minion, r5_devminion  # noqa: F401
    import json as real_json

    # Plain json.loads should not inject Minion's default keys.
    parsed = real_json.loads('{"a": 1}')
    assert set(parsed) == {"a"}, (
        f"real json.loads was monkeypatched with Minion shape: {parsed!r}"
    )


def test_aggregate_calls_counts_every_round() -> None:
    """DevMinion's per-step attempt structure should produce correct totals.

    1 cloud (runbook) + N * (1 local + 1 cloud) per step + 1 cloud (final).
    """
    from hybrid_coding_eval.runners.r5_devminion import _aggregate_calls, LOCAL_MODEL

    fake = {
        "session_log": {
            "runbook": {"steps": []},
            "steps_completed": [
                {
                    "attempts": [
                        {"local_response": "impl1", "review_decision": "request_edits"},
                        {"local_response": "impl2", "review_decision": "merge_changes"},
                    ],
                },
                {
                    "attempts": [
                        {"local_response": "impl3", "review_decision": "merge_changes"},
                    ],
                },
            ],
            "final_assessment": {"project_status": "ok"},
        },
    }
    cloud, local, backends = _aggregate_calls(fake)
    # runbook=1, step1=(2*2=4), step2=(1*2=2), final=1 => cloud=1+2+1+1=5, local=2+1=3
    assert cloud == 5
    assert local == 3
    assert cloud + local == len(backends)
    # per_call_backends alternates sensibly within steps.
    assert backends[0] == "gpt-5.5"  # runbook
    assert LOCAL_MODEL in backends
    assert backends[-1] == "gpt-5.5"  # final integration review


def test_aggregate_calls_handles_empty_session() -> None:
    """If runbook generation fails everything should be zeros (no crash)."""
    from hybrid_coding_eval.runners.r5_devminion import _aggregate_calls

    for empty in ({}, {"session_log": {}}, {"session_log": {"runbook": None}}):
        cloud, local, backends = _aggregate_calls(empty)
        assert cloud == 0
        assert local == 0
        assert backends == []


def test_devminion_inputs_for_swebench_task() -> None:
    """SWE-bench tasks should receive a task+requirements pair (not context)."""
    from hybrid_coding_eval.runners.r5_devminion import _devminion_inputs

    class _FakeTask:
        id = "swebench-verified/foo__bar-123"
        category = "B"
        problem_statement = "Something is broken."
        repo = "foo/bar"
        base_commit = "abcdef1"
        hints_text = ""
        prompt = ""

    task_desc, requirements = _devminion_inputs(_FakeTask())
    assert isinstance(task_desc, str) and task_desc
    assert isinstance(requirements, str) and requirements
    assert "diff" in task_desc.lower()
    assert "foo/bar" in requirements
    assert "abcdef1" in requirements
    assert "Something is broken." in requirements


def test_runner_dispatch_registers_r5() -> None:
    """The core experiment dispatch should resolve 'R5' to our run()."""
    from hybrid_coding_eval.core.experiment import ROUTES, _runner_for
    from hybrid_coding_eval.runners import r5_devminion

    assert "R5" in ROUTES
    assert _runner_for("R5") is r5_devminion.run


def test_r4_import_does_not_break() -> None:
    """R5 piggy-backs on R4's bootstrap; R4 must keep working standalone."""
    from hybrid_coding_eval.runners import r4_minion, r5_devminion  # noqa: F401

    assert r4_minion.ROUTE == "R4"
    assert callable(r4_minion.run)


@pytest.mark.parametrize("route", ["R1", "R2", "R3", "R4", "R5"])
def test_bench_config_schema_accepts_r5(route: str) -> None:
    """Config schema's Route Literal must include every live runner id."""
    from hybrid_coding_eval.core.config.schema import BenchConfig
    from pydantic import ValidationError

    payload = {
        "variant_tag": "test",
        "out_dir": "results/runs/test",
        "models": {"cloud": "gpt-5.5", "local": "devstral:24b"},
        "benchmark": {"categories": ["B"], "routes": [route]},
    }
    try:
        cfg = BenchConfig.model_validate(payload)
    except ValidationError as exc:  # pragma: no cover - reproduction aid
        pytest.fail(f"schema rejected valid route {route!r}: {exc}")
    assert cfg.benchmark.routes == [route]
