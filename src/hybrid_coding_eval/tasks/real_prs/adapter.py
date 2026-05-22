"""SWE-bench Verified adapter.

Loads tasks from ``princeton-nlp/SWE-bench_Verified`` (the human-validated subset
of the original SWE-bench) and exposes them as :class:`Task` objects the rest of
the eval harness can consume.

This adapter is deliberately thin: it does NOT depend on Docker. Only the
companion ``verify_harness.py`` script touches Docker, because that's where the
actual pass/fail grading happens. For the MVP the whole benchmark is restricted
to the *easy* tier (``"<15 min fix"``) — the fastest-to-grade bucket, and also
the one where open-source local models have the best chance of being
competitive with frontier cloud models. We only sample 10 instances because
each scored task requires pulling a ~500 MB per-task Docker image.

The upstream dataset schema (as of 2026-05, dataset version 1.0, 500 rows) is
one row per instance with these columns::

    repo, instance_id, base_commit, patch, test_patch, problem_statement,
    hints_text, created_at, version, FAIL_TO_PASS, PASS_TO_PASS,
    environment_setup_commit, difficulty

Our ``Task`` wrapper renames ``patch`` → ``expected_patch`` because the word
"patch" on its own is ambiguous in this codebase (we also have model-produced
patches and test patches) and because we want to make it syntactically obvious
in calling code that this field is the *gold* answer the model must not see.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# The "easy" bucket in SWE-bench Verified. Confirmed empirically against the
# dataset: of 500 rows, 194 fall into this bucket, 261 into "15 min - 1 hour",
# 42 into "1-4 hours", 3 into ">4 hours". This is the shortest-fix bucket, i.e.
# the most likely to be solvable in a single pass without long agent loops.
EASY_DIFFICULTY_VALUES: tuple[str, ...] = ("<15 min fix",)

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
DATASET_SPLIT = "test"


@dataclass
class Task:
    """One SWE-bench Verified task wrapped for the hybrid-coding-eval harness.

    ``id`` is namespaced (``"swebench-verified/<instance_id>"``) so tasks from
    different upstream sources can share a registry without colliding.
    """

    id: str
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    test_patch: str
    expected_patch: str
    hints_text: str
    category: str = "B"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-serialisable view (for ``tasks.jsonl``)."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "Task":
        """Construct a ``Task`` from one upstream dataset row."""
        instance_id = row["instance_id"]
        return cls(
            id=f"swebench-verified/{instance_id}",
            instance_id=instance_id,
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
            test_patch=row["test_patch"],
            expected_patch=row["patch"],
            hints_text=row.get("hints_text") or "",
            category="B",
            metadata={
                "difficulty": row.get("difficulty"),
                "created_at": row.get("created_at"),
                "version": row.get("version"),
                "environment_setup_commit": row.get("environment_setup_commit"),
                "FAIL_TO_PASS": row.get("FAIL_TO_PASS"),
                "PASS_TO_PASS": row.get("PASS_TO_PASS"),
                "source": "swebench-verified",
                "dataset": DATASET_NAME,
                "split": DATASET_SPLIT,
            },
        )


def _tasks_jsonl_path() -> Path:
    return Path(__file__).with_name("tasks.jsonl")


def _load_from_pinned_jsonl() -> list[Task] | None:
    """If ``tasks.jsonl`` exists, load pinned tasks from it (no HF download)."""
    path = _tasks_jsonl_path()
    if not path.exists():
        return None
    tasks: list[Task] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        tasks.append(
            Task(
                id=row["id"],
                instance_id=row["instance_id"],
                repo=row["repo"],
                base_commit=row["base_commit"],
                problem_statement=row["problem_statement"],
                test_patch=row["test_patch"],
                expected_patch=row["expected_patch"],
                hints_text=row.get("hints_text", ""),
                category=row.get("category", "B"),
                metadata=row.get("metadata", {}),
            )
        )
    return tasks


def _load_from_hf(
    n: int,
    seed: int,
    difficulty: str,
    cache_dir: Optional[Path],
) -> list[Task]:
    """Fetch from HuggingFace, filter by difficulty, sample ``n`` with ``seed``."""
    from datasets import load_dataset  # local import so pure-loaders don't need `datasets`

    load_kwargs = {"split": DATASET_SPLIT}
    if cache_dir is not None:
        load_kwargs["cache_dir"] = str(cache_dir)
    ds = load_dataset(DATASET_NAME, **load_kwargs)

    # Resolve difficulty filter. ``difficulty`` is a user-friendly knob; we
    # translate "easy" to the concrete upstream value. Any other value is
    # matched literally against the upstream ``difficulty`` column so callers
    # can pick any bucket directly.
    if difficulty == "easy":
        allowed = set(EASY_DIFFICULTY_VALUES)
    else:
        allowed = {difficulty}

    filtered = [row for row in ds if row.get("difficulty") in allowed]
    if not filtered:
        raise ValueError(
            f"No SWE-bench Verified rows match difficulty={difficulty!r}. "
            f"Available: {sorted({r.get('difficulty') for r in ds})}"
        )

    # Deterministic shuffle + take.
    # Sort by instance_id first so the order we sample from is insensitive
    # to HF's row-order changes between dataset revisions.
    filtered.sort(key=lambda r: r["instance_id"])
    rng = random.Random(seed)
    rng.shuffle(filtered)
    picked = filtered[:n]

    return [Task.from_row(row) for row in picked]


def load_tasks(
    n: int = 10,
    seed: int = 42,
    difficulty: str = "easy",
    cache_dir: Path | None = None,
) -> list[Task]:
    """Load ``n`` SWE-bench Verified tasks, seeded.

    Strategy:

    1. If ``benchmark/swebench_verified/tasks.jsonl`` exists with at least ``n``
       pinned tasks of the requested difficulty, use that (zero-network).
    2. Otherwise, download the dataset from HuggingFace, filter by difficulty,
       sample ``n`` with ``seed``.

    The pinned JSONL is the source of truth for the committed benchmark; the
    HF download is a bootstrapping fallback used to *generate* the JSONL in the
    first place.
    """
    pinned = _load_from_pinned_jsonl()
    if pinned is not None:
        matching = [
            t
            for t in pinned
            if (difficulty == "easy" and t.metadata.get("difficulty") in EASY_DIFFICULTY_VALUES)
            or t.metadata.get("difficulty") == difficulty
        ]
        if len(matching) >= n:
            # Sort pinned by instance_id then take deterministically. We do not
            # re-shuffle pinned tasks — the pin IS the sample.
            matching.sort(key=lambda t: t.instance_id)
            # But still honour seed for sub-selection stability: shuffle with
            # seed and take n, so callers asking for smaller n get a stable
            # prefix.
            rng = random.Random(seed)
            matching_shuffled = list(matching)
            rng.shuffle(matching_shuffled)
            return matching_shuffled[:n]

    return _load_from_hf(n=n, seed=seed, difficulty=difficulty, cache_dir=cache_dir)


def write_tasks_jsonl(tasks: list[Task], path: Path | None = None) -> Path:
    """Write ``tasks`` to ``tasks.jsonl`` (one JSON object per line)."""
    out = path or _tasks_jsonl_path()
    lines = [json.dumps(t.to_dict(), sort_keys=True) for t in tasks]
    out.write_text("\n".join(lines) + "\n")
    return out
