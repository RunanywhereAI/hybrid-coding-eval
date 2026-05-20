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
import subprocess
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

    # Explicit task-ID whitelist (v1.3+) — scopes a sweep to a known-good
    # subset (e.g. R7-compatible D1+D5 real_dev tasks).
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


# ---------- setup ----------------------------------------------------------

_MINIONS_GIT_URL = "https://github.com/HazyResearch/minions.git"
# Opencode (R8) fork install — env-overridable so iteration can pin a
# specific SHA without code edits. See docs/AGENTIC_ROUTES.md.
import os as _os

_OPENCODE_GIT_URL = _os.environ.get(
    "OPENCODE_GIT_URL",
    "https://github.com/RunanywhereAI/opencode-1.git",
)
_OPENCODE_GIT_REF = _os.environ.get("OPENCODE_GIT_REF", "feat/hybrid-routing-plugin")
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # repo root


def _ensure_minions(verbose: bool = True) -> bool:
    """Clone vendor/minions/ if missing. Returns True on success.

    Idempotent: returns True immediately if already present (detected via
    ``.git`` or the upstream's ``app.py`` sentinel — handles both git
    clones and manual extractions). Used by both ``bench setup`` and
    ``bench run`` (auto-clone on first R4/R5 route).
    """
    target = _REPO_ROOT / "vendor" / "minions"
    if (target / ".git").exists() or (target / "app.py").exists():
        if verbose:
            print(f"  ✓ vendor/minions/ present at {target}")
        return True
    if verbose:
        print(f"  Cloning Stanford Minions (~9 MB) into {target}…")
    target.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", _MINIONS_GIT_URL, str(target)],
            check=True,
            capture_output=not verbose,
        )
        if verbose:
            print("  ✓ vendor/minions/ ready")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"  ✗ git clone failed: {exc}", file=sys.stderr)
        print(
            f"    Manually clone: cd vendor && git clone {_MINIONS_GIT_URL}",
            file=sys.stderr,
        )
        return False


def _ensure_opencode(verbose: bool = True) -> bool:
    """Clone the opencode fork (R8 route) into ``vendor/opencode/``.

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
    pointing at the proxy on :8787. The R8 runner expects model id shape
    ``hybrid-router/router/<strategy>[/run-<id>]``.
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


def _cmd_setup(args: argparse.Namespace) -> int:  # noqa: ARG001
    """One-shot setup: clone minions, build Docker image, pull aux models, sanity-check env.

    Idempotent — safe to re-run.
    """
    import shutil
    import subprocess

    print("=== bench setup — preparing the benchmark harness ===\n")
    failures = []

    # 1. Stanford Minions (required for R4 + R5 routes)
    print("[1/6] Stanford Minions (R4 + R5 routes)")
    if not _ensure_minions(verbose=True):
        failures.append("minions clone failed")

    # 2. Docker image for functional scoring sandbox
    print("\n[2/6] Functional-scoring Docker image (hybrid-eval-python:latest)")
    if not shutil.which("docker"):
        print("  ⚠ docker not on PATH — skipping image build")
        print("    Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
    else:
        try:
            subprocess.run(
                ["docker", "image", "inspect", "hybrid-eval-python:latest"],
                check=True,
                capture_output=True,
            )
            print("  ✓ hybrid-eval-python:latest already built")
        except subprocess.CalledProcessError:
            dockerfile = _REPO_ROOT / "src" / "hybrid_coding_eval" / "scorers" / "Dockerfile.functional_python"
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

    # 3. Auxiliary Ollama models (router strategies)
    print("\n[3/6] Auxiliary local models (router classifier + embedding)")
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

    # 4. Aider (R7 route — the v1.2 canonical agent for hybrid eval).
    # Installed into the repo's venv so subprocess can find it via the
    # R7 runner's .venv/bin/aider fallback. Independent of system PATH.
    print("\n[4/6] Aider (R7 route — primary agent for v1.2 hybrid sweeps)")
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

    # 5. Opencode fork (R8 route — EXPERIMENTAL in v1.2).
    # Skipped by default in v1.2. Set BENCH_SETUP_OPENCODE=1 to enable.
    # R8 stays in-tree (results at v1.1.x tags) but isn't the v1.2
    # canonical because qwen3-coder:30b + opencode's free-form tool-use
    # pattern doesn't produce useful work — see CHANGELOG v1.1.3 + v1.2.
    if _os.environ.get("BENCH_SETUP_OPENCODE", "0") in ("1", "true", "yes"):
        print("\n[5/6] Opencode (R8 route — EXPERIMENTAL; enabled via BENCH_SETUP_OPENCODE=1)")
        if not shutil.which("opencode"):
            print("  ⚠ opencode CLI not on PATH — R8 route won't work")
            print("    Install via Homebrew: brew install opencode")
        else:
            print("  ✓ opencode CLI on PATH")
        if not _ensure_opencode(verbose=True):
            failures.append("opencode fork clone failed")
        if not _ensure_opencode_config(verbose=True):
            failures.append("opencode.json config setup failed")
    else:
        print("\n[5/6] Opencode (R8 route) — SKIPPED (EXPERIMENTAL in v1.2)")
        print("  R8 is in the tree but qwen3-coder:30b + opencode's free-form tool-use")
        print("  protocol doesn't produce useful work in hybrid setups (see CHANGELOG).")
        print("  v1.1.x tags have the diagnostic data. To enable anyway:")
        print("    BENCH_SETUP_OPENCODE=1 ./bench setup")

    # 6. Environment sanity (.env file, Python version)
    print("\n[6/6] Environment sanity")
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
        print("\nFix the items above, then re-run `./bench setup`. Once clean, try:")
    else:
        print("  ✓ All checks passed.")
        print("\nNext:")
    print("  1. Ensure .env has OPEN_AI_API_KEY (and ANTHROPIC_API_KEY for judge)")
    print("  2. Pull a local model: `ollama pull devstral:24b` (or another from configs/variants/)")
    print("  3. Start the router proxy: `(cd router && ./start.sh) &`")
    print("  4. Run a smoke test: `./bench run --config configs/variants/_template.yaml --smoke`")
    return 1 if failures else 0


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


def _cmd_sweep(args: argparse.Namespace) -> int:
    """Loop a single YAML config across multiple strategies × seeds.

    The reproducer for v1.1+ canonical sweeps. Replaces the deleted
    bin/v4*.sh scripts. Each ``(strategy, seed)`` combination writes to
    its own subdirectory under ``out_dir``::

        <out_dir>/<strategy>/seed-<seed>/raw.jsonl

    so the analysis layer (./bench analyze + bootstrap) can stratify by
    both axes without raw.jsonl key collisions.

    v1.3+: ``--cascade-thresholds N1,N2,…`` sweeps the cascade strategy
    only, spawning a fresh router per threshold so ROUTER_CASCADE_THRESHOLD
    is observed. Layout becomes ``<out_dir>/cascade-threshold-<N>/seed-<seed>/``.
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
            f"# bench sweep (cascade-threshold mode): "
            f"{len(cascade_thresholds)} thresholds × {len(seeds)} seeds "
            f"= {total} runs → {base_out}"
        )
    else:
        total = len(strategies) * len(seeds)
        print(
            f"# bench sweep: {len(strategies)} strategies × {len(seeds)} seeds "
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
        )
        try:
            ret = _cmd_run(sub_args)
        except Exception as exc:  # noqa: BLE001 — keep sweep alive
            print(f"  ! pass crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
            ret = 99
        if ret != 0:
            failures.append((strat if threshold is None else f"cascade@{threshold}", seed, ret))

    if cascade_thresholds is not None:
        # Spawn a fresh router per threshold; loop seeds inside.
        port = base_config.router.port
        idx = 0
        for threshold in cascade_thresholds:
            if args.dry_run:
                print(
                    f"\n--- (dry-run) would spawn router with "
                    f"ROUTER_CASCADE_THRESHOLD={threshold} ---"
                )
                for seed in seeds:
                    idx += 1
                    sub_out = base_out / f"cascade-threshold-{threshold}" / f"seed-{seed}"
                    _run_pass(idx, "cascade", seed, sub_out, threshold=threshold)
                continue
            print(f"\n--- spawning router with ROUTER_CASCADE_THRESHOLD={threshold} ---")
            try:
                proc = _spawn_router(
                    {"ROUTER_CASCADE_THRESHOLD": str(threshold)}, port=port
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ! router spawn failed for threshold={threshold}: {exc}", file=sys.stderr)
                for seed in seeds:
                    idx += 1
                    failures.append((f"cascade@{threshold}", seed, 98))
                continue
            try:
                for seed in seeds:
                    idx += 1
                    sub_out = base_out / f"cascade-threshold-{threshold}" / f"seed-{seed}"
                    _run_pass(idx, "cascade", seed, sub_out, threshold=threshold)
            finally:
                _kill_router(proc)
                print(f"--- killed router (threshold={threshold}) ---")
    else:
        idx = 0
        for strat in strategies:
            for seed in seeds:
                idx += 1
                sub_out = base_out / strat / f"seed-{seed}"
                _run_pass(idx, strat, seed, sub_out)

    print("\n=== sweep summary ===")
    print(f"  total passes : {total}")
    print(f"  successful   : {total - len(failures)}")
    print(f"  failed       : {len(failures)}")
    for strat, seed, ret in failures:
        print(f"    - [{strat}, seed={seed}]: exit {ret}")
    print(f"  output       : {base_out}")
    print(f"  next step    : ./bench analyze {base_out}")
    return 1 if failures else 0


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

    p_setup = sub.add_parser(
        "setup",
        help="One-shot setup: clone vendor/minions, build Docker image, pull auxiliary models.",
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
            "the intended cutoff. Requires no router on :8787 at start time."
        ),
    )
    p_sweep.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan each pass without running.",
    )
    p_sweep.set_defaults(func=_cmd_sweep)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
