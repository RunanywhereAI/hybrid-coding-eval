#!/usr/bin/env python3
"""Re-score Category-D functional rows (D1 + D5) whose Quality is None.

Why this exists
---------------
The category-D ``real_dev`` scorer (``benchmarks/real_dev/scorers.py``)
runs pytest inside the ``hybrid-eval-python`` Docker sandbox for D1 / D5
shapes. When the Docker daemon dies mid-sweep, the sandbox helper raises
``RuntimeError``, the scorer catches it and returns
``Quality(functional_pass=None, ...)`` so the sweep does not abort and
the failure isn't conflated with a real model miss.

The downside is that every row affected by the outage is left with
``functional_pass=None`` even though the model's output is on disk and
the test fixture is unchanged. This helper re-runs the scorer for those
rows once Docker is back up, mutating ``raw.jsonl`` in place.

It is the real_dev counterpart of ``bin/rescore-swebench.py``.

Usage
-----
    .venv/bin/python bin/rescore_real_dev_functional.py results/runs/07-v3-devstral-all-routes
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / "pyproject.toml").is_file():
        HERE = _p
        break
else:  # pragma: no cover
    HERE = _here.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "src"))

from hybrid_coding_eval.benchmarks.real_dev import adapter as real_dev_adapter  # noqa: E402
from hybrid_coding_eval.benchmarks.real_dev import scorers as real_dev_scorers  # noqa: E402
from hybrid_coding_eval.core.experiment import _read_output_text  # noqa: E402
from hybrid_coding_eval.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)

# Shapes scored functionally via the Docker sandbox. D2 is deliberately
# excluded — it's still stubbed to return all-None Quality until a
# repo-clone + diff harness lands. D3/D4 use the LLM-judge and shouldn't
# be touched by this script.
_FUNCTIONAL_SHAPES = ("D1", "D5")


def _row_from_dict(d: dict) -> ResultRow:
    return ResultRow(
        task_id=d["task_id"],
        category=d["category"],
        route=d["route"],
        hardware_profile_ref=d.get("hardware_profile_ref", ""),
        tokens=TokenUsage(**d.get("tokens", {})),
        latency=Latency(**d.get("latency", {})),
        quality=Quality(**(d.get("quality") or {})),
        routing=Routing(**d.get("routing", {})),
        output_ref=d.get("output_ref", ""),
        error=d.get("error"),
    )


def _shape_matches(task_id: str) -> str | None:
    """Return the D-shape prefix (``D1`` / ``D5``) for ``task_id`` or
    ``None`` if it's not one of the functional shapes we re-score.
    """
    if not task_id.startswith("real-dev/"):
        return None
    if task_id.startswith("real-dev/d1-"):
        return "D1"
    if task_id.startswith("real-dev/d5-"):
        return "D5"
    return None


def main(results_dir: Path) -> int:
    raw = results_dir / "raw.jsonl"
    if not raw.exists():
        print(f"no such file: {raw}", file=sys.stderr)
        return 1

    # Load the full task set once; the adapter is cheap (just a JSONL parse).
    tasks = {t.id: t for t in real_dev_adapter.load_tasks()}

    rows = [json.loads(l) for l in raw.open()]
    targets: list[tuple[int, dict, str]] = []
    for i, r in enumerate(rows):
        shape = _shape_matches(r["task_id"])
        if shape is None:
            continue
        if r.get("error"):
            # Real infrastructure error — leave alone.
            continue
        q = r.get("quality") or {}
        if q.get("functional_pass") is not None:
            # Already scored, skip.
            continue
        targets.append((i, r, shape))

    print(f"[rescore-real-dev] {len(targets)} rows to re-grade (D1/D5)")
    updated = 0
    for idx, (i, r, shape) in enumerate(targets, 1):
        tid = r["task_id"]
        task = tasks.get(tid)
        if not task:
            print(f"  [{idx}/{len(targets)}] {tid} {r['route']}: task not in adapter, skip")
            continue
        row = _row_from_dict(r)
        text = _read_output_text(row)
        if not text:
            print(f"  [{idx}/{len(targets)}] {tid} {r['route']}: no output text on disk, marking fail")
            q = Quality(
                functional_pass=False,
                tests_passed=0,
                tests_total=1,
                composite=0.0,
            )
        else:
            print(
                f"  [{idx}/{len(targets)}] {tid} {r['route']} ({shape}): grading "
                f"({len(text)} chars)...",
                flush=True,
            )
            try:
                q = real_dev_scorers.score(task, text, context={})
            except Exception as exc:  # noqa: BLE001
                print(f"    error: {exc!r}")
                continue
        print(
            f"    -> pass={q.functional_pass} "
            f"tests={q.tests_passed}/{q.tests_total} comp={q.composite}"
        )
        r["quality"] = asdict(q)
        updated += 1

    # Atomic rewrite.
    tmp = raw.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(raw)
    print(f"[rescore-real-dev] updated {updated} rows; wrote {raw}")
    return 0


def cli_main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: rescore_real_dev_functional.py RESULTS_DIR", file=sys.stderr)
        return 2
    return main(Path(argv[0]))


if __name__ == "__main__":
    raise SystemExit(cli_main())
