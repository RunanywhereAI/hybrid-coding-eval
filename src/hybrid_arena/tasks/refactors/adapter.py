"""``refactors`` task adapter — real-developer Python refactor tasks.

Tasks representing what a real developer hands their coding agent on a
normal weekday. Tasks are partitioned across six *shapes*:

- **D1** — feature add (small new endpoint / handler / utility).
- **D2** — bug fix (reproducer + patch).
- **D3** — refactor / extract (move code; behaviour preserved).
- **D4** — PR review (given a diff, produce a critique).
- **D5** — script / one-shot (data-munging / CLI glue).
- **D6** — hard implementation challenge (v1.5; calibrated to stress 30B local models).

D1, D5, D6 are scored functionally (pytest against a fixture overlay).
D3 and D4 are scored by an LLM-judge against a 5-dimension rubric. D2
is retained for reference but not in the canonical sweep.

The adapter is deliberately dumb: read ``tasks.jsonl``, parse each line
into a :class:`Task`, return the list. Prompt assembly (inlining
fixture files) happens in :func:`task_prompt`.

JSONL row shape
---------------

Every row is a single JSON object on one line. The required keys are
``id``, ``shape``, and ``prompt``. All other fields are optional and
vary by shape.

.. code-block:: jsonc

    // --- D1 (feature add) ---
    {
      "id":             "real-dev/d1-rate-limit",
      "shape":          "D1",                      // D1 | D2 | D3 | D4 | D5
      "prompt":         "Add a sliding-window rate-limit decorator...",
      "fixtures_dir":   "d1-rate-limit",           // relative to fixtures/
      "tests":          "d1-rate-limit/test_rate_limit.py",
      "source_url":     "https://github.com/...",
      "source_license": "MIT"
    }

    // --- D2 (bug fix) — same as D1 but prompt describes the reproducer ---
    {"id":"real-dev/d2-utf8-roundtrip","shape":"D2","prompt":"...","fixtures_dir":"d2-utf8-roundtrip","tests":"d2-utf8-roundtrip/test_roundtrip.py","source_url":"...","source_license":"Apache-2.0"}

    // --- D3 (refactor / extract) — judge-scored; carries a rubric, no tests ---
    {
      "id":           "real-dev/d3-extract-util",
      "shape":        "D3",
      "prompt":       "Extract the argument-parsing block into a helper...",
      "fixtures_dir": "d3-extract-util",
      "rubric": {
        "correctness":     "Behaviour is preserved; all existing call-sites still typecheck.",
        "completeness":    "Every duplicate block is replaced by the extracted helper.",
        "style":           "Extraction is idiomatic; helper name/signature fits the codebase conventions.",
        "reasoning_depth": "Justifies the shape of the helper (single vs multi-return, where the imports live).",
        "practicality":    "A reviewer would merge this without further changes."
      },
      "source_url":     "https://github.com/..."
    }

    // --- D4 (PR review) — diff lives under fixtures_dir; judge-scored ---
    {"id":"real-dev/d4-review-auth","shape":"D4","prompt":"Review this PR...","fixtures_dir":"d4-review-auth","rubric":{"correctness":"...","completeness":"..."},"source_url":"..."}

    // --- D5 (script / one-shot) — input fixture inlined into the prompt ---
    {"id":"real-dev/d5-csv-to-json","shape":"D5","prompt":"Write a script that...","fixtures_dir":"d5-csv-to-json","tests":"d5-csv-to-json/test_csv.py","source_url":"..."}

Fixture layout
--------------

Each task with a ``fixtures_dir`` has a directory under ``fixtures/``
named accordingly. For functional shapes (D1, D2, D5) the directory
also holds the pytest/jest file referenced by ``tests``. For D3 and
D4 the directory holds the "before" state (D3) or the PR diff (D4)
that :func:`task_prompt` inlines into the prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TASKS_PATH = Path(__file__).resolve().parent / "tasks.jsonl"
_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"

_VALID_SHAPES = ("D1", "D2", "D3", "D4", "D5", "D6")


@dataclass(frozen=True)
class Task:
    """A single refactors task.

    Fields
    ------
    id
        Slug of the form ``real-dev/<shape-slug>`` — unique across the set.
    category
        Always ``"refactors"`` for this adapter.
    shape
        One of ``D1`` | ``D2`` | ``D3`` | ``D4`` | ``D5`` | ``D6``.
        D1/D5 are the v1.4 canonical small-feature / one-shot script tasks.
        D2 (bug-fix-from-stacktrace) and D3/D4 (refactor / review) are
        retained but not in the canonical sweep — see ``scorers.py``.
        D6 (v1.5) is the **hard-refactor** task class: single-file
        implementation challenges with comprehensive pytest suites
        deliberately calibrated to stress 30B local models.
    prompt
        The natural-language instruction, without inlined fixtures.
        Use :func:`task_prompt` to get the version sent to the model.
    fixtures_dir
        Directory under ``real_dev/fixtures/`` containing any files the
        task depends on (test file, "before" state, diff, etc.).
        Relative path (e.g. ``"d1-rate-limit"``). ``None`` if the task
        has no fixtures.
    tests
        Relative path (under ``fixtures/``) to the pytest/jest file used
        to score functional shapes (D1, D2, D5). ``None`` for D3, D4.
    rubric
        The 5-dimension rubric for judge-scored shapes (D3, D4). ``None``
        for functional shapes. Keys match the custom_arch rubric:
        ``correctness`` / ``completeness`` / ``style`` / ``reasoning_depth``
        / ``practicality``.
    source_url
        Link to the upstream source (issue, PR, gist) the task was
        adapted from. ``None`` for synthetic tasks.
    source_license
        SPDX license identifier for the upstream source, when known.
    """

    id: str
    shape: str
    prompt: str
    category: str = "refactors"
    fixtures_dir: str | None = None
    tests: str | None = None
    rubric: dict[str, str] | None = None
    source_url: str | None = None
    source_license: str | None = None


def _parse_task(raw: dict[str, Any]) -> Task:
    if "id" not in raw:
        raise ValueError("task row missing required field 'id'")
    if "shape" not in raw:
        raise ValueError(f"{raw.get('id')}: row missing required field 'shape'")
    if "prompt" not in raw:
        raise ValueError(f"{raw.get('id')}: row missing required field 'prompt'")
    shape = raw["shape"]
    if shape not in _VALID_SHAPES:
        raise ValueError(
            f"{raw.get('id')}: shape must be one of {_VALID_SHAPES}, got {shape!r}"
        )
    rubric = raw.get("rubric")
    if rubric is not None and not isinstance(rubric, dict):
        raise ValueError(f"{raw.get('id')}: rubric must be an object or null")
    return Task(
        id=raw["id"],
        category="refactors",
        shape=shape,
        prompt=raw["prompt"],
        fixtures_dir=raw.get("fixtures_dir"),
        tests=raw.get("tests"),
        rubric=rubric,
        source_url=raw.get("source_url"),
        source_license=raw.get("source_license"),
    )


def load_tasks(
    n: int | None = None,
    seed: int = 42,
    path: Path | None = None,
) -> list[Task]:
    """Load refactor tasks from ``tasks.jsonl``.

    Parameters
    ----------
    n
        If given, cap to the first ``n`` tasks (in file order). ``None``
        returns the whole file.
    seed
        Unused — the adapter does not sample. Kept in the signature to
        match ``humaneval_plus`` / ``swebench_verified`` / friends.
    path
        Override for the JSONL path. Mostly useful in tests.

    Returns
    -------
    list[Task]
        The parsed tasks. An empty file yields an empty list.
    """
    del seed  # reserved for future sampling; see docstring.
    tasks_path = path if path is not None else _TASKS_PATH

    out: list[Task] = []
    if not tasks_path.exists():
        return out

    with tasks_path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{tasks_path}:{lineno}: invalid JSON ({exc})"
                ) from exc
            out.append(_parse_task(raw))
    if n is not None:
        out = out[:n]
    return out


def _read_fixture_files(fixtures_dir: Path) -> list[tuple[str, str]]:
    """Return ``[(relative_name, contents), ...]`` for every regular file
    under ``fixtures_dir``, recursively and in sorted order. Used by
    :func:`task_prompt` to inline fixture snippets into the prompt.
    """
    if not fixtures_dir.exists() or not fixtures_dir.is_dir():
        return []
    files: list[tuple[str, str]] = []
    for child in sorted(fixtures_dir.rglob("*")):
        if not child.is_file():
            continue
        if child.name == ".gitkeep":
            continue
        try:
            contents = child.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # Skip binary or unreadable files; they shouldn't appear in
            # real_dev fixtures, but don't crash the prompt builder.
            continue
        rel = child.relative_to(fixtures_dir).as_posix()
        files.append((rel, contents))
    return files


def task_prompt(task: Task, *, fixtures_root: Path | None = None) -> str:
    """Return the full prompt sent to the model for ``task``.

    Inlines fixture-file contents based on the task's shape:

    - **D1 / D2** — appends every file under ``fixtures_dir`` (this
      usually includes the pytest file so the model sees the contract).
    - **D3** — appends every file under ``fixtures_dir`` as the
      "before" state to refactor.
    - **D4** — appends every file under ``fixtures_dir``; by convention
      this directory contains the PR diff the reviewer must critique.
    - **D5** — appends every file under ``fixtures_dir`` as inline
      input fixtures for the one-shot script.

    Tasks with no ``fixtures_dir`` get the plain ``task.prompt``.
    """
    if not task.fixtures_dir:
        return task.prompt

    root = fixtures_root if fixtures_root is not None else _FIXTURES_ROOT
    fixtures_dir = root / task.fixtures_dir
    files = _read_fixture_files(fixtures_dir)
    if not files:
        return task.prompt

    if task.shape in ("D1", "D2"):
        header = "\n\n---\n\nAttached files:"
    elif task.shape == "D3":
        header = "\n\n---\n\nBefore (refactor this):"
    elif task.shape == "D4":
        header = "\n\n---\n\nPR diff to review:"
    elif task.shape == "D5":
        header = "\n\n---\n\nInput fixtures:"
    else:  # pragma: no cover — guarded by _VALID_SHAPES in _parse_task
        header = "\n\n---\n\nAttached files:"

    parts: list[str] = [task.prompt, header]
    for rel, contents in files:
        parts.append(f"\n### {rel}\n```\n{contents}\n```")
    return "".join(parts)


__all__ = ["Task", "load_tasks", "task_prompt"]
