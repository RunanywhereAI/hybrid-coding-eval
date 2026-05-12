#!/usr/bin/env python
"""T4.1 orchestrator — loops (task × route), appends to raw.jsonl.

See PLAN.md §4 and the T4.1 spec: this CLI produces the canonical
``results/<timestamp>/raw.jsonl`` that later T5 aggregation consumes.

Key properties:
  * Resume-safe (each row is flushed immediately; ``--resume`` skips
    (task_id, route) pairs already present).
  * Per-row scoring runs inline unless ``--skip-scoring``.
  * Infrastructure errors never crash the sweep — the runner returns an
    error-flavoured ResultRow which is logged to ``ERRORS.md``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

_here = Path(__file__).resolve()
for _p in (_here, *_here.parents):
    if (_p / "pyproject.toml").is_file():
        _REPO_ROOT = _p
        break
else:  # pragma: no cover
    _REPO_ROOT = _here.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Also add src/ so ``hybrid_coding_eval`` is importable when run as a
# script without ``pip install -e .``.
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hybrid_coding_eval.core.experiment import (  # noqa: E402
    CATEGORY_SOURCES,
    ROUTES,
    TaskPlan,
    build_task_plan,
    pair_already_done,
    run_pair,
    timestamp_dirname,
)

# --------------------------------------------------------------------------- #
# Env manifest
# --------------------------------------------------------------------------- #


def _load_or_generate_manifest(
    supplied: Path | None, out_dir: Path
) -> tuple[Path, str]:
    """Resolve the hardware manifest path and compute a profile-ref string.

    Returns ``(manifest_copy_path_in_out_dir, hardware_profile_ref)``.
    """
    if supplied is not None:
        manifest_src = supplied.resolve()
        if not manifest_src.exists():
            raise SystemExit(
                f"--hardware-manifest not found: {manifest_src}"
            )
        manifest_data = json.loads(manifest_src.read_text(encoding="utf-8"))
    else:
        # Generate fresh via the cli env_detect module (bin/env-detect.py was
        # removed in the v3.1 cleanup; the canonical entry point is now the
        # python module).
        tmp = out_dir / "env-manifest.json"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "hybrid_coding_eval.cli.env_detect", "--out", str(tmp)],
                cwd=_REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            _ = proc.stdout  # noqa: F841
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                f"env-detect failed ({exc.returncode}): {exc.stderr}"
            ) from exc
        manifest_data = json.loads(tmp.read_text(encoding="utf-8"))

    # Always (re)write the manifest into out_dir so one directory carries
    # the full reproducibility bundle.
    target = out_dir / "env-manifest.json"
    target.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ``hardware_profile_ref`` — short, human-readable, stable across rows.
    sha = (manifest_data.get("git_sha") or "")[:7]
    chip = (manifest_data.get("hardware") or {}).get("chip") or "unknown-chip"
    ram = (manifest_data.get("hardware") or {}).get("ram_gb")
    ram_s = f"{ram}GB" if ram is not None else ""
    self_hash = (manifest_data.get("_self_hash") or "")[:8]
    parts = [p for p in [chip, ram_s, f"git{sha}", f"mh{self_hash}"] if p]
    return target, "|".join(parts)


# --------------------------------------------------------------------------- #
# Argparse
# --------------------------------------------------------------------------- #


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run-experiment",
        description="Run the hybrid-coding-eval sweep (T4.1).",
    )
    p.add_argument(
        "--categories",
        type=_csv,
        default=["A", "B", "C"],
        help="Comma-separated list of category letters (default: A,B,C).",
    )
    p.add_argument(
        "--routes",
        type=_csv,
        default=list(ROUTES),
        help="Comma-separated list of route ids (default: R1,R2,R3).",
    )
    p.add_argument(
        "--tasks",
        type=int,
        default=None,
        help="Cap number of tasks per category (default: all).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Default: results/<timestamp>_<host>/",
    )
    p.add_argument(
        "--hardware-manifest",
        type=Path,
        default=None,
        help="Path to an existing env-manifest.json. Default: run env-detect.",
    )
    p.add_argument(
        "--proxy-url",
        default="http://127.0.0.1:8787",
        help="Router proxy base URL (default: http://127.0.0.1:8787).",
    )
    p.add_argument("--smoke", action="store_true", help="1 task per category.")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip (task_id, route) pairs already in raw.jsonl.",
    )
    p.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Run routes without scoring inline.",
    )
    p.add_argument(
        "--router-strategy",
        default="heuristic",
        choices=[
            "always-cloud",
            "always-local",
            "rules",
            "heuristic",
            "llm-classifier",
            "embedding-knn",
            "cascade",
        ],
        help=(
            "Routing strategy R3's executor + synthesizer steps use "
            "(default: heuristic). Ignored by R1/R2 (forced by definition) "
            "and R4/R5 (role-fixed). Sourced from config.router.strategy "
            "when launched via ./bench."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned work and exit without running.",
    )
    args = p.parse_args(argv)

    # Validate.
    for c in args.categories:
        if c not in CATEGORY_SOURCES:
            p.error(f"unknown category {c!r} (valid: {sorted(CATEGORY_SOURCES)})")
    for r in args.routes:
        if r not in ROUTES:
            p.error(f"unknown route {r!r} (valid: {list(ROUTES)})")
    return args


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def _progress_line(i: int, total: int, plan_item: TaskPlan, row: Any) -> str:
    q = row.quality
    if row.error:
        status = f"ERROR:{row.error[:40]}"
    elif q.functional_pass is True:
        status = "PASS"
    elif q.functional_pass is False:
        status = "FAIL"
    elif q.composite is not None:
        status = f"score={q.composite:.2f}"
    else:
        status = "ran"
    return (
        f"[{i:3d}/{total:3d}] {plan_item.category} {plan_item.route} "
        f"{plan_item.task_id:<48s} "
        f"wall={row.latency.wall_ms}ms "
        f"tokens={(row.tokens.prompt or 0) + (row.tokens.completion or 0)} "
        f"{status}"
    )


def _write_progress(progress_path: Path, line: str) -> None:
    with progress_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_error(errors_path: Path, plan_item: TaskPlan, row: Any) -> None:
    with errors_path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"- `{plan_item.task_id}` + `{plan_item.route}` "
            f"(category {plan_item.category}, source `{plan_item.source}`): "
            f"{row.error}\n"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    out_dir: Path = args.out or (_REPO_ROOT / "results" / timestamp_dirname())
    out_dir = out_dir.resolve()
    raw_path = out_dir / "raw.jsonl"
    progress_path = out_dir / "progress.log"
    errors_path = out_dir / "ERRORS.md"
    outputs_dir = out_dir / "outputs"

    # Build the plan first so --dry-run can show it without touching disk.
    plan = build_task_plan(
        categories=args.categories,
        routes=args.routes,
        smoke=args.smoke,
        tasks_cap=args.tasks,
    )

    if args.dry_run:
        print(f"Would write to: {out_dir}")
        print(f"Planned pairs: {len(plan)}")
        for i, item in enumerate(plan, start=1):
            print(
                f"  [{i}/{len(plan)}] {item.category} {item.route} "
                f"{item.task_id} (source={item.source})"
            )
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Manifest.
    manifest_path, hardware_profile_ref = _load_or_generate_manifest(
        args.hardware_manifest, out_dir
    )
    print(f"env-manifest: {manifest_path}")
    print(f"hardware_profile_ref: {hardware_profile_ref}")
    print(f"out: {out_dir}")
    print(f"plan: {len(plan)} (task, route) pairs")

    # Filter by --resume before counting progress.
    if args.resume and raw_path.exists():
        filtered: list[TaskPlan] = []
        for item in plan:
            if pair_already_done(raw_path, item.task_id, item.route):
                print(f"[resume] skip {item.task_id} + {item.route}")
                continue
            filtered.append(item)
        plan = filtered
        print(f"after resume filter: {len(plan)} pairs to run")

    total = len(plan)
    if total == 0:
        print("nothing to do.")
        return 0

    had_infra_error = False
    for i, item in enumerate(plan, start=1):
        try:
            row = run_pair(
                item,
                proxy_url=args.proxy_url,
                hardware_profile_ref=hardware_profile_ref,
                outputs_dir=outputs_dir,
                raw_path=raw_path,
                skip_scoring=args.skip_scoring,
                router_strategy=args.router_strategy,
            )
        except Exception as exc:  # noqa: BLE001 — keep the sweep alive
            had_infra_error = True
            tb = traceback.format_exc(limit=4)
            msg = f"[{i}/{total}] {item.category} {item.route} {item.task_id} UNCAUGHT: {exc}"
            print(msg, file=sys.stderr)
            print(tb, file=sys.stderr)
            _write_progress(progress_path, msg)
            with errors_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"- `{item.task_id}` + `{item.route}`: uncaught "
                    f"{type(exc).__name__}: {exc}\n"
                )
            continue

        line = _progress_line(i, total, item, row)
        print(line)
        _write_progress(progress_path, line)
        if row.error:
            _append_error(errors_path, item, row)

    # Summary stats.
    summary_lines = [
        "",
        "## summary",
        f"- planned pairs: {total}",
        f"- out dir: {out_dir}",
        f"- raw.jsonl: {raw_path}",
    ]
    for ln in summary_lines:
        _write_progress(progress_path, ln)
        print(ln)

    return 2 if had_infra_error else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
