"""Bias-corrected pairwise LLM-judge scorer (Category C).

This module is the Python port (and rubric-adaptation) of the MT-Bench
pairwise judge shipped in ``EXTERNAL/lm-eval-harness-judge/src/``. We do
NOT import from that vendored directory; it is reference-only. Here we
use the five-dimension rubric attached to each ``benchmark.custom_arch``
``Task`` to drive per-axis scoring, then run the judge twice — once with
candidate A first, once with B first — and average to cancel position
bias.

Design notes
------------
- Judge model is Anthropic's ``claude-opus-4-7``. We score OpenAI routes
  in this project, so using a cross-vendor judge avoids self-preference
  bias (the judge can't favour "its own" responses).
- The judge is asked to return JSON-only output. We parse it robustly:
  strip code fences, extract the first balanced ``{...}`` block, fall
  back to a permissive regex for each field.
- Bias correction: if both orderings agree on the winner, the margin is
  the mean of their reported margins. If they disagree, we call it a
  ``tie`` and report a small residual margin (the mean of the two,
  halved — so a flipped verdict is visibly weak).
- Per-dimension scores are averaged across orderings independent of the
  winner decision, which gives a stable per-axis signal even when the
  overall verdict wobbles.

Public API: :func:`judge_pairwise`, :func:`judge_to_quality`, and the
``JudgmentResult`` dataclass.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.metrics import Quality

# Lazy import of ``anthropic`` happens inside :func:`judge_pairwise` so that
# importing this module in environments without the SDK (e.g. static type
# checks) doesn't explode.

_DIMENSIONS: tuple[str, ...] = (
    "correctness",
    "completeness",
    "style",
    "reasoning_depth",
    "practicality",
)

_DEFAULT_JUDGE_MODEL = "claude-opus-4-7"

_SYSTEM_PROMPT = (
    "You are an expert evaluator rating two candidate responses to a "
    "coding or software-architecture task. Be impartial. Do not let the "
    "order in which responses are presented influence your verdict. Do "
    "not favour either response for length alone. Return ONLY valid JSON "
    "in the shape requested — no preamble, no code fences."
)


@dataclass
class JudgmentResult:
    """Bias-corrected verdict from two orderings of the same pair."""

    winner: str  # 'A' | 'B' | 'tie'
    margin: float  # 0..1, confidence in the verdict
    a_score: float  # 0..5, rubric-weighted overall for A
    b_score: float  # 0..5, rubric-weighted overall for B
    a_dimensions: dict[str, float] = field(default_factory=dict)
    b_dimensions: dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    raw_response_ab: str = ""
    raw_response_ba: str = ""
    judge_model: str = _DEFAULT_JUDGE_MODEL


# --------------------------------------------------------------------------- #
# env / api-key handling
# --------------------------------------------------------------------------- #


def _load_dotenv_once() -> None:
    """Populate ``os.environ`` from the repo-root ``.env`` file.

    Minimal parser — we don't want to pull ``python-dotenv`` for three
    lines. Silently skips if the file is absent or malformed. Never
    overwrites keys already present in the environment.
    """
    # Walk up from this file to find the repo root (first parent containing
    # ``.env`` or ``pyproject.toml``). Prevents surprises if CWD is weird.
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        env_path = candidate / ".env"
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            except OSError:
                pass
            return
        if (candidate / "pyproject.toml").is_file():
            return


def _resolve_api_key(explicit: str | None) -> str:
    if explicit:
        return explicit
    if "ANTHROPIC_API_KEY" not in os.environ:
        _load_dotenv_once()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return key


# --------------------------------------------------------------------------- #
# prompt building
# --------------------------------------------------------------------------- #


def _rubric_lines(task: Any) -> str:
    """Format the task's rubric as a bullet list for the prompt."""
    rubric = getattr(task, "rubric", {}) or {}
    lines: list[str] = []
    for dim in _DIMENSIONS:
        desc = ""
        if dim in rubric:
            desc = getattr(rubric[dim], "description", "") or ""
        if not desc:
            # Fall back to a generic description so the judge still has a
            # prompt even for tasks that don't define this axis.
            desc = f"how well the response addresses {dim.replace('_', ' ')}"
        lines.append(f"- {dim}: {desc}")
    return "\n".join(lines)


def _build_user_prompt(task: Any, first: str, second: str) -> str:
    prompt = getattr(task, "prompt", "") or ""
    return f"""You are an expert evaluator rating two candidate responses to a coding/architecture task.

TASK:
{prompt}

RUBRIC (score each 0-5):
{_rubric_lines(task)}

RESPONSE A:
{first}

RESPONSE B:
{second}

For each response, rate each dimension 0-5. Then declare a winner (A, B, or tie) and explain in 2-3 sentences.

Return ONLY valid JSON with this exact shape:
{{
  "a_dimensions": {{"correctness": N, "completeness": N, "style": N, "reasoning_depth": N, "practicality": N}},
  "b_dimensions": {{"correctness": N, "completeness": N, "style": N, "reasoning_depth": N, "practicality": N}},
  "a_overall": N,
  "b_overall": N,
  "winner": "A" | "B" | "tie",
  "margin": 0.0,
  "reasoning": "..."
}}
"""


# --------------------------------------------------------------------------- #
# response parsing
# --------------------------------------------------------------------------- #


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _extract_json_object(text: str) -> str | None:
    """Return the first top-level balanced ``{...}`` substring of *text*.

    Ignores braces inside string literals. Returns ``None`` if no balanced
    object is found.
    """
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return text[start : i + 1]
    return None


def _clamp_score(x: Any, lo: float = 0.0, hi: float = 5.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(lo, min(hi, v))


def _parse_judge_response(text: str) -> dict[str, Any]:
    """Parse the judge's JSON blob into a normalized dict.

    Always returns a dict with keys ``a_dimensions`` (dict of 5 floats),
    ``b_dimensions`` (dict of 5 floats), ``a_overall`` (float 0..5),
    ``b_overall`` (float 0..5), ``winner`` ('A'|'B'|'tie'), ``margin``
    (float 0..1), ``reasoning`` (str). Missing fields get safe defaults.
    """
    cleaned = _strip_fences(text).strip()
    blob = _extract_json_object(cleaned) or cleaned
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    def _dims(src: Any) -> dict[str, float]:
        src = src if isinstance(src, dict) else {}
        return {dim: _clamp_score(src.get(dim)) for dim in _DIMENSIONS}

    a_dims = _dims(data.get("a_dimensions"))
    b_dims = _dims(data.get("b_dimensions"))
    a_overall = (
        _clamp_score(data.get("a_overall"))
        if "a_overall" in data
        else sum(a_dims.values()) / len(_DIMENSIONS)
    )
    b_overall = (
        _clamp_score(data.get("b_overall"))
        if "b_overall" in data
        else sum(b_dims.values()) / len(_DIMENSIONS)
    )

    winner_raw = str(data.get("winner", "")).strip().upper()
    if winner_raw == "A":
        winner = "A"
    elif winner_raw == "B":
        winner = "B"
    else:
        winner = "tie"

    margin = _clamp_score(data.get("margin"), 0.0, 1.0)
    reasoning = str(data.get("reasoning", "")).strip()

    return {
        "a_dimensions": a_dims,
        "b_dimensions": b_dims,
        "a_overall": a_overall,
        "b_overall": b_overall,
        "winner": winner,
        "margin": margin,
        "reasoning": reasoning,
    }


# --------------------------------------------------------------------------- #
# anthropic call
# --------------------------------------------------------------------------- #


def _call_anthropic(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    import anthropic  # local import so import-time has no hard dep

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    chunks: list[str] = []
    for block in resp.content or []:
        # The SDK returns ``TextBlock`` instances; each has ``.text``.
        text = getattr(block, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks).strip()


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #


def judge_pairwise(
    task: Any,
    output_a: str,
    output_b: str,
    judge_model: str = _DEFAULT_JUDGE_MODEL,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
) -> JudgmentResult:
    """Run two pairwise judgments (A-vs-B + B-vs-A) and return a
    bias-corrected :class:`JudgmentResult`.

    Parameters
    ----------
    task
        A :class:`benchmark.custom_arch.Task` (or any duck-typed object
        exposing ``prompt`` and ``rubric``).
    output_a, output_b
        Candidate responses to compare.
    judge_model
        Anthropic model id. Defaults to ``claude-opus-4-7``.
    api_key
        Overrides ``$ANTHROPIC_API_KEY``. ``.env`` at the repo root is
        consulted if the variable is unset.
    temperature
        Judge temperature; ``0.0`` for determinism.
    max_tokens
        Cap for the judge's response (JSON blob).
    """
    key = _resolve_api_key(api_key)

    # Ordering 1: A first, B second.
    raw_ab = _call_anthropic(
        api_key=key,
        model=judge_model,
        system=_SYSTEM_PROMPT,
        user=_build_user_prompt(task, output_a, output_b),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    parsed_ab = _parse_judge_response(raw_ab)

    # Ordering 2: B first, A second. ``winner`` in this ordering's frame of
    # reference is inverted before averaging.
    raw_ba = _call_anthropic(
        api_key=key,
        model=judge_model,
        system=_SYSTEM_PROMPT,
        user=_build_user_prompt(task, output_b, output_a),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    parsed_ba_local = _parse_judge_response(raw_ba)

    # Remap ordering-2 to the canonical (A, B) frame.
    winner_ba = parsed_ba_local["winner"]
    if winner_ba == "A":
        remapped_winner_ba = "B"
    elif winner_ba == "B":
        remapped_winner_ba = "A"
    else:
        remapped_winner_ba = "tie"

    parsed_ba = {
        "a_dimensions": parsed_ba_local["b_dimensions"],
        "b_dimensions": parsed_ba_local["a_dimensions"],
        "a_overall": parsed_ba_local["b_overall"],
        "b_overall": parsed_ba_local["a_overall"],
        "winner": remapped_winner_ba,
        "margin": parsed_ba_local["margin"],
        "reasoning": parsed_ba_local["reasoning"],
    }

    # Average per-dimension & overall scores across orderings.
    a_dims = {
        d: (parsed_ab["a_dimensions"][d] + parsed_ba["a_dimensions"][d]) / 2
        for d in _DIMENSIONS
    }
    b_dims = {
        d: (parsed_ab["b_dimensions"][d] + parsed_ba["b_dimensions"][d]) / 2
        for d in _DIMENSIONS
    }
    a_score = (parsed_ab["a_overall"] + parsed_ba["a_overall"]) / 2
    b_score = (parsed_ab["b_overall"] + parsed_ba["b_overall"]) / 2

    # Reconcile the winner across the two orderings.
    if parsed_ab["winner"] == parsed_ba["winner"]:
        winner = parsed_ab["winner"]
        margin = (parsed_ab["margin"] + parsed_ba["margin"]) / 2
    else:
        # Disagreement → position bias likely flipped the verdict. Call it
        # a tie with a deliberately small margin so downstream aggregation
        # can see "there was signal but it was weak".
        winner = "tie"
        margin = (parsed_ab["margin"] + parsed_ba["margin"]) / 4

    reasoning = parsed_ab["reasoning"]
    if parsed_ba["reasoning"] and parsed_ba["reasoning"] != reasoning:
        # Keep both so the audit log shows the judge's argument from each
        # ordering. Cheap, and useful when we're debugging a surprising
        # verdict.
        reasoning = (
            f"[A-first] {parsed_ab['reasoning']}\n"
            f"[B-first] {parsed_ba['reasoning']}"
        )

    return JudgmentResult(
        winner=winner,
        margin=float(margin),
        a_score=float(a_score),
        b_score=float(b_score),
        a_dimensions=a_dims,
        b_dimensions=b_dims,
        reasoning=reasoning,
        raw_response_ab=raw_ab,
        raw_response_ba=raw_ba,
        judge_model=judge_model,
    )


def judge_to_quality(judgment: JudgmentResult, *, side: str = "A") -> Quality:
    """Convert a :class:`JudgmentResult` into a :class:`lib.metrics.Quality`
    for a SINGLE row (the A side or the B side of the pair).

    ``judge_win_rate``: the probability this side won, expressed in
    ``[0, 1]``. For a decisive verdict this is ``margin`` when the side
    won, ``1 - margin`` when it lost, and ``0.5`` on a tie.

    ``composite``: this side's rubric-weighted overall score mapped to
    ``[0, 1]`` (i.e. divided by 5). Lets downstream aggregation compare
    quality across category C tasks with a single scalar.
    """
    side_u = side.upper()
    if side_u not in ("A", "B"):
        raise ValueError(f"side must be 'A' or 'B', got {side!r}")

    if judgment.winner == "tie":
        win_rate = 0.5
    elif judgment.winner == side_u:
        win_rate = judgment.margin
    else:
        win_rate = 1.0 - judgment.margin

    overall = judgment.a_score if side_u == "A" else judgment.b_score
    composite = max(0.0, min(1.0, overall / 5.0))

    return Quality(
        functional_pass=None,
        tests_passed=None,
        tests_total=None,
        judge_win_rate=float(win_rate),
        composite=float(composite),
    )


__all__ = [
    "JudgmentResult",
    "judge_pairwise",
    "judge_to_quality",
]
