"""Functional test for d5-todo-counter.

Runs ``solution.py`` from inside the ``tree/`` fixture directory and
checks that stdout exactly matches ``expected.txt`` (bytes-for-bytes).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_todo_counter_matches_expected() -> None:
    here = Path(__file__).resolve().parent
    tree = here / "tree"
    expected = (here / "expected.txt").read_text(encoding="utf-8")
    solution = here / "solution.py"

    assert tree.is_dir(), f"missing fixture tree: {tree}"
    assert solution.is_file(), f"missing solution script: {solution}"

    proc = subprocess.run(
        [sys.executable, str(solution)],
        cwd=str(tree),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"script failed: {proc.stderr}"
    assert proc.stdout == expected, (
        f"stdout mismatch.\n--- expected ---\n{expected!r}\n"
        f"--- got ---\n{proc.stdout!r}"
    )
