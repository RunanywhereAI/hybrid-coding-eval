"""T-14: judge robustness — triple-judge × 2-order replay on custom_arch.

Re-judges the custom_arch pairings from ``results/runs/02-v2-qwen-fixed-synth/``
with three judges (Opus, Sonnet, gpt-5.5) × two orderings (A-vs-B and
B-vs-A) = 6 verdicts per pairing. Writes aggregated stats to
``results/reprice/judge_robustness.md`` and raw verdicts to
``results/runs/10-judge-robust/judge.jsonl``.

**No new inference beyond the judge calls.** The R1 / R3 outputs under
``results/runs/02-v2-qwen-fixed-synth/outputs/`` are re-used as-is.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from hybrid_coding_eval.core.paths import repo_root

JUDGES = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "gpt-5.5",
]


def _load_prior_verdicts(src_judge: Path) -> dict[str, list[dict]]:
    """Return task_id → list of historical judge records from the
    source run (02-v2-qwen-fixed-synth).
    """
    out: dict[str, list[dict]] = defaultdict(list)
    if not src_judge.is_file():
        return out
    for line in src_judge.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[rec["task_id"]].append(rec)
    return out


def _maybe_call_judge(
    task,
    out_a: str,
    out_b: str,
    judge_model: str,
) -> dict | None:
    """Delegate to ``scorers.llm_judge`` if the SDK supports the model."""
    from hybrid_coding_eval.scorers import llm_judge

    try:
        result = llm_judge.judge_pairwise(
            task, out_a, out_b, judge_model=judge_model, max_tokens=4000
        )
    except Exception as exc:  # pragma: no cover — defensive
        return {"error": f"judge call failed: {exc!r}"}
    return {
        "winner": result.winner,
        "margin": result.margin,
        "a_score": result.a_score,
        "b_score": result.b_score,
        "reasoning": result.reasoning,
        "judge_model": result.judge_model,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="judge_robustness")
    parser.add_argument(
        "--source-run",
        default="02-v2-qwen-fixed-synth",
        help="Name of the source run dir under results/runs/.",
    )
    parser.add_argument(
        "--target-run",
        default="10-judge-robust",
        help="Where to write the new judge.jsonl (under results/runs/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without calling any judge API.",
    )
    args = parser.parse_args(argv or sys.argv[1:])

    root = repo_root()
    src_dir = root / "results" / "runs" / args.source_run
    tgt_dir = root / "results" / "runs" / args.target_run
    reprice_dir = root / "results" / "reprice"
    reprice_dir.mkdir(parents=True, exist_ok=True)

    if not src_dir.is_dir():
        print(f"source run not found: {src_dir}", file=sys.stderr)
        return 2

    source_judge = src_dir / "judge.jsonl"
    prior = _load_prior_verdicts(source_judge)
    if not prior:
        print(f"no prior judge records in {source_judge}", file=sys.stderr)
        return 2

    # Figure out which tasks had pairings and load their outputs.
    from hybrid_coding_eval.benchmarks.custom_arch.adapter import load_tasks

    tasks_by_id = {t.id: t for t in load_tasks()}

    src_outputs = src_dir / "outputs"

    def _route_output_path(base: Path, tid: str, route: str) -> Path | None:
        """R3 outputs use .r3.answer.txt; R1/R2/R4/R5 use _R<n>.txt."""
        slug = tid.replace("/", "__")
        if route == "R3":
            p = base / f"{slug}.r3.answer.txt"
            return p if p.is_file() else None
        p = base / f"{slug}_{route}.txt"
        return p if p.is_file() else None

    # Collect (task, out_a, out_b, pair_label) tuples. Only custom-arch
    # pairings (prose deliverables) — bigcodebench pairs in the same
    # judge.jsonl are functional tasks and should be scored by the
    # pytest harness, not re-judged.
    pairings: list[tuple] = []
    for tid, recs in prior.items():
        if not tid.startswith("custom-arch/"):
            continue
        task = tasks_by_id.get(tid)
        if task is None:
            continue
        # One pairing per unique (route_a, route_b); Opus may have
        # recorded two (A/B swap). Collapse to the canonical A=R1 pair.
        seen: set[tuple[str, str]] = set()
        for rec in recs:
            pair = (rec.get("route_a", "R1"), rec.get("route_b", "R3"))
            if pair in seen:
                continue
            seen.add(pair)
            out_a_path = _route_output_path(src_outputs, tid, pair[0])
            out_b_path = _route_output_path(src_outputs, tid, pair[1])
            if out_a_path is None or out_b_path is None:
                continue
            pairings.append(
                (
                    task,
                    out_a_path.read_text(encoding="utf-8"),
                    out_b_path.read_text(encoding="utf-8"),
                    pair,
                )
            )

    print(
        f"[judge_robustness] {len(pairings)} pairings × {len(JUDGES)} judges × 2 orders "
        f"= {len(pairings) * len(JUDGES) * 2} calls"
    )
    if args.dry_run:
        return 0

    # Before we call any API, make sure we can.
    missing_keys = []
    if any(j.startswith("claude") for j in JUDGES) and not os.environ.get("ANTHROPIC_API_KEY"):
        missing_keys.append("ANTHROPIC_API_KEY")
    if any(j.startswith("gpt") for j in JUDGES) and not (
        os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")
    ):
        missing_keys.append("OPENAI_API_KEY")
    if missing_keys:
        print(
            f"missing required API keys: {missing_keys}. Set them in .env and retry.",
            file=sys.stderr,
        )
        return 2

    tgt_dir.mkdir(parents=True, exist_ok=True)
    out_judge = tgt_dir / "judge.jsonl"

    records: list[dict] = []
    for task, out_a, out_b, (route_a, route_b) in pairings:
        for judge in JUDGES:
            for order in ("AB", "BA"):
                a, b = (out_a, out_b) if order == "AB" else (out_b, out_a)
                verdict = _maybe_call_judge(task, a, b, judge) or {}
                rec = {
                    "task_id": task.id,
                    "pair": f"{route_a}_vs_{route_b}",
                    "route_a": route_a,
                    "route_b": route_b,
                    "order": order,
                    "judge_model": judge,
                    **verdict,
                }
                records.append(rec)
                print(
                    f"[judge_robustness] {task.id} judge={judge} order={order} "
                    f"winner={rec.get('winner', '?')}"
                )

    out_judge.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    print(f"wrote {out_judge} ({len(records)} verdicts)")

    # Aggregate.
    md = _render_summary(records)
    md_path = reprice_dir / "judge_robustness.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"wrote {md_path}")
    return 0


def _render_summary(records: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Judge-robustness audit (T-14)")
    lines.append("")
    lines.append(
        "Triple-judge × 2-order replay of the custom_arch pairings that "
        "the MVP report's Category C finding was load-bearing on."
    )
    lines.append("")
    lines.append(f"Total verdicts: **{len(records)}**.")
    lines.append("")

    # Group by (task_id, pair). For each group, does the winner agree
    # across judges and orders?
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        grouped[(r["task_id"], r["pair"])].append(r)

    lines.append("| task | pair | unanimous? | majority | order-swap flips |")
    lines.append("|---|---|:-:|---|---:|")
    for (tid, pair), group in sorted(grouped.items()):
        winners = [r.get("winner") for r in group]
        unanimous = len(set(winners)) == 1
        from collections import Counter
        counter = Counter(winners)
        majority = counter.most_common(1)[0][0]

        # Compare AB vs BA per judge.
        flips = 0
        by_judge: dict[str, dict[str, str]] = defaultdict(dict)
        for r in group:
            by_judge[r["judge_model"]][r.get("order", "?")] = r.get("winner") or "?"
        for judge, orders in by_judge.items():
            if "AB" in orders and "BA" in orders and orders["AB"] != orders["BA"]:
                flips += 1

        lines.append(
            f"| `{tid}` | {pair} | {'✅' if unanimous else '❌'} | "
            f"**{majority}** ({counter[majority]}/{len(group)}) | "
            f"{flips}/{len(by_judge)} judges |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Interpretation: any task with order-swap flips is *contested* "
        "and its winner should be marked with a footnote in the article."
    )

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
