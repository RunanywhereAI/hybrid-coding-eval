"""HumanEval+ adapter.

Loads a deterministic 10-task sample from the HumanEval+ dataset (the
EvalPlus-extended variant of OpenAI's HumanEval). Each Task carries the
natural-language+signature prompt, the reference canonical solution, the
EvalPlus-extended pytest code used for scoring (T3.1), and the dataset
entry-point function name.

Caching: the sampled 10 tasks are persisted to `tasks.jsonl` next to this
file. On subsequent calls the adapter loads from that file with no
network access. Delete the file to force re-sampling.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

DEFAULT_CACHE_FILE = Path(__file__).parent / "tasks.jsonl"
CATEGORY = "A"
ID_PREFIX = "humaneval-plus/"

# Fields we know about from the evalplus dataset. Anything beyond the
# explicit Task fields is stuffed into `metadata` so later stages
# (scorer, analysis) don't lose information.
_KNOWN_EVALPLUS_FIELDS = {
    "task_id",
    "prompt",
    "entry_point",
    "canonical_solution",
    "test",
}


@dataclass
class Task:
    id: str                  # e.g. "humaneval-plus/HumanEval_42"
    prompt: str              # problem statement + function signature
    canonical_solution: str  # reference solution body from the dataset
    tests: str               # EvalPlus pytest code used to score a candidate
    entry_point: str         # function name being solved
    category: str = CATEGORY  # category-A per PLAN.md §3
    metadata: dict = field(default_factory=dict)


def _namespaced_id(task_id: str) -> str:
    """Turn `HumanEval/42` into `humaneval-plus/HumanEval_42`."""
    return ID_PREFIX + task_id.replace("/", "_")


def _task_from_evalplus(raw: dict) -> Task:
    extras = {k: v for k, v in raw.items() if k not in _KNOWN_EVALPLUS_FIELDS}
    return Task(
        id=_namespaced_id(raw["task_id"]),
        prompt=raw["prompt"],
        canonical_solution=raw["canonical_solution"],
        tests=raw["test"],
        entry_point=raw["entry_point"],
        category=CATEGORY,
        metadata={"source_task_id": raw["task_id"], **extras},
    )


def _write_jsonl(tasks: list[Task], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[Task]:
    tasks: list[Task] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            tasks.append(
                Task(
                    id=d["id"],
                    prompt=d["prompt"],
                    canonical_solution=d["canonical_solution"],
                    tests=d["tests"],
                    entry_point=d["entry_point"],
                    category=d.get("category", CATEGORY),
                    metadata=d.get("metadata", {}),
                )
            )
    return tasks


def _sample_from_evalplus(n: int, seed: int) -> list[Task]:
    # Lazy import: evalplus pulls in heavy deps (torch-free but still
    # large), we only need it when cache is cold.
    from evalplus.data import get_human_eval_plus  # type: ignore

    raw = get_human_eval_plus()
    sorted_ids = sorted(raw.keys())
    rng = random.Random(seed)
    picked = rng.sample(sorted_ids, n)
    # Preserve the sampled order so reruns with the same seed emit
    # identical JSONL byte-for-byte.
    return [_task_from_evalplus(raw[tid]) for tid in picked]


def load_tasks(
    n: int = 10,
    seed: int = 42,
    cache_dir: Path | None = None,
) -> list[Task]:
    """Load n HumanEval+ tasks (default 10, seed 42).

    If a cache file exists and contains exactly n entries, it is used as
    the source of truth with no network access. Otherwise, we fetch the
    dataset via `evalplus`, take a seed-pinned random sample, write the
    cache, and return it.
    """
    cache_path = (
        (cache_dir / "tasks.jsonl") if cache_dir is not None else DEFAULT_CACHE_FILE
    )

    if cache_path.exists():
        cached = _read_jsonl(cache_path)
        if len(cached) == n:
            return cached
        # Size mismatch — regenerate rather than silently returning wrong n.

    tasks = _sample_from_evalplus(n=n, seed=seed)
    _write_jsonl(tasks, cache_path)
    return tasks


__all__ = ["Task", "load_tasks"]
