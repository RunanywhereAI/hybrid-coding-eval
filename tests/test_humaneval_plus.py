"""Tests for benchmark/humaneval_plus/adapter.py (T1.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.humaneval_plus.adapter import Task, load_tasks


def test_load_tasks_returns_ten_with_default_seed(tmp_path: Path) -> None:
    tasks = load_tasks(n=10, seed=42, cache_dir=tmp_path)
    assert isinstance(tasks, list)
    assert len(tasks) == 10
    for t in tasks:
        assert isinstance(t, Task)
        assert t.id.startswith("humaneval-plus/")
        assert t.category == "A"


def test_task_fields_are_populated(tmp_path: Path) -> None:
    tasks = load_tasks(n=10, seed=42, cache_dir=tmp_path)
    for t in tasks:
        assert t.prompt and isinstance(t.prompt, str)
        assert t.canonical_solution and isinstance(t.canonical_solution, str)
        assert t.tests and isinstance(t.tests, str)
        assert t.entry_point and isinstance(t.entry_point, str)
        # EvalPlus test code defines `def check(candidate)` — sanity check.
        assert "check" in t.tests
        # Prompt must include the function name we're solving.
        assert t.entry_point in t.prompt


def test_same_seed_same_ids_across_two_calls(tmp_path: Path) -> None:
    # First call populates cache.
    first = load_tasks(n=10, seed=42, cache_dir=tmp_path)
    first_ids = [t.id for t in first]
    # Second call reads cache (no network needed).
    second = load_tasks(n=10, seed=42, cache_dir=tmp_path)
    second_ids = [t.id for t in second]
    assert first_ids == second_ids
    # And independent regeneration into a different cache dir yields the
    # same IDs in the same order (seeded sampling reproducibility).
    other = tmp_path / "other"
    other.mkdir()
    third = load_tasks(n=10, seed=42, cache_dir=other)
    assert [t.id for t in third] == first_ids
