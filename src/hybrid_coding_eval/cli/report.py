"""Report generator — writes reports/ARTICLE.md + appendices.

Invoked via ``./bench report <what>`` where ``<what>`` is one of:
 - ``article``            writes reports/ARTICLE.md (authored by T-18)
 - ``appendix-tasks``     reports/APPENDIX_TASKS.md (per-row forensic record)
 - ``appendix-scenarios`` reports/APPENDIX_SCENARIOS.md (multi-scenario matrix)
 - ``appendix-routes``    reports/APPENDIX_ROUTES.md (per-route worked examples)
 - ``all``                every sub-report

The appendix generators read only committed files:
 - ``results/raw.jsonl`` — the 180-row merged dataset (+ new rows from
   Wave 2 sweeps).
 - ``src/hybrid_coding_eval/benchmarks/*/tasks.jsonl`` — problem text.
 - ``src/hybrid_coding_eval/runners/_shared.py`` — prompt templates.
 - ``results/runs/*/outputs/*.txt`` — model outputs.
 - ``results/runs/*/judge.jsonl`` — judge reasoning (C-category only).
 - ``results/runs/*/minion_logs/*.json`` — Minion Q&A transcripts (R4 only).

ARTICLE.md is hand-edited at T-18 and is *not* regenerated here; the
``article`` command simply fails fast if it doesn't exist yet.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from hybrid_coding_eval.core.paths import repo_root
from hybrid_coding_eval.core.pricing import PRICING_META
from hybrid_coding_eval.core.results import load_results

logger = logging.getLogger(__name__)

_REPO_ROOT = repo_root()
_RESULTS = _REPO_ROOT / "results"
_REPORTS = _REPO_ROOT / "reports"


# --------------------------------------------------------------------------- #
# task text reconstruction
# --------------------------------------------------------------------------- #


@dataclass
class TaskBundle:
    """Everything we show per row in the appendix."""

    task_id: str
    route: str
    variant: str | None
    category: str
    source: str
    problem_text: str
    prompt_sent: str
    output_excerpt: str
    output_truncated: bool
    score: str
    judge_reasoning: str | None
    minion_transcript: str | None
    tokens_cloud: int
    tokens_local: int


def _load_tasks_by_id() -> dict[str, tuple[str, Any]]:
    """Return task_id → (source, task)."""
    out: dict[str, tuple[str, Any]] = {}
    from hybrid_coding_eval.benchmarks.bigcodebench_hard.adapter import load_tasks as bch
    from hybrid_coding_eval.benchmarks.custom_arch.adapter import load_tasks as ca
    from hybrid_coding_eval.benchmarks.humaneval_plus.adapter import load_tasks as hep
    from hybrid_coding_eval.benchmarks.swebench_verified.adapter import load_tasks as swe

    for loader, source in [
        (lambda: hep(n=10), "humaneval_plus"),
        (lambda: swe(n=10), "swebench_verified"),
        (lambda: bch(n=5), "bigcodebench_hard"),
        (lambda: ca(), "custom_arch"),
    ]:
        try:
            for t in loader():
                out[t.id] = (source, t)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("task loader for %s failed: %s", source, exc)
    return out


def _problem_text(task: Any, source: str) -> str:
    """Return the verbatim problem statement for ``task``."""
    if source in ("humaneval_plus", "bigcodebench_hard"):
        # The prompt field in these adapters IS the problem stub + docstring.
        return getattr(task, "prompt", "") or getattr(task, "instruct_prompt", "")
    if source == "swebench_verified":
        repo = getattr(task, "repo", "?")
        commit = getattr(task, "base_commit", "?")
        ps = getattr(task, "problem_statement", "") or ""
        return f"Repository: {repo}\nBase commit: {commit}\n\n{ps}"
    if source == "custom_arch":
        ctx = getattr(task, "context", "") or ""
        prompt = getattr(task, "prompt", "") or ""
        return (ctx + "\n\n" + prompt).strip() if ctx else prompt
    return ""


def _prompt_sent(task: Any, source: str) -> str:
    """Reconstruct the exact prompt string the runner submitted."""
    from hybrid_coding_eval.runners._shared import task_prompt

    try:
        return task_prompt(task)
    except Exception as exc:  # pragma: no cover
        return f"[prompt reconstruction failed: {exc}]"


_OUTPUT_CAP_CHARS = 2000


def _output_excerpt(output_ref: str) -> tuple[str, bool]:
    """Return ``(excerpt_text, was_truncated)``."""
    if not output_ref:
        return "", False
    path = Path(output_ref)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    if not path.exists():
        return f"[output not found at {output_ref}]", False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover
        return f"[read failed: {exc}]", False
    if len(text) <= _OUTPUT_CAP_CHARS:
        return text, False
    return text[:_OUTPUT_CAP_CHARS] + "\n…[truncated]", True


def _score_summary(row: Any) -> str:
    q = row.quality
    parts = []
    if q.functional_pass is True:
        parts.append("**PASS**")
    elif q.functional_pass is False:
        parts.append("**FAIL**")
    if q.tests_passed is not None and q.tests_total is not None:
        parts.append(f"{q.tests_passed}/{q.tests_total}")
    if q.judge_win_rate is not None:
        parts.append(f"judge_win_rate={q.judge_win_rate:.2f}")
    if q.composite is not None:
        parts.append(f"composite={q.composite:.2f}")
    if row.error:
        parts.append(f"error={row.error[:80]}")
    return " · ".join(parts) if parts else "_unscored_"


def _judge_reasoning_for(task_id: str, route: str, variant: str | None) -> str | None:
    """Find the judge's reasoning in per-run judge.jsonl files."""
    for run_dir in sorted(_RESULTS.glob("runs/*")):
        judge = run_dir / "judge.jsonl"
        if not judge.is_file():
            continue
        for line in judge.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("task_id") != task_id:
                continue
            if route in {rec.get("route_a"), rec.get("route_b")}:
                txt = rec.get("reasoning") or ""
                if txt:
                    return f"[judge={rec.get('judge_model', '?')}] {txt}"
    return None


def _minion_transcript_for(task_id: str) -> str | None:
    """Locate the Minion Q&A transcript for a task in any run's minion_logs/."""
    slug = task_id.replace("/", "__").replace(" ", "_")
    for run_dir in sorted(_RESULTS.glob("runs/*")):
        logs = run_dir / "minion_logs"
        if not logs.is_dir():
            continue
        for p in sorted(logs.glob(f"{slug}*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            rounds = data.get("supervisor_messages", [])
            if rounds:
                return "(minion log available at "\
                    f"results/runs/{run_dir.name}/minion_logs/{p.name}, "\
                    f"{len(rounds)} supervisor turns)"
    return None


def _token_split(row: Any) -> tuple[int, int]:
    t = row.tokens
    cloud = int(t.cloud_prompt or 0) + int(t.cloud_completion or 0)
    local = int(t.local_prompt or 0) + int(t.local_completion or 0)
    # Fallback for R1 cloud-only rows that never populated the split.
    if cloud == 0 and local == 0:
        cloud = int(t.prompt or 0) + int(t.completion or 0)
    return cloud, local


# --------------------------------------------------------------------------- #
# bundle construction
# --------------------------------------------------------------------------- #


def _bundles_for_rows(rows: Iterable[Any]) -> list[TaskBundle]:
    tasks_by_id = _load_tasks_by_id()
    bundles: list[TaskBundle] = []
    for row in rows:
        src_task = tasks_by_id.get(row.task_id)
        if not src_task:
            source, problem_text, prompt_sent = "?", "", ""
        else:
            source, task = src_task
            problem_text = _problem_text(task, source)
            prompt_sent = _prompt_sent(task, source)
        excerpt, truncated = _output_excerpt(row.output_ref or "")
        score = _score_summary(row)
        judge = _judge_reasoning_for(row.task_id, row.route, row.variant)
        minion = _minion_transcript_for(row.task_id) if row.route == "R4" else None
        cloud_toks, local_toks = _token_split(row)
        bundles.append(
            TaskBundle(
                task_id=row.task_id,
                route=row.route,
                variant=row.variant,
                category=row.category,
                source=source,
                problem_text=problem_text,
                prompt_sent=prompt_sent,
                output_excerpt=excerpt,
                output_truncated=truncated,
                score=score,
                judge_reasoning=judge,
                minion_transcript=minion,
                tokens_cloud=cloud_toks,
                tokens_local=local_toks,
            )
        )
    return bundles


# --------------------------------------------------------------------------- #
# renderers
# --------------------------------------------------------------------------- #


def _render_appendix_tasks(bundles: list[TaskBundle]) -> str:
    """Per-row forensic appendix — one section per (task_id, route, variant)."""
    lines: list[str] = []
    lines.append("# Appendix A — tasks, prompts, outputs, and scores")
    lines.append("")
    lines.append(
        "This is the forensic record. For every ``(task_id, route, variant)`` "
        "tuple in the committed dataset we reproduce: the verbatim problem "
        "statement, the exact prompt sent to the model, an excerpt of the "
        "model output, the score it received, the judge's reasoning where "
        "applicable, and the token split between cloud and local."
    )
    lines.append("")
    lines.append(
        "Prompt reconstructions go through ``hybrid_coding_eval.runners._shared.task_prompt`` "
        "— bit-identical to what the runner submitted. Model outputs are "
        f"truncated to {_OUTPUT_CAP_CHARS} chars with a pointer to the full "
        "file under ``results/runs/NN-*/outputs/``."
    )
    lines.append("")

    # Index
    lines.append("## Index")
    lines.append("")
    by_category: dict[str, list[TaskBundle]] = defaultdict(list)
    for b in bundles:
        by_category[b.category].append(b)
    for cat in sorted(by_category):
        lines.append(f"- **Category {cat}** — {len(by_category[cat])} rows")
    lines.append("")

    by_task: dict[str, list[TaskBundle]] = defaultdict(list)
    for b in bundles:
        by_task[b.task_id].append(b)

    for task_id in sorted(by_task):
        variants = by_task[task_id]
        cat = variants[0].category
        source = variants[0].source
        lines.append(f"## `{task_id}`")
        lines.append("")
        lines.append(f"- category **{cat}** · source `{source}`")
        lines.append(
            f"- appears in {len({v.variant for v in variants})} variants "
            f"across {len({v.route for v in variants})} routes"
        )
        lines.append("")

        # Problem text once (shared across variants/routes).
        lines.append("### Problem")
        lines.append("")
        lines.append("```text")
        lines.append(_trim(variants[0].problem_text, 1500))
        lines.append("```")
        lines.append("")

        # Each (route, variant) pair.
        for b in sorted(variants, key=lambda x: (x.route, x.variant or "")):
            title = f"`{b.route}`"
            if b.variant:
                title += f" (variant `{b.variant}`)"
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- score: {b.score}")
            lines.append(f"- tokens: cloud={b.tokens_cloud:,} · local={b.tokens_local:,}")
            lines.append("")
            lines.append("<details><summary>prompt sent to the model</summary>")
            lines.append("")
            lines.append("```text")
            lines.append(_trim(b.prompt_sent, 1500))
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")
            lines.append("<details><summary>model output (excerpt)</summary>")
            lines.append("")
            lines.append("```text")
            lines.append(b.output_excerpt.rstrip() or "[empty]")
            lines.append("```")
            if b.output_truncated:
                lines.append("")
                lines.append(
                    f"*Full output:* `{_output_path_hint(b.task_id, b.route, b.variant)}`"
                )
            lines.append("")
            lines.append("</details>")
            lines.append("")
            if b.judge_reasoning:
                lines.append("<details><summary>judge reasoning</summary>")
                lines.append("")
                lines.append(_trim(b.judge_reasoning, 1500))
                lines.append("")
                lines.append("</details>")
                lines.append("")
            if b.minion_transcript:
                lines.append(f"*Minion Q&A:* {b.minion_transcript}")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"_Generated by `./bench report appendix-tasks`. Pricing table "
        f"sha256={PRICING_META['sha256'][:12]}… dated {PRICING_META['fetched_at']}._"
    )
    lines.append("")
    return "\n".join(lines)


def _trim(s: str, limit: int) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s.rstrip()
    return s[:limit].rstrip() + "\n…[trimmed]"


def _output_path_hint(task_id: str, route: str, variant: str | None) -> str:
    """Best-effort guess at the path for the full output file."""
    slug = task_id.replace("/", "__").replace(" ", "_")
    return f"results/runs/*/outputs/{slug}_{route}.txt"


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def _cmd_appendix_tasks(argv: list[str]) -> int:
    # Merge MVP dataset + post-MVP run dirs (05+). Avoid double-counting
    # runs 01-04 which are already baked into results/raw.jsonl.
    raw = _RESULTS / "raw.jsonl"
    rows = list(load_results(raw))
    for run_dir in sorted((_RESULTS / "runs").glob("*")):
        if not run_dir.is_dir():
            continue
        if run_dir.name.startswith(("01-", "02-", "03-", "04-")):
            continue
        inner = run_dir / "raw.jsonl"
        if inner.is_file():
            rows.extend(load_results(inner))

    bundles = _bundles_for_rows(rows)
    body = _render_appendix_tasks(bundles)
    out = _REPORTS / "APPENDIX_TASKS.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({len(bundles)} bundles)")
    return 0


def _cmd_article(argv: list[str]) -> int:
    out = _REPORTS / "ARTICLE.md"
    if not out.is_file():
        print(
            f"{out} does not exist yet — write the article manually at T-18. "
            "This subcommand does not regenerate it.",
            file=sys.stderr,
        )
        return 2
    print(f"{out} exists; no regeneration performed (article is hand-authored).")
    return 0


def _cmd_appendix_scenarios(argv: list[str]) -> int:
    out = _REPORTS / "APPENDIX_SCENARIOS.md"
    if not out.is_file():
        print(
            f"{out} will be generated by T-20. Placeholder only for now.",
            file=sys.stderr,
        )
        return 2
    return 0


def _cmd_appendix_routes(argv: list[str]) -> int:
    out = _REPORTS / "APPENDIX_ROUTES.md"
    if not out.is_file():
        print(
            f"{out} will be generated by T-20. Placeholder only for now.",
            file=sys.stderr,
        )
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="bench report", description="Regenerate report artefacts.")
    parser.add_argument(
        "what",
        choices=["article", "appendix-tasks", "appendix-scenarios", "appendix-routes", "all"],
    )
    args = parser.parse_args(argv)

    if args.what == "all":
        rcs = [
            _cmd_article([]),
            _cmd_appendix_tasks([]),
            _cmd_appendix_scenarios([]),
            _cmd_appendix_routes([]),
        ]
        return max(rcs) if rcs else 0
    if args.what == "article":
        return _cmd_article([])
    if args.what == "appendix-tasks":
        return _cmd_appendix_tasks([])
    if args.what == "appendix-scenarios":
        return _cmd_appendix_scenarios([])
    if args.what == "appendix-routes":
        return _cmd_appendix_routes([])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
