#!/usr/bin/env python3
"""Re-judge custom-arch rows with Claude Opus 4.7 (bias-clean cross-vendor).

Variant of ``bin/judge-custom-arch.py`` that hardcodes the judge model
to ``claude-opus-4-7`` and requires ``ANTHROPIC_API_KEY`` — no silent
fallback to gpt-5. Outputs to ``judge.jsonl`` (overwriting any prior
verdicts) and updates the ``quality`` field on custom-arch rows in
``raw.jsonl`` in place.

Usage:
    ./bin/rejudge-custom-arch.py results/full-sweep-v2
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / 'pyproject.toml').is_file():
        HERE = _p
        break
else:  # pragma: no cover
    HERE = _here.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'src'))

# Load repo-root .env so ANTHROPIC_API_KEY is populated before the scorer runs.
_env = HERE / ".env"
if _env.is_file():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

if "ANTHROPIC_API_KEY" not in os.environ:
    print("ERROR: ANTHROPIC_API_KEY not set. This script requires the real "
          "cross-vendor judge; it does not fall back to gpt-5.", file=sys.stderr)
    sys.exit(2)

from benchmark.custom_arch import adapter as custom_arch_adapter  # noqa: E402
from hybrid_coding_eval.core.experiment import _read_output_text  # noqa: E402
from hybrid_coding_eval.core.metrics import Quality, ResultRow, TokenUsage, Latency, Routing  # noqa: E402
from scorers import llm_judge  # noqa: E402

JUDGE_MODEL = "claude-opus-4-7"


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
    judge_log = results_dir / "judge.jsonl"
    if not raw.exists():
        print(f"no such file: {raw}", file=sys.stderr)
        sys.exit(1)

    tasks = {t.id: t for t in custom_arch_adapter.load_tasks()}
    rows = [json.loads(l) for l in raw.open()]
    by_task: dict[str, dict[str, dict]] = {}
    for r in rows:
        tid = r["task_id"]
        if not tid.startswith("custom-arch/"):
            continue
        if r.get("error"):
            continue
        by_task.setdefault(tid, {})[r["route"]] = r

    pairs = [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]
    judge_records: list[dict[str, Any]] = []
    accum: dict[tuple[str, str], list[tuple[float, float]]] = {}
    empty_rows: set[tuple[str, str]] = set()

    for tid, routes in by_task.items():
        task = tasks.get(tid)
        if not task:
            print(f"[rejudge] task {tid} not found, skip")
            continue
        for a, b in pairs:
            row_a = routes.get(a)
            row_b = routes.get(b)
            if not row_a or not row_b:
                continue
            out_a = _read_output_text(_row_from_dict(row_a))
            out_b = _read_output_text(_row_from_dict(row_b))
            a_empty = not out_a.strip()
            b_empty = not out_b.strip()
            if a_empty and b_empty:
                print(f"[rejudge] {tid} {a} vs {b}: BOTH empty — tie (0)")
                empty_rows.add((tid, a))
                empty_rows.add((tid, b))
                judge_records.append({
                    "task_id": tid, "pair": f"{a}_vs_{b}",
                    "route_a": a, "route_b": b,
                    "winner": "tie", "margin": 0.0,
                    "a_score": 0.0, "b_score": 0.0,
                    "reasoning": "both outputs empty",
                    "judge_model": "auto-empty",
                })
                continue
            if a_empty:
                print(f"[rejudge] {tid} {a} vs {b}: {a} empty, auto-B wins")
                empty_rows.add((tid, a))
                accum.setdefault((tid, b), []).append((1.0, 0.5))
                judge_records.append({
                    "task_id": tid, "pair": f"{a}_vs_{b}",
                    "route_a": a, "route_b": b,
                    "winner": "B", "margin": 1.0,
                    "a_score": 0.0, "b_score": 3.0,
                    "reasoning": f"{a} empty; {b} has content",
                    "judge_model": "auto-empty",
                })
                continue
            if b_empty:
                print(f"[rejudge] {tid} {a} vs {b}: {b} empty, auto-A wins")
                empty_rows.add((tid, b))
                accum.setdefault((tid, a), []).append((1.0, 0.5))
                judge_records.append({
                    "task_id": tid, "pair": f"{a}_vs_{b}",
                    "route_a": a, "route_b": b,
                    "winner": "A", "margin": 1.0,
                    "a_score": 3.0, "b_score": 0.0,
                    "reasoning": f"{a} has content; {b} empty",
                    "judge_model": "auto-empty",
                })
                continue
            print(f"[rejudge] {tid}: {a} vs {b} (Opus) ...", flush=True)
            try:
                result = llm_judge.judge_pairwise(
                    task, out_a, out_b, judge_model=JUDGE_MODEL, max_tokens=4000,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  error: {exc!r}")
                continue
            print(
                f"  winner={result.winner} margin={result.margin:.2f} "
                f"A={result.a_score:.2f} B={result.b_score:.2f}"
            )
            q_a = llm_judge.judge_to_quality(result, side="A")
            q_b = llm_judge.judge_to_quality(result, side="B")
            accum.setdefault((tid, a), []).append((q_a.judge_win_rate, q_a.composite))
            accum.setdefault((tid, b), []).append((q_b.judge_win_rate, q_b.composite))
            judge_records.append({
                "task_id": tid, "pair": f"{a}_vs_{b}",
                "route_a": a, "route_b": b,
                "winner": result.winner,
                "margin": result.margin,
                "a_score": result.a_score,
                "b_score": result.b_score,
                "a_dimensions": result.a_dimensions,
                "b_dimensions": result.b_dimensions,
                "reasoning": result.reasoning,
                "judge_model": result.judge_model,
            })

    with judge_log.open("w") as f:
        for rec in judge_records:
            f.write(json.dumps(rec) + "\n")
    print(f"[rejudge] wrote {len(judge_records)} pairings to {judge_log}")

    # Update custom-arch rows
    updated = 0
    for r in rows:
        tid = r["task_id"]
        if not tid.startswith("custom-arch/"):
            continue
        key = (tid, r["route"])
        samples = accum.get(key, [])
        if key in empty_rows and not samples:
            r["quality"] = {
                "functional_pass": False,
                "tests_passed": 0,
                "tests_total": None,
                "judge_win_rate": 0.0,
                "composite": 0.0,
            }
            updated += 1
            continue
        if not samples:
            continue
        win_rate = sum(s[0] for s in samples) / len(samples)
        composite = sum(s[1] for s in samples) / len(samples)
        if key in empty_rows:
            composite = 0.0
            win_rate = 0.0
        r["quality"] = {
            "functional_pass": None,
            "tests_passed": None,
            "tests_total": None,
            "judge_win_rate": win_rate,
            "composite": composite,
        }
        updated += 1

    tmp = raw.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(raw)
    print(f"[rejudge] updated {updated} rows in {raw}")


def cli_main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    results_dir = Path(argv[0]) if argv else Path("results/full-sweep-v2")
    main(results_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
