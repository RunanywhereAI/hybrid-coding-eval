"""Unit tests for :mod:`hybrid_coding_eval.agents.cline` (R10).

These tests verify the module shape and the "cline binary missing"
graceful-fallback path without spinning up the router proxy or
invoking any model. The runner mirrors R7 (aider) for fixture copy +
local pytest scoring so we lean on a synthetic Exercism-style fixture
to exercise the FileNotFoundError → ResultRow branch.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_cline_module_imports() -> None:
    """R10 module is importable and exposes the run() and ROUTE symbols."""
    from hybrid_coding_eval.agents import cline as r10_cline

    assert r10_cline.ROUTE == "cline"
    assert callable(r10_cline.run)

    sig = inspect.signature(r10_cline.run)
    for kw in (
        "proxy_url",
        "hardware_profile_ref",
        "output_dir",
        "router_strategy",
        "timeout_s",
    ):
        assert kw in sig.parameters, f"run() missing kw-only arg {kw!r}"


def test_runner_dispatch_registers_r10() -> None:
    """The core experiment dispatch should resolve 'R10' (and 'cline') to
    our run().
    """
    from hybrid_coding_eval.agents import cline as r10_cline
    from hybrid_coding_eval.core.experiment import _runner_for

    assert _runner_for("cline") is r10_cline.run
    # Phase-2-friendly alias.
    assert _runner_for("cline") is r10_cline.run


class _FakeTask:
    """Minimal duck-typed Exercism-style task for the runner."""

    def __init__(self, fixture_dir: Path) -> None:
        self.id = "exercism-python/leap"
        self.category = "X"
        self.prompt = "Implement is_leap_year so the tests pass."
        self.fixture_dir = fixture_dir


def _seed_fixture(fixture_dir: Path) -> None:
    """Plant the smallest possible Exercism-style fixture under ``fixture_dir``.

    One stub + one test file; the runner's copy + pytest steps don't
    care about the actual content beyond the file-name conventions
    (``leap.py`` + ``leap_test.py``).
    """
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "leap.py").write_text(
        "def is_leap_year(year):\n    return False\n",
        encoding="utf-8",
    )
    (fixture_dir / "leap_test.py").write_text(
        "from leap import is_leap_year\n\n"
        "def test_leap_year():\n"
        "    assert is_leap_year(2000) is True\n",
        encoding="utf-8",
    )


def test_cline_run_no_cline_installed_returns_error_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the cline binary isn't on PATH, run() must NOT raise.

    The runner should catch FileNotFoundError from subprocess.run and
    return a ResultRow with ``error="cline_not_installed"``.
    """
    from hybrid_coding_eval.agents import cline as r10_cline

    # 1. Seed a minimal Exercism-style fixture so the copy step succeeds.
    fixture_dir = tmp_path / "fixture"
    _seed_fixture(fixture_dir)
    task = _FakeTask(fixture_dir=fixture_dir)

    # 2. Force the "not installed" branch deterministically. shutil.which
    # returns None on a clean system, and we also intercept subprocess.run
    # to raise FileNotFoundError if cline somehow IS installed on the host
    # running this test (the runner falls back to /opt/homebrew/bin/cline
    # when which() returns None — that fallback string also ends in
    # "cline" so the argv0 check below still catches it).
    monkeypatch.setattr(r10_cline.shutil, "which", lambda _name: None)

    real_run = subprocess.run

    def _maybe_raise(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        # The cline subprocess call is identifiable by argv[0]; everything
        # else (e.g. the host pytest scoring subprocess) should pass through.
        argv0 = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
        if isinstance(argv0, str) and argv0.endswith("cline"):
            raise FileNotFoundError(2, "No such file or directory: 'cline'")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(r10_cline.subprocess, "run", _maybe_raise)

    # 3. Invoke the runner. Output dir under tmp_path to avoid littering
    # the repo's results/ tree.
    output_dir = tmp_path / "out"
    row = r10_cline.run(
        task,
        proxy_url="http://127.0.0.1:8787",
        hardware_profile_ref="test-hw",
        output_dir=output_dir,
        router_strategy="heuristic",
        timeout_s=30,
    )

    # 4. Verify the graceful-fallback shape.
    assert row.route == "cline"
    assert row.task_id == task.id
    assert row.error == "cline_not_installed"
    # Zero-work side effects: no tokens consumed, no calls made.
    assert row.tokens.prompt == 0
    assert row.tokens.completion == 0
    assert row.routing.total_calls == 0
    # Quality should be empty (functional_pass=None) — we didn't actually
    # run pytest because the agent never ran.
    assert row.quality.functional_pass is None
    assert row.router_strategy == "heuristic"
    # output_ref should still point at the answer.py snapshot path so
    # the orchestrator's per-row append logic doesn't choke.
    assert row.output_ref


def test_cline_argv_matches_real_cli_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the cline subprocess argv matches the real cline 3.0.9 CLI.

    Locks in the verified invocation:
        cline -P ollama -m router/<strategy>/run-<bench_run_id>
              -c <scratch> --auto-approve true --json -t <timeout_s>
              "<prompt>"

    Previously this runner emitted fictional flags (``run`` subcommand,
    ``--task``, ``--provider openai-compatible``, ``--base-url``,
    ``--non-interactive``, ``--yes``, ``--file``) — none of which exist
    in cline 3.0.9. This test exists to catch a regression.
    """
    from hybrid_coding_eval.agents import cline as r10_cline

    fixture_dir = tmp_path / "fixture"
    _seed_fixture(fixture_dir)
    task = _FakeTask(fixture_dir=fixture_dir)

    # Pretend cline is installed at a predictable path so argv[0] is stable.
    fake_cline = "/usr/local/bin/cline"
    _orig_which = r10_cline.shutil.which
    monkeypatch.setattr(
        r10_cline.shutil, "which",
        lambda name: fake_cline if name == "cline" else _orig_which(name),
    )

    captured: dict[str, Any] = {}
    real_run = subprocess.run

    class _FakeCompleted:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def _intercept(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        argv0 = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
        if isinstance(argv0, str) and argv0 == fake_cline:
            captured["cmd"] = list(cmd)
            captured["cwd"] = kwargs.get("cwd")
            captured["env"] = kwargs.get("env")
            return _FakeCompleted()
        # Let host pytest scoring run normally.
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(r10_cline.subprocess, "run", _intercept)

    r10_cline.run(
        task,
        proxy_url="http://127.0.0.1:8787",
        hardware_profile_ref="test-hw",
        output_dir=tmp_path / "out",
        router_strategy="heuristic",
        timeout_s=42,
    )

    cmd = captured.get("cmd")
    assert cmd is not None, "cline subprocess was never invoked"

    # argv[0] is the cline binary.
    assert cmd[0] == fake_cline

    # Spot-check each required flag pair appears in order.
    assert cmd[1:3] == ["-P", "ollama"], f"provider flag wrong: {cmd[1:3]}"

    # -m <model> with the router/strategy/run-<id> shape.
    assert cmd[3] == "-m"
    model_id = cmd[4]
    assert model_id.startswith("router/heuristic/run-"), model_id
    # bench_run_id is 12 hex chars per generate_run_id().
    run_suffix = model_id.rsplit("run-", 1)[-1]
    assert len(run_suffix) == 12 and all(c in "0123456789abcdef" for c in run_suffix)

    # -c <scratch>, --auto-approve true, --json, -t <timeout>.
    assert cmd[5] == "-c"
    assert Path(cmd[6]).name == "scratch"
    assert cmd[7:9] == ["--auto-approve", "true"]
    assert cmd[9] == "--json"
    assert cmd[10:12] == ["-t", "42"]

    # The prompt is the last positional arg and references the stub file.
    prompt = cmd[12]
    assert "leap.py" in prompt
    assert "leap_test.py" in prompt
    # Make sure no fictional flags slipped back in.
    forbidden = {
        "run",
        "--task",
        "--provider",
        "openai-compatible",
        "--base-url",
        "--non-interactive",
        "--yes",
        "--file",
        "--openai-api-base",
        "--openai-api-key",
    }
    assert not (forbidden & set(cmd)), f"forbidden flags present: {forbidden & set(cmd)}"

    # cwd must be the scratch dir so cline edits the right files.
    assert captured["cwd"] and Path(captured["cwd"]).name == "scratch"

    # env should NOT override the OpenAI/Cline secret vars — base URL is
    # configured via providers.json and the leaked-secret risk isn't
    # worth the no-op.
    env = captured["env"] or {}
    # If the caller's env happens to have these, we should pass them
    # through unchanged — we just don't *set* synthetic values.
    assert env.get("OPENAI_API_KEY") == os.environ.get("OPENAI_API_KEY")
    assert env.get("CLINE_API_KEY") == os.environ.get("CLINE_API_KEY")


def test_cline_run_fixture_copy_failure_returns_error_row(tmp_path: Path) -> None:
    """When the task fixture is missing, run() returns a ``fixture_copy_failed``
    row rather than crashing. Mirrors R7/R8.
    """
    from hybrid_coding_eval.agents import cline as r10_cline

    class _BadTask:
        id = "exercism-python/does-not-exist"
        category = "X"
        prompt = "noop"
        fixture_dir = tmp_path / "does_not_exist"  # never created

    row = r10_cline.run(
        _BadTask(),
        output_dir=tmp_path / "out",
        router_strategy="heuristic",
    )
    assert row.route == "cline"
    assert row.error is not None and row.error.startswith("fixture_copy_failed")
    assert row.tokens.prompt == 0
