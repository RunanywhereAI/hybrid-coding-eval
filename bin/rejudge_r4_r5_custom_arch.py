#!/usr/bin/env python3
"""Fill in the LLM-judge gap for custom-arch R4 / R5 rows.

The MVP ``bench rejudge`` (and ``bin/rejudge-custom-arch.py``) only pair
R1, R2, R3 against each other — the dispatcher hard-codes
``[("R1","R2"), ("R1","R3"), ("R2","R3")]``. The v3 sweep added two new
hybrid routes (R4 and R5) to category C, so those rows still have
``composite=None`` after rejudge finishes.

This script is a one-shot fix for that gap. It:

1. Reads the v3 sweep's ``raw.jsonl`` and ``judge.jsonl``.
2. For every custom-arch task, judges R3-vs-R4 and R3-vs-R5
   (R3 is the strongest non-R4/R5 hybrid reference in the existing
   judge.jsonl, see the long discussion in P3.2b).
3. Appends the new bias-corrected ``JudgmentResult`` records to
   ``judge.jsonl`` and recomputes the per-route quality aggregate
   exactly like ``rejudge-custom-arch.py`` does, so R4 / R5 rows now
   carry ``judge_win_rate`` and ``composite``.

Existing R1/R2/R3 judgments and quality entries are preserved unchanged.

Usage
-----
    .venv/bin/python bin/rejudge_r4_r5_custom_arch.py results/runs/07-v3-devstral-all-routes
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / "pyproject.toml").is_file():
        HERE = _p
        break
else:  # pragma: no cover
    HERE = _here.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "src"))

# Load repo-root .env so ANTHROPIC_API_KEY is populated before importing the
# scorer (same shape as rejudge-custom-arch.py).
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
    print(
        "ERROR: ANTHROPIC_API_KEY not set. This script requires the real "
        "cross-vendor judge; it does not fall back to gpt-5.",
        file=sys.stderr,
    )
    sys.exit(2)

from hybrid_coding_eval.benchmarks.custom_arch import (
    adapter as custom_arch_adapter,  # noqa: E402
)
from hybrid_coding_eval.core.experiment import _read_output_text  # noqa: E402
from hybrid_coding_eval.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)
from hybrid_coding_eval.scorers import llm_judge  # noqa: E402

JUDGE_MODEL = "claude-opus-4-7"

# Pair R3 against each of the new routes. Keep R3 in the "A" slot so the
# direction is consistent across pairings — bias-correction in
# llm_judge.judge_pairwise already runs both orderings internally.
NEW_PAIRS = [("R3", "R4"), ("R3", "R5")]


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


def _existing_judge_records(judge_log: Path) -> list[dict[str, Any]]:
    if not judge_log.is_file():
        return []
    out: list[dict[str, Any]] = []
    with judge_log.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _seed_accum_from_existing(
    existing: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, str], list[tuple[float, float]]], set[tuple[str, str]]
]:
    """Reconstruct ``accum`` (per-route win-rate / composite samples) from
    the judgments already on disk so we can re-emit the same per-route
    quality for R1 / R2 / R3 untouched by this script.
    """
    accum: dict[tuple[str, str], list[tuple[float, float]]] = {}
    empty_rows: set[tuple[str, str]] = set()
    for rec in existing:
        tid = rec.get("task_id")
        a = rec.get("route_a")
        b = rec.get("route_b")
        if not tid or not a or not b:
            continue
        # Mirror the auto-empty branches used by rejudge-custom-arch:
        # they record concrete scores but their "judge_model" is
        # ``auto-empty``. Treat them the same way here.
        a_score = rec.get("a_score", 0.0)
        b_score = rec.get("b_score", 0.0)
        winner = rec.get("winner", "tie")
        margin = rec.get("margin", 0.0)
        if rec.get("judge_model") == "auto-empty":
            if winner == "tie":
                empty_rows.add((tid, a))
                empty_rows.add((tid, b))
                continue
            if winner == "A":
                empty_rows.add((tid, b))
                accum.setdefault((tid, a), []).append((1.0, 0.5))
                continue
            if winner == "B":
                empty_rows.add((tid, a))
                accum.setdefault((tid, b), []).append((1.0, 0.5))
                continue
        # Real judge verdict — rebuild the per-side samples the same way
        # ``judge_to_quality`` does internally.
        a_composite = max(0.0, min(1.0, a_score / 5.0))
        b_composite = max(0.0, min(1.0, b_score / 5.0))
        if winner == "tie":
            a_win = 0.5
            b_win = 0.5
        elif winner == "A":
            a_win = margin
            b_win = 1.0 - margin
        else:  # "B"
            a_win = 1.0 - margin
            b_win = margin
        accum.setdefault((tid, a), []).append((a_win, a_composite))
        accum.setdefault((tid, b), []).append((b_win, b_composite))
    return accum, empty_rows


def _judge_pair(
    task: Any,
    tid: str,
    a: str,
    b: str,
    row_a: dict,
    row_b: dict,
    accum: dict[tuple[str, str], list[tuple[float, float]]],
    empty_rows: set[tuple[str, str]],
    judge_records: list[dict[str, Any]],
) -> None:
    """Run one bias-corrected pairing and append its record + per-route
    samples to ``accum`` / ``judge_records``. Mirrors the body of the
    main loop in ``rejudge-custom-arch.py``.
    """
    out_a = _read_output_text(_row_from_dict(row_a))
    out_b = _read_output_text(_row_from_dict(row_b))
    a_empty = not out_a.strip()
    b_empty = not out_b.strip()
    if a_empty and b_empty:
        print(f"[rejudge-r4r5] {tid} {a} vs {b}: BOTH empty - tie (0)")
        empty_rows.add((tid, a))
        empty_rows.add((tid, b))
        judge_records.append(
            {
                "task_id": tid,
                "pair": f"{a}_vs_{b}",
                "route_a": a,
                "route_b": b,
                "winner": "tie",
                "margin": 0.0,
                "a_score": 0.0,
                "b_score": 0.0,
                "reasoning": "both outputs empty",
                "judge_model": "auto-empty",
            }
        )
        return
    if a_empty:
        print(f"[rejudge-r4r5] {tid} {a} vs {b}: {a} empty, auto-B wins")
        empty_rows.add((tid, a))
        accum.setdefault((tid, b), []).append((1.0, 0.5))
        judge_records.append(
            {
                "task_id": tid,
                "pair": f"{a}_vs_{b}",
                "route_a": a,
                "route_b": b,
                "winner": "B",
                "margin": 1.0,
                "a_score": 0.0,
                "b_score": 3.0,
                "reasoning": f"{a} empty; {b} has content",
                "judge_model": "auto-empty",
            }
        )
        return
    if b_empty:
        print(f"[rejudge-r4r5] {tid} {a} vs {b}: {b} empty, auto-A wins")
        empty_rows.add((tid, b))
        accum.setdefault((tid, a), []).append((1.0, 0.5))
        judge_records.append(
            {
                "task_id": tid,
                "pair": f"{a}_vs_{b}",
                "route_a": a,
                "route_b": b,
                "winner": "A",
                "margin": 1.0,
                "a_score": 3.0,
                "b_score": 0.0,
                "reasoning": f"{a} has content; {b} empty",
                "judge_model": "auto-empty",
            }
        )
        return

    print(f"[rejudge-r4r5] {tid}: {a} vs {b} (Opus) ...", flush=True)
    try:
        result = llm_judge.judge_pairwise(
            task,
            out_a,
            out_b,
            judge_model=JUDGE_MODEL,
            max_tokens=4000,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  error: {exc!r}")
        return
    print(
        f"  winner={result.winner} margin={result.margin:.2f} "
        f"A={result.a_score:.2f} B={result.b_score:.2f}"
    )
    q_a = llm_judge.judge_to_quality(result, side="A")
    q_b = llm_judge.judge_to_quality(result, side="B")
    accum.setdefault((tid, a), []).append((q_a.judge_win_rate, q_a.composite))
    accum.setdefault((tid, b), []).append((q_b.judge_win_rate, q_b.composite))
    judge_records.append(
        {
            "task_id": tid,
            "pair": f"{a}_vs_{b}",
            "route_a": a,
            "route_b": b,
            "winner": result.winner,
            "margin": result.margin,
            "a_score": result.a_score,
            "b_score": result.b_score,
            "a_dimensions": result.a_dimensions,
            "b_dimensions": result.b_dimensions,
            "reasoning": result.reasoning,
            "judge_model": result.judge_model,
        }
    )


def main(results_dir: Path) -> int:
    raw = results_dir / "raw.jsonl"
    judge_log = results_dir / "judge.jsonl"
    if not raw.exists():
        print(f"no such file: {raw}", file=sys.stderr)
        return 1

    tasks = {t.id: t for t in custom_arch_adapter.load_tasks()}
    rows = [json.loads(l) for l in raw.open()]

    # Group custom-arch rows by task -> route.
    by_task: dict[str, dict[str, dict]] = {}
    for r in rows:
        if not r["task_id"].startswith("custom-arch/"):
            continue
        if r.get("error"):
            continue
        by_task.setdefault(r["task_id"], {})[r["route"]] = r

    # Seed accum / empty_rows from the existing judge.jsonl so R1/R2/R3
    # quality is preserved verbatim. ``existing`` is also kept so we can
    # append (not overwrite) the new pairings to judge.jsonl.
    existing = _existing_judge_records(judge_log)
    accum, empty_rows = _seed_accum_from_existing(existing)
    judge_records: list[dict[str, Any]] = []

    skipped_pairs = {(r["task_id"], r["pair"]) for r in existing}

    for tid, routes in by_task.items():
        task = tasks.get(tid)
        if not task:
            print(f"[rejudge-r4r5] task {tid} not found, skip")
            continue
        for a, b in NEW_PAIRS:
            pair_label = f"{a}_vs_{b}"
            if (tid, pair_label) in skipped_pairs:
                print(
                    f"[rejudge-r4r5] {tid} {pair_label}: already in judge.jsonl, skip"
                )
                continue
            row_a = routes.get(a)
            row_b = routes.get(b)
            if not row_a or not row_b:
                continue
            _judge_pair(
                task=task,
                tid=tid,
                a=a,
                b=b,
                row_a=row_a,
                row_b=row_b,
                accum=accum,
                empty_rows=empty_rows,
                judge_records=judge_records,
            )

    # Append (don't overwrite) the new judgments to judge.jsonl.
    with judge_log.open("a") as f:
        for rec in judge_records:
            f.write(json.dumps(rec) + "\n")
    print(
        f"[rejudge-r4r5] appended {len(judge_records)} new pairings to {judge_log}"
    )

    # Recompute quality for every custom-arch route from the combined
    # samples (old pairings + new pairings). Identical aggregation logic
    # to rejudge-custom-arch.py.
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
    print(f"[rejudge-r4r5] updated {updated} custom-arch rows in {raw}")
    return 0


def cli_main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: rejudge_r4_r5_custom_arch.py RESULTS_DIR", file=sys.stderr)
        return 2
    return main(Path(argv[0]))


if __name__ == "__main__":
    raise SystemExit(cli_main())
