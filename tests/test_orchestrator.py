"""Tests for the orchestrator (``hybrid_coding_eval.cli.run`` + ``core.experiment``)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_coding_eval.core.experiment import (  # noqa: E402
    TaskPlan,
    build_task_plan,
    pair_already_done,
)
from hybrid_coding_eval.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_coding_eval.core.results import append_row  # noqa: E402

RUN_ARGS = [sys.executable, "-m", "hybrid_coding_eval.cli.run"]


def _make_row(task_id: str, route: str) -> ResultRow:
    return ResultRow(
        task_id=task_id,
        category="A",
        route=route,
        hardware_profile_ref="test-hw",
        tokens=TokenUsage(prompt=10, completion=20, cloud_prompt=10, cloud_completion=20),
        latency=Latency(wall_ms=100, per_call_ms=[100]),
        quality=Quality(functional_pass=True, tests_passed=1, tests_total=1, composite=1.0),
        routing=Routing(total_calls=1, local_calls=0, cloud_calls=1, per_call_backends=["gpt-5.5"]),
        output_ref="outputs/fake.txt",
    )


# --------------------------------------------------------------------------- #
# Unit tests for the helpers
# --------------------------------------------------------------------------- #


def test_pair_already_done_detects_prior_rows(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    assert not pair_already_done(raw, "foo/bar", "R1")

    append_row(raw, _make_row("foo/bar", "R1"))
    assert pair_already_done(raw, "foo/bar", "R1")
    # Different route → not done yet.
    assert not pair_already_done(raw, "foo/bar", "R2")
    # Different task → not done yet.
    assert not pair_already_done(raw, "other/task", "R1")


def test_build_task_plan_smoke_shape() -> None:
    """Smoke build: 1 task per category × 3 routes = 3 × 3 = 9 items for A+B+C."""
    plan = build_task_plan(
        categories=["A", "B", "C"],
        routes=["R1", "R2", "R3"],
        smoke=True,
        tasks_cap=None,
    )
    assert len(plan) == 9
    # Each category has exactly 3 items (one per route).
    by_cat: dict[str, int] = {}
    for item in plan:
        assert isinstance(item, TaskPlan)
        by_cat[item.category] = by_cat.get(item.category, 0) + 1
    assert by_cat == {"A": 3, "B": 3, "C": 3}
    # Routes present in the expected deterministic order per task.
    routes_seen = [item.route for item in plan if item.category == "A"]
    assert routes_seen == ["R1", "R2", "R3"]


# --------------------------------------------------------------------------- #
# CLI-level tests
# --------------------------------------------------------------------------- #


def test_dry_run_prints_plan_and_exits_zero(tmp_path: Path) -> None:
    out = tmp_path / "dryrun"
    proc = subprocess.run(
        [
            *RUN_ARGS,
            "--smoke",
            "--categories",
            "A",
            "--routes",
            "R1",
            "--out",
            str(out),
            "--dry-run",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Would write to" in proc.stdout
    assert "Planned pairs: 1" in proc.stdout
    # Dry-run must not create the output dir.
    assert not out.exists(), "dry-run should not touch disk"


def test_resume_skip_is_a_noop_when_all_pairs_done(tmp_path: Path) -> None:
    """Seed raw.jsonl with a row for the one smoke pair; run with --resume.

    Expect the orchestrator to detect the pair is already done and add no new rows.
    This exercises the resume-safety code path without hitting the proxy.
    """
    out = tmp_path / "resume"
    out.mkdir(parents=True)
    raw = out / "raw.jsonl"

    # Pre-populate manifest so env-detect is skipped.
    manifest = {
        "schema_version": "1.0",
        "git_sha": "0000000",
        "hardware": {"chip": "test-chip", "ram_gb": 0},
        "_self_hash": "deadbeef",
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    # Discover which task A/R1 would run against.
    plan = build_task_plan(
        categories=["A"], routes=["R1"], smoke=True, tasks_cap=None
    )
    assert len(plan) == 1
    seeded_task_id = plan[0].task_id
    append_row(raw, _make_row(seeded_task_id, "R1"))
    assert raw.read_text().count("\n") == 1

    proc = subprocess.run(
        [
            *RUN_ARGS,
            "--smoke",
            "--categories",
            "A",
            "--routes",
            "R1",
            "--out",
            str(out),
            "--hardware-manifest",
            str(manifest_path),
            "--resume",
            "--skip-scoring",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "[resume] skip" in proc.stdout
    # No new rows appended.
    assert raw.read_text().count("\n") == 1


def test_dry_run_with_all_categories_routes(tmp_path: Path) -> None:
    """Full smoke plan is 9 pairs."""
    out = tmp_path / "plan9"
    proc = subprocess.run(
        [
            *RUN_ARGS,
            "--smoke",
            "--categories",
            "A,B,C",
            "--routes",
            "R1,R2,R3",
            "--out",
            str(out),
            "--dry-run",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Planned pairs: 9" in proc.stdout
