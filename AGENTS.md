# AGENTS.md

A single canonical guide for any AI coding agent (Claude Code, Aider, Cursor, Codex, etc.) working in this repository. Read this first.

## What this repo is

A **reproducible benchmark harness** that measures whether a coding task should run on local hardware, cloud, or via hybrid routing. It is **not a product**. It is a one-developer-laptop research artefact that publishes per-`(category, route, strategy)` bootstrap-CI datasets comparing five agentic routes (R6 mini-swe-agent · R7 aider · R8 opencode · R9 claude-code · R10 cline) across two task classes (puzzles = Exercism Python, refactors = real-developer D-tasks) under six pricing scenarios.

**Top-level canonical surfaces:**

- `README.md` — the OSS landing page (v1.4 hero, 4-command quickstart)
- `docs/REPRODUCING.md` — copy-paste reproduction with a "how to read the results" cell→headline map
- `docs/BENCHMARK_NEW_MODEL.md` — add-a-new-local-model walkthrough
- `docs/release-notes/v1.4.0.md` — v1.4.0 canonical findings (tracked in git)
- `configs/v1.4-canonical.yaml` — the canonical v1.4 sweep config (drop-in surface for new models)
- `CHANGELOG.md` — release history (Keep a Changelog format)
- `CONTRIBUTING.md` — how to add a model, task, or routing strategy
- `LICENSE` (MIT, code) + `LICENSE-DATA` (CC-BY-4.0, data) + `LICENSE.md` + `NOTICE.md`

> The article + appendices that were previously under `reports/` live under the maintainer's gitignored `personal/` directory. The empirical record (the `results/runs/` datasets and `docs/release-notes/`) stays tracked.

**Status:** v1.4.0 cleanup + production-pipeline release. v1.4 deletes the legacy non-agentic R1/R2/R3 routes and the experimental Stanford-Minion R4/R5 wrappers. The agentic surface (R6..R10) is the only sweep target going forward. `bench sweep` auto-spawns the router proxy from `models.local`, so the canonical reproducer is now four copy-paste commands.

The historical v1.0–v1.3 datasets stay tracked at their original commits. v1.4+ per-tag datasets are GitHub release tarballs (`results-v1.4.K.tar.gz`).

## Drop in a new model

```bash
ollama pull <new-model>
./bench setup                                                          # first run only — Docker image, aux models, aider
./bench sweep --config configs/v1.4-canonical.yaml \
  --set models.local=<new-model> \
  --set out_dir=results/runs/v1.4-<new-model> \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42 --smoke
./bench analyze results/runs/v1.4-<new-model>/
```

`./bench show-config --config configs/v1.4-canonical.yaml` prints the merged config + SHA256.
`./bench sweep … --dry-run` prints each pass without running.

## Common commands

Python env is pinned at 3.11/3.12. Always use `.venv/bin/python` or `.venv/bin/pytest` — the repo installs editable via `pip install -e ".[dev]"`.

```bash
# one-time env setup
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# fast tests (SWE-bench Docker tests are marked slow)
.venv/bin/pytest tests/ -q -m 'not slow'

# one test file / one test
.venv/bin/pytest tests/test_orchestrator.py -q
.venv/bin/pytest tests/test_aggregate.py::test_name -q

# ruff (repo-wide)
.venv/bin/ruff check src/ tests/

# router proxy — auto-spawned by `bench sweep`. Manual start (rarely needed):
(cd router && ./start.sh)
curl -s http://127.0.0.1:8787/healthz | jq .

# router's own test sweep (strategies × prompts matrix)
cd router && npm test                                                  # writes tests/RESULTS.md

# the bench dispatcher
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench sweep --config configs/v1.4-canonical.yaml --strategies heuristic --seeds 42 --dry-run
./bench show-config --config configs/v1.4-canonical.yaml
./bench env-detect --out results/my-run/env-manifest.json
./bench rejudge  results/runs/v1.4-canonical/                          # post-sweep Opus re-judge
./bench analyze  results/runs/v1.4-canonical/                          # aggregate + bootstrap CIs + charts
./bench token-budget results/runs/v1.4-canonical/                      # 6-scenario token + cost matrix
./bench schema --out configs/schema.json                               # regen JSON Schema
./bench setup                                                          # one-shot first-time setup
```

> `./bench report` regenerates the maintainer's article + appendices into the gitignored `personal/reports/` directory. It is not part of the public OSS surface.

## Folder-by-folder inventory

Every directory in the repo and what it contains. If you're a new agent and want to find something, this is the map.

### Top level

| Path | What it is |
| --- | --- |
| `README.md` | OSS landing page |
| `AGENTS.md` | **this file** — canonical agent guide |
| `CHANGELOG.md` | Keep-a-Changelog release history |
| `CONTRIBUTING.md` | Dev setup, model/benchmark contribution flow, PR style |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1 |
| `LICENSE` | MIT (covers code under `src/`, `router/`, `tests/`, `configs/`) |
| `LICENSE-DATA` | CC-BY-4.0 (covers data under `results/`, charts, docs prose) |
| `LICENSE.md` | File-type breakdown of MIT vs CC-BY-4.0 |
| `NOTICE.md` | Third-party attribution |
| `bench` | Shell wrapper that execs `python -m hybrid_coding_eval.cli.bench` |
| `pyproject.toml` | Python package config — version, deps, pytest, ruff. Declares `bench` console script |
| `requirements.txt` | Pip dependency pins (kept in sync with pyproject.toml's `[project.dependencies]`) |
| `.env.example` | Template — copy to `.env` and fill `OPEN_AI_API_KEY` (+ optionally `ANTHROPIC_API_KEY`) |

### `configs/` — variant configs, pricing, router corpus, JSON schema

```
configs/
├── v1.4-canonical.yaml           # ← canonical v1.4 sweep config (5 agents, 8 strategies, 18 tasks)
├── pricing/pricing_tables.json   # 6 pricing scenarios, SHA256-pinned
├── router/corpus.json            # 50-example hand-labelled corpus for the embedding-kNN strategy
├── schema.json                   # auto-generated JSON Schema for BenchConfig
└── variants/                     # legacy per-variant configs (v1.0–v1.3, kept as recipes)
    ├── 07-v3-devstral-all-routes.yaml         # historical v3 canonical config
    ├── 26-v1.2-aider-r7-canonical.yaml        # v1.2.0 canonical
    ├── 28-v1.3-aider-r7-expanded.yaml         # v1.3.0 baseline sweep
    ├── 29-v1.3-aider-r7-gemma4.yaml           # v1.3.0 gemma4 multi-model sweep
    └── 30-v1.3-aider-r7-cascade-threshold.yaml # v1.3.0 cascade threshold sweep
```

YAML configs are the canonical sweep-definition surface. The schema at `configs/schema.json` is auto-generated from `src/hybrid_coding_eval/core/config/schema.py` — never hand-edit. Override fields on the CLI with `--set key.path=value` rather than editing the YAML for one-shot runs.

### `src/hybrid_coding_eval/` — the Python package

```
src/hybrid_coding_eval/
├── cli/                          # ./bench dispatcher and subcommands
│   ├── bench.py                  # top-level CLI entry — dispatches to subcommand modules + sweep
│   ├── run.py                    # ./bench run — single-pass sweep orchestrator
│   ├── analyze.py                # ./bench analyze — aggregate + bootstrap CIs + charts
│   ├── rescore.py                # ./bench rescore — post-sweep functional rescore
│   ├── rejudge.py                # ./bench rejudge — post-sweep LLM-judge re-run
│   ├── judge.py                  # internal helper used by rejudge
│   ├── report.py                 # ./bench report — regenerates ARTICLE/APPENDIX/... (maintainer-only)
│   └── env_detect.py             # ./bench env-detect — captures hardware + software snapshot
│
├── core/                         # everything every agent + scorer + analysis depends on
│   ├── experiment.py             # build_task_plan, run_pair — the dispatcher loop
│   ├── metrics.py                # ResultRow + TokenUsage + Latency + Quality + Routing dataclasses
│   ├── pricing.py                # token → cost derivation against pricing_tables.json
│   ├── results.py                # append_row + pair_already_done (raw.jsonl I/O)
│   ├── sandbox.py                # Docker sandbox helper for functional scorer
│   ├── paths.py                  # repo-root resolver
│   └── config/                   # YAML config schema + loader + variable resolver
│       ├── schema.py             # Pydantic BenchConfig model (source of truth for configs/schema.json)
│       ├── loader.py             # YAML → BenchConfig with env-var ${ENV:VAR} expansion
│       └── resolve.py            # config flag overrides (--set key.path=value)
│
├── agents/                       # one module per agentic route (post-v1.4 rename of runners/)
│   ├── r6_mini_swe.py            # mini-swe-agent (Princeton)
│   ├── r7_aider.py               # aider (architect/editor protocol — the v1.2/v1.3 canonical)
│   ├── r8_opencode.py            # opencode (free-form tool use)
│   ├── r9_claude_code.py         # Anthropic claude-code CLI
│   ├── r10_cline.py              # cline VSCode agent (headless)
│   ├── _agent_attribution.py     # correlation-id token attribution for the proxy
│   └── _shared.py                # proxy_health, token_normalize, chat call helpers
│
├── scorers/                      # one scorer per quality dimension
│   ├── functional_python.py      # extracts code, runs pytest in a Docker sandbox
│   ├── llm_judge.py              # claude-opus-4-7 pairwise judge with 5-dim rubric
│   └── Dockerfile.functional_python  # python:3.12-slim + pytest sandbox image
│
├── benchmarks/                   # task-source adapters
│   ├── exercism_python/          # puzzles (was category X); Aider polyglot benchmark, MIT
│   └── real_dev/                 # refactors (was category D); hand-written real-PR patterns
│       ├── tasks-d1.jsonl        # 4 small-feature tasks
│       ├── tasks-d5.jsonl        # 4 small one-shot tasks
│       ├── scorers.py            # per-task scorer dispatcher
│       └── fixtures/             # per-task fixture dirs (d1-*, d5-*)
│
├── analysis/                     # post-sweep number-crunching
│   ├── all.py                    # the entry-point; runs everything below
│   ├── aggregate.py              # per-(category, route, strategy) means/medians/sums
│   ├── bootstrap.py              # 95% percentile CIs per cell (v1.1+)
│   ├── decision_matrix.py        # category × route → recommendation
│   ├── cost_scenarios.py         # re-price under 6 pricing scenarios
│   ├── token_budget.py           # ./bench token-budget — token-first matrix
│   ├── token_share.py            # cloud_fraction analysis
│   └── reprice.py                # standalone re-pricing helper
│
└── viz/                          # chart generators
    ├── cost_quality_pareto.py    # Pareto scatter (cost vs quality)
    └── decision_heatmap.py       # category × route quality/cost heatmaps
```

> **Note on `agents/` vs `runners/`:** v1.4 renames the agentic-route modules to `agents/`. If you're reading the tree pre-rename, look for `src/hybrid_coding_eval/runners/r6_*.py` … `r10_*.py`. The rename is mechanical and tracked in the v1.4.0 CHANGELOG.

### `router/` — zero-deps Node hybrid proxy

OpenAI-compatible HTTP proxy on `:8787`. **Auto-spawned by `bench sweep`** in v1.4 — manual start is rarely needed. The `model` field of each request selects a routing strategy (`router/always-local`, `router/heuristic`, `router/cascade`, etc.; 8 total). Append `!local`/`!cloud` to force a backend.

```
router/
├── server.mjs                    # the HTTP server; entry point
├── strategies.mjs                # 8 routing strategies
├── pricing.mjs                   # shared pricing table reader (kept in sync with configs/pricing)
├── start.sh                      # manual starter — loads ../.env, binds 127.0.0.1
├── package.json                  # minimal — declares "node-test" runner only
├── pipelines/architect/          # historical R3 planner/executor/synth pipeline (legacy)
├── tests/                        # router's own test sweep
└── logs/decisions.jsonl          # historical routing decisions (tracked)
```

Config is env-driven: `LOCAL_BASE`, `LOCAL_MODEL`, `CLOUD_MODEL`, `CLOUD_API_KEY` (resolves from `OPENAI_API_KEY` or `OPEN_AI_API_KEY`). Binds 127.0.0.1 only; no auth — don't expose.

### `tests/` — pytest suite

Fast tests are ~180 (3 marked `slow` for the Docker harness). All hit `.venv/bin/pytest`.

```
tests/
├── analysis/test_token_budget.py
├── benchmarks/test_real_dev_scaffold.py
├── agents/test_r*.py              # one per agentic route (R6..R10) — post-v1.4 location
├── scorers/test_real_dev_scorers.py
├── test_humaneval_plus.py / test_bigcodebench_hard.py / test_custom_arch.py    # legacy benchmarks (kept for v3 dataset replay)
├── test_functional_python.py / test_sandbox.py
├── test_llm_judge.py
├── test_aggregate.py / test_arqgc.py
├── test_orchestrator.py / test_results.py
├── test_metrics_new_fields.py
├── test_config.py
├── test_env_detect.py
└── test_pricing_parity.py / test_pricing_path_parity.py
```

Subprocess-based tests `pytest.skip` cleanly if the router proxy is down.

### `vendor/` — third-party (read-only)

```
vendor/
├── README.md                     # explains what's vendored
├── lm-eval-harness-judge/        # MT-Bench judge reference (Apache 2.0) — referenced, not imported
└── opencode/                     # opencode fork for R8 (only cloned if BENCH_SETUP_OPENCODE=1)
```

Treat `vendor/` as immutable. If you find a bug, patch our wrapper in `agents/`, not the vendored source. Long-term fix is an upstream PR.

### `results/` — canonical research data (CC-BY-4.0)

```
results/
├── raw.jsonl                     # MVP merged dataset (180 rows, bit-identical forever)
├── REPORT_v1_mvp.md              # MVP report (frozen)
├── env-manifests/                # 01–04 hardware snapshots
└── runs/                         # one dir per preserved sweep
    ├── README.md                 # run-by-run index
    ├── 01-v1-qwen-original/      # MVP v1 sweep
    ├── 02-v2-qwen-fixed-synth/   # MVP v2 (Opus judge)
    ├── 03-v2-devstral/           # MVP v2 with devstral local
    ├── 04-r4-minion/             # MVP R4 Minion sweep (legacy R4 — preserved data)
    ├── 07-v3-devstral-all-routes/ # ← v3 canonical 250-row sweep (legacy R1–R5)
    └── 11-judge-robust-D/        # 96-verdict triple-judge audit on D3+D4
```

**`results/runs/` is gitignored going forward.** v1.4+ per-tag datasets are GitHub release tarballs (`results-v1.4.K.tar.gz`). Pre-existing tracked runs (01–04, 07, 11) are immutable.

### `docs/` — reference documentation (CC-BY-4.0)

```
docs/
├── REPRODUCING.md                # v1.4 reproducer + how-to-read-results cell→headline map
├── BENCHMARK_NEW_MODEL.md        # add-a-new-local-model walkthrough
├── METHODOLOGY.md                # scoring rubrics + biases acknowledged + what we do/don't claim
├── ARCHITECTURE.md               # long-form code layout + data flow
├── ROUTING_STRATEGIES.md         # deep dive on the 8 router strategies
├── AGENTIC_ROUTES.md             # R6..R10 design + correlation-id attribution
├── HYBRID_ROUTER_DESIGN.md       # router architecture deep-dive
├── PRIOR_ART.md                  # 2026 research synthesis
├── audits/
│   └── T-22-v3-publish-readiness.md   # historical pre-public audit
└── release-notes/                # tracked-in-git release notes (v1.4+)
    └── v1.4.0.md                 # v1.4.0 canonical findings
```

ARCHITECTURE.md is the longest doc — read it if you need to understand the code in depth. METHODOLOGY.md is the doc to read before interpreting any number in `results/runs/`.

## Architecture — the big picture

Five agentic routes (R6..R10), one shared pricing + scoring + analysis pipeline, two languages glued through a local HTTP proxy that is auto-spawned by `bench sweep`.

### Data flow for one experiment row

```text
./bench sweep --config configs/v1.4-canonical.yaml --strategies heuristic --seeds 42
  → hybrid_coding_eval.cli.bench._cmd_sweep
  → _router_for_model(local_model, port, …)             # auto-spawn router/server.mjs
    → for each (strategy, seed):
      → hybrid_coding_eval.cli.bench._cmd_run
      → hybrid_coding_eval.cli.run.main                  # dispatches via argv for back-compat
      → hybrid_coding_eval.core.experiment.build_task_plan()
      → hybrid_coding_eval.core.experiment.run_pair()    # picks the agent per route
           ├── agents/r6_mini_swe.py
           ├── agents/r7_aider.py
           ├── agents/r8_opencode.py
           ├── agents/r9_claude_code.py
           └── agents/r10_cline.py
      → scorers/*                                         # functional_python (Docker sandbox), llm_judge
      → core/results.append_row()                         # one JSON line per (task, route) to <out>/raw.jsonl
```

Rows are flushed after each `(task, route)` completes, so sweeps are crash-resumable (the orchestrator checks `(task_id, route)` pairs already in `raw.jsonl`).

### The router proxy (`router/`, Node zero-deps)

OpenAI-compatible HTTP proxy on `:8787`. The `model` field of each request selects a routing strategy. Append `!local`/`!cloud` to force a backend.

Strategies (in `router/strategies.mjs`):

1. `always-cloud` — control baseline; every request goes cloud
2. `always-local` — control baseline; every request goes local
3. `rules` — keyword + regex rules
4. `heuristic` — weighted-score classifier, agent-aware
5. `llm-classifier` — `qwen3:0.6b` returns SIMPLE/COMPLEX
6. `embedding-knn` — top-5 cosine-similar examples from a 50-example labelled corpus
7. `cascade` — heuristic decides first; on low confidence, llm-classifier tiebreaks
8. `cascade-tuned` — cascade with `ROUTER_CASCADE_THRESHOLD` env-tunable

Decisions are appended to `router/logs/decisions.jsonl`.

### Auto-spawn-router (v1.4)

`bench sweep` reads `models.local` from the config and spawns `node router/server.mjs` with:

- `LOCAL_MODEL=<config.models.local>`
- `CLOUD_MODEL=<config.models.cloud>` (default `gpt-5.5`)
- `OPEN_AI_API_KEY=...` (loaded from `.env`)
- `PORT=<config.router.port>` (default 8787)

…then waits for `/healthz` 200 before running the first pass. Tears down on completion. Pass `--external-router` to opt out (e.g. if you want to manage the router proxy yourself for debugging).

For the `--cascade-thresholds` path, the router is respawned once per threshold value with `ROUTER_CASCADE_THRESHOLD` injected on top of `LOCAL_MODEL`.

### Metrics schema (`core/metrics.py`)

One `ResultRow` per (task, route, seed). Tokens split into `local_*` / `cloud_*` (always-local must always have `cloud_* = 0`; non-zero is a routing bug). Metadata fields: `variant`, `cloud_model_id`, `local_model_id`, `judge_model_id`, `router_classifier_model_id`, `router_strategy`, `seed`, `config_sha`. All optional for back-compat with v1.0–v1.3 datasets.

### Scorers

- `scorers/functional_python.py` — extracts the first Python code block from the model output, runs pytest in a `python:3.12-slim` Docker sandbox (image `hybrid-eval-python:latest`) with `--network none`, memory caps, 60 s wall-clock timeout. Used by both task classes.
- `scorers/llm_judge.py` — `claude-opus-4-7` (cross-vendor, avoids GPT self-preference) pairwise judge with 5-dimension rubric. `temperature=0.0`. Used for prose-scored rows. Skips cleanly if `ANTHROPIC_API_KEY` unset.

### Analysis pipeline

`analysis.all` runs (in order):

1. `aggregate` — per-(category, route, strategy) means/medians/sums
2. `bootstrap` — 95% percentile CIs per cell
3. `decision_matrix` — category × route → recommendation
4. `cost_scenarios` — re-price under all 6 scenarios
5. `token_budget` — token-first matrix
6. `viz/cost_quality_pareto` + `viz/decision_heatmap` — charts

## Conventions and gotchas

- **Always call Python via `.venv/bin/python` or `.venv/bin/pytest`**, not bare `python`. The repo installs editable via `pip install -e ".[dev]"`.
- **The router proxy is auto-spawned by `bench sweep`.** You no longer need a separate `(cd router && ./start.sh) &` terminal. If you're running individual tests or scripts that need the proxy, start it manually.
- **`tests/test_*` marked `slow`** invoke the Docker harness (minutes per test). Skip with `-m 'not slow'`.
- **Preserved runs are read-only.** `results/raw.jsonl` and the tracked `results/runs/{01..04, 07, 11}/` dirs never change bytes.
- **Cost is derived, not stored.** Any `cost_usd_*` field in `raw.jsonl` is a bug. Cost is computed on read via `core/pricing.py`. The 6 pricing scenarios live in `configs/pricing/pricing_tables.json`.
- **Env keys**: `OPENAI_API_KEY` / `OPEN_AI_API_KEY` accepted (router checks both). `ANTHROPIC_API_KEY` required for the Opus judge.
- **Task classes**: `puzzles` (was `X`) = Exercism Python; `refactors` (was `D`) = real-developer D-tasks. Cell keys in `bootstrap_cis.json` use the v1.4 names.
- **`vendor/`** is vendored third-party source. Read-only.
- **YAML configs** are the canonical way to define a sweep. Override fields on the CLI with `--set key.path=value` rather than editing the YAML for one-shot runs.
- **Legacy R1–R5 routes were deleted in v1.4.** The historical 250-row v3 dataset stays at its commit; new sweeps go through R6..R10 only.

## Where to read next

In priority order:

1. `docs/REPRODUCING.md` — copy-paste v1.4 reproducer + how-to-read-results cell→headline map
2. `docs/BENCHMARK_NEW_MODEL.md` — add-a-new-local-model walkthrough
3. `docs/METHODOLOGY.md` — scoring rubrics, biases acknowledged
4. `docs/ROUTING_STRATEGIES.md` — deep dive on the 8 router strategies
5. `docs/AGENTIC_ROUTES.md` — R6..R10 design + correlation-id attribution
6. `docs/ARCHITECTURE.md` — long-form code layout + data flow
7. `docs/PRIOR_ART.md` — research synthesis
8. `docs/release-notes/v1.4.0.md` — v1.4.0 canonical findings
9. `CONTRIBUTING.md` — for anyone adding a model, benchmark, or strategy
10. `CHANGELOG.md` — v1.0 → v1.4 lineage

## License + attribution

- **Code** (`src/`, `router/`, `tests/`, `configs/`, `bench`): MIT — see `LICENSE`.
- **Data + figures + docs prose** (`results/`, `docs/`, charts): CC-BY-4.0 — see `LICENSE-DATA`. See `LICENSE.md` for the file-type breakdown.
- **Third-party**: see `NOTICE.md` and `vendor/README.md`.

Suggested citation: BibTeX entry in `README.md`.
