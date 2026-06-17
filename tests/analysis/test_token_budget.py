"""Tests for :mod:`hybrid_arena.analysis.token_budget` (P0.1)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_arena.analysis.token_budget import (  # noqa: E402
    HEADLINE_SCENARIOS,
    compute_token_budget,
    render_csv,
    render_markdown,
)
from hybrid_arena.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)


def _mk_row(
    *,
    task_id: str,
    route: str,
    variant: str = "test",
    category: str = "puzzles",
    local_prompt: int = 0,
    local_completion: int = 0,
    cloud_prompt: int = 0,
    cloud_completion: int = 0,
    functional_pass: bool | None = True,
    composite: float | None = 1.0,
) -> ResultRow:
    return ResultRow(
        task_id=task_id,
        category=category,
        route=route,
        hardware_profile_ref="test|hw",
        tokens=TokenUsage(
            prompt=cloud_prompt + local_prompt,
            completion=cloud_completion + local_completion,
            local_prompt=local_prompt,
            local_completion=local_completion,
            cloud_prompt=cloud_prompt,
            cloud_completion=cloud_completion,
        ),
        latency=Latency(wall_ms=1000),
        quality=Quality(functional_pass=functional_pass, composite=composite),
        routing=Routing(total_calls=1, local_calls=0, cloud_calls=1),
        output_ref="/dev/null",
        variant=variant,
    )


def _fixture() -> list[ResultRow]:
    """Synthesize a 2-route × 3-task fixture.

    Route ``aider`` (cloud-only here): 3 tasks, nonzero cloud tokens,
    zero local.
    Route ``opencode`` (local-only here): 3 tasks, nonzero local
    tokens, zero cloud.
    """
    rows: list[ResultRow] = []
    for i, task in enumerate(("t1", "t2", "t3")):
        rows.append(
            _mk_row(
                task_id=task,
                route="aider",
                cloud_prompt=1000 * (i + 1),
                cloud_completion=500 * (i + 1),
            )
        )
        rows.append(
            _mk_row(
                task_id=task,
                route="opencode",
                local_prompt=800 * (i + 1),
                local_completion=400 * (i + 1),
                # exercise the None path for composite on one row
                composite=None if i == 2 else 1.0,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_cloud_fraction_in_unit_interval() -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    assert (df["cloud_fraction"] >= 0.0).all()
    assert (df["cloud_fraction"] <= 1.0).all()


def test_local_only_rows_have_zero_cost_under_every_scenario() -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    local_only = df[df["route"] == "opencode"]
    assert not local_only.empty
    for s in HEADLINE_SCENARIOS:
        col = f"cost_{s}_usd"
        assert col in df.columns, f"missing column {col}"
        # local-only rows have zero cloud tokens → cost must be 0 under
        # every scenario (local tokens are priced at __local__ = $0).
        assert (local_only[col].abs() < 1e-12).all(), (
            f"opencode rows should have zero cost under {s}, got "
            f"{local_only[col].tolist()}"
        )


def test_dataframe_length_equals_input_length() -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    assert len(df) == len(rows)


def test_cloud_only_rows_have_cloud_fraction_one() -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    cloud_only = df[df["route"] == "aider"]
    assert (cloud_only["cloud_fraction"] == 1.0).all()


def test_cloud_only_rows_have_nonzero_cost() -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    cloud_only = df[df["route"] == "aider"]
    # openai-gpt5.5 has nonzero rates in pricing_tables.json, so any
    # nonzero cloud tokens must produce a strictly positive cost.
    col = "cost_openai-gpt5.5_usd"
    assert (cloud_only[col] > 0.0).all()


def test_render_markdown_contains_required_strings(tmp_path: Path) -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    out = tmp_path / "TOKEN_BUDGET.md"
    render_markdown(df, HEADLINE_SCENARIOS, out, source="test.jsonl")
    text = out.read_text(encoding="utf-8")

    # The acceptance criteria demand this exact string appear.
    assert "cost is derived from tokens at read time" in text
    # The phrase "cloud_fraction" should appear (it's the central column).
    assert "cloud_fraction" in text
    # All 6 scenario names must show up somewhere in the markdown.
    for s in HEADLINE_SCENARIOS:
        assert s in text, f"scenario {s!r} missing from markdown"


def test_render_csv_roundtrip(tmp_path: Path) -> None:
    rows = _fixture()
    df = compute_token_budget(rows, HEADLINE_SCENARIOS)
    out = tmp_path / "token_budget.csv"
    render_csv(df, out)
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    # Header + one row per input row.
    assert len(lines) == len(rows) + 1
    header = lines[0].split(",")
    assert "task_id" in header
    assert "cloud_fraction" in header
    for s in HEADLINE_SCENARIOS:
        assert f"cost_{s}_usd" in header


def test_headline_scenarios_has_six() -> None:
    # Enforce the "6 headline scenarios" contract from the P0.1 spec.
    assert len(HEADLINE_SCENARIOS) == 6
    assert "anthropic-claude-haiku-4.5" in HEADLINE_SCENARIOS
