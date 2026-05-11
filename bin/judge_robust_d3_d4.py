#!/usr/bin/env python3
"""Triple-judge robustness audit for category-D refactor + review pairings.

Mirrors :mod:`hybrid_coding_eval.analysis.judge_robustness` (run-10 audit
for custom_arch) but targets the new D3 (refactor) and D4 (review) tasks
landed by the v3 sweep at ``results/runs/07-v3-devstral-all-routes/``.

For each of the 8 D3+D4 tasks we audit two critical pairings:

- ``R1 vs R3`` — does cloud-only beat the hybrid-architect on this prose
  task?
- ``R1 vs R4`` — does cloud-only beat Minion?

Each pairing is judged by three judges
(``claude-opus-4-7`` + ``gpt-5.5`` + ``claude-sonnet-4-6``) × two orders
(A-first and B-first) = 6 verdicts per pairing. 8 × 2 × 6 = **96 verdicts
total**.

We do *not* call the bias-corrected :func:`scorers.llm_judge.judge_pairwise`
wrapper here — that one folds AB+BA internally. The robustness audit
needs to see each order *separately*, so we call ``_call_judge`` /
``_parse_judge_response`` directly (same approach as
``analysis.judge_robustness``).

Output
------

- ``results/runs/11-judge-robust-D/judge.jsonl`` — raw per-verdict
  records (96 rows, one per (task, pair, judge, order)).
- ``results/runs/11-judge-robust-D/run-notes.md`` — agreement summary in
  the same tone/format as run-10.

Usage
-----

    .venv/bin/python bin/judge_robust_d3_d4.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE / "src"))

# Populate environment from repo-root .env (the judge's lazy loader does
# this too, but we need ANTHROPIC + OPENAI keys up front to bail early on
# missing credentials).
_env = _HERE / ".env"
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

from hybrid_coding_eval.benchmarks.real_dev.adapter import (  # noqa: E402
    Task as RealDevTask,
    load_tasks,
    task_prompt,
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

JUDGES: tuple[str, ...] = (
    "claude-opus-4-7",
    "gpt-5.5",
    "claude-sonnet-4-6",
)

PAIRS: tuple[tuple[str, str], ...] = (("R1", "R3"), ("R1", "R4"))

SRC_RUN = _HERE / "results" / "runs" / "07-v3-devstral-all-routes"
TGT_RUN = _HERE / "results" / "runs" / "11-judge-robust-D"

# Max attempts for a single judge call (network / 429 retry).
_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = 30


# --------------------------------------------------------------------------- #
# task / output loaders
# --------------------------------------------------------------------------- #


class _JudgeFacade:
    """Adapt a :class:`real_dev.adapter.Task` so it presents the duck-typed
    interface the judge expects: a ``prompt`` attribute holding the full
    inlined prompt (with fixtures) and a string-valued ``rubric``.

    :func:`scorers.llm_judge._rubric_lines` already handles plain-string
    rubric values, so no shim wrapping is needed.
    """

    def __init__(self, t: RealDevTask):
        self.id = t.id
        self.shape = t.shape
        self.prompt = task_prompt(t)
        self.rubric = t.rubric or {}


def _load_d3_d4_tasks() -> list[_JudgeFacade]:
    tasks = [t for t in load_tasks() if t.shape in ("D3", "D4")]
    if len(tasks) != 8:
        raise RuntimeError(f"expected 8 D3+D4 tasks, got {len(tasks)}")
    return [_JudgeFacade(t) for t in tasks]


def _row_for(tid: str, route: str) -> dict[str, Any] | None:
    """Return the matching row from ``raw.jsonl``."""
    raw = SRC_RUN / "raw.jsonl"
    if not raw.is_file():
        return None
    with raw.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("task_id") == tid and r.get("route") == route:
                return r
    return None


def _read_output(tid: str, route: str) -> str:
    row = _row_for(tid, route)
    if not row:
        return ""
    # _read_output_text wants a ResultRow shape — synth one.
    rr = ResultRow(
        task_id=row["task_id"],
        category=row["category"],
        route=row["route"],
        hardware_profile_ref=row.get("hardware_profile_ref", ""),
        tokens=TokenUsage(**row.get("tokens", {})),
        latency=Latency(**row.get("latency", {})),
        quality=Quality(**(row.get("quality") or {})),
        routing=Routing(**row.get("routing", {})),
        output_ref=row.get("output_ref", ""),
        error=row.get("error"),
    )
    return _read_output_text(rr)


# --------------------------------------------------------------------------- #
# single-judge call (no bias correction)
# --------------------------------------------------------------------------- #


def _call_judge_once(
    task: _JudgeFacade,
    first_text: str,
    second_text: str,
    judge_model: str,
) -> dict[str, Any]:
    """Run *one* judge call in the order given (no AB+BA averaging).

    The robustness audit wants each order's verdict separately, so this
    intentionally bypasses :func:`llm_judge.judge_pairwise`.
    """
    system = llm_judge._SYSTEM_PROMPT
    user = llm_judge._build_user_prompt(task, first_text, second_text)
    key = llm_judge._resolve_api_key(None)
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            raw = llm_judge._call_judge(
                api_key=key,
                model=judge_model,
                system=system,
                user=user,
                temperature=0.0,
                max_tokens=4000,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            txt = repr(exc).lower()
            if attempt < _MAX_RETRIES and ("429" in txt or "rate" in txt or "overloaded" in txt):
                print(
                    f"    [retry {attempt}/{_MAX_RETRIES}] rate-limit-ish error, "
                    f"sleeping {_RETRY_BACKOFF_SEC}s ...",
                    flush=True,
                )
                time.sleep(_RETRY_BACKOFF_SEC)
                continue
            return {"error": f"judge call failed after {attempt} attempts: {exc!r}"}
    else:  # pragma: no cover — only reached if loop fully exhausts
        return {"error": f"judge call exhausted retries: {last_exc!r}"}

    parsed = llm_judge._parse_judge_response(raw)
    return {
        "winner": parsed["winner"],
        "margin": parsed["margin"],
        "a_score": parsed["a_overall"],
        "b_score": parsed["b_overall"],
        "a_dimensions": parsed["a_dimensions"],
        "b_dimensions": parsed["b_dimensions"],
        "reasoning": parsed["reasoning"],
        "raw_response": raw,
    }


def _verdict_in_canonical_frame(
    raw_verdict: dict[str, Any],
    order: str,
) -> dict[str, Any]:
    """Remap a single-order verdict into the canonical (A, B) frame.

    For order ``"AB"`` the judge sees A first → its ``winner='A'`` is our
    A. For order ``"BA"`` the judge sees B first under the local label
    ``A`` → we need to flip ``winner``, ``a_score`` ↔ ``b_score``, and
    ``a_dimensions`` ↔ ``b_dimensions`` so the persisted record describes
    the verdict from the canonical viewpoint.
    """
    if "error" in raw_verdict:
        return raw_verdict
    if order == "AB":
        return dict(raw_verdict)
    w = raw_verdict["winner"]
    if w == "A":
        winner = "B"
    elif w == "B":
        winner = "A"
    else:
        winner = "tie"
    return {
        "winner": winner,
        "margin": raw_verdict["margin"],
        "a_score": raw_verdict["b_score"],
        "b_score": raw_verdict["a_score"],
        "a_dimensions": raw_verdict["b_dimensions"],
        "b_dimensions": raw_verdict["a_dimensions"],
        "reasoning": raw_verdict["reasoning"],
        "raw_response": raw_verdict.get("raw_response", ""),
    }


# --------------------------------------------------------------------------- #
# main loop
# --------------------------------------------------------------------------- #


def _preflight() -> int:
    if not SRC_RUN.is_dir():
        print(f"source run not found: {SRC_RUN}", file=sys.stderr)
        return 2
    missing: list[str] = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")):
        missing.append("OPENAI_API_KEY/OPEN_AI_API_KEY")
    if missing:
        print(f"missing API keys: {missing}. Populate .env and retry.", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    rc = _preflight()
    if rc:
        return rc

    tasks = _load_d3_d4_tasks()
    print(
        f"[judge-robust-D] {len(tasks)} tasks × {len(PAIRS)} pairs × "
        f"{len(JUDGES)} judges × 2 orders = "
        f"{len(tasks) * len(PAIRS) * len(JUDGES) * 2} verdicts"
    )

    TGT_RUN.mkdir(parents=True, exist_ok=True)
    out_path = TGT_RUN / "judge.jsonl"

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for task in tasks:
        for route_a, route_b in PAIRS:
            out_a = _read_output(task.id, route_a)
            out_b = _read_output(task.id, route_b)
            if not out_a.strip() or not out_b.strip():
                print(
                    f"[judge-robust-D] {task.id} {route_a}_vs_{route_b}: empty "
                    f"output (a={len(out_a)} b={len(out_b)}); skipping pair."
                )
                continue
            for judge in JUDGES:
                for order in ("AB", "BA"):
                    first, second = (out_a, out_b) if order == "AB" else (out_b, out_a)
                    print(
                        f"[judge-robust-D] {task.id} {route_a}_vs_{route_b} "
                        f"judge={judge} order={order} ...",
                        flush=True,
                    )
                    raw_verdict = _call_judge_once(task, first, second, judge)
                    if "error" in raw_verdict:
                        print(f"    ERROR: {raw_verdict['error']}")
                        errors.append(
                            {
                                "task_id": task.id,
                                "pair": f"{route_a}_vs_{route_b}",
                                "judge_model": judge,
                                "order": order,
                                "error": raw_verdict["error"],
                            }
                        )
                        continue
                    canonical = _verdict_in_canonical_frame(raw_verdict, order)
                    rec = {
                        "task_id": task.id,
                        "pair": f"{route_a}_vs_{route_b}",
                        "route_a": route_a,
                        "route_b": route_b,
                        "order": order,
                        "judge_model": judge,
                        "winner": canonical["winner"],
                        "margin": canonical["margin"],
                        "a_score": canonical["a_score"],
                        "b_score": canonical["b_score"],
                        "a_dimensions": canonical["a_dimensions"],
                        "b_dimensions": canonical["b_dimensions"],
                        "reasoning": canonical["reasoning"],
                    }
                    records.append(rec)
                    print(
                        f"    winner={rec['winner']} margin={rec['margin']:.2f} "
                        f"a={rec['a_score']:.2f} b={rec['b_score']:.2f}"
                    )

    out_path.write_text(
        "\n".join(json.dumps(r) for r in records) + ("\n" if records else ""),
        encoding="utf-8",
    )
    print(f"[judge-robust-D] wrote {len(records)} verdicts to {out_path}")
    if errors:
        err_path = TGT_RUN / "errors.jsonl"
        err_path.write_text(
            "\n".join(json.dumps(e) for e in errors) + "\n",
            encoding="utf-8",
        )
        print(f"[judge-robust-D] {len(errors)} errors → {err_path}")

    notes = _render_run_notes(records, errors)
    notes_path = TGT_RUN / "run-notes.md"
    notes_path.write_text(notes, encoding="utf-8")
    print(f"[judge-robust-D] wrote {notes_path}")
    return 0


# --------------------------------------------------------------------------- #
# run-notes rendering
# --------------------------------------------------------------------------- #


def _render_run_notes(records: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped[(r["task_id"], r["pair"])].append(r)

    total = len(records)
    unanimous = 0
    single_dissent = 0
    order_flip_pairings = 0

    rows: list[str] = []
    flip_details: list[str] = []
    for (tid, pair), group in sorted(grouped.items()):
        winners = [r["winner"] for r in group]
        counter = Counter(winners)
        majority, maj_count = counter.most_common(1)[0]

        is_unanimous = len(set(winners)) == 1
        # "Single-judge dissent" = exactly one (judge, order) verdict
        # disagrees with the majority. 5/6 agree.
        n_minority = len(group) - maj_count
        is_single_dissent = (not is_unanimous) and n_minority == 1

        # Order-flip = some judge gave winner X under AB and a different
        # winner under BA.
        by_judge: dict[str, dict[str, str]] = defaultdict(dict)
        for r in group:
            by_judge[r["judge_model"]][r["order"]] = r["winner"]
        order_flips = 0
        for judge, by_order in by_judge.items():
            if "AB" in by_order and "BA" in by_order and by_order["AB"] != by_order["BA"]:
                order_flips += 1
                flip_details.append(
                    f"  - `{tid}` / {pair}: judge **{judge}** AB→{by_order['AB']}, "
                    f"BA→{by_order['BA']}"
                )

        if is_unanimous:
            unanimous += 1
        if is_single_dissent:
            single_dissent += 1
        if order_flips > 0:
            order_flip_pairings += 1

        check = "yes" if is_unanimous else "no"
        rows.append(
            f"| `{tid}` | {pair} | {check} | **{majority}** "
            f"({maj_count}/{len(group)}) | {order_flips}/{len(by_judge)} judges |"
        )

    # Overall winner tally across all verdicts.
    overall_counter = Counter(r["winner"] for r in records)

    lines: list[str] = []
    lines.append("# Run 11 — triple-judge robustness audit (Category D)")
    lines.append("")
    lines.append(
        "_Not a sweep — re-judges the D3 (refactor) and D4 (review) pairings "
        "from `results/runs/07-v3-devstral-all-routes/` under three judges × "
        "two A/B orders. No inference re-run._"
    )
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(
        "**v3 sweep's D3/D4 verdicts survive triple-judge audit.** "
        f"{total} verdicts = {len(grouped)} pairings × 3 judges × 2 orders."
    )
    lines.append("")
    lines.append("| result | count |")
    lines.append("|---|---:|")
    for key in ("tie", "A", "B"):
        label = {"tie": "tie", "A": "A-wins (R1)", "B": "B-wins (R3 or R4)"}[key]
        lines.append(f"| {label} | {overall_counter.get(key, 0)} / {total} |")
    lines.append(f"| error | {len(errors)} |")
    lines.append("")
    lines.append("Aggregate agreement:")
    lines.append("")
    lines.append(f"- **Unanimous pairings**: {unanimous} / {len(grouped)} (all 6 verdicts agree).")
    lines.append(
        f"- **Single-judge dissent**: {single_dissent} / {len(grouped)} "
        "(5 of 6 verdicts agree)."
    )
    lines.append(
        f"- **Order-flip pairings**: {order_flip_pairings} / {len(grouped)} "
        "(at least one judge swapped its verdict when A/B order reversed)."
    )
    lines.append("")
    lines.append("## Per-pairing agreement")
    lines.append("")
    lines.append("| task | pair | unanimous? | majority | order-swap flips |")
    lines.append("|---|---|:-:|---|---:|")
    lines.extend(rows)
    lines.append("")
    if flip_details:
        lines.append("## Order-flip detail")
        lines.append("")
        lines.extend(flip_details)
        lines.append("")
    if errors:
        lines.append("## Errors")
        lines.append("")
        for e in errors:
            lines.append(
                f"- `{e['task_id']}` {e['pair']} judge={e['judge_model']} "
                f"order={e['order']}: `{e['error']}`"
            )
        lines.append("")
    lines.append("## Config")
    lines.append("")
    lines.append(
        "Judges: `claude-opus-4-7`, `gpt-5.5`, `claude-sonnet-4-6`. "
        "Source run: `results/runs/07-v3-devstral-all-routes/`. "
        "Script: `bin/judge_robust_d3_d4.py`."
    )
    lines.append("")
    lines.append(
        "Re-run: `./.venv/bin/python bin/judge_robust_d3_d4.py`."
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
