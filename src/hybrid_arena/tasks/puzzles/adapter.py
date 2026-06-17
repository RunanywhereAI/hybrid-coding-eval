"""Exercism Python adapter — polyglot-style puzzle tasks for the agents.

Reads task subdirectories from ``fixtures/``. Each task dir has:
  - ``<slug>.py``         — the stub the model edits in place
  - ``<slug>_test.py``    — the test file used to score
  - ``.docs/instructions.md`` — the natural-language prompt
  - ``.meta/example.py``  — the reference solution (used only for verification)

The 5 selected tasks are picked from the Aider polyglot-benchmark Python
slice. They are small (~30-100 LOC stubs), well-known Exercism exercises
with deterministic tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures"

# Five tasks from the polyglot-benchmark Python slice. Chosen for: small
# size, deterministic tests, well-known canonical solutions, all under
# 100 LOC of stub+test together. Easy enough that even a 24B local model
# has a fighting chance, hard enough that always-cloud doesn't just win
# trivially.
DEFAULT_TASK_SLUGS: tuple[str, ...] = (
    "grep",
    "list-ops",
    "phone-number",
    "robot-name",
    "pig-latin",
)


@dataclass
class Task:
    """One Exercism Python task."""

    id: str
    category: str  # "A" — single-file functional shape (consistent w/ HumanEval+)
    slug: str
    prompt: str
    stub_path: Path
    test_path: Path
    fixture_dir: Path
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "slug": self.slug,
            "stub_path": str(self.stub_path),
            "test_path": str(self.test_path),
            "fixture_dir": str(self.fixture_dir),
        }


def _read_prompt(task_dir: Path) -> str:
    """Concatenate any instructions in ``.docs/``."""
    docs = task_dir / ".docs"
    if not docs.is_dir():
        return f"Implement the function(s) in {task_dir.name}.py to pass {task_dir.name}_test.py."
    parts: list[str] = []
    # canonical order: instructions, then any append, then examples
    for fname in ("introduction.md", "instructions.md", "instructions.append.md"):
        p = docs / fname
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts) if parts else f"Implement {task_dir.name}.py."


def load_tasks(slugs: Optional[list[str]] = None) -> list[Task]:
    """Load Exercism Python tasks.

    Parameters
    ----------
    slugs
        If given, load exactly these task slugs in this order. Default:
        :data:`DEFAULT_TASK_SLUGS`.

    Returns
    -------
    list[Task]
        Sorted in the order given by ``slugs``. Missing slugs are silently
        skipped (with a logger warning would be added if anyone cared) —
        the orchestrator will just see a shorter list.
    """
    use = list(slugs) if slugs else list(DEFAULT_TASK_SLUGS)
    out: list[Task] = []
    for slug in use:
        task_dir = _FIXTURES / slug
        if not task_dir.is_dir():
            continue
        # Normalise slug → snake_case for stub/test file lookup.
        # polyglot uses kebab-case for dir, snake_case for files (e.g.
        # "list-ops" → "list_ops.py").
        snake = slug.replace("-", "_")
        candidates_stub = [task_dir / f"{snake}.py", task_dir / f"{slug}.py"]
        candidates_test = [task_dir / f"{snake}_test.py", task_dir / f"{slug}_test.py"]
        stub = next((c for c in candidates_stub if c.is_file()), None)
        test = next((c for c in candidates_test if c.is_file()), None)
        if stub is None or test is None:
            continue
        prompt = _read_prompt(task_dir)
        out.append(
            Task(
                id=f"exercism-python/{slug}",
                category="puzzles",
                slug=slug,
                prompt=prompt,
                stub_path=stub,
                test_path=test,
                fixture_dir=task_dir,
            )
        )
    return out
