"""Functional test for d5-log-errors-today.

Runs ``solution.sh`` against the fixture's ``app-2026-05-06.log`` (today's
log) and checks stdout matches ``expected.txt``. A separate older log
sits in the same directory to ensure the script only touches the path
it was given.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_log_errors_today_matches_expected() -> None:
    here = Path(__file__).resolve().parent
    today_log = here / "app-2026-05-06.log"
    expected = (here / "expected.txt").read_text(encoding="utf-8")
    solution = here / "solution.sh"

    assert today_log.is_file(), f"missing log fixture: {today_log}"
    assert solution.is_file(), f"missing solution script: {solution}"

    proc = subprocess.run(
        ["bash", str(solution), str(today_log)],
        cwd=str(here),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"script failed: {proc.stderr}"
    assert proc.stdout == expected, (
        f"stdout mismatch.\n--- expected ---\n{expected!r}\n"
        f"--- got ---\n{proc.stdout!r}"
    )
