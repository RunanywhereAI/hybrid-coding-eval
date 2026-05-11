"""Tests for ``hybrid_coding_eval.benchmarks.real_dev.scorers`` (P2.1).

Covers:

- the shape-dispatcher (``score`` → ``_score_dN`` mapping);
- per-shape smoke tests for D1 / D2 / D5 against the fixture's
  ``_reference/`` solution;
- mocked D3 / D4 judge flow (we do NOT call Anthropic here);
- the ``_extract_files_for_targets`` fenced-block matcher used by D1 / D5
  to map a multi-file model response onto the expected file layout.

Docker-dependent tests (D1 / D5 end-to-end) are auto-skipped when the
daemon is unreachable or the custom scorer image
(``hybrid-eval-python:latest``) is not built. Running them locally only
requires Docker Desktop to be up; no external network access is used
once the image is present.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_coding_eval.benchmarks.real_dev.adapter import Task, load_tasks  # noqa: E402
from hybrid_coding_eval.benchmarks.real_dev.scorers import (  # noqa: E402
    _FIXTURES_ROOT,
    _extract_files_for_targets,
    _list_reference_targets,
    _score_d3_d4,
    score,
)
from hybrid_coding_eval.core.metrics import Quality  # noqa: E402
from hybrid_coding_eval.scorers.llm_judge import JudgmentResult  # noqa: E402

# --------------------------------------------------------------------------- #
# Docker availability guards (copied pattern from test_functional_python.py)
# --------------------------------------------------------------------------- #


def _docker_available() -> bool:
    try:
        import docker  # type: ignore[import-untyped]
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
    except Exception:
        return False
    return True


def _image_available(tag: str) -> bool:
    try:
        import docker  # type: ignore[import-untyped]
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.images.get(tag)
    except Exception:
        return False
    return True


requires_docker = pytest.mark.skipif(
    not _docker_available(), reason="docker daemon not reachable"
)
requires_scorer_image = pytest.mark.skipif(
    not _image_available("hybrid-eval-python:latest"),
    reason="hybrid-eval-python:latest image not built",
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def all_tasks():
    tasks = load_tasks()
    assert tasks, "real_dev tasks.jsonl must be populated (run bin/merge_real_dev_shards.py)"
    return tasks


@pytest.fixture
def d1_task(all_tasks):
    for t in all_tasks:
        if t.id == "real-dev/d1-rate-limit":
            return t
    pytest.skip("d1-rate-limit not present in tasks.jsonl")


@pytest.fixture
def d2_task(all_tasks):
    for t in all_tasks:
        if t.id == "real-dev/d2-click-3298":
            return t
    pytest.skip("d2-click-3298 not present in tasks.jsonl")


@pytest.fixture
def d3_task(all_tasks):
    for t in all_tasks:
        if t.id == "real-dev/d3-extract-validation-helper":
            return t
    pytest.skip("d3-extract-validation-helper not present")


@pytest.fixture
def d4_task(all_tasks):
    for t in all_tasks:
        if t.id == "real-dev/d4-review-pagination":
            return t
    pytest.skip("d4-review-pagination not present")


@pytest.fixture
def d5_task(all_tasks):
    # Pick csv-dedupe: pure-stdin/stdout, no shell, fastest to run in sandbox.
    for t in all_tasks:
        if t.id == "real-dev/d5-csv-dedupe":
            return t
    pytest.skip("d5-csv-dedupe not present")


def _wrap(body: str, lang: str = "python") -> str:
    return f"```{lang}\n{body}\n```\n"


def _read_reference(slug: str, relpath: str) -> str:
    return (_FIXTURES_ROOT / slug / "_reference" / relpath).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #


def test_score_dispatcher_unknown_shape_raises():
    """A bogus shape short-circuits to ValueError (adapter validation should
    have caught it first, but the scorer defends anyway)."""
    fake = Task(
        id="real-dev/bogus",
        shape="DZ",  # type: ignore[arg-type]
        prompt="whatever",
    )
    with pytest.raises(ValueError, match="unknown shape"):
        score(fake, "model output")


def test_score_dispatcher_d2_is_deferred_with_none_quality(d2_task):
    """D2 grading is deferred (see the _score_d2 docstring). The sweep
    must receive an all-None Quality so aggregators see 'not graded'."""
    q = score(d2_task, "```diff\n--- a/foo.py\n+++ b/foo.py\n```")
    assert q.functional_pass is None
    assert q.composite is None


# --------------------------------------------------------------------------- #
# Target-extraction helper
# --------------------------------------------------------------------------- #


def test_list_reference_targets_d1_rate_limit():
    """Targets are enumerated relative to _reference/ and in sorted order."""
    targets = _list_reference_targets(_FIXTURES_ROOT / "d1-rate-limit")
    assert targets == ["middleware.py"]


def test_list_reference_targets_d1_retry_has_two():
    targets = _list_reference_targets(_FIXTURES_ROOT / "d1-retry-decorator")
    assert set(targets) == {"main.py", "retry.py"}


def test_extract_single_file_from_plain_fence():
    """Single-target tasks accept a single python fence with no filename label."""
    model_output = "```python\ndef foo():\n    pass\n```\n"
    out = _extract_files_for_targets(model_output, ["solution.py"])
    assert list(out) == ["solution.py"]
    assert "def foo():" in out["solution.py"]


def test_extract_multifile_uses_markdown_heading_labels():
    """Models returning `### retry.py` + `### main.py` must route to both."""
    model_output = (
        "Here it is:\n\n"
        "### retry.py\n"
        "```python\n"
        "def retry(): return None\n"
        "```\n\n"
        "### main.py\n"
        "```python\n"
        "import client\n"
        "```\n"
    )
    out = _extract_files_for_targets(
        model_output, ["retry.py", "main.py"]
    )
    assert set(out) == {"retry.py", "main.py"}
    assert "def retry()" in out["retry.py"]
    assert "import client" in out["main.py"]


def test_extract_empty_output_yields_empty_map():
    assert _extract_files_for_targets("", ["solution.py"]) == {}
    assert _extract_files_for_targets("   \n  \n", ["solution.py"]) == {}


# --------------------------------------------------------------------------- #
# D1 — functional end-to-end (reference solution must pass)
# --------------------------------------------------------------------------- #


@requires_docker
@requires_scorer_image
def test_d1_reference_solution_passes(d1_task):
    """The phase-1-calibrated reference solution for d1-rate-limit must
    score as a full pass. If this test goes red, either the fixture was
    edited or the scorer's fixture-overlay is broken."""
    body = _read_reference("d1-rate-limit", "middleware.py")
    q = score(d1_task, _wrap(body))
    assert isinstance(q, Quality)
    assert q.functional_pass is True, f"reference D1 failed: {q}"
    assert q.tests_total is not None and q.tests_total > 0
    assert q.tests_passed == q.tests_total
    assert q.composite == pytest.approx(1.0)


@requires_docker
@requires_scorer_image
def test_d1_empty_output_fails(d1_task):
    """An empty model output must fail cleanly — Quality with
    functional_pass=False, not an exception."""
    q = score(d1_task, "")
    assert q.functional_pass is False
    assert (q.composite or 0.0) < 1.0


# --------------------------------------------------------------------------- #
# D5 — functional end-to-end (reference script must pass)
# --------------------------------------------------------------------------- #


@requires_docker
@requires_scorer_image
def test_d5_reference_script_passes(d5_task):
    """The d5-csv-dedupe reference solution must score as a full pass."""
    body = _read_reference("d5-csv-dedupe", "solution.py")
    q = score(d5_task, _wrap(body))
    assert q.functional_pass is True, f"reference D5 failed: {q}"
    assert q.tests_total is not None and q.tests_total >= 1
    assert q.tests_passed == q.tests_total


@requires_docker
@requires_scorer_image
def test_d5_wrong_solution_fails(d5_task):
    """A no-op solution that just prints nothing must fail the stdout diff."""
    q = score(d5_task, "```python\nimport sys; sys.exit(0)\n```")
    assert q.functional_pass is False


# --------------------------------------------------------------------------- #
# D3 / D4 — judge path (mocked; no Anthropic calls)
# --------------------------------------------------------------------------- #


def _mk_judgment(winner: str, margin: float, a_score: float, b_score: float):
    dims_a = {d: a_score for d in (
        "correctness", "completeness", "style", "reasoning_depth", "practicality",
    )}
    dims_b = {d: b_score for d in (
        "correctness", "completeness", "style", "reasoning_depth", "practicality",
    )}
    return JudgmentResult(
        winner=winner,
        margin=margin,
        a_score=a_score,
        b_score=b_score,
        a_dimensions=dims_a,
        b_dimensions=dims_b,
        reasoning="synthetic",
        raw_response_ab="",
        raw_response_ba="",
        judge_model="claude-opus-4-7",
    )


def test_d3_uses_judge_and_maps_to_quality(d3_task):
    """D3 dispatch calls llm_judge.judge_pairwise and converts the result
    to a judge_win_rate + composite Quality."""
    fake = _mk_judgment(winner="A", margin=0.7, a_score=4.0, b_score=3.0)
    with patch(
        "hybrid_coding_eval.scorers.llm_judge.judge_pairwise",
        return_value=fake,
    ) as mocked:
        q = score(d3_task, "arbitrary refactor output")
    mocked.assert_called_once()
    assert q.functional_pass is None  # judge path never sets functional_pass
    # A won the synthetic judgment → win_rate == margin.
    assert q.judge_win_rate == pytest.approx(0.7)
    # composite == a_score / 5
    assert q.composite == pytest.approx(4.0 / 5.0)


def test_d4_uses_judge_and_maps_to_quality(d4_task):
    """D4 dispatch uses the same judge path as D3."""
    fake = _mk_judgment(winner="B", margin=0.9, a_score=2.0, b_score=4.5)
    with patch(
        "hybrid_coding_eval.scorers.llm_judge.judge_pairwise",
        return_value=fake,
    ) as mocked:
        q = score(d4_task, "arbitrary review output")
    mocked.assert_called_once()
    # A (model) lost decisively, so win_rate == 1 - margin.
    assert q.judge_win_rate == pytest.approx(1.0 - 0.9)
    assert q.composite == pytest.approx(2.0 / 5.0)


def test_d3_when_judge_raises_returns_unknown_quality(d3_task):
    """If the judge blows up (e.g. ANTHROPIC_API_KEY missing) we return
    unknown Quality rather than crashing the sweep."""
    with patch(
        "hybrid_coding_eval.scorers.llm_judge.judge_pairwise",
        side_effect=RuntimeError("no api key"),
    ):
        q = score(d3_task, "whatever")
    assert q.functional_pass is None
    assert q.composite is None
    assert q.judge_win_rate is None


def test_d3_uses_gold_exemplar_as_side_b(d3_task):
    """The judge must see the gold exemplar as candidate B (the thing to
    beat), not as candidate A. This pins the convention used by
    judge_to_quality(side='A')."""
    captured = {}

    def fake_judge(task, output_a, output_b, **kwargs):
        captured["output_a"] = output_a
        captured["output_b"] = output_b
        return _mk_judgment(winner="A", margin=0.5, a_score=3.5, b_score=3.5)

    with patch(
        "hybrid_coding_eval.scorers.llm_judge.judge_pairwise",
        side_effect=fake_judge,
    ):
        _ = _score_d3_d4(d3_task, "model refactor text")
    assert captured["output_a"] == "model refactor text"
    # The gold exemplar for d3-extract-validation-helper concatenates
    # the reference app.py + validate.py; just check both filenames appear
    # as headers in the concatenated string.
    assert "### app.py" in captured["output_b"]
    assert "### validate.py" in captured["output_b"]


def test_d4_gold_exemplar_uses_gold_review_md(d4_task):
    """D4 gold exemplar should be the raw markdown of gold_review.md, not
    a concatenation with headers (D4 has exactly one gold file)."""
    captured = {}

    def fake_judge(task, output_a, output_b, **kwargs):
        captured["output_b"] = output_b
        return _mk_judgment(winner="A", margin=0.5, a_score=3.5, b_score=3.5)

    with patch(
        "hybrid_coding_eval.scorers.llm_judge.judge_pairwise",
        side_effect=fake_judge,
    ):
        _ = _score_d3_d4(d4_task, "model review text")
    # Gold review markdown starts with a top-level heading — assert it's
    # carried through verbatim (no ``### gold_review.md`` wrapper).
    assert captured["output_b"].lstrip().startswith("#")
    assert "gold_review.md" not in captured["output_b"].splitlines()[0]


# --------------------------------------------------------------------------- #
# llm_judge._rubric_lines string-rubric compatibility (regression test for the
# P1.3 gotcha — real_dev rubrics are dict[str, str], custom_arch rubrics are
# dict[str, Rubric]).
# --------------------------------------------------------------------------- #


def test_rubric_lines_accepts_plain_string_descriptions(d3_task):
    """real_dev tasks carry rubric = dict[str, str]. The judge's
    _rubric_lines helper must render them without raising AttributeError."""
    from hybrid_coding_eval.scorers.llm_judge import _rubric_lines

    out = _rubric_lines(d3_task)
    assert "correctness" in out
    # The d3 task's correctness description starts with 'The refactor
    # preserves behaviour' — verify a substring of the rubric actually
    # made it into the formatted prompt.
    assert "preserves" in out
