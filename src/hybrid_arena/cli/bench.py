"""The ``arena`` dispatcher CLI.

Subcommands:

- ``arena run --config configs/foo.yaml`` → runs one bench-run from a YAML.
- ``arena sweep --config configs/foo.yaml --strategies ... --seeds ...``
  → loops strategies × seeds in the foreground (canonical reproducer).
- ``arena show-config configs/foo.yaml`` → prints merged config JSON.
- ``arena env-detect [--out PATH]`` → writes an env-manifest.json.
- ``arena analyze RESULTS_DIR`` → aggregate → bootstrap CIs → decision matrix → charts.
- ``arena schema [--out configs/schema.json]`` → dump JSON Schema.
- ``arena setup`` → one-shot install (aider + opencode + cline + …).

v1.4+ sweep lifecycle (background, pausable, resumable):

- ``arena start --config ... --strategies ... --seeds ...``
  → spawns a sweep in the background. Auto-starts Ollama if needed.
- ``arena pause`` → kills orchestrator + agents + router; Ollama stays.
- ``arena resume`` → relaunches the paused sweep with --resume so it
  skips rows already in raw.jsonl. Picks up from where it left off.
- ``arena stop`` → like pause, but also kills Ollama (frees ~19 GB).
  Sweep state is retained for a future ``arena resume``.
- ``arena status`` → show the active sweep's PID, config, log, row count.

Every subcommand delegates to an existing module. The dispatcher owns
argparse-style dispatch, the ``run``/``sweep`` YAML→argv wiring, and
the lifecycle commands' state file (``/tmp/hcev-sweep.json``).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from hybrid_arena.core.config.loader import dump_schema_json, load_config
from hybrid_arena.core.config.resolve import apply_overrides
from hybrid_arena.core.config.schema import BenchConfig

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
    # docker) that ``arena show-config`` should not have to pay for.
    # Delegate to the existing CLI main() in cli.run. It accepts argv;
    # we translate the config back into its flag shape until T-08 lets
    # run_pair() take a BenchConfig directly.
    from hybrid_arena.cli.run import main as run_main
    from hybrid_arena.core.experiment import run_pair as _run_pair  # noqa: F401

    argv: list[str] = [
        "--out",
        str(config.out_dir),
        "--task-classes",
        ",".join(config.benchmark.task_classes),
        "--agents",
        ",".join(config.benchmark.agents),
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
    seed = getattr(args, "seed", None)
    if seed is not None:
        argv += ["--seed", str(seed)]

    # Task caps — ``run-experiment.py`` only takes a single ``--tasks N``
    # flag (cap applied uniformly across the selected categories). So we
    # can only forward a per-category cap when every listed category has
    # the *same* cap. The single-category case (e.g. the real_dev smoke)
    # falls out for free.
    tpc = config.benchmark.tasks_per_class
    if tpc:
        caps = [tpc[c] for c in config.benchmark.task_classes if c in tpc]
        if caps and len(set(caps)) == 1:
            argv += ["--tasks", str(caps[0])]
        elif caps:
            logger.warning(
                "tasks_per_class has heterogeneous caps %r for task_classes %r; "
                "--tasks only supports a single uniform cap — skipping forward. "
                "Use a dedicated variant per category for now.",
                tpc,
                config.benchmark.task_classes,
            )

    # Explicit task-ID whitelist (v1.3+) — scopes a sweep to a known-good
    # subset (e.g. the aider-compatible D1+D5 refactor tasks).
    if config.benchmark.task_ids:
        argv += ["--task-ids", ",".join(config.benchmark.task_ids)]

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
    print("# arena run plan")
    print(f"variant_tag      {config.variant_tag}")
    print(f"out_dir          {config.out_dir}")
    print(f"config_sha       {config.canonical_sha256()[:12]}…")
    print(f"cloud_model      {config.models.cloud}")
    print(f"local_model      {config.models.local}")
    print(f"router           strategy={config.router.strategy} port={config.router.port}")
    print(f"task_classes     {config.benchmark.task_classes}")
    print(f"agents           {config.benchmark.agents}")
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
    from hybrid_arena.cli.env_detect import main as env_main

    argv: list[str] = []
    if args.out:
        argv += ["--out", str(args.out)]
    return int(env_main(argv) or 0)


# ---------- subcommand: analyze -------------------------------------------


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Run the analysis pipeline on a results directory.

    Behaviour:

    * If ``args.results_dir`` directly contains a ``raw.jsonl``, analyse it.
    * Otherwise walk one level of subdirectories and analyse each
      ``raw.jsonl`` we find. This is what a sweep produces — one
      ``<strategy>/seed-<seed>/raw.jsonl`` per pass.
    """
    from hybrid_arena.analysis.all import main as analyze_main

    root: Path = args.results_dir
    if not root.exists():
        print(f"error: results path not found: {root}", file=sys.stderr)
        return 2

    if (root / "raw.jsonl").is_file():
        return int(analyze_main([str(root)]) or 0)

    # Walk one level deep — accept any subdir that has its own raw.jsonl.
    sub_raws = sorted(p.parent for p in root.glob("**/raw.jsonl") if p.is_file())
    if not sub_raws:
        print(f"error: no raw.jsonl under {root}", file=sys.stderr)
        return 2

    failed = 0
    for d in sub_raws:
        print(f"=== analysing {d} ===", file=sys.stderr)
        rc = int(analyze_main([str(d)]) or 0)
        if rc != 0:
            failed += 1
            print(f"  (rc={rc})", file=sys.stderr)
    return 1 if failed else 0


# ---------- subcommand: token-budget --------------------------------------


def _cmd_token_budget(args: argparse.Namespace) -> int:
    # Lazy imports — pandas + pricing tables aren't needed by other subcommands.
    from hybrid_arena.analysis.token_budget import (
        HEADLINE_SCENARIOS,
        compute_token_budget,
        render_csv,
        render_markdown,
    )
    from hybrid_arena.core.results import load_results

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


# ---------- setup ----------------------------------------------------------

# Opencode fork install — env-overridable so iteration can pin a
# specific SHA without code edits. See docs/HYBRID_ROUTING_DESIGN.md §3.
import os as _os

_OPENCODE_GIT_URL = _os.environ.get(
    "OPENCODE_GIT_URL",
    "https://github.com/RunanywhereAI/opencode-1.git",
)
_OPENCODE_GIT_REF = _os.environ.get("OPENCODE_GIT_REF", "feat/hybrid-routing-plugin")
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # repo root


def _ensure_opencode(verbose: bool = True) -> bool:
    """Clone the opencode fork into ``vendor/opencode/``.

    Fork + ref are env-overridable:

    - ``OPENCODE_GIT_URL`` (default ``RunanywhereAI/opencode-1``)
    - ``OPENCODE_GIT_REF`` (default ``feat/hybrid-routing-plugin``)

    Returns True on success / already-present. Idempotent.
    """
    target = _REPO_ROOT / "vendor" / "opencode"
    if (target / ".git").exists() or (target / "packages").is_dir():
        if verbose:
            print(f"  ✓ vendor/opencode/ present at {target}")
        return True
    if verbose:
        print(
            f"  Cloning opencode fork into {target}"
            f" (url={_OPENCODE_GIT_URL}, ref={_OPENCODE_GIT_REF})…"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    import subprocess

    try:
        subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--branch", _OPENCODE_GIT_REF,
                _OPENCODE_GIT_URL,
                str(target),
            ],
            check=True,
            capture_output=not verbose,
        )
        if verbose:
            print("  ✓ vendor/opencode/ ready")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"  ✗ git clone failed: {exc}", file=sys.stderr)
        print(
            f"    Manually clone: cd vendor && "
            f"git clone -b {_OPENCODE_GIT_REF} {_OPENCODE_GIT_URL} opencode",
            file=sys.stderr,
        )
        return False


def _ensure_opencode_config(verbose: bool = True) -> bool:
    """Ensure ``~/.config/opencode/opencode.json`` has the hybrid-router provider.

    If the file already mentions ``hybrid-router`` (substring), leave it
    alone. Otherwise back it up (or create fresh) with a minimal config
    pointing at the proxy on :8787. The opencode runner expects the model
    id shape ``hybrid-router/router/<strategy>[/run-<id>]``.
    """
    import os
    from pathlib import Path as _P

    config_dir = _P(os.path.expanduser("~/.config/opencode"))
    config_path = config_dir / "opencode.json"

    if config_path.exists():
        try:
            existing = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            if verbose:
                print(f"  ✗ couldn't read {config_path}: {exc}")
            return False
        if "hybrid-router" in existing:
            if verbose:
                print(f"  ✓ {config_path} already registers hybrid-router")
            return True
        # User has an opencode.json without hybrid-router. Back it up first.
        backup = config_path.with_suffix(".json.pre-bench-setup")
        backup.write_text(existing, encoding="utf-8")
        if verbose:
            print(f"  → backed up existing config to {backup}")

    config_dir.mkdir(parents=True, exist_ok=True)
    minimal = {
        "$schema": "https://opencode.ai/config.json",
        "providers": {
            "hybrid-router": {
                "type": "openai",
                "base_url": "http://127.0.0.1:8787/v1",
                "api_key": "bench-eval-key",
                "models": {
                    "router/heuristic":     {"name": "router/heuristic"},
                    "router/cascade":       {"name": "router/cascade"},
                    "router/always-cloud":  {"name": "router/always-cloud"},
                    "router/always-local":  {"name": "router/always-local"},
                },
            },
        },
    }
    config_path.write_text(json.dumps(minimal, indent=2) + "\n", encoding="utf-8")
    if verbose:
        print(f"  ✓ wrote {config_path} with hybrid-router provider")
    return True


def _ensure_cline_install(verbose: bool = True) -> bool:
    """Ensure cline 3.0.9+ is on PATH. Install via npm if missing.

    The runtime is a node binary (NOT a pip package), so it sits in
    /opt/homebrew/bin/cline on macOS or /usr/local/bin/cline on Linux.
    Idempotent: skips install if already present.
    """
    import shutil
    import subprocess

    if shutil.which("cline"):
        if verbose:
            print(f"  ✓ cline already installed at {shutil.which('cline')}")
        return True

    if not shutil.which("npm"):
        print("  ✗ npm not on PATH — install Node.js first (https://nodejs.org).",
              file=sys.stderr)
        return False

    if verbose:
        print("  Installing cline@3.0.9 via npm (~50 MB)...")
    try:
        subprocess.run(
            ["npm", "install", "-g", "cline@3.0.9"],
            check=True,
            capture_output=not verbose,
        )
        if verbose:
            print(f"  ✓ cline installed at {shutil.which('cline')}")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"  ✗ cline install failed: {exc}", file=sys.stderr)
        return False


def _ensure_cline_config(verbose: bool = True) -> bool:
    """Ensure ~/.cline/data/settings/providers.json has the ollama provider
    pointed at our router proxy.

    If the file already mentions 'ollama' provider, leave it alone.
    Otherwise back up (if exists) and write a minimal config.
    """
    import os
    from pathlib import Path as _P

    config_dir = _P(os.path.expanduser("~/.cline/data/settings"))
    config_path = config_dir / "providers.json"

    if config_path.exists():
        try:
            existing_raw = config_path.read_text(encoding="utf-8")
            existing = json.loads(existing_raw)
        except (OSError, json.JSONDecodeError) as exc:
            if verbose:
                print(f"  ✗ couldn't read {config_path}: {exc}", file=sys.stderr)
            return False
        if "ollama" in existing.get("providers", {}):
            if verbose:
                print(f"  ✓ {config_path} already registers ollama provider")
            return True
        # Existing config without ollama — back it up
        backup = config_path.with_suffix(".json.pre-bench-setup")
        backup.write_text(existing_raw, encoding="utf-8")
        if verbose:
            print(f"  → backed up existing config to {backup}")

    config_dir.mkdir(parents=True, exist_ok=True)
    minimal = {
        "providers": {
            "ollama": {
                "baseUrl": "http://127.0.0.1:8787/v1",
                "apiKey": "bench-eval-key",
            },
        },
    }
    config_path.write_text(json.dumps(minimal, indent=2) + "\n", encoding="utf-8")
    if verbose:
        print(f"  ✓ wrote {config_path} with ollama provider")
    return True


def _cmd_setup(args: argparse.Namespace) -> int:  # noqa: ARG001
    """One-shot setup: build Docker image, pull aux models, install agents, sanity-check env.

    Idempotent — safe to re-run.
    """
    import shutil
    import subprocess

    print("=== arena setup — preparing the benchmark harness ===\n")
    failures = []

    # 1. Docker image for functional scoring sandbox
    print("[1/7] Functional-scoring Docker image (hybrid-eval-python:latest)")
    if not shutil.which("docker"):
        print("  ⚠ docker not on PATH — skipping image build")
        print("    Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
    else:
        # Fail fast if the daemon is down — building images and other
        # docker subcommands will hang for many seconds before timing out.
        try:
            subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("  ⚠ docker daemon is not running — start Docker Desktop and re-run `./arena setup`.")
            failures.append("Docker daemon not running")
        try:
            subprocess.run(
                ["docker", "image", "inspect", "hybrid-eval-python:latest"],
                check=True,
                capture_output=True,
            )
            print("  ✓ hybrid-eval-python:latest already built")
        except subprocess.CalledProcessError:
            dockerfile = _REPO_ROOT / "src" / "hybrid_arena" / "scorers" / "Dockerfile.functional_python"
            print(f"  Building hybrid-eval-python:latest from {dockerfile}…")
            try:
                subprocess.run(
                    ["docker", "build", "-f", str(dockerfile), "-t", "hybrid-eval-python:latest", str(_REPO_ROOT)],
                    check=True,
                )
                print("  ✓ Docker image built")
            except subprocess.CalledProcessError as exc:
                print(f"  ⚠ docker build failed: {exc}")
                failures.append("Docker image build failed")

    # 2. Auxiliary Ollama models (router strategies)
    print("\n[2/7] Auxiliary local models (router classifier + embedding)")
    if not shutil.which("ollama"):
        print("  ⚠ ollama not on PATH — skipping model pulls")
        print("    Install Ollama: https://ollama.com/download")
    else:
        aux_models = [
            ("qwen3:0.6b", "router llm-classifier strategy", "~520 MB"),
            ("nomic-embed-text", "router embedding-knn strategy", "~270 MB"),
        ]
        for tag, purpose, size in aux_models:
            try:
                result = subprocess.run(
                    ["ollama", "list"], check=True, capture_output=True, text=True
                )
                if tag.split(":")[0] in result.stdout:
                    print(f"  ✓ {tag} already pulled ({purpose})")
                    continue
                print(f"  Pulling {tag} for {purpose} ({size})…")
                subprocess.run(["ollama", "pull", tag], check=True)
                print(f"  ✓ {tag} pulled")
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                print(f"  ⚠ pull failed for {tag}: {exc}")

    # 3. Aider agent. Installed into the repo's venv so the aider runner's
    # ``.venv/bin/aider`` fallback picks it up without needing system PATH.
    print("\n[3/7] aider agent")
    aider_bin = _REPO_ROOT / ".venv" / "bin" / "aider"
    if aider_bin.exists():
        print(f"  ✓ aider already installed at {aider_bin}")
    else:
        venv_pip = _REPO_ROOT / ".venv" / "bin" / "pip"
        if not venv_pip.exists():
            print("  ⚠ no .venv/bin/pip — set up venv first: python3.12 -m venv .venv && .venv/bin/pip install -e .")
            failures.append("aider install skipped: no venv")
        else:
            print(f"  Installing aider-chat into {venv_pip.parent}…")
            try:
                subprocess.run([str(venv_pip), "install", "-q", "aider-chat"], check=True)
                print(f"  ✓ aider installed: {aider_bin}")
            except subprocess.CalledProcessError as exc:
                print(f"  ⚠ aider install failed: {exc}")
                failures.append("aider install failed")

    # 4. mini-swe-agent — bash-only ReAct, the SWE-bench Verified
    # apples-to-apples reference. Installed into the repo's venv so the
    # runner's ``.venv/bin/mini-extra`` fallback picks it up.
    print("\n[4/7] mini-swe-agent")
    mini_extra_bin = _REPO_ROOT / ".venv" / "bin" / "mini-extra"
    if mini_extra_bin.exists():
        print(f"  ✓ mini-swe-agent already installed at {mini_extra_bin}")
    else:
        venv_pip = _REPO_ROOT / ".venv" / "bin" / "pip"
        if not venv_pip.exists():
            print("  ⚠ no .venv/bin/pip — set up venv first: python3.12 -m venv .venv && .venv/bin/pip install -e .")
            failures.append("mini-swe-agent install skipped: no venv")
        else:
            print(f"  Installing mini-swe-agent>=2.2,<3 into {venv_pip.parent}…")
            try:
                subprocess.run(
                    [str(venv_pip), "install", "-q", "mini-swe-agent>=2.2,<3"],
                    check=True,
                )
                print(f"  ✓ mini-swe-agent installed: {mini_extra_bin}")
            except subprocess.CalledProcessError as exc:
                print(f"  ⚠ mini-swe-agent install failed: {exc}")
                failures.append("mini-swe-agent install failed")

    # 5. Opencode fork — opt-in via env because the fork clone is large
    # and gemma4-specific (qwen variants do not benefit; see release notes).
    if _os.environ.get("BENCH_SETUP_OPENCODE", "0") in ("1", "true", "yes"):
        print("\n[5/7] opencode (opt-in via BENCH_SETUP_OPENCODE=1)")
        if not shutil.which("opencode"):
            print("  ⚠ opencode CLI not on PATH — the opencode agent won't work")
            print("    Install via Homebrew: brew install opencode")
        else:
            print("  ✓ opencode CLI on PATH")
        if not _ensure_opencode(verbose=True):
            failures.append("opencode fork clone failed")
        if not _ensure_opencode_config(verbose=True):
            failures.append("opencode.json config setup failed")
    else:
        print("\n[5/7] opencode — SKIPPED (opt-in)")
        print("  To enable: BENCH_SETUP_OPENCODE=1 ./arena setup")

    # 6. cline agent — LiteLLM-compatible CLI. The npm package is installed
    # globally so ``cline`` ends up on PATH; the providers.json points it at
    # our router proxy on :8787.
    print("\n[6/7] cline agent")
    if not _ensure_cline_install(verbose=True):
        failures.append("cline install failed")
    if not _ensure_cline_config(verbose=True):
        failures.append("cline providers.json setup failed")

    # 7. Environment sanity (.env file, Python version)
    print("\n[7/7] Environment sanity")
    env_path = _REPO_ROOT / ".env"
    env_example = _REPO_ROOT / ".env.example"
    if env_path.exists():
        print(f"  ✓ .env exists at {env_path}")
    elif env_example.exists():
        print("  ⚠ .env not found — copy .env.example and add your API keys:")
        print("      cp .env.example .env && $EDITOR .env")
    else:
        print("  ⚠ .env not found and no .env.example template; create .env with OPEN_AI_API_KEY")

    if sys.version_info < (3, 11):
        print(f"  ⚠ Python {sys.version_info.major}.{sys.version_info.minor} — repo requires 3.11+")
        failures.append("Python < 3.11")
    else:
        print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}")

    # Summary
    print("\n=== Setup summary ===")
    if failures:
        print(f"  ⚠ {len(failures)} issue(s): {', '.join(failures)}")
        print("\nFix the items above, then re-run `./arena setup`. Once clean, try:")
    else:
        print("  ✓ All checks passed.")
        print("\nNext:")
    print("  1. Ensure .env has OPEN_AI_API_KEY (required to call gpt-5.5 through the router).")
    print("  2. (Optional, only for hybrid/local sweeps) `ollama pull gemma4:31b` (or qwen3-coder:30b / qwen3.6:35b).")
    print("  3. Run the smoke sweep:  `./arena sweep --config configs/v1.4-smoke.yaml`.")
    print("     The router proxy is auto-spawned from `models.local`.")
    return 1 if failures else 0


# ---------- sweep lifecycle (start / pause / resume / stop / status) -------
#
# v1.4 lifecycle commands wrap `./arena sweep` so a long sweep can be
# detached, paused (to free the laptop), and resumed without losing
# already-completed rows.
#
# State lives in two files under ``/tmp/`` (single-host single-sweep):
#
#   /tmp/hcev-sweep.json         {pid, config, strategies, seeds, started_at}
#                                — present while a sweep is running
#   /tmp/hcev-sweep.paused.json  — same payload, renamed when paused
#
# Cleanup helpers handle the heavy resources (router proxy + ollama
# runners). Ollama.app itself is left alone for fast resume by default;
# ``./arena stop`` kills it.

_SWEEP_STATE = Path("/tmp/hcev-sweep.json")
_SWEEP_STATE_PAUSED = Path("/tmp/hcev-sweep.paused.json")


def _proc_alive(pid: int) -> bool:
    """Return True if process ``pid`` is alive."""
    try:
        import os as _os
        _os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_pid_tree(pid: int, verbose: bool = False) -> None:
    """SIGTERM the process and any descendants. SIGKILL after 5s if still alive."""
    import os as _os
    import signal as _sig
    import time as _t
    # Collect descendants via pgrep -P (recursive)
    def descendants(root: int) -> list[int]:
        try:
            out = subprocess.check_output(
                ["pgrep", "-P", str(root)], text=True
            ).split()
            kids = [int(p) for p in out]
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        all_kids = list(kids)
        for k in kids:
            all_kids.extend(descendants(k))
        return all_kids

    tree = [pid] + descendants(pid)
    for p in reversed(tree):
        try:
            _os.kill(p, _sig.SIGTERM)
            if verbose:
                print(f"  SIGTERM pid={p}")
        except (OSError, ProcessLookupError):
            pass
    # Wait briefly, then force-kill stragglers.
    _t.sleep(2)
    for p in reversed(tree):
        if _proc_alive(p):
            try:
                _os.kill(p, _sig.SIGKILL)
                if verbose:
                    print(f"  SIGKILL pid={p}")
            except (OSError, ProcessLookupError):
                pass


def _kill_agent_subprocs(verbose: bool = False) -> None:
    """Kill in-flight agent subprocesses (aider/opencode/cline/mini-extra).

    Independent of the sweep PID-tree because these are spawned via the
    benchmark runner and may outlive a faulty kill of the parent.
    """
    patterns = [
        "aider --architect",
        "opencode run -m",
        "cline -P ollama",
        "mini-extra swebench-single",
        "claude -p",
    ]
    for pat in patterns:
        try:
            subprocess.run(
                ["pkill", "-f", pat],
                check=False, capture_output=True
            )
            if verbose:
                print(f"  pkill -f {pat!r}")
        except FileNotFoundError:
            pass


def _kill_router_on_port(port: int = 8787, verbose: bool = False) -> None:
    """Kill any process listening on the router port."""
    try:
        out = subprocess.check_output(
            ["lsof", "-t", f"-i:{port}"], text=True
        ).split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for p in out:
        try:
            import os as _os
            import signal as _sig
            _os.kill(int(p), _sig.SIGTERM)
            if verbose:
                print(f"  router pid={p} → SIGTERM")
        except (OSError, ValueError):
            pass


def _ollama_running() -> bool:
    """Return True iff Ollama is reachable on its default port."""
    try:
        import urllib.request as _ur
        with _ur.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5):
            return True
    except Exception:
        return False


def _ensure_ollama_running(verbose: bool = True) -> bool:
    """Start Ollama.app if not already up. macOS-specific (uses `open -a`)."""
    if _ollama_running():
        if verbose:
            print("  ✓ ollama already running")
        return True
    if verbose:
        print("  ollama not running — starting Ollama.app…")
    try:
        subprocess.run(["open", "-a", "Ollama"], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"  ✗ couldn't auto-start Ollama: {exc}", file=sys.stderr)
        print("    Start it manually then retry: `ollama serve` or open Ollama.app",
              file=sys.stderr)
        return False
    # Poll for it to be up.
    import time as _t
    for _ in range(20):
        if _ollama_running():
            if verbose:
                print("  ✓ ollama up")
            return True
        _t.sleep(1)
    print("  ✗ ollama never came up after 20s", file=sys.stderr)
    return False


def _kill_ollama_runners(verbose: bool = False) -> None:
    """Kill Ollama's model runner subprocesses (the heavy memory hogs).

    The Ollama.app + serve are kept; only the per-model runner processes
    that hold the 19GB-class models in RAM are terminated. This frees
    most of the memory but lets the user / scripts re-pull models fast.
    """
    try:
        subprocess.run(
            ["pkill", "-f", "ollama runner"],
            check=False, capture_output=True
        )
        if verbose:
            print("  pkilled ollama runner processes")
    except FileNotFoundError:
        pass


def _kill_ollama_fully(verbose: bool = False) -> None:
    """Kill Ollama runners + .app + serve. Fully releases ~19 GB RAM."""
    _kill_ollama_runners(verbose=verbose)
    try:
        subprocess.run(["pkill", "-f", "ollama serve"], check=False, capture_output=True)
        subprocess.run(["pkill", "-x", "Ollama"], check=False, capture_output=True)
        if verbose:
            print("  pkilled Ollama.app + serve")
    except FileNotFoundError:
        pass


def _read_sweep_state() -> tuple[Path, dict] | tuple[None, None]:
    """Return (state_file, payload) for whichever state file exists."""
    for path in (_SWEEP_STATE, _SWEEP_STATE_PAUSED):
        if path.exists():
            try:
                return path, json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return None, None


def _write_sweep_state(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _cmd_start(args: argparse.Namespace) -> int:
    """Start a sweep in the background.

    Wraps `./arena sweep` in a detached process. Auto-starts Ollama if
    it's not running. Writes /tmp/hcev-sweep.json with the active PID +
    sweep parameters so `./arena pause/resume/stop/status` can find it.
    """
    import datetime as _dt
    # Refuse to start a new sweep if one is already active.
    state_file, state = _read_sweep_state()
    if state_file == _SWEEP_STATE and state and _proc_alive(state.get("pid", -1)):
        print(
            f"a sweep is already running (pid={state['pid']}, config={state.get('config')}).",
            file=sys.stderr,
        )
        print("  pause it first:  ./arena pause", file=sys.stderr)
        return 1
    # Stale state file → clean up.
    if state_file == _SWEEP_STATE:
        state_file.unlink()

    # Ensure Ollama is up.
    if not _ensure_ollama_running():
        return 1

    # Build the sweep argv.
    cmd = [
        sys.executable, "-m", "hybrid_arena.cli.bench", "sweep",
        "--config", str(args.config),
        "--strategies", args.strategies,
        "--seeds", args.seeds,
    ]
    if args.cascade_thresholds:
        cmd.extend(["--cascade-thresholds", args.cascade_thresholds])
    if args.external_router:
        cmd.append("--external-router")
    if args.resume:
        # Plumb `resume=true` via --set so the per-pass `arena run` picks it up.
        cmd.extend(["--set", "resume=true"])

    # Resolve out_dir for log placement.
    config = _load_merged(args)
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "sweep.log"

    # Spawn detached. The child writes both stdout and stderr to log_file.
    print(f"starting sweep: {args.config}")
    print(f"  strategies: {args.strategies}")
    print(f"  seeds:      {args.seeds}")
    if args.resume:
        print("  resume:     true (skipping rows already in raw.jsonl)")
    print(f"  log:        {log_file}")
    logf = open(log_file, "ab")
    proc = subprocess.Popen(
        cmd, stdout=logf, stderr=logf, start_new_session=True,
    )

    payload = {
        "pid": proc.pid,
        "config": str(args.config),
        "strategies": args.strategies,
        "seeds": args.seeds,
        "cascade_thresholds": args.cascade_thresholds,
        "external_router": bool(args.external_router),
        "resume": bool(args.resume),
        "out_dir": str(out_dir),
        "log": str(log_file),
        "started_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    _write_sweep_state(_SWEEP_STATE, payload)
    print(f"  ✓ sweep started pid={proc.pid}")
    print(f"  state:      {_SWEEP_STATE}")
    print("  status:     ./arena status")
    print("  pause:      ./arena pause")
    return 0


def _cmd_pause(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Pause the active sweep: kill orchestrator + agents + router; keep Ollama."""
    state_file, state = _read_sweep_state()
    if state_file is None:
        print("no sweep state found; nothing to pause")
        return 0
    if state_file == _SWEEP_STATE_PAUSED:
        print("sweep already paused; resume with: ./arena resume")
        return 0

    pid = state.get("pid", -1)
    if not _proc_alive(pid):
        print(f"sweep pid={pid} is not running (state may be stale)")
        # Treat as a graceful pause: move state to paused.
        _SWEEP_STATE.rename(_SWEEP_STATE_PAUSED)
        return 0

    print(f"pausing sweep pid={pid}…")
    # 1. Kill agent subprocesses (heavy)
    _kill_agent_subprocs(verbose=True)
    # 2. Kill orchestrator + bench-sweep python (whole tree)
    _kill_pid_tree(pid, verbose=True)
    # 3. Kill router on default port
    port = 8787
    _kill_router_on_port(port=port, verbose=True)
    # Mark paused.
    _SWEEP_STATE.rename(_SWEEP_STATE_PAUSED)
    print("  ✓ paused. Ollama still running for fast resume.")
    print("  resume:    ./arena resume")
    print("  stop+free: ./arena stop")
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    """Resume a paused sweep. Reads state from /tmp/hcev-sweep.paused.json."""
    state_file, state = _read_sweep_state()
    if state_file is None:
        print("no paused sweep found; start fresh with: ./arena start --config <yaml> --strategies ... --seeds ...",
              file=sys.stderr)
        return 1
    if state_file == _SWEEP_STATE and _proc_alive(state.get("pid", -1)):
        print("a sweep is already running; ./arena pause first or ./arena status to see", file=sys.stderr)
        return 1

    # Reconstruct args from state + override with --resume.
    print(f"resuming sweep from state: {state_file}")
    print(f"  config:     {state.get('config')}")
    print(f"  strategies: {state.get('strategies')}")
    print(f"  seeds:      {state.get('seeds')}")
    resume_args = argparse.Namespace(
        config=Path(state["config"]),
        set=[],
        variant_tag=None,
        out=None,
        smoke=False,
        resume=True,
        strategies=state["strategies"],
        seeds=state["seeds"],
        cascade_thresholds=state.get("cascade_thresholds"),
        external_router=bool(state.get("external_router", False)),
        dry_run=False,
    )
    # Clean up paused-state file; _cmd_start will write a fresh active state.
    state_file.unlink()
    return _cmd_start(resume_args)


def _cmd_stop(args: argparse.Namespace) -> int:
    """Stop the active sweep AND release Ollama memory.

    Like ``./arena pause`` but also kills Ollama runners + .app to free
    ~19 GB of RAM the local models are holding. Use when you're done
    with the sweep for the day and want the laptop back fully.
    """
    rc = _cmd_pause(args)
    print()
    print("killing Ollama (releases ~19 GB)…")
    if getattr(args, "keep_ollama_app", False):
        _kill_ollama_runners(verbose=True)
        print("  Ollama.app kept; only runners killed")
    else:
        _kill_ollama_fully(verbose=True)
    # Clear paused state too — stop is more terminal than pause.
    if _SWEEP_STATE_PAUSED.exists():
        # Keep a copy at the resume-friendly location so the user can still
        # resume later. Caller passing --clear deletes it.
        if getattr(args, "clear_state", False):
            _SWEEP_STATE_PAUSED.unlink()
            print("  sweep state cleared (won't be resumable without re-passing args)")
        else:
            print(f"  sweep state retained at {_SWEEP_STATE_PAUSED}")
            print("  resume later with: ./arena resume")
    return rc


def _cmd_status(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Show whether a sweep is running, paused, or absent."""
    state_file, state = _read_sweep_state()
    if state_file is None:
        print("status: NO SWEEP")
        print("  start one with: ./arena start --config <yaml> --strategies ... --seeds ...")
        return 0

    is_paused = (state_file == _SWEEP_STATE_PAUSED)
    pid = state.get("pid", -1)
    alive = _proc_alive(pid)

    if is_paused:
        print("status: PAUSED")
    elif alive:
        print("status: RUNNING")
    else:
        print("status: STALE (state present but pid not alive)")
    print(f"  pid:        {pid}{' (alive)' if alive else ' (dead)'}")
    print(f"  config:     {state.get('config')}")
    print(f"  strategies: {state.get('strategies')}")
    print(f"  seeds:      {state.get('seeds')}")
    if state.get("cascade_thresholds"):
        print(f"  thresholds: {state.get('cascade_thresholds')}")
    print(f"  out_dir:    {state.get('out_dir')}")
    print(f"  log:        {state.get('log')}")
    print(f"  started:    {state.get('started_at')}")
    # Row count for visibility
    out_dir = state.get("out_dir")
    if out_dir and Path(out_dir).exists():
        n = 0
        for f in Path(out_dir).rglob("raw.jsonl"):
            try:
                n += sum(1 for _ in f.open())
            except OSError:
                pass
        print(f"  rows so far: {n}")
    return 0


# ---------- sweep ---------------------------------------------------------


def _load_dotenv(env: dict[str, str]) -> None:
    """Merge KEY=VALUE lines from ``.env`` into ``env`` (no overwrite of
    existing keys). Used by :func:`_spawn_router` so spawned routers see
    ``OPEN_AI_API_KEY`` / ``OPENAI_API_KEY`` etc. without requiring the
    parent shell to source ``.env``."""
    dotenv_path = _REPO_ROOT / ".env"
    if not dotenv_path.is_file():
        return
    try:
        for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in env:
                env[key] = value
        if "OPEN_AI_API_KEY" in env and "OPENAI_API_KEY" not in env:
            env["OPENAI_API_KEY"] = env["OPEN_AI_API_KEY"]
    except OSError:
        pass


def _spawn_router(env_overrides: dict[str, str], port: int = 8787) -> "subprocess.Popen[bytes]":
    """Spawn ``node router/server.mjs`` with the given env overrides.

    Used by the v1.3+ ``--cascade-thresholds`` sweep so each threshold sees
    a router instance with ``ROUTER_CASCADE_THRESHOLD`` set. Waits up to
    20 s for ``/healthz`` to return 200 before returning. Caller is
    responsible for killing the returned ``Popen`` when done.
    """
    import os as _os
    import subprocess as _sp
    import time as _t
    import urllib.error as _ue
    import urllib.request as _ur

    server_mjs = _REPO_ROOT / "router" / "server.mjs"
    if not server_mjs.is_file():
        raise FileNotFoundError(f"router/server.mjs not found at {server_mjs}")

    env = _os.environ.copy()
    _load_dotenv(env)
    env.update(env_overrides)
    env["PORT"] = str(port)

    log_dir = _REPO_ROOT / "results" / "router-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"router-{port}-{int(_t.time())}.log"
    log_file = open(log_path, "ab")
    proc = _sp.Popen(
        ["node", str(server_mjs)],
        cwd=str(_REPO_ROOT / "router"),
        env=env,
        stdout=log_file,
        stderr=_sp.STDOUT,
    )

    # Wait for /healthz to come up.
    deadline = _t.time() + 20.0
    last_err: Exception | None = None
    while _t.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"router exited prematurely (rc={proc.returncode}); log: {log_path}"
            )
        try:
            with _ur.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1.0) as resp:
                if resp.status == 200:
                    print(f"  ✓ router up on :{port} (env: {env_overrides}) — log: {log_path}")
                    return proc
        except (_ue.URLError, ConnectionError, OSError) as exc:
            last_err = exc
        _t.sleep(0.25)
    proc.terminate()
    raise RuntimeError(f"router never healthy on :{port} after 20s: {last_err!r}")


def _kill_router(proc: "subprocess.Popen[bytes]") -> None:
    """Politely terminate the router proc started by :func:`_spawn_router`."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except Exception:  # noqa: BLE001
        proc.kill()


def _is_router_up(port: int) -> bool:
    """Return True if a router is already reachable on ``port``.

    Used to decide whether ``arena sweep`` should auto-spawn a router or
    defer to an already-running instance (the user's choice via
    ``--external-router`` or an inadvertent leftover).
    """
    import urllib.error as _ue
    import urllib.request as _ur

    try:
        with _ur.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.5) as resp:
            return resp.status == 200
    except (_ue.URLError, ConnectionError, OSError):
        return False


@contextmanager
def _router_for_model(
    local_model: str,
    port: int,
    *,
    cloud_model: str | None = None,
    external: bool = False,
    extra_env: dict[str, str] | None = None,
) -> Iterator[None]:
    """Context manager that yields with a healthy router on ``port``.

    If ``external`` is True OR a router is already healthy on the port,
    yields without spawning (caller-managed lifecycle). Otherwise spawns
    ``node router/server.mjs`` with ``LOCAL_MODEL=<local_model>``,
    ``CLOUD_MODEL=<cloud_model>``, and any ``extra_env`` (e.g.
    ``ROUTER_CASCADE_THRESHOLD``), waits for ``/healthz``, and tears down
    on exit.

    This is the shared lifecycle helper for ``arena sweep`` — both the
    regular path and the ``--cascade-thresholds`` path use it.
    """
    if external:
        if not _is_router_up(port):
            print(
                f"  ! --external-router set but no router responding on :{port}; "
                f"continuing anyway (passes may fail).",
                file=sys.stderr,
            )
        else:
            print(f"  ✓ using external router on :{port}")
        yield
        return

    if _is_router_up(port):
        print(
            f"  ✓ router already up on :{port} — not respawning "
            f"(use --external-router to silence this auto-spawn check)"
        )
        yield
        return

    env_overrides: dict[str, str] = {"LOCAL_MODEL": local_model}
    if cloud_model:
        env_overrides["CLOUD_MODEL"] = cloud_model
    if extra_env:
        env_overrides.update(extra_env)
    proc = _spawn_router(env_overrides, port=port)
    try:
        yield
    finally:
        _kill_router(proc)
        cloud_note = f", CLOUD_MODEL={cloud_model}" if cloud_model else ""
        print(f"--- killed router (LOCAL_MODEL={local_model}{cloud_note}) ---")


def _cmd_sweep(args: argparse.Namespace) -> int:
    """Loop a single YAML config across multiple strategies × seeds.

    The reproducer for v1.1+ canonical sweeps. Replaces the deleted
    bin/v4*.sh scripts. Each ``(strategy, seed)`` combination writes to
    its own subdirectory under ``out_dir``::

        <out_dir>/<strategy>/seed-<seed>/raw.jsonl

    so the analysis layer (./arena analyze + bootstrap) can stratify by
    both axes without raw.jsonl key collisions.

    v1.3+: ``--cascade-thresholds N1,N2,…`` sweeps the cascade strategy
    only, spawning a fresh router per threshold so ROUTER_CASCADE_THRESHOLD
    is observed. Layout becomes ``<out_dir>/cascade-threshold-<N>/seed-<seed>/``.

    v1.4+: the sweep auto-spawns ``node router/server.mjs`` with
    ``LOCAL_MODEL=<config.models.local>`` (so the user no longer needs
    a separate ``(cd router && ./start.sh) &`` terminal) and tears it
    down on completion. Pass ``--external-router`` to opt out.
    """
    cascade_thresholds_arg = getattr(args, "cascade_thresholds", None)
    cascade_thresholds: list[int] | None = None
    if cascade_thresholds_arg:
        cascade_thresholds = [int(s.strip()) for s in cascade_thresholds_arg.split(",") if s.strip()]
        if not cascade_thresholds:
            print("error: --cascade-thresholds must list at least one integer", file=sys.stderr)
            return 2

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    seeds_arg = args.seeds or "42"
    seeds = [int(s.strip()) for s in seeds_arg.split(",") if s.strip()]
    if not strategies:
        print("error: --strategies must list at least one strategy", file=sys.stderr)
        return 2

    # --cascade-thresholds implies --strategies cascade; warn if the user
    # passed others.
    if cascade_thresholds is not None:
        non_cascade = [s for s in strategies if s != "cascade"]
        if non_cascade:
            print(
                f"warning: --cascade-thresholds is set; ignoring non-cascade "
                f"strategies: {non_cascade}",
                file=sys.stderr,
            )
        strategies = ["cascade"]

    # Resolve base_out once (so per-pass overrides redirect into subdirs).
    base_config = _load_merged(args)
    base_out = Path(args.out) if args.out else Path(base_config.out_dir)
    base_out.mkdir(parents=True, exist_ok=True)

    if cascade_thresholds is not None:
        total = len(cascade_thresholds) * len(seeds)
        print(
            f"# arena sweep (cascade-threshold mode): "
            f"{len(cascade_thresholds)} thresholds × {len(seeds)} seeds "
            f"= {total} runs → {base_out}"
        )
    else:
        total = len(strategies) * len(seeds)
        print(
            f"# arena sweep: {len(strategies)} strategies × {len(seeds)} seeds "
            f"= {total} runs → {base_out}"
        )

    failures: list[tuple[str, int, int]] = []

    def _run_pass(
        pass_idx: int,
        strat: str,
        seed: int,
        sub_out: Path,
        threshold: int | None = None,
    ) -> None:
        tag = f"strategy={strat} seed={seed}"
        if threshold is not None:
            tag = f"strategy={strat} threshold={threshold} seed={seed}"
        print(f"\n=== [{pass_idx}/{total}] {tag} → {sub_out} ===")
        sub_args = argparse.Namespace(
            config=args.config,
            set=list(args.set or []) + [
                f"router.strategy={strat}",
                f"out_dir={sub_out}",
            ],
            variant_tag=None,
            out=sub_out,
            smoke=args.smoke,
            resume=args.resume,
            dry_run=args.dry_run,
            seed=seed,
        )
        try:
            ret = _cmd_run(sub_args)
        except Exception as exc:  # noqa: BLE001 — keep sweep alive
            print(f"  ! pass crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
            ret = 99
        if ret != 0:
            failures.append((strat if threshold is None else f"cascade@{threshold}", seed, ret))

    port = base_config.router.port
    local_model = base_config.models.local
    cloud_model = base_config.models.cloud
    external_router = bool(getattr(args, "external_router", False))

    if cascade_thresholds is not None:
        # Spawn a fresh router per threshold; loop seeds inside.
        # Each pass injects ROUTER_CASCADE_THRESHOLD on top of LOCAL_MODEL.
        idx = 0
        for threshold in cascade_thresholds:
            if args.dry_run:
                print(
                    f"\n--- (dry-run) would spawn router with "
                    f"LOCAL_MODEL={local_model} "
                    f"ROUTER_CASCADE_THRESHOLD={threshold} ---"
                )
                for seed in seeds:
                    idx += 1
                    sub_out = base_out / f"cascade-threshold-{threshold}" / f"seed-{seed}"
                    _run_pass(idx, "cascade", seed, sub_out, threshold=threshold)
                continue
            print(
                f"\n--- spawning router with LOCAL_MODEL={local_model} "
                f"ROUTER_CASCADE_THRESHOLD={threshold} ---"
            )
            try:
                with _router_for_model(
                    local_model,
                    port,
                    cloud_model=cloud_model,
                    external=external_router,
                    extra_env={"ROUTER_CASCADE_THRESHOLD": str(threshold)},
                ):
                    for seed in seeds:
                        idx += 1
                        sub_out = base_out / f"cascade-threshold-{threshold}" / f"seed-{seed}"
                        _run_pass(idx, "cascade", seed, sub_out, threshold=threshold)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"  ! router spawn failed for threshold={threshold}: {exc}",
                    file=sys.stderr,
                )
                for seed in seeds:
                    idx += 1
                    failures.append((f"cascade@{threshold}", seed, 98))
                continue
    else:
        # Regular sweep — auto-spawn one router for the whole sweep with the
        # config's local model so every (strategy, seed) pass sees the same
        # backend without manual router lifecycle. Skipped if --external-router
        # is set OR a router is already healthy on the port.
        if args.dry_run:
            print(
                f"\n--- (dry-run) would spawn router with LOCAL_MODEL={local_model} ---"
            )
            idx = 0
            for strat in strategies:
                for seed in seeds:
                    idx += 1
                    sub_out = base_out / strat / f"seed-{seed}"
                    _run_pass(idx, strat, seed, sub_out)
        else:
            try:
                with _router_for_model(
                    local_model,
                    port,
                    cloud_model=cloud_model,
                    external=external_router,
                ):
                    idx = 0
                    for strat in strategies:
                        for seed in seeds:
                            idx += 1
                            sub_out = base_out / strat / f"seed-{seed}"
                            _run_pass(idx, strat, seed, sub_out)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! router spawn failed: {exc}", file=sys.stderr)
                # The context manager raised before any pass could run —
                # mark every (strategy, seed) as failed for the summary.
                for strat in strategies:
                    for seed in seeds:
                        failures.append((strat, seed, 98))

    print("\n=== sweep summary ===")
    print(f"  total passes : {total}")
    print(f"  successful   : {total - len(failures)}")
    print(f"  failed       : {len(failures)}")
    for strat, seed, ret in failures:
        print(f"    - [{strat}, seed={seed}]: exit {ret}")
    print(f"  output       : {base_out}")
    print(f"  next step    : ./arena analyze {base_out}")
    return 1 if failures else 0


# ---------- dispatcher ----------------------------------------------------


def _add_config_arg(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="Path to a sweep YAML config under configs/ (e.g. configs/v1.4-canonical-gemma4.yaml).",
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
        prog="arena",
        description="Hybrid Coding Arena top-level CLI.",
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

    p_analyze = sub.add_parser(
        "analyze",
        help="Aggregate + bootstrap CIs + decision matrix + charts.",
    )
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

    p_schema = sub.add_parser("schema", help="Dump JSON Schema for BenchConfig.")
    p_schema.add_argument("--out", type=Path, default=None)
    p_schema.set_defaults(func=_cmd_schema)

    p_setup = sub.add_parser(
        "setup",
        help="One-shot setup: build Docker image, pull aux models, install aider/cline/mini-swe-agent.",
    )
    p_setup.set_defaults(func=_cmd_setup)

    p_sweep = sub.add_parser(
        "sweep",
        help="Loop a YAML across multiple strategies × seeds (v1.1+ canonical reproducer).",
    )
    _add_config_arg(p_sweep)
    p_sweep.add_argument(
        "--strategies",
        required=True,
        help="Comma-separated strategy names. Example: always-cloud,always-local,heuristic,cascade",
    )
    p_sweep.add_argument(
        "--seeds",
        default="42",
        help="Comma-separated seed integers (default: 42).",
    )
    p_sweep.add_argument(
        "--cascade-thresholds",
        default=None,
        help=(
            "v1.3+: Comma-separated integers to sweep the cascade strategy's "
            "ROUTER_CASCADE_THRESHOLD. Example: 5,10,15,20,25. Implies "
            "--strategies cascade (other strategies are ignored). The sweep "
            "spawns a fresh router proxy per threshold so each pass observes "
            "the intended cutoff."
        ),
    )
    p_sweep.add_argument(
        "--external-router",
        action="store_true",
        help=(
            "Opt out of the v1.4 auto-spawn-router behavior. By default, "
            "`arena sweep` reads models.local from the config and spawns "
            "`node router/server.mjs` with LOCAL_MODEL=<model>, tearing it "
            "down on completion. Pass this flag to manage the router "
            "yourself (e.g. `(cd router && ./start.sh) &` in another shell)."
        ),
    )
    p_sweep.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan each pass without running.",
    )
    p_sweep.set_defaults(func=_cmd_sweep)

    # ---- v1.4 sweep lifecycle: start / pause / resume / stop / status -----

    def _add_start_args(p: argparse.ArgumentParser) -> None:
        # _add_config_arg() already provides --resume; don't double-register.
        _add_config_arg(p)
        p.add_argument("--strategies", required=True,
                       help="Comma-separated strategy names. Example: always-cloud,always-local,heuristic,cascade")
        p.add_argument("--seeds", default="42",
                       help="Comma-separated seed integers (default: 42).")
        p.add_argument("--cascade-thresholds", default=None,
                       help="Comma-separated integers to sweep ROUTER_CASCADE_THRESHOLD.")
        p.add_argument("--external-router", action="store_true",
                       help="Don't auto-spawn router; manage it yourself.")

    p_start = sub.add_parser(
        "start",
        help="Start a sweep in the background. Auto-starts Ollama + writes /tmp/hcev-sweep.json.",
    )
    _add_start_args(p_start)
    p_start.set_defaults(func=_cmd_start)

    p_pause = sub.add_parser(
        "pause",
        help="Pause the active sweep (kill orchestrator + agents + router). Ollama stays up for fast resume.",
    )
    p_pause.set_defaults(func=_cmd_pause)

    p_resume = sub.add_parser(
        "resume",
        help="Resume the paused sweep using its saved state. Adds --resume to skip already-completed rows.",
    )
    p_resume.set_defaults(func=_cmd_resume)

    p_stop = sub.add_parser(
        "stop",
        help="Stop the sweep AND release Ollama (~19 GB RAM). Sweep state retained for later ./arena resume.",
    )
    p_stop.add_argument("--keep-ollama-app", action="store_true",
                        help="Keep Ollama.app running (only kill the model runners). Defaults: kill everything.")
    p_stop.add_argument("--clear-state", action="store_true",
                        help="Also remove the paused state file (not resumable without re-passing args).")
    p_stop.set_defaults(func=_cmd_stop)

    p_status = sub.add_parser(
        "status",
        help="Show whether a sweep is running, paused, or absent. Includes row count + log path.",
    )
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
