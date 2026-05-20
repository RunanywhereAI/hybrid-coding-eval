"""Unit tests for :mod:`hybrid_coding_eval.runners.r10_cline` (R10).

These tests verify the module shape and the "cline binary missing"
graceful-fallback path without spinning up the router proxy or
invoking any model. The runner mirrors R7 (aider) for fixture copy +
local pytest scoring so we lean on a synthetic Exercism-style fixture
to exercise the FileNotFoundError → ResultRow branch.
"""

from __future__ import annotations

import inspect
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
    from hybrid_coding_eval.runners import r10_cline

    assert r10_cline.ROUTE == "R10"
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
    from hybrid_coding_eval.core.experiment import _runner_for
    from hybrid_coding_eval.runners import r10_cline

    assert _runner_for("R10") is r10_cline.run
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
    from hybrid_coding_eval.runners import r10_cline

    # 1. Seed a minimal Exercism-style fixture so the copy step succeeds.
    fixture_dir = tmp_path / "fixture"
    _seed_fixture(fixture_dir)
    task = _FakeTask(fixture_dir=fixture_dir)

    # 2. Force the "not installed" branch deterministically. shutil.which
    # returns None on a clean system, and we also intercept subprocess.run
    # to raise FileNotFoundError if cline somehow IS installed on the host
    # running this test.
    monkeypatch.setattr(r10_cline.shutil, "which", lambda _name: None)

    # Also nuke any .venv/bin/cline that might exist (it doesn't today,
    # but be defensive against future bench-setup wiring).
    real_exists = Path.exists

    def _no_venv_cline(self: Path) -> bool:
        if self.name == "cline" and ".venv" in self.parts:
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", _no_venv_cline)

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
    assert row.route == "R10"
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


def test_cline_run_fixture_copy_failure_returns_error_row(tmp_path: Path) -> None:
    """When the task fixture is missing, run() returns a ``fixture_copy_failed``
    row rather than crashing. Mirrors R7/R8.
    """
    from hybrid_coding_eval.runners import r10_cline

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
    assert row.route == "R10"
    assert row.error is not None and row.error.startswith("fixture_copy_failed")
    assert row.tokens.prompt == 0
