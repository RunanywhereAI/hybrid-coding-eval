"""Dataclasses that define the canonical result-row shape.

These are the tokens-first metrics the eval harness writes to
``results/*.jsonl`` — one ``ResultRow`` per (task × route × seed) run.

See ``PLAN.md`` §7 "result schema" for the rationale. The three guiding
principles:

  1. Tokens are always captured (prompt / completion / cached / reasoning,
     split by local vs cloud) — cost is derived later via ``lib.pricing``,
     never persisted.
  2. Latency is wall-clock + per-call so we can re-aggregate differently.
  3. Quality fields are all ``Optional`` because not every scorer applies to
     every task (functional-pass vs LLM-judge vs composite).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class TokenUsage:
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
    judge_win_rate: float | None = None
    composite: float | None = None


@dataclass
class Routing:
    total_calls: int
    local_calls: int
    cloud_calls: int
    per_call_backends: list[str] = field(default_factory=list)


@dataclass
class ResultRow:
    task_id: str
    category: str  # 'A' | 'B' | 'C'
    route: str  # 'R1' | 'R2' | 'R3' | 'R4'
    hardware_profile_ref: str
    tokens: TokenUsage
    latency: Latency
    quality: Quality
    routing: Routing
    output_ref: str
    # Optional metadata.
    started_at: str | None = None
    finished_at: str | None = None
    # Populated when a runner fails (proxy 5xx, timeout, bad JSON). When set,
    # callers should treat the row as a *skipped* run — tokens are zero, quality
    # is all-None, and the failure string explains why. This was added as a
    # minimal cross-cutting change so runners can report errors structurally
    # without crashing the orchestrator. Default None preserves backward-compat
    # for rows written before this field existed.
    error: str | None = None
    # Variant tag — populated from ``BenchConfig.variant_tag``. Rows from the
    # MVP sweeps (v1-qwen, v2-qwen-fixed, v2-devstral, r4-minion) set this
    # directly; post-T-07 rows inherit it from the loaded config. Optional
    # for backward compat with rows written before the field existed.
    variant: str | None = None
    # Model provenance for the row. None on historical rows (the info was
    # previously encoded only in ``routing.per_call_backends``); required on
    # all new sweeps. Populated by runners from the resolved BenchConfig.
    cloud_model_id: str | None = None
    local_model_id: str | None = None
    judge_model_id: str | None = None
    router_classifier_model_id: str | None = None
    router_strategy: str | None = None
    seed: int | None = None
    # SHA256 of the canonical JSON dump of the BenchConfig. Pairs every row
    # uniquely with the config that produced it.
    config_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Flatten for JSONL serialization. Uses ``dataclasses.asdict`` which
        recurses through the nested dataclasses."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResultRow":
        """Inverse of :meth:`to_dict`. Strict on required fields; unknown keys
        are ignored (forward-compatible)."""
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
