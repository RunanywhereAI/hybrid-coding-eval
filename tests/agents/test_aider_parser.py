"""Regression tests for ``_parse_pytest_summary`` in the aider runner.

The original implementation used a single regex that assumed pytest
emits ``"X passed, Y failed"`` in that order. Pytest actually re-orders
the tokens depending on outcome: when failures exist, the summary line
is ``"Y failed, X passed in Zs"`` (failed first). The original parser
saw the inverted order and recorded ``passed=0, total=Y_failed`` — for
example, a row with "2 failed, 21 passed in 0.05s" came back as 0/2
instead of 21/23. v1.5 replaces the regex with three independent
matches so token order doesn't matter.
"""

from __future__ import annotations

import pytest

from hybrid_arena.agents.aider import _parse_pytest_summary


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("======== 23 passed in 0.05s ========", (23, 23)),
        ("======== 2 failed, 21 passed in 0.05s ========", (21, 23)),
        ("======== 21 passed, 2 failed in 0.05s ========", (21, 23)),
        ("======== 5 passed, 1 skipped in 0.02s ========", (5, 5)),
        ("======== 3 failed, 2 errors in 0.10s ========", (0, 5)),
        ("======== 1 error in 0.01s ========", (0, 1)),
        ("======== 16 passed, 2 failed, 1 error in 0.30s ========", (16, 19)),
        ("", (0, 0)),
        ("collected 0 items", (0, 0)),
    ],
)
def test_parser_token_order_invariance(line: str, expected: tuple[int, int]) -> None:
    assert _parse_pytest_summary(line) == expected


def test_parser_walks_to_last_summary_line() -> None:
    log = (
        "test_cache.py::test_thing_1 PASSED\n"
        "test_cache.py::test_thing_2 PASSED\n"
        "test_cache.py::test_thing_3 FAILED\n"
        "\n"
        "======== 1 failed, 2 passed in 0.04s ========\n"
    )
    assert _parse_pytest_summary(log) == (2, 3)


def test_parser_ignores_intermediate_passed_mentions() -> None:
    log = (
        "test_x.py::test_a PASSED\n"
        "test_x.py::test_b PASSED\n"
        "======== 2 passed in 0.01s ========\n"
    )
    assert _parse_pytest_summary(log) == (2, 2)
