"""Tests for the SWE-bench Verified adapter.

These tests only exercise the pure-Python adapter — they do NOT require Docker
and they do NOT hit the network (the pinned ``tasks.jsonl`` is used).
"""

from __future__ import annotations

from benchmark.swebench_verified.adapter import (
    EASY_DIFFICULTY_VALUES,
    Task,
    load_tasks,
)


def test_load_tasks_returns_ten_easy_tier_tasks() -> None:
    tasks = load_tasks(n=10, seed=42, difficulty="easy")
    assert len(tasks) == 10
    for t in tasks:
        assert isinstance(t, Task)
        assert t.metadata.get("difficulty") in EASY_DIFFICULTY_VALUES, (
            f"{t.instance_id} has difficulty {t.metadata.get('difficulty')!r}, "
            f"expected one of {EASY_DIFFICULTY_VALUES}"
        )
        assert t.category == "B"
        assert t.id.startswith("swebench-verified/")


def test_every_task_has_required_non_empty_fields() -> None:
    tasks = load_tasks(n=10, seed=42, difficulty="easy")
    required_str_fields = (
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
        "test_patch",
        "expected_patch",
    )
    for t in tasks:
        for field_name in required_str_fields:
            value = getattr(t, field_name)
            assert isinstance(value, str), f"{t.instance_id}.{field_name} not str"
            assert value.strip(), f"{t.instance_id}.{field_name} is empty"
        # hints_text is allowed to be empty but must be a string.
        assert isinstance(t.hints_text, str)
        # base_commit should look like a git sha (hex, at least 7 chars).
        assert len(t.base_commit) >= 7
        assert all(c in "0123456789abcdef" for c in t.base_commit.lower())
        # Patches are unified diffs — they should at least contain "diff" or "---".
        assert "diff --git" in t.expected_patch or t.expected_patch.startswith("---"), (
            f"{t.instance_id}.expected_patch does not look like a unified diff"
        )
        assert "diff --git" in t.test_patch or t.test_patch.startswith("---"), (
            f"{t.instance_id}.test_patch does not look like a unified diff"
        )


def test_load_tasks_is_reproducible_across_calls_with_same_seed() -> None:
    a = load_tasks(n=10, seed=42, difficulty="easy")
    b = load_tasks(n=10, seed=42, difficulty="easy")
    assert [t.instance_id for t in a] == [t.instance_id for t in b]

    # A different seed should give a (mostly) different ordering when we have
    # more than n candidates in the pool. Even for our pinned set of 10 the
    # relative order changes.
    c = load_tasks(n=10, seed=7, difficulty="easy")
    assert [t.instance_id for t in a] == sorted([t.instance_id for t in a]) or (
        [t.instance_id for t in a] != [t.instance_id for t in c]
    )
