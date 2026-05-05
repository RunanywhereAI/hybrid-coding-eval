"""Tests for scorers/llm_judge.py (T3.3).

These exercise the real Anthropic API and are skipped gracefully when
``ANTHROPIC_API_KEY`` is not set in the environment (or a repo-root
``.env``). The judge is deterministic at ``temperature=0``, so the
assertions here are tolerant of small wording changes but strict on the
bias-correction contract.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmark.custom_arch import load_tasks
from scorers.llm_judge import (
    JudgmentResult,
    judge_pairwise,
    judge_to_quality,
)


def _load_repo_env() -> None:
    """Populate ``os.environ`` from the repo-root ``.env`` (if present)
    so the skip guard and the judge see the same key."""
    if "ANTHROPIC_API_KEY" in os.environ:
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_repo_env()

requires_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live judge tests",
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def arch_task():
    tasks = load_tasks()
    assert tasks, "custom_arch tasks must be loadable"
    # Prefer an architecture-design task as a meaty, open-ended prompt.
    for t in tasks:
        if t.kind == "architecture-design":
            return t
    return tasks[0]


STRONG_RESPONSE = """\
## Multi-tenant auth design

**Schema**
- `tenants(id UUID PK, slug CITEXT UNIQUE, created_at TIMESTAMPTZ)`
- `users(id UUID PK, email CITEXT UNIQUE, password_hash TEXT)`
- `roles(id SERIAL PK, name TEXT, tenant_id UUID REFERENCES tenants(id))`
  - unique(name, tenant_id) lets every tenant carry its own "admin" row.
- `memberships(user_id UUID, tenant_id UUID, role_id INT, PRIMARY KEY(user_id, tenant_id))`
  - index on `(tenant_id, user_id)` supports the hot per-tenant lookup.

**Row-level security**
Every tenant-scoped table carries a `tenant_id UUID NOT NULL`. We enable
RLS and install a policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
FastAPI middleware issues `SET LOCAL app.tenant_id = '...'` inside a
transaction per request, so connection pooling is safe.

**Tokens**
Short-lived JWT (15 min) carrying `sub`, `tid`, `rid`. Refresh token
stored server-side, rotated on use, revoked by `jti` allowlist in Redis.
Never put role names in the JWT — always re-resolve from `memberships`
to honour revocation.

**FastAPI plumbing**
- Dependency `get_current_user` verifies JWT, looks up membership, sets
  the Postgres tenant var, returns a `Principal(user, tenant, role)`.
- Permission dependency `requires("invoice.read")` is a factory that
  raises 403 if the resolved role's permission bitmap lacks the flag.

**Tradeoffs**
RLS trades raw throughput (every query adds a predicate) for a hard
safety floor — even a buggy query can't leak across tenants. For
admin/cross-tenant reporting we use a separate read-only role that can
`SET ROLE` past RLS.
"""

WEAK_RESPONSE = "Use auth0 or similar. Store a tenant_id column. Check it on every request."


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #


@requires_key
def test_strong_a_beats_weak_b(arch_task):
    """A clearly-better response should win with a high margin."""
    result = judge_pairwise(arch_task, STRONG_RESPONSE, WEAK_RESPONSE)
    assert isinstance(result, JudgmentResult)
    assert result.winner == "A", (
        f"expected A to win, got {result.winner!r}. reasoning={result.reasoning!r}"
    )
    assert result.margin > 0.5, f"expected decisive margin, got {result.margin}"
    # And A's overall should clearly exceed B's.
    assert result.a_score > result.b_score + 1.0, (
        f"expected a_score >> b_score, got a={result.a_score} b={result.b_score}"
    )


@requires_key
def test_bias_correction_runs_both_orderings(arch_task):
    """Both raw_response fields must be populated and the winner must be
    order-invariant for a clear case."""
    result = judge_pairwise(arch_task, STRONG_RESPONSE, WEAK_RESPONSE)
    assert result.raw_response_ab, "A-vs-B raw response must be populated"
    assert result.raw_response_ba, "B-vs-A raw response must be populated"
    assert result.raw_response_ab != result.raw_response_ba, (
        "the two orderings should produce different raw responses"
    )
    # Consistency: swapping inputs should still pick the same candidate.
    flipped = judge_pairwise(arch_task, WEAK_RESPONSE, STRONG_RESPONSE)
    # In the flipped call, the strong response is now B.
    assert flipped.winner == "B", (
        f"winner should track the strong response, got {flipped.winner!r}"
    )


@requires_key
def test_rubric_dimensions_populated(arch_task):
    """All 5 rubric dimensions must carry a numeric score for both sides."""
    result = judge_pairwise(arch_task, STRONG_RESPONSE, WEAK_RESPONSE)
    expected = {"correctness", "completeness", "style", "reasoning_depth", "practicality"}
    assert set(result.a_dimensions) == expected
    assert set(result.b_dimensions) == expected
    for dim, score in result.a_dimensions.items():
        assert isinstance(score, (int, float)), f"a.{dim} not numeric: {score!r}"
        assert 0.0 <= score <= 5.0, f"a.{dim} out of range: {score}"
    for dim, score in result.b_dimensions.items():
        assert isinstance(score, (int, float)), f"b.{dim} not numeric: {score!r}"
        assert 0.0 <= score <= 5.0, f"b.{dim} out of range: {score}"
    # Reasoning must be substantive, not a one-liner.
    assert len(result.reasoning) >= 40, (
        f"expected substantive reasoning, got: {result.reasoning!r}"
    )


@requires_key
def test_tie_on_identical_outputs(arch_task):
    """Two identical outputs should produce a tie or a very low margin."""
    result = judge_pairwise(arch_task, STRONG_RESPONSE, STRONG_RESPONSE)
    assert result.winner == "tie" or result.margin < 0.3, (
        f"identical outputs should tie; got winner={result.winner!r} margin={result.margin}"
    )


# --------------------------------------------------------------------------- #
# pure (offline) tests — exercise judge_to_quality without calling the API.
# --------------------------------------------------------------------------- #


def _mk(winner: str, margin: float, a: float, b: float) -> JudgmentResult:
    dims_a = {d: a for d in ("correctness", "completeness", "style", "reasoning_depth", "practicality")}
    dims_b = {d: b for d in ("correctness", "completeness", "style", "reasoning_depth", "practicality")}
    return JudgmentResult(
        winner=winner,
        margin=margin,
        a_score=a,
        b_score=b,
        a_dimensions=dims_a,
        b_dimensions=dims_b,
        reasoning="",
        raw_response_ab="",
        raw_response_ba="",
        judge_model="claude-opus-4-7",
    )


def test_judge_to_quality_winner_side():
    j = _mk("A", 0.8, 4.5, 2.0)
    qa = judge_to_quality(j, side="A")
    qb = judge_to_quality(j, side="B")
    assert qa.judge_win_rate == pytest.approx(0.8)
    assert qb.judge_win_rate == pytest.approx(0.2)
    assert qa.composite == pytest.approx(0.9)
    assert qb.composite == pytest.approx(0.4)
    # Category C scorer does not set functional_pass.
    assert qa.functional_pass is None and qa.tests_total is None


def test_judge_to_quality_tie():
    j = _mk("tie", 0.1, 3.5, 3.5)
    qa = judge_to_quality(j, side="A")
    qb = judge_to_quality(j, side="B")
    assert qa.judge_win_rate == 0.5
    assert qb.judge_win_rate == 0.5


def test_judge_to_quality_invalid_side():
    j = _mk("A", 0.8, 4.5, 2.0)
    with pytest.raises(ValueError):
        judge_to_quality(j, side="X")
