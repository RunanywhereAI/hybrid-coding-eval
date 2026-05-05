"""Tests for :mod:`analysis.arqgc` — Bounded-ARQGC.

Key properties (per spec):

  * 3 rows per route → scalar ARQGC in [0, 1].
  * All-fail (composite=0) → ARQGC = 0.
  * All-pass (composite=1, equal cost) → ARQGC = 1.
  * Decision matrix artifact renders from synthetic inputs.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.metrics import Latency, Quality, ResultRow, Routing, TokenUsage  # noqa: E402

from analysis.arqgc import arqgc_for_rows, bounded_arqgc  # noqa: E402
from analysis.decision_matrix import build_decision_matrix  # noqa: E402


def _mk_row(
    *,
    task_id: str,
    category: str = "A",
    route: str = "R1",
    cloud_prompt: int = 0,
    cloud_completion: int = 0,
    local_prompt: int = 0,
    local_completion: int = 0,
    composite: float | None = 1.0,
    functional_pass: bool | None = True,
) -> ResultRow:
    return ResultRow(
        task_id=task_id,
        category=category,
        route=route,
        hardware_profile_ref="hw",
        tokens=TokenUsage(
            prompt=cloud_prompt + local_prompt,
            completion=cloud_completion + local_completion,
            cloud_prompt=cloud_prompt,
            cloud_completion=cloud_completion,
            local_prompt=local_prompt,
            local_completion=local_completion,
        ),
        latency=Latency(wall_ms=1000, per_call_ms=[1000]),
        quality=Quality(composite=composite, functional_pass=functional_pass),
        routing=Routing(total_calls=1, local_calls=0, cloud_calls=1, per_call_backends=["x"]),
        output_ref="",
    )


def test_arqgc_in_range_three_rows():
    rows = [
        _mk_row(task_id=f"t{i}", cloud_prompt=1000, cloud_completion=500, composite=0.6 + 0.1 * i)
        for i in range(3)
    ]
    score = arqgc_for_rows(rows, "openai-gpt5.5", cost_cap=0.1)
    assert 0.0 <= score <= 1.0


def test_arqgc_all_fail_is_zero():
    rows = [
        _mk_row(task_id=f"t{i}", cloud_prompt=1000, cloud_completion=500, composite=0.0, functional_pass=False)
        for i in range(3)
    ]
    score = arqgc_for_rows(rows, "openai-gpt5.5", cost_cap=0.5)
    assert score == 0.0


def test_arqgc_all_pass_equal_cost_is_one():
    """When every row has quality=1 and cumulative cost reaches cost_cap,
    the area under the step function is 1.0 × cap == cap, normalised to 1.0."""
    # Three rows with identical cost; set cap to exactly their sum.
    rows = [
        _mk_row(task_id=f"t{i}", cloud_prompt=1000, cloud_completion=500, composite=1.0)
        for i in range(3)
    ]
    # Each row costs 0.02 → total 0.06. With cap=0.06 the area = 0.06*1 / 0.06 = 1.
    score = arqgc_for_rows(rows, "openai-gpt5.5", cost_cap=0.06)
    assert math.isclose(score, 1.0, abs_tol=1e-9)


def test_arqgc_empty_rows_zero():
    assert arqgc_for_rows([], "openai-gpt5.5", cost_cap=0.1) == 0.0


def test_bounded_arqgc_per_route_and_per_category():
    """Small mixed fixture: two routes × two categories, each with 2 rows."""
    rows = []
    for cat in ("A", "B"):
        # R1 rows: cheap-ish cloud, high quality.
        for i in range(2):
            rows.append(
                _mk_row(
                    task_id=f"{cat}-r1-{i}",
                    category=cat,
                    route="R1",
                    cloud_prompt=1000,
                    cloud_completion=500,
                    composite=0.9,
                )
            )
        # R2 rows: free local, mid quality.
        for i in range(2):
            rows.append(
                _mk_row(
                    task_id=f"{cat}-r2-{i}",
                    category=cat,
                    route="R2",
                    local_prompt=1000,
                    local_completion=500,
                    composite=0.5,
                )
            )

    result = bounded_arqgc(rows, scenario="openai-gpt5.5")
    assert result["scenario"] == "openai-gpt5.5"
    assert "per_route" in result
    assert set(result["per_route"].keys()) == {"R1", "R2"}
    for score in result["per_route"].values():
        assert 0.0 <= score <= 1.0
    assert "per_category_route" in result
    # Every (cat, route) combo in the fixture appears.
    assert set(result["per_category_route"].keys()) == {
        "A/R1",
        "A/R2",
        "B/R1",
        "B/R2",
    }
    for score in result["per_category_route"].values():
        assert 0.0 <= score <= 1.0


def test_decision_matrix_renders_valid_markdown(tmp_path: Path):
    """End-to-end smoke test: aggregate + arqgc dicts in → decision_matrix.md out."""
    rows = [
        _mk_row(task_id="t1", category="A", route="R1", cloud_prompt=1000, cloud_completion=500, composite=0.9),
        _mk_row(task_id="t2", category="A", route="R2", local_prompt=1000, local_completion=500, composite=0.5),
        _mk_row(task_id="t3", category="B", route="R1", cloud_prompt=2000, cloud_completion=1000, composite=0.7),
        _mk_row(task_id="t4", category="B", route="R2", local_prompt=2000, local_completion=1000, composite=0.6),
    ]

    from analysis.aggregate import aggregate_results

    raw = tmp_path / "raw.jsonl"
    from lib.results import append_row
    for r in rows:
        append_row(raw, r)

    agg = aggregate_results(raw, tmp_path / "aggregate.json")
    arqgc = bounded_arqgc(rows, "openai-gpt5.5")
    (tmp_path / "arqgc.json").write_text(json.dumps(arqgc, indent=2))

    out = tmp_path / "decision_matrix.md"
    build_decision_matrix(agg, arqgc, out)
    md = out.read_text()
    assert "Decision matrix" in md
    assert "R1" in md and "R2" in md
    assert "ARQGC" in md or "arqgc" in md.lower()
    # At least one cost value formatted as USD.
    assert "$" in md
