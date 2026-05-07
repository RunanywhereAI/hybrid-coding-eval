#!/usr/bin/env python3
"""Re-score SWE-bench rows whose `quality.functional_pass` is None.

Writes results back to raw.jsonl in-place (atomic rewrite).

Usage:
    ./bin/rescore-swebench.py results/full-sweep
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / 'pyproject.toml').is_file():
        HERE = _p
        break
else:  # pragma: no cover
    HERE = _here.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'src'))

from benchmark.swebench_verified import adapter as swebench_adapter  # noqa: E402
from hybrid_coding_eval.core.experiment import _read_output_text  # noqa: E402
from hybrid_coding_eval.core.metrics import ResultRow, TokenUsage, Latency, Quality, Routing  # noqa: E402
from scorers import swebench as swebench_scorer  # noqa: E402


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


def main(results_dir: Path) -> None:
    raw = results_dir / "raw.jsonl"
    if not raw.exists():
        print(f"no such file: {raw}", file=sys.stderr)
        sys.exit(1)

    # Load all tasks so we can resolve a task by id.
    tasks = {t.id: t for t in swebench_adapter.load_tasks(n=10, seed=42)}

    rows = [json.loads(l) for l in raw.open()]
    targets = [
        (i, r)
        for i, r in enumerate(rows)
        if r["task_id"].startswith("swebench-verified/")
        and (r.get("quality") or {}).get("functional_pass") is None
        and not r.get("error")
    ]

    print(f"[rescore] {len(targets)} SWE-bench rows to re-grade")
    updated = 0
    for idx, (i, r) in enumerate(targets, 1):
        tid = r["task_id"]
        task = tasks.get(tid)
        if not task:
            print(f"  [{idx}/{len(targets)}] {tid} {r['route']}: task not in 10-sample, skip")
            continue
        row = _row_from_dict(r)
        text = _read_output_text(row)
        if not text:
            print(f"  [{idx}/{len(targets)}] {tid} {r['route']}: no output text, marking fail")
            q = Quality(functional_pass=False, tests_passed=0, tests_total=1, composite=0.0)
        else:
            print(f"  [{idx}/{len(targets)}] {tid} {r['route']}: grading ({len(text)} chars)...", flush=True)
            try:
                q = swebench_scorer.score(task, text, timeout_s=900)
            except Exception as exc:  # noqa: BLE001
                print(f"    error: {exc!r}")
                continue
        print(f"    → pass={q.functional_pass} comp={q.composite}")
        r["quality"] = asdict(q)
        updated += 1

    # Atomic rewrite
    tmp = raw.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(raw)
    print(f"[rescore] updated {updated} rows; wrote {raw}")


def cli_main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    results_dir = Path(argv[0]) if argv else Path("results/full-sweep")
    main(results_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
