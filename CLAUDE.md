# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **reproducible benchmark harness** (not a product) that compares local vs cloud vs hybrid LLM routing on coding tasks. One developer laptop, one cloud model, one local model, five routes (R1-R5), 50 tasks × 5 routes = 250 v3 rows (plus 180 preserved MVP rows). Canonical article lives at `reports/ARTICLE.md` (~7,600 words; comprehensive — covers methodology, per-shape dives, per-route worked examples, 10 surprising findings, hypothesis scorecard, limits, reproducibility, citations). The preserved MVP report is `results/REPORT_v1_mvp.md`; the canonical MVP dataset is `results/raw.jsonl`. Experimental runs are **preserved as-is** under `results/runs/NN-*/` — never edit rows after a sweep; re-score or re-judge produces new per-run directories.

**Status.** v3 sweep complete on branch `mono-repo-reorg` (tag `v3-public-candidate`). Pre-MVP narrative, dated planning artefacts, and research input snapshots live in `archive/` (see `archive/README.md`); they're preserved for lineage but are not part of the canonical OSS surface. The active 22-task plan that drove the v3 cycle is `docs/FINAL_REPORT_PLAN.md` (landed).

## Drop in a new model in 90 seconds

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
# edit two lines (variant_tag + models.cloud or models.local), then:
./bench run --config configs/variants/my-model.yaml
./bench analyze results/runs/my-variant/
./bench report article
```

Need to see what the config resolves to? `./bench show-config --config configs/variants/my-model.yaml` prints the merged config + SHA256. The same `./bench run … --dry-run` prints the plan without executing.

## Common commands

Python env is pinned at 3.11/3.12. Always use `.venv/bin/python` or `.venv/bin/pytest` (the repo installs editable via `pip install -e .`).

```bash
# one-time env setup
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .

# fast tests (SWE-bench Docker tests are marked slow)
.venv/bin/pytest tests/ -q -m 'not slow'

# one test file / one test
.venv/bin/pytest tests/test_r3_hybrid_architect.py -q
.venv/bin/pytest tests/test_aggregate.py::test_name -q

# ruff (repo-wide)
.venv/bin/ruff check src/ tests/

# start the router proxy (port 8787) — REQUIRED before R1/R3/R4/R5 runs
(cd router && ./start.sh)
curl -s http://127.0.0.1:8787/healthz | jq .

# router's own test sweep (strategies × prompts matrix)
cd router && npm test                                 # writes tests/RESULTS.md

# the bench dispatcher
./bench run --config configs/variants/07-v3-devstral-all-routes.yaml   # canonical v3 full sweep
./bench run --config configs/variants/_template.yaml --dry-run         # plan only
./bench run --config configs/variants/my.yaml --set models.cloud=gpt-5 --smoke
./bench show-config --config configs/variants/07-v3-devstral-all-routes.yaml
./bench env-detect --out results/my-run/env-manifest.json
./bench rescore  results/runs/03-v2-devstral/                          # post-sweep SWE-bench rescore
./bench rejudge  results/runs/02-v2-qwen-fixed-synth/                  # post-sweep Opus re-judge
./bench analyze  results/runs/07-v3-devstral-all-routes/               # aggregate + ARQGC + charts
./bench token-budget results/runs/07-v3-devstral-all-routes/           # 6-scenario token+cost matrix
./bench schema --out configs/schema.json                               # regen JSON Schema
./bench report article                                                 # regenerate reports/ARTICLE + appendices
```

## Architecture — the big picture

Five routes (R1-R5), one shared pricing + scoring + analysis pipeline, two languages glued through a local HTTP proxy.

### Directory layout

```text
hybrid-coding-eval/
├── bench                          # top-level shell wrapper → bench.py
├── configs/
│   ├── pricing/pricing_tables.json  # shared source of truth (Python + Node)
│   ├── router/corpus.json          # embedding-kNN strategy training data
│   ├── schema.json                  # auto-generated from BenchConfig
│   └── variants/*.yaml              # one per sweep — the "drop in a new model" UX
├── src/hybrid_coding_eval/
│   ├── core/                        # metrics, pricing, results, experiment, sandbox, config/
│   ├── runners/                     # R1..R5 + _shared
│   ├── scorers/                     # functional_python, llm_judge, swebench
│   ├── benchmarks/                  # humaneval_plus, swebench_verified, bigcodebench_hard, custom_arch, real_dev
│   ├── analysis/                    # aggregate, arqgc, cost_scenarios, decision_matrix, token_budget
│   ├── viz/                         # pareto + heatmap
│   └── cli/                         # bench, run, env_detect, rescore, rejudge, analyze, token_budget, report
├── router/                          # Node proxy (zero-deps)
│   ├── server.mjs, strategies.mjs, pricing.mjs
│   └── pipelines/architect/         # core.mjs + runner.mjs (Node shim R3 subprocesses)
├── vendor/                          # vendored third-party (Stanford minions, lm-eval-harness-judge)
├── tests/                           # pytest suite
├── reports/                         # publish surface (ARTICLE, DECISION_TABLE, TOKEN_BUDGET, APPENDICES)
├── results/                         # read-only — preserved runs + canonical dataset
│   ├── raw.jsonl                    # 180 MVP rows, bit-identical forever
│   ├── REPORT_v1_mvp.md             # MVP report (frozen)
│   └── runs/                        # one dir per sweep; never edit rows in place
│       ├── 01-v1-qwen-original/     # MVP v1
│       ├── 02-v2-qwen-fixed-synth/  # MVP v2 + Opus judge
│       ├── 03-v2-devstral/          # MVP v2 with devstral
│       ├── 04-r4-minion/            # MVP R4 Minion on SWE-bench
│       ├── 07-v3-devstral-all-routes/  # v3 250-row sweep (5 routes × 8 shapes)
│       └── 11-judge-robust-D/       # 96-verdict triple-judge audit on D3+D4
├── docs/                            # reference (ARCHITECTURE, METHODOLOGY, REPRODUCING, ROUTING_STRATEGIES, PRIOR_ART, audits/T-22)
├── examples/                        # "drop in a new model" walkthrough + run-comparison.mjs
└── archive/                         # preserved lineage — pre-MVP narrative, research inputs, POC examples
```

### Data flow for one experiment row

```text
./bench run --config X.yaml
  → hybrid_coding_eval.cli.bench._cmd_run
  → hybrid_coding_eval.cli.run.main   (dispatches via argv for backward compat)
  → hybrid_coding_eval.core.experiment.build_task_plan()   # (category, source, task, route)
  → hybrid_coding_eval.core.experiment.run_pair()           # runner per route
       ├── runners/r1_cloud_only.py      # → router/always-cloud → cloud
       ├── runners/r2_local_only.py      # → router/always-local → Ollama
       ├── runners/r3_hybrid_architect.py → subprocess router/pipelines/architect/runner.mjs
       │                                    → router/pipelines/architect/core.mjs
       │                                    → router proxy (planner/executor/synth)
       ├── runners/r4_minion.py          # vendor/minions (Stanford Minion protocol)
       └── runners/r5_devminion.py       # vendor/minions DevMinion (architect/editor review loop)
  → scorers/*                            # functional_python (Docker sandbox), swebench, llm_judge
  → core/results.append_row()            # one JSON line per (task, route) to <out>/raw.jsonl
```

Rows are flushed after each (task, route) so sweeps are crash-resumable via `--resume` (checks `(task_id, route)` pairs already in `raw.jsonl`).

### The router proxy (`router/`, Node zero-deps)

OpenAI-compatible HTTP proxy on `:8787` that every R1/R3/R4/R5 call goes through. The `model` field of the request selects a routing strategy (`router/always-local`, `router/heuristic`, `router/cascade`, …; seven total in `router/strategies.mjs`). Append `!local`/`!cloud` to force a backend. Decisions are appended to `router/logs/decisions.jsonl` — historical file tracked, new per-run churn gitignored.

Config is env-driven (`LOCAL_BASE`, `LOCAL_MODEL`, `CLOUD_MODEL`, `CLOUD_API_KEY` resolving from `OPENAI_API_KEY` or `OPEN_AI_API_KEY`). `./router/start.sh` loads `../.env`. Binds `127.0.0.1` only; no auth — don't expose.

### R3 two-language boundary

R3 is the one place Python and Node cross: `runners/r3_hybrid_architect.py` subprocesses `router/pipelines/architect/runner.mjs` and parses its JSON stdout. The JS side returns `totals.hybridCostUsd` for cross-check only — **the Python aggregator re-derives cost from tokens** via `core/pricing.py` using `configs/pricing/pricing_tables.json` (2026-04-27, sourced from models.dev). **Cost is never persisted** in `raw.jsonl`; only tokens-per-backend. Same runs are re-priceable under any scenario by swapping `pricing.primary`.

### Metrics schema (`core/metrics.py`)

One `ResultRow` per (task, route, seed). Tokens split into `local_*` / `cloud_*` (R2 must always have `cloud_*` = 0; non-zero = routing bug). Optional metadata fields: `variant`, `cloud_model_id`, `local_model_id`, `judge_model_id`, `router_classifier_model_id`, `router_strategy`, `seed`, `config_sha`. All Optional for backward-compat.

### Scorers

- `scorers/functional_python.py` runs generated code in a `python:3.12-slim` Docker sandbox (image `hybrid-eval-python:latest`, built from `scorers/Dockerfile.functional_python`) with `--network none`, mem caps, wall-clock timeout.
- `scorers/swebench.py` shells out to the SWE-bench harness (x86_64 images, ~10 min/task under Rosetta on Apple Silicon).
- `scorers/llm_judge.py` uses Anthropic Opus as the judge for Categories C and D (prose-scored shapes). Judge model is configurable per call; default `claude-opus-4-7`. Skips cleanly if `ANTHROPIC_API_KEY` unset.

### Benchmarks

Five adapters under `src/hybrid_coding_eval/benchmarks/` (HumanEval+, SWE-bench Verified, BigCodeBench-Hard, custom-arch, real-dev D1-D5), each exposing `load_tasks(n=...)` → Task dataclasses with stable `id`. Pinned `tasks.jsonl` committed; `datasets`/`evalplus` only needed to refresh.

### Analysis

`analysis.all` runs: `aggregate` (means/medians per category × route) → `arqgc` (bounded area-under-quality-cost curve, capped at p90 of R1 cost per category) → `decision_matrix` → `cost_scenarios` (re-price under alternate scenarios) → `token_budget` (token-first matrix under 6 pricing scenarios) → charts.

## Conventions and gotchas

- **Always call Python via `.venv/bin/python` or `.venv/bin/pytest`**, not bare `python`. The repo installs editable.
- **The router must be running** before any R1/R3/R4/R5 runner or integration test. Tests call `runners._shared.proxy_health()` and `pytest.skip` cleanly when it's down.
- **`tests/test_*` marked `slow`** invoke the SWE-bench Docker harness (minutes per test). Skip with `-m 'not slow'`.
- **Preserved runs are read-only.** `results/raw.jsonl` and `results/runs/{01..04, 07, 11}/` never change bytes. New sweeps go to fresh-numbered dirs (e.g., `12-*/` for the next sweep).
- **Cost is derived, not stored.** Any `cost_usd_*` field in `raw.jsonl` is a bug. Cost is computed on read via `core/pricing.py`. Token-first analysis lives in `reports/TOKEN_BUDGET.md`; cost is re-derived under 6 scenarios.
- **Env keys:** `OPENAI_API_KEY` / `OPEN_AI_API_KEY` accepted. `ANTHROPIC_API_KEY` required for the Opus judge path.
- **Task adapters vs categories:** A=HumanEval+, B=SWE-bench Verified, C=BigCodeBench-Hard + custom-arch, D=real-dev (D1 small features, D2 GitHub-issue patches, D3 refactor, D4 code-review, D5 small one-shots). See `core.experiment.CATEGORY_SOURCES`.
- **`vendor/`** is vendored third-party source (Stanford `minions` for R4 + R5, `lm-eval-harness-judge` reference). Read-only. See `NOTICE.md` for licenses.
- **YAML configs under `configs/variants/` are the canonical way to define a sweep.** Override fields on the CLI with `--set key.path=value` rather than editing the YAML if you're doing a one-shot.
- **`archive/` is read-only lineage.** Don't add to it during normal work; don't import from it; don't reference it in new code or docs.

## Where to read next

- `reports/ARTICLE.md` — the canonical v3 article (~7,600 words; standalone).
- `reports/DECISION_TABLE.md`, `reports/TOKEN_BUDGET.md`, `reports/APPENDIX_{TASKS,SCENARIOS,ROUTES}.md` — the published surface.
- `results/REPORT_v1_mvp.md` — MVP report (frozen).
- `docs/ARCHITECTURE.md` — full code layout + data flow (long).
- `docs/METHODOLOGY.md` — scoring rubrics, contamination analysis, what the eval does and doesn't claim.
- `docs/REPRODUCING.md` — copy-paste reproduction on a fresh machine.
- `docs/ROUTING_STRATEGIES.md` — deep dive on the seven router strategies.
- `docs/PRIOR_ART.md` — research synthesis.
- `docs/audits/T-22-v3-publish-readiness.md` — final publish-readiness audit.
- `archive/README.md` — provenance for archived material (read only if auditing project evolution).
