"""Tests for :mod:`lib.results` — JSONL IO + aggregation.

Seven scenarios drawn straight from T0.2's acceptance criteria:

  1. Round-trip: dataclass → JSONL → dataclass preserves every field.
  2. Aggregate by a single key (``route``).
  3. Aggregate by two keys (``category`` × ``route``).
  4. Cost derivation exactness on pure-cloud, pure-local, and mixed rows.
  5. ``None`` in ``quality.composite`` aggregates to NaN.
  6. ``None`` in ``functional_pass`` is ignored in the pass-rate.
  7. Every line in the appended JSONL is valid JSON (atomic-write proof).
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

# Make ``lib`` importable regardless of pytest invocation style.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_arena.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_arena.core.results import aggregate_by, append_row, load_results  # noqa: E402

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _mk_row(
    *,
    task_id: str = "t0",
    category: str = "puzzles",
    route: str = "aider",
    prompt: int = 1000,
    completion: int = 500,
    cached: int = 0,
    reasoning: int = 0,
    local_prompt: int = 0,
    local_completion: int = 0,
    cloud_prompt: int = 0,
    cloud_completion: int = 0,
    wall_ms: int = 1000,
    per_call_ms: list[int] | None = None,
    total_calls: int = 1,
    local_calls: int = 0,
    cloud_calls: int = 1,
    per_call_backends: list[str] | None = None,
    functional_pass: bool | None = True,
    tests_passed: int | None = None,
    tests_total: int | None = None,
    judge_win_rate: float | None = None,
    composite: float | None = 0.85,
    output_ref: str = "results/x.txt",
    hardware_profile_ref: str = "hw-m4max",
    started_at: str | None = None,
    finished_at: str | None = None,
) -> ResultRow:
    """Compact factory so test bodies stay readable."""
    return ResultRow(
        task_id=task_id,
        category=category,
        route=route,
        hardware_profile_ref=hardware_profile_ref,
        tokens=TokenUsage(
            prompt=prompt,
            completion=completion,
            cached=cached,
            reasoning=reasoning,
            local_prompt=local_prompt,
            local_completion=local_completion,
            cloud_prompt=cloud_prompt,
            cloud_completion=cloud_completion,
        ),
        latency=Latency(wall_ms=wall_ms, per_call_ms=per_call_ms or [wall_ms]),
        quality=Quality(
            functional_pass=functional_pass,
            tests_passed=tests_passed,
            tests_total=tests_total,
            judge_win_rate=judge_win_rate,
            composite=composite,
        ),
        routing=Routing(
            total_calls=total_calls,
            local_calls=local_calls,
            cloud_calls=cloud_calls,
            per_call_backends=per_call_backends or (["cloud"] * cloud_calls + ["local"] * local_calls),
        ),
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
    )


# --------------------------------------------------------------------------- #
# 1. Round-trip
# --------------------------------------------------------------------------- #


def test_round_trip_preserves_all_fields(tmp_path: Path):
    """Write 5 rows (some with ``None`` fields), read back, deep-equal."""
    rng = random.Random(20260505)
    rows: list[ResultRow] = []
    for i in range(5):
        rows.append(
            _mk_row(
                task_id=f"task-{i}",
                category=rng.choice(["puzzles", "refactors", "real-prs"]),
                route=rng.choice(["aider", "opencode", "mini-swe-agent"]),
                prompt=rng.randint(100, 10_000),
                completion=rng.randint(50, 5_000),
                cached=rng.randint(0, 500),
                reasoning=rng.randint(0, 500),
                local_prompt=rng.randint(0, 2_000) if i % 2 else 0,
                cloud_prompt=rng.randint(0, 2_000),
                cloud_completion=rng.randint(0, 1_000),
                wall_ms=rng.randint(500, 30_000),
                total_calls=rng.randint(1, 5),
                local_calls=rng.randint(0, 3),
                cloud_calls=rng.randint(0, 3),
                # Mix of populated and None quality fields.
                functional_pass=rng.choice([True, False, None]),
                composite=None if i == 2 else rng.random(),
                tests_passed=None if i == 1 else rng.randint(0, 10),
                tests_total=None if i == 1 else 10,
                started_at=None if i == 3 else "2026-05-05T12:00:00Z",
            )
        )

    path = tmp_path / "raw.jsonl"
    for r in rows:
        append_row(path, r)

    loaded = load_results(path)
    assert len(loaded) == len(rows)
    for original, roundtrip in zip(rows, loaded):
        assert original == roundtrip, f"mismatch:\n  want: {original}\n  got:  {roundtrip}"


# --------------------------------------------------------------------------- #
# 2. Single-key aggregation
# --------------------------------------------------------------------------- #


def test_aggregate_by_single_key_counts_and_central_tendency():
    """10 rows split 6/4 across two agents; verify count/median/mean."""
    rows: list[ResultRow] = []
    # 6 aider rows with prompts 100..600, completions all 100.
    for i in range(6):
        rows.append(
            _mk_row(
                task_id=f"aider-{i}",
                route="aider",
                prompt=100 * (i + 1),  # 100, 200, ..., 600
                completion=100,
                cloud_prompt=100 * (i + 1),
                cloud_completion=100,
                wall_ms=1000 + 100 * i,
            )
        )
    # 4 cline rows with prompts 1000..4000, completions all 500.
    for i in range(4):
        rows.append(
            _mk_row(
                task_id=f"cline-{i}",
                route="cline",
                prompt=1000 * (i + 1),  # 1000, 2000, 3000, 4000
                completion=500,
                local_prompt=200,
                local_completion=50,
                cloud_prompt=800 + 1000 * i,
                cloud_completion=450,
                total_calls=3,
                local_calls=1,
                cloud_calls=2,
                wall_ms=5000 + 100 * i,
            )
        )

    df = aggregate_by(rows, keys=["route"])
    df = df.sort_values("route").reset_index(drop=True)

    assert list(df["route"]) == ["aider", "cline"]
    assert list(df["count"]) == [6, 4]

    # aider: prompts [100,200,300,400,500,600]; median = 350, mean = 350.
    aider = df[df["route"] == "aider"].iloc[0]
    assert int(aider["prompt_tokens_median"]) == 350
    assert int(aider["prompt_tokens_mean"]) == 350
    assert int(aider["completion_tokens_median"]) == 100
    assert int(aider["completion_tokens_mean"]) == 100
    # aider rows have no local split; _row_cost_usd treats tokens.prompt as cloud.
    assert int(aider["local_prompt_tokens_sum"]) == 0
    assert int(aider["cloud_prompt_tokens_sum"]) == 100 + 200 + 300 + 400 + 500 + 600

    # cline: prompts [1000,2000,3000,4000]; median = 2500, mean = 2500.
    cline = df[df["route"] == "cline"].iloc[0]
    assert int(cline["prompt_tokens_median"]) == 2500
    assert int(cline["prompt_tokens_mean"]) == 2500
    assert int(cline["completion_tokens_median"]) == 500
    assert int(cline["local_prompt_tokens_sum"]) == 200 * 4
    # cloud prompts: 800, 1800, 2800, 3800 → sum = 9200
    assert int(cline["cloud_prompt_tokens_sum"]) == 800 + 1800 + 2800 + 3800
    # total_calls is 3 across all 4 rows → median 3.
    assert int(cline["total_calls_median"]) == 3
    assert int(cline["local_calls_median"]) == 1
    assert int(cline["cloud_calls_median"]) == 2


# --------------------------------------------------------------------------- #
# 3. Two-key aggregation
# --------------------------------------------------------------------------- #


def test_aggregate_by_two_keys_shape_and_values():
    """20 rows across 3 categories × 3 routes. Verify groupby shape & counts."""
    rng = random.Random(42)
    cats = ["puzzles", "refactors", "real-prs"]
    routes = ["aider", "opencode", "mini-swe-agent"]
    rows: list[ResultRow] = []
    counts: dict[tuple[str, str], int] = {}

    for i in range(20):
        c = cats[i % 3]
        r = routes[(i // 3) % 3]
        counts[(c, r)] = counts.get((c, r), 0) + 1
        rows.append(
            _mk_row(
                task_id=f"t-{i}",
                category=c,
                route=r,
                prompt=rng.randint(500, 2000),
                completion=rng.randint(100, 1000),
                cloud_prompt=rng.randint(500, 2000),
                cloud_completion=rng.randint(100, 1000),
                wall_ms=rng.randint(1000, 5000),
                composite=rng.random(),
            )
        )

    df = aggregate_by(rows, keys=["category", "route"])

    # Shape: one row per (category, route) combination that actually
    # appears in the data.
    assert set(zip(df["category"], df["route"])) == set(counts.keys())
    assert len(df) == len(counts)
    # Sum of counts matches total.
    assert int(df["count"].sum()) == 20
    # Per-cell counts match.
    for _, agg_row in df.iterrows():
        key = (agg_row["category"], agg_row["route"])
        assert int(agg_row["count"]) == counts[key], f"wrong count for {key}"


# --------------------------------------------------------------------------- #
# 4. Cost derivation
# --------------------------------------------------------------------------- #


def test_cost_derivation_pure_cloud_and_pure_local_and_mixed():
    """openai-gpt5.5 rate: input 5/M, output 30/M.

    * pure-cloud 1000/500 → $0.020 exactly
    * pure-local 1000/500 → $0.000 exactly
    * mixed → sum of the two components
    """
    # --- Pure cloud.
    cloud_only = _mk_row(
        task_id="cloud",
        route="aider",
        prompt=1000,
        completion=500,
        cloud_prompt=1000,
        cloud_completion=500,
    )
    df = aggregate_by([cloud_only], keys=["route"])
    mean_col = "cost_usd_openai-gpt5.5_mean"
    assert math.isclose(float(df[mean_col].iloc[0]), 0.020, abs_tol=1e-12)

    # --- Pure local.
    local_only = _mk_row(
        task_id="local",
        route="opencode",
        prompt=1000,
        completion=500,
        local_prompt=1000,
        local_completion=500,
    )
    df = aggregate_by([local_only], keys=["route"])
    assert math.isclose(float(df[mean_col].iloc[0]), 0.0, abs_tol=1e-12)

    # --- Mixed. 500 local + 500 cloud prompt, 200 local + 300 cloud completion.
    # cloud cost = 500*5/1e6 + 300*30/1e6 = 0.0025 + 0.009 = 0.0115
    mixed = _mk_row(
        task_id="mix",
        route="cline",
        prompt=1000,
        completion=500,
        local_prompt=500,
        local_completion=200,
        cloud_prompt=500,
        cloud_completion=300,
    )
    df = aggregate_by([mixed], keys=["route"])
    assert math.isclose(float(df[mean_col].iloc[0]), 0.0115, abs_tol=1e-12)

    # --- Fallback: no split set, prompt/completion only → treated as cloud.
    fallback = _mk_row(
        task_id="fallback",
        route="aider",
        prompt=1000,
        completion=500,
        cloud_prompt=0,
        cloud_completion=0,
        local_prompt=0,
        local_completion=0,
    )
    df = aggregate_by([fallback], keys=["route"])
    assert math.isclose(float(df[mean_col].iloc[0]), 0.020, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# 5. None quality composite
# --------------------------------------------------------------------------- #


def test_none_quality_composite_aggregates_to_nan():
    """A group whose composite is None everywhere → mean/median NaN.

    A mixed group with some None and some floats → mean excludes Nones.
    """
    rows = [
        _mk_row(task_id="a1", route="aider", composite=None),
        _mk_row(task_id="a2", route="aider", composite=None),
        _mk_row(task_id="b1", route="opencode", composite=0.9),
        _mk_row(task_id="b2", route="opencode", composite=None),
        _mk_row(task_id="b3", route="opencode", composite=0.7),
    ]
    df = aggregate_by(rows, keys=["route"]).sort_values("route").reset_index(drop=True)

    aider = df[df["route"] == "aider"].iloc[0]
    assert math.isnan(float(aider["quality_composite_mean"]))
    assert math.isnan(float(aider["quality_composite_median"]))

    opencode = df[df["route"] == "opencode"].iloc[0]
    # Pandas .mean() / .median() skip NaN by default, so mean = 0.8, median = 0.8.
    assert math.isclose(float(opencode["quality_composite_mean"]), 0.8, abs_tol=1e-12)
    assert math.isclose(float(opencode["quality_composite_median"]), 0.8, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# 6. None functional_pass ignored in pass-rate
# --------------------------------------------------------------------------- #


def test_functional_pass_rate_ignores_none():
    """Pass rate is computed over non-None rows only."""
    rows = [
        _mk_row(task_id="p1", route="aider", functional_pass=True),
        _mk_row(task_id="p2", route="aider", functional_pass=False),
        _mk_row(task_id="p3", route="aider", functional_pass=None),  # ignored
        _mk_row(task_id="p4", route="aider", functional_pass=True),
        # All-None group → NaN.
        _mk_row(task_id="q1", route="opencode", functional_pass=None),
        _mk_row(task_id="q2", route="opencode", functional_pass=None),
    ]
    df = aggregate_by(rows, keys=["route"]).sort_values("route").reset_index(drop=True)

    aider = df[df["route"] == "aider"].iloc[0]
    # 2 of 3 non-None are True → 2/3.
    assert math.isclose(float(aider["functional_pass_rate"]), 2.0 / 3.0, abs_tol=1e-12)

    opencode = df[df["route"] == "opencode"].iloc[0]
    assert math.isnan(float(opencode["functional_pass_rate"]))


# --------------------------------------------------------------------------- #
# 7. Atomic append — every line is valid JSON
# --------------------------------------------------------------------------- #


def test_append_writes_complete_valid_json_lines(tmp_path: Path):
    """Writing N rows one at a time → N lines, each valid JSON.

    This is a weaker property than true crash safety (which we can't
    unit-test without process control) but it's the observable one:
    if the implementation ever buffered a partial line, you'd see a
    truncated JSON object here.
    """
    path = tmp_path / "raw.jsonl"
    rows = [_mk_row(task_id=f"task-{i}", prompt=1000 + i) for i in range(25)]
    for r in rows:
        append_row(path, r)

    content = path.read_text(encoding="utf-8")
    # File ends with a newline — no partial last line.
    assert content.endswith("\n"), "atomic append must terminate every record with \\n"

    lines = content.splitlines()
    assert len(lines) == len(rows)
    for i, line in enumerate(lines):
        assert line, f"line {i} is empty"
        # Must parse cleanly — proves no half-line was persisted.
        parsed = json.loads(line)
        assert parsed["task_id"] == f"task-{i}"

    # And a full load_results round-trip should also succeed.
    loaded = load_results(path)
    assert len(loaded) == len(rows)


# --------------------------------------------------------------------------- #
# Bonus: load_results skips bad lines instead of raising.
# --------------------------------------------------------------------------- #


def test_load_results_skips_malformed_lines(tmp_path: Path, caplog):
    """A hand-crafted file with a mix of good / empty / bad lines."""
    path = tmp_path / "raw.jsonl"
    good = _mk_row(task_id="good")
    append_row(path, good)
    # Append some garbage + an empty line + another good row.
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n")  # empty line
        fh.write("{not json at all\n")
        fh.write("\n")
    append_row(path, _mk_row(task_id="good2"))

    with caplog.at_level("WARNING"):
        loaded = load_results(path)

    assert [r.task_id for r in loaded] == ["good", "good2"]
