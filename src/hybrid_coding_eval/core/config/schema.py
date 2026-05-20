"""Pydantic v2 schema for benchmark-run configs.

A ``BenchConfig`` is the single declarative description of *what to
run*: which models, which routes, which categories, which pricing
scenarios, where to dump results. The YAML files under
``configs/variants/`` are instances of this schema.

Design:

- Every axis that varies between sweeps lives here. That includes
  hidden axes surfaced during the plan-agent pressure test:
  ``cloud_fallback``, ``local_base_url``, ``cloud_base_url``, router
  thresholds, prompt-cache toggle, per-route seed, git-SHA pin, etc.
- Defaults match the MVP numbers (gpt-5.5 / devstral:24b / Opus judge /
  heuristic router / three categories / four routes).
- Anything with ``| None = None`` is optional. Anything required has
  no default and must appear in YAML or on the CLI.

The loaded-and-resolved ``BenchConfig`` is hashed (SHA256 of canonical
JSON) and the hash is written into every ``ResultRow.config_sha`` at
T-08, so two rows produced by the same sweep are re-derivable even
after the YAML is edited.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ModelsConfig",
    "RouterConfig",
    "BenchmarkConfig",
    "PricingConfig",
    "ScoringConfig",
    "BenchConfig",
]


RouteStrategy = Literal[
    "always-local",
    "always-cloud",
    "rules",
    "heuristic",
    "llm-classifier",
    "embedding-knn",
    "cascade",
]
Category = Literal["A", "B", "C", "D", "X"]
Route = Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]


class ModelsConfig(BaseModel):
    """Which models make up cloud / local / judge / router-classifier slots."""

    model_config = ConfigDict(extra="forbid")

    cloud: str = Field(
        ..., description="Cloud model id (e.g. 'gpt-5.5'). Used by R1 + R3 + R4 supervisor."
    )
    cloud_fallback: str | None = Field(
        default=None,
        description="Fallback cloud model if ``cloud`` 404s (e.g. 'gpt-5').",
    )
    local: str = Field(
        ..., description="Local model id as Ollama tag (e.g. 'devstral:24b')."
    )
    judge: str = Field(
        default="claude-opus-4-7",
        description="LLM-judge model for custom-arch scoring (C-category).",
    )
    router_classifier: str = Field(
        default="qwen3:0.6b",
        description="Small local model used by the llm-classifier router strategy.",
    )
    local_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        description="Ollama OpenAI-compatible endpoint.",
    )
    cloud_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Cloud base URL.",
    )


class RouterConfig(BaseModel):
    """Router-proxy deployment + strategy knobs."""

    model_config = ConfigDict(extra="forbid")

    strategy: RouteStrategy = Field(
        default="heuristic",
        description="Which routing strategy R3's per-step executor uses.",
    )
    port: int = Field(default=8787, description="Router proxy port.")
    banner: bool = Field(
        default=True,
        description="Prefix a one-line ``[router] …`` note on the first delta.",
    )
    heuristic_threshold: float | None = Field(
        default=None,
        description="Override the heuristic cutoff in router/strategies.mjs.",
    )
    prompt_cache: bool = Field(
        default=False,
        description="Turn on OpenAI prompt caching on static R3 prefixes.",
    )


class BenchmarkConfig(BaseModel):
    """Which categories × routes × how many tasks."""

    model_config = ConfigDict(extra="forbid")

    categories: list[Category] = Field(default=["A", "B", "C"])
    routes: list[Route] = Field(default=["R1", "R2", "R3", "R4"])
    tasks_per_category: dict[str, int] | None = Field(
        default=None,
        description="Cap N per category, e.g. {'A': 3, 'B': 3, 'C': 3}.",
    )
    task_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional explicit task-ID whitelist. When set, only tasks whose "
            "``id`` field matches one of these strings are included in the "
            "plan — `categories` + `tasks_per_category` still apply for which "
            "sources to load FROM, but the final selection is filtered to "
            "this list. v1.3+: use to scope to R7-compatible D1+D5 tasks."
        ),
    )
    seeds: list[int] = Field(default=[42])
    smoke: bool = Field(
        default=False,
        description="Take one task per category (deterministic).",
    )


class PricingConfig(BaseModel):
    """Official API per-M-token scenarios for the report."""

    model_config = ConfigDict(extra="forbid")

    scenarios: list[str] = Field(
        default=[
            "openai-gpt5.5",
            "openai-gpt5",
            "openai-gpt5-mini",
            "anthropic-claude-opus-4.7",
            "anthropic-claude-sonnet-4.6",
            "anthropic-claude-haiku-4.5",
        ],
        description="Named pricing scenarios to re-price the dataset under.",
    )
    primary: str = Field(
        default="openai-gpt5.5",
        description="Scenario used for headline numbers in decision matrices.",
    )


class ScoringConfig(BaseModel):
    """Scoring-pipeline toggles."""

    model_config = ConfigDict(extra="forbid")

    skip: bool = Field(
        default=False, description="Run routes without inline scoring."
    )
    judge_temperature: float = Field(default=0.0)
    swebench_image: str = Field(
        default="hybrid-eval-python:latest",
        description="Docker image tag for the functional sandbox.",
    )


class BenchConfig(BaseModel):
    """Top-level benchmark-run configuration.

    Two required fields (``variant_tag`` and ``out_dir``) + one required
    ``models`` block. Everything else has MVP-matching defaults so a
    minimal YAML is:

        variant_tag: my-variant
        out_dir: results/runs/XX-my-variant
        models:
          cloud: gpt-5.5
          local: devstral:24b
    """

    model_config = ConfigDict(extra="forbid")

    variant_tag: str = Field(
        ...,
        description=(
            "Stable identifier written into every ResultRow.variant. "
            "Used by analysis to group rows by sweep."
        ),
    )
    out_dir: Path = Field(
        ...,
        description="Where to write raw.jsonl / outputs/ / run-notes.md.",
    )
    models: ModelsConfig
    router: RouterConfig = RouterConfig()
    benchmark: BenchmarkConfig = BenchmarkConfig()
    pricing: PricingConfig = PricingConfig()
    scoring: ScoringConfig = ScoringConfig()
    resume: bool = Field(
        default=False,
        description="Skip (task_id, route) pairs already in raw.jsonl.",
    )
    git_sha_pin: str | None = Field(
        default=None,
        description=(
            "If set, assert current git HEAD matches this SHA before running "
            "— guards against accidental replays of a dataset from a dirty "
            "working tree."
        ),
    )

    def canonical_sha256(self) -> str:
        """Stable SHA256 over the canonicalised JSON dump.

        Two equivalent YAMLs produce identical hashes. The hash is
        written into every ResultRow.config_sha field at T-08 so
        individual rows are re-derivable without the original YAML.
        """
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
