"""Functional test for d5-env-var-redactor.

Runs ``solution.py`` with ``input.json`` piped to stdin and asserts that
stdout exactly matches ``expected.txt``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_env_var_redactor_matches_expected() -> None:
    here = Path(__file__).resolve().parent
    input_json = (here / "input.json").read_bytes()
    expected = (here / "expected.txt").read_text(encoding="utf-8")
    solution = here / "solution.py"

    assert solution.is_file(), f"missing solution script: {solution}"

    proc = subprocess.run(
        [sys.executable, str(solution)],
        input=input_json,
        cwd=str(here),
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"script failed: {proc.stderr!r}"
    got = proc.stdout.decode("utf-8")
    assert got == expected, (
        f"stdout mismatch.\n--- expected ---\n{expected!r}\n"
        f"--- got ---\n{got!r}"
    )
