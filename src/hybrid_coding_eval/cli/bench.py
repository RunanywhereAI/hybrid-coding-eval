"""The ``bench`` dispatcher CLI.

Subcommands:

- ``bench run --config configs/variants/foo.yaml`` → runs the sweep.
- ``bench show-config configs/variants/foo.yaml`` → prints merged config.
- ``bench env-detect [--out PATH]`` → writes an env-manifest.json.
- ``bench rescore RESULTS_DIR`` → post-sweep SWE-bench rescoring.
- ``bench rejudge RESULTS_DIR`` → post-sweep Opus re-judge.
- ``bench analyze RESULTS_DIR`` → aggregate → ARQGC → charts.
- ``bench report <article|appendix-tasks|appendix-scenarios|appendix-routes|all>``
  → regenerate the publish surface under ``reports/``.
- ``bench schema [--out configs/schema.json]`` → dump JSON Schema.

Every subcommand delegates to an existing module. The dispatcher only
owns argparse-style dispatch and the ``run`` subcommand's YAML→sweep
wiring (because that is new functionality).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from hybrid_coding_eval.core.config.loader import dump_schema_json, load_config
from hybrid_coding_eval.core.config.resolve import apply_overrides
from hybrid_coding_eval.core.config.schema import BenchConfig

logger = logging.getLogger(__name__)


# ---------- helpers -------------------------------------------------------


def _load_merged(args: argparse.Namespace) -> BenchConfig:
    config = load_config(args.config)
    if args.set:
        config = apply_overrides(config, args.set)
    # CLI flags override specific fields:
    overrides: list[str] = []
    if getattr(args, "variant_tag", None):
        overrides.append(f"variant_tag={args.variant_tag}")
    if getattr(args, "out", None):
        overrides.append(f"out_dir={args.out}")
    if getattr(args, "smoke", False):
        overrides.append("benchmark.smoke=true")
    if getattr(args, "resume", False):
        overrides.append("resume=true")
    if overrides:
        config = apply_overrides(config, overrides)
    return config


# ---------- subcommand: run -----------------------------------------------


def _cmd_run(args: argparse.Namespace) -> int:
    config = _load_merged(args)

    if args.dry_run:
        _print_plan(config)
        return 0

    # Import lazily: the orchestrator has heavy transitive deps (pandas,
    # docker) that ``bench show-config`` should not have to pay for.
    # Delegate to the existing CLI main() in cli.run. It accepts argv;
    # we translate the config back into its flag shape until T-08 lets
    # run_pair() take a BenchConfig directly.
    from hybrid_coding_eval.cli.run import main as run_main
    from hybrid_coding_eval.core.experiment import run_pair as _run_pair  # noqa: F401

    argv: list[str] = [
        "--out",
        str(config.out_dir),
        "--categories",
        ",".join(config.benchmark.categories),
        "--routes",
        ",".join(config.benchmark.routes),
        "--proxy-url",
        f"http://127.0.0.1:{config.router.port}",
        "--router-strategy",
        config.router.strategy,
    ]
    if config.benchmark.smoke:
        argv.append("--smoke")
    if config.resume:
        argv.append("--resume")
    if config.scoring.skip:
        argv.append("--skip-scoring")

    # Task caps — ``run-experiment.py`` only takes a single ``--tasks N``
    # flag (cap applied uniformly across the selected categories). So we
    # can only forward a per-category cap when every listed category has
    # the *same* cap. The single-category case (e.g. the real_dev smoke)
    # falls out for free.
    tpc = config.benchmark.tasks_per_category
    if tpc:
        caps = [tpc[c] for c in config.benchmark.categories if c in tpc]
        if caps and len(set(caps)) == 1:
            argv += ["--tasks", str(caps[0])]
        elif caps:
            logger.warning(
                "tasks_per_category has heterogeneous caps %r for categories %r; "
                "--tasks only supports a single uniform cap — skipping forward. "
                "Use a dedicated variant per category for now.",
                tpc,
                config.benchmark.categories,
            )

    # Write a config-manifest alongside the run so the YAML-→actual-run
    # mapping is auditable.
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "bench-config.json"
    manifest.write_text(
        json.dumps(
            {
                "config": config.model_dump(mode="json"),
                "sha256": config.canonical_sha256(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return int(run_main(argv) or 0)


def _print_plan(config: BenchConfig) -> None:
    print("# bench run plan")
    print(f"variant_tag      {config.variant_tag}")
    print(f"out_dir          {config.out_dir}")
    print(f"config_sha       {config.canonical_sha256()[:12]}…")
    print(f"cloud_model      {config.models.cloud}")
    print(f"local_model      {config.models.local}")
    print(f"judge_model      {config.models.judge}")
    print(f"router           strategy={config.router.strategy} port={config.router.port}")
    print(f"categories       {config.benchmark.categories}")
    print(f"routes           {config.benchmark.routes}")
    print(f"seeds            {config.benchmark.seeds}")
    print(f"primary pricing  {config.pricing.primary}")
    print(f"scenarios        {config.pricing.scenarios}")


# ---------- subcommand: show-config ---------------------------------------


def _cmd_show_config(args: argparse.Namespace) -> int:
    config = _load_merged(args)
    print(
        json.dumps(
            {
                "config": config.model_dump(mode="json"),
                "sha256": config.canonical_sha256(),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


# ---------- subcommand: env-detect ----------------------------------------


def _cmd_env_detect(args: argparse.Namespace) -> int:
    from hybrid_coding_eval.cli.env_detect import main as env_main

    argv: list[str] = []
    if args.out:
        argv += ["--out", str(args.out)]
    return int(env_main(argv) or 0)


# ---------- subcommand: rescore / rejudge / analyze -----------------------


def _cmd_rescore(args: argparse.Namespace) -> int:
    from hybrid_coding_eval.cli.rescore import cli_main

    return int(cli_main([str(args.results_dir)]) or 0)


def _cmd_rejudge(args: argparse.Namespace) -> int:
    from hybrid_coding_eval.cli.rejudge import cli_main

    return int(cli_main([str(args.results_dir)]) or 0)


def _cmd_analyze(args: argparse.Namespace) -> int:
    from hybrid_coding_eval.analysis.all import main as analyze_main

    return int(analyze_main([str(args.results_dir)]) or 0)


# ---------- subcommand: token-budget --------------------------------------


def _cmd_token_budget(args: argparse.Namespace) -> int:
    # Lazy imports — pandas + pricing tables aren't needed by other subcommands.
    from hybrid_coding_eval.analysis.token_budget import (
        HEADLINE_SCENARIOS,
        compute_token_budget,
        render_csv,
        render_markdown,
    )
    from hybrid_coding_eval.core.results import load_results

    results_path: Path = args.results_path
    # Accept either a raw.jsonl file directly OR a runs/*/ directory
    # (we look for ``raw.jsonl`` inside it).
    if results_path.is_dir():
        jsonl = results_path / "raw.jsonl"
        if not jsonl.is_file():
            print(
                f"error: no raw.jsonl found under {results_path}",
                file=sys.stderr,
            )
            return 2
        source = str(jsonl)
    elif results_path.is_file():
        source = str(results_path)
    else:
        print(f"error: path not found: {results_path}", file=sys.stderr)
        return 2

    rows = load_results(source)
    if not rows:
        print(f"warning: {source} contained no parseable rows", file=sys.stderr)

    scenarios = (
        [s.strip() for s in args.scenarios.split(",") if s.strip()]
        if args.scenarios
        else list(HEADLINE_SCENARIOS)
    )

    out_md: Path = args.out_md or Path("reports/TOKEN_BUDGET.md")
    out_csv: Path = args.out_csv or (out_md.parent / "token_budget.csv")

    df = compute_token_budget(rows, scenarios)
    render_markdown(df, scenarios, out_md, source=source)
    render_csv(df, out_csv)

    print(f"wrote {out_md} ({len(df)} rows × {len(scenarios)} scenarios)")
    print(f"wrote {out_csv}")
    return 0


# ---------- subcommand: report --------------------------------------------


def _cmd_report(args: argparse.Namespace) -> int:
    # Lazy import; T-19+T-20 will populate hybrid_coding_eval.cli.report.
    try:
        from hybrid_coding_eval.cli import report as report_mod
    except ModuleNotFoundError:
        print(
            "report generator not yet implemented "
            "(added by T-19). Falling back to printing the plan.",
            file=sys.stderr,
        )
        return 2
    return int(report_mod.main([args.what]) or 0)


# ---------- subcommand: schema --------------------------------------------


def _cmd_schema(args: argparse.Namespace) -> int:
    payload = dump_schema_json()
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(body, encoding="utf-8")
        print(f"wrote schema to {args.out}")
    else:
        sys.stdout.write(body)
    return 0


# ---------- dispatcher ----------------------------------------------------


def _add_config_arg(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="Path to a YAML config under configs/variants/.",
    )
    sub.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a config field. Repeatable. E.g. models.cloud=gpt-5",
    )
    sub.add_argument("--variant-tag", default=None)
    sub.add_argument("--out", type=Path, default=None)
    sub.add_argument("--smoke", action="store_true")
    sub.add_argument("--resume", action="store_true")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="bench",
        description="hybrid-coding-eval top-level CLI.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run a sweep from a YAML config.")
    _add_config_arg(p_run)
    p_run.add_argument("--dry-run", action="store_true", help="Plan only.")
    p_run.set_defaults(func=_cmd_run)

    p_show = sub.add_parser("show-config", help="Print merged config JSON.")
    _add_config_arg(p_show)
    p_show.set_defaults(func=_cmd_show_config)

    p_env = sub.add_parser("env-detect", help="Write an env-manifest.json.")
    p_env.add_argument("--out", type=Path, default=None)
    p_env.set_defaults(func=_cmd_env_detect)

    p_rescore = sub.add_parser("rescore", help="Post-sweep SWE-bench rescore.")
    p_rescore.add_argument("results_dir", type=Path)
    p_rescore.set_defaults(func=_cmd_rescore)

    p_rejudge = sub.add_parser("rejudge", help="Post-sweep Opus re-judge.")
    p_rejudge.add_argument("results_dir", type=Path)
    p_rejudge.set_defaults(func=_cmd_rejudge)

    p_analyze = sub.add_parser("analyze", help="Aggregate + ARQGC + charts.")
    p_analyze.add_argument("results_dir", type=Path)
    p_analyze.set_defaults(func=_cmd_analyze)

    p_tb = sub.add_parser(
        "token-budget",
        help="Token-first analysis — emit TOKEN_BUDGET.md + token_budget.csv.",
    )
    p_tb.add_argument(
        "results_path",
        type=Path,
        help="Path to raw.jsonl OR a runs/*/ dir containing raw.jsonl.",
    )
    p_tb.add_argument(
        "--out-md",
        type=Path,
        default=None,
        help="Markdown output path (default reports/TOKEN_BUDGET.md).",
    )
    p_tb.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="CSV output path (default next to the .md).",
    )
    p_tb.add_argument(
        "--scenarios",
        default=None,
        help="Comma-separated scenario names (default: 6 headline scenarios).",
    )
    p_tb.set_defaults(func=_cmd_token_budget)

    p_report = sub.add_parser(
        "report", help="Regenerate reports/ARTICLE, APPENDICES, etc."
    )
    p_report.add_argument(
        "what",
        choices=["article", "appendix-tasks", "appendix-scenarios", "appendix-routes", "all"],
        help="Which report artefact to render.",
    )
    p_report.set_defaults(func=_cmd_report)

    p_schema = sub.add_parser("schema", help="Dump JSON Schema for BenchConfig.")
    p_schema.add_argument("--out", type=Path, default=None)
    p_schema.set_defaults(func=_cmd_schema)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
