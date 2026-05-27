"""Smoke tests for :mod:`hybrid_coding_eval.agents.mini_swe` (R6).

These tests verify that the module loads cleanly and exposes the
expected interface — no live ``mini-extra`` CLI invocation is
performed. A full end-to-end run requires the SWE-bench Docker harness
and the router proxy on :8787, which are too heavyweight for unit
tests; that path is covered by the canonical sweep itself.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Skip the entire module if mini-swe-agent isn't installed. CI typically
# omits it because it's not in the base `pip install -e ".[dev]"`; the
# `agents` optional-deps install (`pip install -e ".[agents]"`) adds it,
# and `./bench setup` installs it on first run.
pytest.importorskip("minisweagent")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_mini_swe_agent_module_imports() -> None:
    """The R6 module loads cleanly and exposes ``run`` + ``ROUTE``."""
    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent

    assert r6_mini_swe_agent.ROUTE == "mini-swe-agent"
    assert callable(r6_mini_swe_agent.run)

    # run() must accept the same kw surface as the other runners so the
    # orchestrator in core.experiment._runner_for can call it uniformly.
    sig = inspect.signature(r6_mini_swe_agent.run)
    for kw in (
        "proxy_url",
        "hardware_profile_ref",
        "output_dir",
        "router_strategy",
        "timeout_s",
    ):
        assert kw in sig.parameters, f"run() missing kw-only arg {kw!r}"


def test_runner_dispatch_registers_r6() -> None:
    """The core experiment dispatch resolves 'R6' to our run()."""
    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent
    from hybrid_coding_eval.core.experiment import _runner_for

    assert _runner_for("mini-swe-agent") is r6_mini_swe_agent.run


def test_default_swebench_yaml_resolves() -> None:
    """The runner's lookup of the package's default ``swebench.yaml``
    points at a real file inside the installed ``mini-swe-agent``.

    If this fails, ``mini-swe-agent`` is either not installed or its
    package layout changed — the runner would fail on the first
    ``-c <default>`` flag of every invocation.
    """
    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent

    p = r6_mini_swe_agent._default_swebench_yaml()
    assert p.exists(), f"package swebench.yaml not found at {p}"
    assert p.name == "swebench.yaml"


def test_strategy_yaml_is_well_formed() -> None:
    """The per-strategy YAML we layer ON TOP of the package default has
    the keys the LiteLLM-based mini-swe-agent reads:

      - ``model.model_name`` (includes the ``/run-<id>`` correlation tag)
      - ``model.model_kwargs.api_base`` (points at our proxy)
      - ``model.model_kwargs.custom_llm_provider: openai`` (so LiteLLM
        does NOT try to resolve the model id against its registry)
    """
    import yaml

    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent

    txt = r6_mini_swe_agent._strategy_yaml(
        api_base="http://127.0.0.1:8787/v1",
        strategy="heuristic",
        bench_run_id="abc123def456",
    )
    obj = yaml.safe_load(txt)
    assert "model" in obj
    mdl = obj["model"]
    assert mdl["model_name"].startswith("openai/router/heuristic/run-")
    assert mdl["model_name"].endswith("run-abc123def456")
    assert mdl["model_kwargs"]["api_base"] == "http://127.0.0.1:8787/v1"
    assert mdl["model_kwargs"]["custom_llm_provider"] == "openai"


def test_extract_diff_from_trajectory_empty_when_missing(tmp_path: Path) -> None:
    """The trajectory parser returns "" when the trajectory file is
    absent (the agent never produced one — e.g., it crashed before
    writing any output)."""
    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent

    missing = tmp_path / "nope.json"
    assert r6_mini_swe_agent._extract_diff_from_trajectory(missing) == ""


def test_extract_diff_from_trajectory_v2_submission(tmp_path: Path) -> None:
    """Trajectory parser reads ``info.submission`` (mini-swe-agent v2 schema)."""
    import json

    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent

    traj = tmp_path / "trajectory.json"
    traj.write_text(
        json.dumps(
            {
                "info": {"submission": "diff --git a/foo b/foo\n--- a/foo\n+++ b/foo\n"},
                "messages": [],
            }
        ),
        encoding="utf-8",
    )
    out = r6_mini_swe_agent._extract_diff_from_trajectory(traj)
    assert out.startswith("diff --git a/foo b/foo")


def test_run_missing_mini_extra_returns_error_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``mini-extra`` is not on PATH, ``run()`` does NOT raise.

    Instead it returns a :class:`ResultRow` with
    ``error="mini_swe_agent_not_installed"`` so the orchestrator can
    log the row and move on. This mirrors the graceful-fallback
    pattern in R10 (cline).
    """
    from hybrid_coding_eval.agents import mini_swe as r6_mini_swe_agent

    class _FakeTask:
        id = "swebench-verified/django__django-11163"
        instance_id = "django__django-11163"
        category = "B"

    real_run = subprocess.run

    def _maybe_raise(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        argv0 = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
        if isinstance(argv0, str) and argv0.endswith("mini-extra"):
            raise FileNotFoundError(2, "No such file or directory: 'mini-extra'")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(r6_mini_swe_agent.subprocess, "run", _maybe_raise)
    # Force the .venv/bin/mini-extra fallback to also be invisible so we
    # hit the FileNotFoundError branch deterministically.
    monkeypatch.setattr(r6_mini_swe_agent.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        r6_mini_swe_agent,
        "_REPO_ROOT",
        tmp_path,  # no .venv/bin/mini-extra under tmp_path
    )

    row = r6_mini_swe_agent.run(
        _FakeTask(),
        output_dir=tmp_path / "out",
        router_strategy="heuristic",
        timeout_s=30,
    )
    assert row.route == "mini-swe-agent"
    assert row.task_id == "swebench-verified/django__django-11163"
    assert row.error == "mini_swe_agent_not_installed"
    assert row.tokens.prompt == 0
    assert row.tokens.completion == 0
    assert row.router_strategy == "heuristic"
