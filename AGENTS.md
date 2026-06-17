# AGENTS.md

A single canonical guide for any AI coding agent (Cursor, Claude Code,
Codex, aider, etc.) working in this repository. Read this first — it's
the folder-by-folder map and the rules-of-the-road for landing changes.

## What this repo is

A **reproducible benchmark harness** that measures whether a coding task
should run on local hardware, the cloud, or via hybrid routing. It is
**not** a coding product. It is a one-developer-laptop research artefact
that publishes per-`(task-class, agent, strategy)` bootstrap-CI datasets
for four coding agents (**aider · opencode · mini-swe-agent · cline**)
across eight routing strategies, under six pricing scenarios.

**Status (v1.5.0):** 4-agent leaderboard across 3 local models, with a
v1.5 **D6 hard-task class** that stress-tests the v1.4.1 champion
configurations. Combined dataset is **1,704 rows** (1,644 v1.4 canonical
+ 60 v1.5 hard-task). Per-tag datasets ship as GitHub release tarballs;
the empirical record (tracked immutable runs in
`results/runs/{01..04, 07, 11}/` + `docs/release-notes/`) stays tracked.

For the canonical design + headline findings:

- [`README.md`](./README.md) — landing page + quickstart.
- [`docs/HYBRID_ROUTING_DESIGN.md`](./docs/HYBRID_ROUTING_DESIGN.md) — design doc.
- [`docs/release-notes/v1.5.0.md`](./docs/release-notes/v1.5.0.md) — latest findings (D6 stress test).
- [`docs/release-notes/v1.4.1.md`](./docs/release-notes/v1.4.1.md) — canonical 3-model leaderboard.

## Drop in a new local model

```bash
ollama pull <new-model>
./arena sweep \
    --config configs/v1.4-canonical-gemma4.yaml \
    --set models.local=<new-model> \
    --set out_dir=results/runs/v1.4-<new-model> \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./arena analyze results/runs/v1.4-<new-model>
```

`./arena setup` is idempotent — re-run any time. Long-form lifecycle
commands (`start`/`pause`/`resume`/`stop`/`status`) live in
`./arena --help`.

## Common commands

Python env is pinned at 3.11/3.12. Always use `.venv/bin/python` or
`.venv/bin/pytest` — the repo installs editable via
`pip install -e ".[dev]"` (add `,agents` for aider + mini-swe-agent).

```bash
# one-time env setup
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev,agents]"

# tests
.venv/bin/pytest tests/ -q

# one test
.venv/bin/pytest tests/test_orchestrator.py::test_name -q

# ruff (repo-wide)
.venv/bin/ruff check src/ tests/

# router proxy — auto-spawned by `arena sweep`. Manual start (rarely needed):
(cd router && ./start.sh)
curl -s http://127.0.0.1:8787/healthz | jq .

# router's own test sweep (strategies × prompts matrix)
cd router && npm test         # writes tests/RESULTS.md

# foreground sweep
./arena sweep --config configs/v1.4-canonical-gemma4.yaml \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./arena sweep --config configs/v1.4-canonical-gemma4.yaml --dry-run

# inspection / one-shot helpers
./arena show-config  --config configs/v1.4-canonical-gemma4.yaml
./arena env-detect   --out results/my-run/env-manifest.json
./arena analyze      results/runs/v1.4-canonical-gemma4
./arena token-budget results/runs/v1.4-canonical-gemma4
./arena schema       --out configs/schema.json
./arena setup        # first-run setup: Docker image, aux models, aider, cline
```

### Sweep lifecycle (background, pausable, resumable)

```bash
./arena start  --config configs/v1.4-canonical-qwen3.6.yaml \
               --strategies always-cloud,always-local,heuristic,cascade \
               --seeds 42,7,13
./arena status            # PID, config, log path, current row count
./arena pause             # kill orchestrator + agents + router; Ollama stays warm
./arena resume            # picks up at next un-written row (raw.jsonl is append-only)
./arena stop              # also kills Ollama (~19 GB freed); state file retained
./arena stop --clear-state          # also wipes /tmp/hcev-sweep.json
./arena stop --keep-ollama-app      # only kill model runners; keep Ollama.app
```

State lives at `/tmp/hcev-sweep.json` and persists across reboots until
you `--clear-state`.

## Folder-by-folder inventory

### Top level

| Path | What it is |
| --- | --- |
| `README.md` | OSS landing page + quickstart |
| `AGENTS.md` | **this file** — canonical agent guide |
| `CHANGELOG.md` | Keep-a-Changelog release history |
| `CONTRIBUTING.md` | Dev setup; how to add a model / agent / strategy / task |
| `CODE_OF_CONDUCT.md` | Short and direct (be kind, stay on-topic, email maintainer for issues) |
| `SECURITY.md` | Vulnerability-reporting channel |
| `LICENSE` | MIT (code + data + docs all unified under MIT in v1.5.1+) |
| `arena` | Shell wrapper → `python -m hybrid_arena.cli.bench` |
| `pyproject.toml` | Python package config — version, deps, ruff, pytest |
| `requirements.txt` | Pip pins (kept in sync with `[project.dependencies]`) |
| `.env.example` | Template — copy to `.env`, fill `OPEN_AI_API_KEY` |

### `configs/` — sweep configs, pricing, router corpus, JSON schema

```
configs/
├── v1.4-canonical-gemma4.yaml       # canonical v1.4.0 baseline (gemma4:31b)
├── v1.4-canonical-qwen3-coder.yaml  # v1.4.1 sweep (qwen3-coder:30b MoE)
├── v1.4-canonical-qwen3.6.yaml      # v1.4.1 sweep (qwen3.6:35b dense)
├── v1.4-opencode-fairness.yaml      # opencode-only fairness slice
├── v1.4-strategy-sweep.yaml         # all 8 strategies on aider/gemma4 for explainer
├── v1.4-real-prs.yaml               # SWE-bench Verified replay (real-prs class)
├── v1.4-smoke.yaml                  # 1-task smoke check (cloud only)
├── v1.5-hard-gemma4.yaml            # v1.5 D6 hard-task sweep on aider+gemma4
├── v1.5-hard-qwen3.6.yaml           # v1.5 D6 hard-task sweep on cline+qwen3.6
├── v1.5-hard-smoke.yaml             # v1.5 D6 smoke check
├── pricing/pricing_tables.json      # 6 pricing scenarios, SHA256-pinned
├── router/corpus.json               # 50-example hand-labelled corpus for embedding-kNN
└── schema.json                      # auto-generated JSON Schema for BenchConfig
```

YAML configs are the canonical sweep-definition surface. The schema at
`configs/schema.json` is auto-generated from
`src/hybrid_arena/core/config/schema.py` — never hand-edit;
regenerate with `./arena schema --out configs/schema.json`. Override
fields on the CLI with `--set key.path=value` instead of editing the
YAML for one-shot runs.

### `src/hybrid_arena/` — the Python package

```
src/hybrid_arena/
├── cli/                          # ./arena dispatcher and subcommands
│   ├── bench.py                  # top-level CLI — all subparsers + lifecycle
│   ├── run.py                    # ./arena run — single-pass sweep orchestrator
│   └── env_detect.py             # ./arena env-detect — hardware + software snapshot
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
│   ├── refactors/                # real-developer refactor tasks (D1/D2/D3/D4/D5/D6)
│   │   ├── tasks.jsonl + tasks-d{2,3,4}.jsonl, scorers.py, fixtures/
│   └── real_prs/                 # SWE-bench Verified replay (adapter shipped, sweep v1.6+)
│
├── analysis/                     # post-sweep number-crunching
│   ├── all.py                    # entry-point; runs everything below
│   ├── aggregate.py              # per-(task_class, agent, strategy) means/medians/sums
│   ├── bootstrap.py              # 95% percentile CIs per cell
│   ├── decision_matrix.py        # task_class × agent → recommendation
│   ├── cost_scenarios.py         # re-price under 5 scenarios
│   ├── token_budget.py           # ./arena token-budget — token-first matrix
│   ├── token_share.py            # cloud_fraction analysis
│   └── reprice.py                # standalone re-pricing helper
│
└── viz/                          # chart generators
    ├── cost_quality_pareto.py    # Pareto scatter (cost vs quality)
    └── decision_heatmap.py       # task_class × agent quality/cost heatmaps
```

### `router/` — zero-deps Node hybrid proxy

OpenAI-compatible HTTP proxy on `:8787`, **auto-spawned by `arena sweep`**.
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
└── logs/                         # routing-decision log (gitignored)
```

Local-call guards (added in v1.4.1 to fix qwen3-coder runaway-generation
crashes):

| Env var | Default | Purpose |
| --- | --- | --- |
| `ROUTER_LOCAL_NUM_PREDICT_CAP` | `4096` | Cap Ollama `num_predict`. `-1` disables. |
| `ROUTER_LOCAL_REQUEST_TIMEOUT_MS` | `180000` | 3-min hard wall-clock per local call (`AbortSignal.timeout`). |
| `ROUTER_LOCAL_REPEAT_PENALTY` | `1.1` | Override weak model defaults (e.g. qwen3-coder ships `1.05`). |

Required env: `LOCAL_BASE`, `LOCAL_MODEL`, `CLOUD_MODEL`,
`CLOUD_API_KEY` (resolves from `OPENAI_API_KEY` or `OPEN_AI_API_KEY`).
Binds 127.0.0.1 only; no auth — don't expose.

### `tests/` — pytest suite

```
tests/
├── agents/test_{aider_parser,cline,mini_swe}.py
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

120 fast tests, all run on every CI build (3.11 + 3.12 matrix).
Subprocess-based tests `pytest.skip` cleanly if the router proxy is down
or Docker is unavailable.

### `vendor/` — third-party (read-only)

```
vendor/
├── README.md                     # explains what's vendored
└── opencode/                     # opencode fork for the opencode agent (BENCH_SETUP_OPENCODE=1)
```

Treat `vendor/` as immutable. If you find a bug, patch our wrapper in
`agents/`, not the vendored source. Long-term fix is an upstream PR.

### `results/` — canonical research data

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
    ├── 07-v3-devstral-all-routes/# v3 canonical 250-row sweep
    └── 11-judge-robust-D/        # 96-verdict triple-judge audit on D3+D4
```

**`results/runs/` is gitignored going forward.** v1.4+ datasets are
GitHub release tarballs (`results-v1.K.tar.gz`). Pre-existing tracked
runs (01–04, 07, 11) are immutable.

### `docs/` — reference documentation

```
docs/
├── HYBRID_ROUTING_DESIGN.md      # THE design doc (strategies + agents + methodology + schema)
└── release-notes/
    ├── v1.4.0.md                 # 708-row gemma4 canonical
    ├── v1.4.1.md                 # 1,644 row leaderboard (qwen3-coder + qwen3.6 added)
    ├── v1.4.2.md / v1.4.3.md / v1.4.4.md   # cleanup releases
    └── v1.5.0.md                 # D6 hard-task stress test (60 new rows)
```

The docs surface is intentionally minimal. Long-form design discussion
lives in `HYBRID_ROUTING_DESIGN.md`; everything else is in the release
notes.

## Architecture in 90 seconds

```text
./arena sweep --config configs/v1.4-canonical-gemma4.yaml --strategies heuristic --seeds 42
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
        → core/results.append_row()         # one JSON line to <out>/<strategy>/seed-<seed>/raw.jsonl
```

Rows are flushed after each `(task, agent)` completes, so sweeps are
crash-resumable. The orchestrator checks `pair_already_done(raw.jsonl,
task_id, route, router_strategy)` to skip completed pairs on `--resume`.

### The 8 routing strategies

`always-cloud · always-local · rules · heuristic · llm-classifier ·
embedding-knn · cascade · phase-aware`. Each is one function in
`router/strategies.mjs`. Decisions are appended to
`router/logs/decisions.jsonl` (gitignored) and correlated back to rows
via `bench_run_id` in the model field.

### Analysis pipeline

`analysis.all` runs in order: `aggregate` → `bootstrap` →
`decision_matrix` → `cost_scenarios` → `token_budget` →
`viz/cost_quality_pareto` + `viz/decision_heatmap`.

## Conventions and gotchas

- **Use `.venv/bin/python` and `.venv/bin/pytest`**, not bare `python`.
  The repo installs editable via `pip install -e ".[dev]"`.
- **The router proxy is auto-spawned by `arena sweep`.** You don't need
  a separate router terminal. For debugging, run `(cd router &&
  ./start.sh)` and pass `--external-router` to `arena sweep`.
- **Tests are not split by speed.** All 120 fast tests run on every CI
  build. SWE-bench Docker tests skip gracefully when Docker is
  unavailable.
- **Preserved runs are read-only.** `results/raw.jsonl` and the tracked
  `results/runs/{01..04, 07, 11}/` dirs never change bytes.
- **Cost is derived, not stored.** Any `cost_usd_*` field in
  `raw.jsonl` is a bug. Cost is computed on read via `core/pricing.py`.
- **Env keys**: `OPENAI_API_KEY` / `OPEN_AI_API_KEY` accepted (router
  checks both). `ANTHROPIC_API_KEY` is unused in v1.4+ (the LLM judge
  was removed).
- **Task classes**: `puzzles`, `refactors`, `real-prs` — the same names
  flow end-to-end through `BenchmarkConfig.task_classes`, the
  `ResultRow.category` field, the `aggregate.json` / `bootstrap_cis.json`
  cell keys (e.g. `puzzles::aider::heuristic`,
  `refactors::cline::cascade`), and release-notes prose.
- **Refactor shapes**: D1 (feature), D2 (bug-fix, not in canonical), D3
  (refactor), D4 (review), D5 (script), **D6 (v1.5 hard implementation
  challenge)**. D1/D5/D6 are functionally scored; D3/D4 use the LLM
  judge.
- **Agent names**: `aider`, `opencode`, `mini-swe-agent`, `cline` —
  used end-to-end (no legacy R-numbers).
- **Local guards** (v1.4.1): every local call is capped at 4096
  `num_predict`, 180 s wall-clock, `repeat_penalty=1.1`. Override via
  `ROUTER_LOCAL_*` env vars.
- **YAML configs** are the canonical sweep-definition surface. Override
  fields on the CLI with `--set key.path=value`.

## Where to read next

1. [`README.md`](./README.md) — quickstart + headline findings
2. [`docs/HYBRID_ROUTING_DESIGN.md`](./docs/HYBRID_ROUTING_DESIGN.md) — design doc
3. [`docs/release-notes/v1.5.0.md`](./docs/release-notes/v1.5.0.md) — latest findings (D6 stress test)
4. [`docs/release-notes/v1.4.1.md`](./docs/release-notes/v1.4.1.md) — canonical 3-model leaderboard
5. [`CONTRIBUTING.md`](./CONTRIBUTING.md) — add a model / agent / strategy
6. [`CHANGELOG.md`](./CHANGELOG.md) — v1.0 → v1.5 lineage

## License

Everything in this repo is **MIT-licensed** — see [`LICENSE`](./LICENSE).
A citation in any derived work would be really appreciated; the BibTeX
block lives in the README.
