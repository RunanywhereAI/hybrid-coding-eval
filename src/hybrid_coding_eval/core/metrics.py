"""Dataclasses that define the canonical result-row shape.

One :class:`ResultRow` per ``(task, route, seed)`` pair is written to
``results/runs/<sweep>/raw.jsonl``. Three principles:

1. **Tokens are always captured** (``prompt`` / ``completion`` / ``cached`` /
   ``reasoning``, split by local vs cloud). Cost is derived later via
   :mod:`hybrid_coding_eval.core.pricing`; cost is never persisted.
2. **Latency** captures both wall-clock and per-call so downstream analysis
   can re-aggregate differently.
3. **Quality fields are optional** — not every scorer applies to every task
   (functional-pass for puzzles, multi-criterion for refactors).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class TokenUsage:
    """Token totals for one row, split between local and cloud backends.

    Invariants enforced downstream:
    * ``prompt == local_prompt + cloud_prompt``
    * ``completion == local_completion + cloud_completion``
    """

    prompt: int = 0
    completion: int = 0
    cached: int = 0
    reasoning: int = 0
    local_prompt: int = 0
    local_completion: int = 0
    cloud_prompt: int = 0
    cloud_completion: int = 0


@dataclass
class Latency:
    wall_ms: int
    per_call_ms: list[int] = field(default_factory=list)


@dataclass
class Quality:
    functional_pass: bool | None = None
    tests_passed: int | None = None
    tests_total: int | None = None
    judge_win_rate: float | None = None  # reserved for future LLM-judge sweeps
    composite: float | None = None


@dataclass
class Routing:
    total_calls: int
    local_calls: int
    cloud_calls: int
    per_call_backends: list[str] = field(default_factory=list)


@dataclass
class ResultRow:
    """One run of one ``(task, agent, strategy, seed)`` cell.

    Field reference (v1.4 schema):

    ``task_id``
        Task adapter id, e.g. ``"exercism-python/grep"`` or
        ``"real-dev/d4-review-pagination"``.
    ``category``
        v1.4 task class: ``"puzzles"``, ``"refactors"``, or ``"real-prs"``.
        Older sweeps may use the legacy letters (``"A"``, ``"D"``, ``"X"``);
        analysis code translates on read.
    ``route``
        Agent name: ``"aider"``, ``"opencode"``, ``"mini-swe-agent"``, or
        ``"cline"``. Older sweeps may use the legacy ``R6/R7/R8/R10`` ids.
    ``router_strategy``
        Which routing strategy was active: ``"always-cloud"``,
        ``"always-local"``, ``"heuristic"``, ``"cascade"``, etc.
    ``seed``
        Deterministic seed used for this row. Populated by the
        orchestrator for every v1.4+ sweep. Older sweeps may have ``None``.
    """

    task_id: str
    category: str
    route: str
    hardware_profile_ref: str
    tokens: TokenUsage
    latency: Latency
    quality: Quality
    routing: Routing
    output_ref: str
    started_at: str | None = None
    finished_at: str | None = None
    # When set, callers should treat the row as a *skipped* run — tokens are
    # zero, quality is all-None, the string explains why. Default None
    # preserves backward-compat with pre-error-field rows.
    error: str | None = None
    variant: str | None = None
    # Model provenance for the row. None on historical rows; required on
    # all new sweeps. Populated from the resolved BenchConfig.
    cloud_model_id: str | None = None
    local_model_id: str | None = None
    router_classifier_model_id: str | None = None
    router_strategy: str | None = None
    seed: int | None = None
    # SHA256 of the canonical JSON dump of the BenchConfig that produced
    # the row. Pairs every row uniquely with its config.
    config_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Flatten for JSONL serialization (recurses into nested dataclasses)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResultRow":
        """Inverse of :meth:`to_dict`. Unknown keys are silently dropped
        (forward-compatible across schema versions)."""

        def _pick(sub_cls, payload):
            names = {f.name for f in fields(sub_cls)}
            return sub_cls(**{k: v for k, v in (payload or {}).items() if k in names})

        allowed = {f.name for f in fields(cls)}
        known = {k: v for k, v in d.items() if k in allowed}
        known["tokens"] = _pick(TokenUsage, d.get("tokens"))
        known["latency"] = _pick(Latency, d.get("latency"))
        known["quality"] = _pick(Quality, d.get("quality"))
        known["routing"] = _pick(Routing, d.get("routing"))
        return cls(**known)
