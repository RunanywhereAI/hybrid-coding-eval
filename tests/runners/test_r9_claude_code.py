"""Smoke tests for :mod:`hybrid_coding_eval.runners.r9_claude_code` (R9).

These tests verify that the module loads and exposes the expected
interface — no live ``claude`` CLI invocation is performed. A full
end-to-end run is exercised by the smoke config at
``configs/variants/_smoke-r9.yaml`` (added separately).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_claude_code_module_imports() -> None:
    """The R9 module loads cleanly and exposes ``run`` + ``ROUTE``."""
    from hybrid_coding_eval.runners import r9_claude_code

    assert r9_claude_code.ROUTE == "claude-code"
    assert callable(r9_claude_code.run)

    # run() must accept the same kw surface as the other runners so the
    # orchestrator in core.experiment._runner_for can call it uniformly.
    sig = inspect.signature(r9_claude_code.run)
    for kw in ("proxy_url", "hardware_profile_ref", "output_dir", "router_strategy"):
        assert kw in sig.parameters, f"run() missing kw-only arg {kw!r}"


def test_runner_dispatch_registers_claude_code() -> None:
    """The core experiment dispatch resolves 'claude-code' to our run()."""
    from hybrid_coding_eval.core.experiment import _runner_for
    from hybrid_coding_eval.runners import r9_claude_code

    assert _runner_for("claude-code") is r9_claude_code.run
