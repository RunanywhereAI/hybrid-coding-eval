# AGENTS.md

A single canonical guide for any AI coding agent (Cursor, Claude Code, Codex,
aider, etc.) working in this repository. Read this first — it's the
folder-by-folder map and the rules-of-the-road for landing changes.

## What this repo is

A **reproducible benchmark harness** that measures whether a coding task
should run on local hardware, the cloud, or via hybrid routing. It is
**not** a coding product. It is a one-developer-laptop research artefact
that publishes per-`(task-class, agent, strategy)` bootstrap-CI datasets
for four coding agents (**aider · opencode · mini-swe-agent · cline**)
across eight routing strategies, under five pricing scenarios.

**Status (v1.5.0):** 4-agent leaderboard across 3 local models, now
with a **D6 hard-task class** that stress-tests the v1.4.1 top
configurations. Combined v1.4 dataset is 1,644 rows (frozen at
v1.4.1); v1.5 adds **60 rows** of hard-task data targeted at the
top-3 configs. v1.4.3 + v1.4.4 are code-only cleanup releases. Per-tag
datasets ship as GitHub release tarballs; the empirical record
(tracked immutable runs in `results/runs/{01..04, 07, 11}/` +
`docs/release-notes/`) stays tracked.

For the canonical design + headline findings:
- [`README.md`](./README.md) — landing page.
- [`docs/HYBRID_ROUTING_DESIGN.md`](./docs/HYBRID_ROUTING_DESIGN.md) — design doc.
- [`docs/release-notes/v1.4.1.md`](./docs/release-notes/v1.4.1.md) — latest results.

## Drop in a new local model

```bash
ollama pull <new-model>
./scripts/reproduce.sh \
    --config configs/v1.4-canonical-gemma4.yaml \
    --set models.local=<new-model> \
    --set out_dir=results/runs/v1.4-<new-model> \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-<new-model>
```

`scripts/reproduce.sh` is the one-command reproducer (checks prereqs,
runs `./bench setup` if needed, then `./bench sweep`). Long-form
lifecycle commands live in `./bench --help`.

## Common commands

Python env is pinned at 3.11/3.12. Always use `.venv/bin/python` or
`.venv/bin/pytest` — the repo installs editable via
`pip install -e ".[dev]"`.

```bash
# one-time env setup
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# fast tests (Docker tests marked `slow`)
.venv/bin/pytest tests/ -q -m 'not slow'

# one test
.venv/bin/pytest tests/test_orchestrator.py::test_name -q

# ruff (repo-wide)
.venv/bin/ruff check src/ tests/

# router proxy — auto-spawned by `bench sweep`. Manual start (rarely needed):
(cd router && ./start.sh)
curl -s http://127.0.0.1:8787/healthz | jq .

# router's own test sweep (strategies × prompts matrix)
cd router && npm test         # writes tests/RESULTS.md

# foreground sweep
./bench sweep --config configs/v1.4-canonical-gemma4.yaml \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench sweep --config configs/v1.4-canonical-gemma4.yaml --dry-run

# inspection / one-shot helpers
./bench show-config  --config configs/v1.4-canonical-gemma4.yaml
./bench env-detect   --out results/my-run/env-manifest.json
./bench analyze      results/runs/v1.4-canonical-gemma4
./bench token-budget results/runs/v1.4-canonical-gemma4
./bench schema       --out configs/schema.json
./bench setup        # first-run setup: Docker image, aux models, aider, cline
```

### Sweep lifecycle (background, pausable, resumable)

```bash
./bench start  --config configs/v1.4-canonical-qwen3.6.yaml \
               --strategies always-cloud,always-local,heuristic,cascade \
               --seeds 42,7,13
./bench status            # PID, config, log path, current row count
./bench pause             # kill orchestrator + agents + router; Ollama stays warm
./bench resume            # picks up at next un-written row (raw.jsonl is append-only)
./bench stop              # also kills Ollama (~19 GB freed); state file retained
./bench stop --clear-state          # also wipes /tmp/hcev-sweep.json
./bench stop --keep-ollama-app      # only kill model runners; keep Ollama.app
```

State lives at `/tmp/hcev-sweep.json` and persists across reboots until
you `--clear-state`.

## Folder-by-folder inventory

### Top level

| Path                  | What it is                                            |
| --------------------- | ----------------------------------------------------- |
| `README.md`           | OSS landing page                                      |
| `AGENTS.md`           | **this file** — canonical agent guide                 |
| `CHANGELOG.md`        | Keep-a-Changelog release history                      |
| `CONTRIBUTING.md`     | Dev setup; how to add a model / agent / strategy      |
| `CODE_OF_CONDUCT.md`  | Contributor Covenant 2.1                              |
| `SECURITY.md`         | Vulnerability-reporting channel                       |
| `LICENSE`             | MIT (code under `src/`, `router/`, `tests/`, `configs/`, `scripts/`) |
| `LICENSE-DATA`        | CC-BY-4.0 (results, charts, docs prose)               |
| `LICENSE.md`          | File-type breakdown of MIT vs CC-BY-4.0               |
| `NOTICE.md`           | Third-party attribution                               |
| `bench`               | Shell wrapper → `python -m hybrid_coding_eval.cli.bench` |
| `scripts/reproduce.sh`| One-command reproducer                                |
| `pyproject.toml`      | Python package config — version, deps, ruff, pytest   |
| `requirements.txt`    | Pip pins (kept in sync with `[project.dependencies]`) |
| `.env.example`        | Template — copy to `.env`, fill `OPEN_AI_API_KEY`     |

### `configs/` — sweep configs, pricing, router corpus, JSON schema

```
configs/
├── v1.4-canonical-gemma4.yaml       # canonical v1.4.0 baseline (gemma4:31b)
├── v1.4-canonical-qwen3-coder.yaml  # v1.4.1 sweep (qwen3-coder:30b MoE)
├── v1.4-canonical-qwen3.6.yaml      # v1.4.1 sweep (qwen3.6:35b dense)
├── v1.4-opencode-fairness.yaml      # opencode-only fairness slice
├── v1.4-strategy-sweep.yaml         # all 8 strategies on aider/gemma4 for explainer
├── v1.4-real-prs.yaml               # SWE-bench Verified replay (real-prs class)
├── v1.4-smoke.yaml                  # 1-task-per-class smoke check
├── pricing/pricing_tables.json      # 5 pricing scenarios, SHA256-pinned
├── router/corpus.json               # 50-example hand-labelled corpus for embedding-kNN
└── schema.json                      # auto-generated JSON Schema for BenchConfig
```

YAML configs are the canonical sweep-definition surface. The schema at
`configs/schema.json` is auto-generated from
`src/hybrid_coding_eval/core/config/schema.py` — never hand-edit;
regenerate with `./bench schema --out configs/schema.json`. Override
fields on the CLI with `--set key.path=value` instead of editing the
YAML for one-shot runs.

### `src/hybrid_coding_eval/` — the Python package

```
src/hybrid_coding_eval/
├── cli/                          # ./bench dispatcher and subcommands
│   ├── bench.py                  # top-level CLI — all subparsers + lifecycle
│   ├── run.py                    # ./bench run — single-pass sweep orchestrator
│   └── env_detect.py             # ./bench env-detect — hardware + software snapshot
│
├── core/                         # shared dispatcher + I/O + config
│   ├── experiment.py             # build_task_plan, run_pair — the dispatcher loop
│   ├── metrics.py                # ResultRow + TokenUsage + Latency + Quality + Routing
│   ├── pricing.py                # token → cost derivation against pricing_tables.json
│   ├── results.py                # append_row + pair_already_done (raw.jsonl I/O)
│   ├── sandbox.py                # Docker sandbox helper for functional scorer
│   ├── paths.py                  # repo-root resolver (single source of truth)
│   └── config/                   # YAML config schema + loader + variable resolver
│       ├── schema.py             # Pydantic BenchConfig model (source of truth)
│       ├── loader.py             # YAML → BenchConfig with env-var ${ENV:VAR} expansion
│       └── resolve.py            # config flag overrides (--set key.path=value)
│
├── agents/                       # one module per coding agent
│   ├── aider.py                  # aider — architect/editor protocol
│   ├── opencode.py               # opencode — free-form tool-use ReAct
│   ├── mini_swe.py               # mini-swe-agent — bash-only ReAct
│   ├── cline.py                  # cline VSCode agent, headless
│   └── attribution.py            # correlation-id token attribution for the proxy
│
├── scorers/                      # one scorer per quality dimension
│   ├── functional_python.py      # extracts code, runs pytest in a Docker sandbox
│   ├── swebench.py               # shells out to upstream `swebench.harness.run_evaluation`
│   └── Dockerfile.functional_python   # python:3.12-slim + pytest sandbox image
│
├── tasks/                        # task-source adapters
│   ├── puzzles/                  # Exercism Python (Aider polyglot benchmark, MIT)
│   ├── refactors/                # real-developer D-tasks
│   │   ├── tasks-d*.jsonl, scorers.py, fixtures/
│   └── real_prs/                 # SWE-bench Verified replay
│
├── analysis/                     # post-sweep number-crunching
│   ├── all.py                    # entry-point; runs everything below
│   ├── aggregate.py              # per-(task_class, agent, strategy) means/medians/sums
│   ├── bootstrap.py              # 95% percentile CIs per cell
│   ├── decision_matrix.py        # task_class × agent → recommendation
│   ├── cost_scenarios.py         # re-price under 5 scenarios
│   ├── token_budget.py           # ./bench token-budget — token-first matrix
│   ├── token_share.py            # cloud_fraction analysis
│   └── reprice.py                # standalone re-pricing helper
│
└── viz/                          # chart generators
    ├── cost_quality_pareto.py    # Pareto scatter (cost vs quality)
    └── decision_heatmap.py       # task_class × agent quality/cost heatmaps
```

### `router/` — zero-deps Node hybrid proxy

OpenAI-compatible HTTP proxy on `:8787`, **auto-spawned by `bench sweep`**.
The `model` field of each request selects a strategy. Append
`!local`/`!cloud` to force a backend on one call.

```
router/
├── server.mjs                    # HTTP server; entry point
├── strategies.mjs                # 8 routing strategies
├── pricing.mjs                   # shared pricing-table reader (in sync with configs/pricing)
├── start.sh                      # manual starter — loads ../.env, binds 127.0.0.1
├── package.json                  # minimal — declares "node-test" runner only
├── tests/                        # router's own test sweep (prompts × strategies)
└── logs/decisions.jsonl          # tracked routing-decision log
```

Local-call guards (added in v1.4.1 to fix qwen3-coder runaway-generation
crashes):

| Env var                            | Default  | Purpose                                                       |
| ---------------------------------- | -------- | ------------------------------------------------------------- |
| `ROUTER_LOCAL_NUM_PREDICT_CAP`     | `4096`   | Cap Ollama `num_predict`. `-1` disables.                      |
| `ROUTER_LOCAL_REQUEST_TIMEOUT_MS`  | `180000` | 3-min hard wall-clock per local call (`AbortSignal.timeout`). |
| `ROUTER_LOCAL_REPEAT_PENALTY`      | `1.1`    | Override weak model defaults (e.g. qwen3-coder ships `1.05`). |

Required env: `LOCAL_BASE`, `LOCAL_MODEL`, `CLOUD_MODEL`,
`CLOUD_API_KEY` (resolves from `OPENAI_API_KEY` or `OPEN_AI_API_KEY`).
Binds 127.0.0.1 only; no auth — don't expose.

### `tests/` — pytest suite

```
tests/
├── agents/test_{cline,mini_swe}.py
├── analysis/test_token_budget.py
├── scorers/test_real_dev_scorers.py
├── tasks/test_refactors_scaffold.py
├── test_aggregate.py, test_bootstrap.py
├── test_config.py, test_env_detect.py
├── test_metrics_new_fields.py
├── test_orchestrator.py, test_results.py
├── test_pricing_parity.py, test_pricing_path_parity.py
├── test_sandbox.py
└── test_viz.py
```

Subprocess-based tests `pytest.skip` cleanly if the router proxy is down.
SWE-bench Docker tests are marked `slow`; skip them with `-m 'not slow'`.

### `vendor/` — third-party (read-only)

```
vendor/
├── README.md                     # explains what's vendored
└── opencode/                     # opencode fork for the opencode agent (BENCH_SETUP_OPENCODE=1)
```

Treat `vendor/` as immutable. If you find a bug, patch our wrapper in
`agents/`, not the vendored source. Long-term fix is an upstream PR.

### `results/` — canonical research data (CC-BY-4.0)

```
results/
├── raw.jsonl                     # MVP merged dataset (180 rows, frozen)
├── REPORT_v1_mvp.md              # MVP report (frozen)
├── env-manifests/                # 01–04 hardware snapshots
└── runs/                         # one dir per preserved sweep
    ├── README.md                 # run-by-run index
    ├── 01-v1-qwen-original/      # MVP v1 sweep
    ├── 02-v2-qwen-fixed-synth/   # MVP v2 (Opus judge)
    ├── 03-v2-devstral/           # MVP v2 with devstral local
    ├── 04-r4-minion/             # MVP R4 Minion sweep (preserved data)
    ├── 07-v3-devstral-all-routes/# v3 canonical 250-row sweep (legacy R1–R5)
    └── 11-judge-robust-D/        # 96-verdict triple-judge audit on D3+D4
```

**`results/runs/` is gitignored going forward.** v1.4+ datasets are
GitHub release tarballs (`results-v1.4.K.tar.gz`). Pre-existing tracked
runs (01–04, 07, 11) are immutable.

### `docs/` — reference documentation (CC-BY-4.0)

```
docs/
├── HYBRID_ROUTING_DESIGN.md      # THE design doc (strategies + agents + methodology + schema)
└── release-notes/
    ├── v1.4.0.md                 # 708-row gemma4 canonical
    └── v1.4.1.md                 # 936 new rows (qwen3-coder + qwen3.6) — 1,644 row leaderboard
```

The docs surface is intentionally minimal. Long-form design discussion
lives in `HYBRID_ROUTING_DESIGN.md`; everything else is in the release
notes.

## Architecture in 90 seconds

```text
./bench sweep --config configs/v1.4-canonical-gemma4.yaml --strategies heuristic --seeds 42
    → cli/bench._cmd_sweep
    → spawn router/server.mjs (LOCAL_MODEL + CLOUD_MODEL injected from config)
    → for each (strategy, seed):
        → cli/bench._cmd_run → cli/run.main
        → core/experiment.build_task_plan()
        → core/experiment.run_pair()        # dispatches per agent
            ├── agents/aider.py
            ├── agents/opencode.py
            ├── agents/mini_swe.py
            └── agents/cline.py
        → scorers/functional_python.py OR scorers/swebench.py
        → core/results.append_row()         # one JSON line to <out>/raw.jsonl
```

Rows are flushed after each `(task, agent)` completes, so sweeps are
crash-resumable. The orchestrator checks `pair_already_done(raw.jsonl,
task_id, route, router_strategy)` to skip completed pairs on `--resume`.

### The 8 routing strategies

`always-cloud · always-local · rules · heuristic · llm-classifier ·
embedding-knn · cascade · phase-aware`. Each is one function in
`router/strategies.mjs`. Decisions are appended to
`router/logs/decisions.jsonl` and correlated back to rows via
`bench_run_id` in the model field.

### Analysis pipeline

`analysis.all` runs in order: `aggregate` → `bootstrap` →
`decision_matrix` → `cost_scenarios` → `token_budget` →
`viz/cost_quality_pareto` + `viz/decision_heatmap`.

## Conventions and gotchas

- **Use `.venv/bin/python` and `.venv/bin/pytest`**, not bare `python`.
  The repo installs editable via `pip install -e ".[dev]"`.
- **The router proxy is auto-spawned by `bench sweep`.** You don't need
  a separate router terminal. For debugging, run `(cd router &&
  ./start.sh)` and pass `--external-router` to `bench sweep`.
- **`tests/test_*` marked `slow`** invoke the Docker harness (minutes
  per test). Skip with `-m 'not slow'`.
- **Preserved runs are read-only.** `results/raw.jsonl` and the tracked
  `results/runs/{01..04, 07, 11}/` dirs never change bytes.
- **Cost is derived, not stored.** Any `cost_usd_*` field in
  `raw.jsonl` is a bug. Cost is computed on read via `core/pricing.py`.
- **Env keys**: `OPENAI_API_KEY` / `OPEN_AI_API_KEY` accepted (router
  checks both). `ANTHROPIC_API_KEY` is unused in v1.4 (the LLM judge
  was removed).
- **Task classes**: `puzzles`, `refactors`, `real-prs` — the same names
  flow end-to-end through `BenchmarkConfig.task_classes`, the
  `ResultRow.category` field, the `aggregate.json` / `bootstrap_cis.json`
  cell keys (e.g. `puzzles::aider::heuristic`), and release-notes prose.
  (The legacy single-letter codes `A`/`B`/`C`/`D` were retired in v1.4.3.)
- **Agent names**: `aider`, `opencode`, `mini-swe-agent`, `cline`.
- **Local guards** (v1.4.1): every local call is capped at 4096
  `num_predict`, 180 s wall-clock, `repeat_penalty=1.1`. Override via
  `ROUTER_LOCAL_*` env vars.
- **YAML configs** are the canonical sweep-definition surface. Override
  fields on the CLI with `--set key.path=value`.

## Where to read next

1. [`README.md`](./README.md) — quickstart + headline findings
2. [`docs/HYBRID_ROUTING_DESIGN.md`](./docs/HYBRID_ROUTING_DESIGN.md) — design doc
3. [`docs/release-notes/v1.4.1.md`](./docs/release-notes/v1.4.1.md) — latest results
4. [`CONTRIBUTING.md`](./CONTRIBUTING.md) — add a model / agent / strategy
5. [`CHANGELOG.md`](./CHANGELOG.md) — v1.0 → v1.4.1 lineage

## License + attribution

- **Code** (`src/`, `router/`, `tests/`, `configs/`, `bench`,
  `scripts/`): MIT — see [`LICENSE`](./LICENSE).
- **Data + figures + docs prose** (`results/`, `docs/`, charts):
  CC-BY-4.0 — see [`LICENSE-DATA`](./LICENSE-DATA) +
  [`LICENSE.md`](./LICENSE.md).
- **Third-party**: see [`NOTICE.md`](./NOTICE.md) and
  `vendor/README.md`.
