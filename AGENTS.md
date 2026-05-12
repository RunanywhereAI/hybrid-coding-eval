# AGENTS.md

A single canonical guide for any AI coding agent (Claude Code, Aider, Cursor, Codex, etc.) working in this repository. Read this first.

## What this repo is

A **reproducible benchmark harness** that measures whether a coding task should run on local hardware, cloud, or via hybrid routing. It is **not a product**. It is a one-developer-laptop research artefact that publishes a 250-row dataset comparing five routes (R1–R5) across eight task shapes (A HumanEval+, B SWE-bench Verified, C BigCodeBench + custom-arch, D1–D5 real-developer tasks) under six pricing scenarios.

**Top-level canonical surfaces:**

- `README.md` — the OSS landing page
- `reports/ARTICLE.md` — the published v3 article (~7,600 words; standalone)
- `docs/REPRODUCING.md` — copy-paste reproduction on a fresh machine
- `results/runs/07-v3-devstral-all-routes/` — the canonical 250-row sweep dataset
- `LICENSE` (MIT, code) + `LICENSE-DATA` (CC-BY-4.0, data/article) + `NOTICE.md` (third-party attribution)

**Status:** v3 sweep landed 2026-05-11. Tag `v3-public-candidate` at commit `34094cc`. Branch `mono-repo-reorg`.

## Drop in a new model in 90 seconds

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
# edit two lines (variant_tag + models.cloud or models.local), then:
./bench run --config configs/variants/my-model.yaml
./bench analyze results/runs/my-variant/
./bench report article
```

`./bench show-config --config configs/variants/my-model.yaml` prints the merged config + SHA256.
`./bench run … --dry-run` prints the plan without executing.

## Common commands

Python env is pinned at 3.11/3.12. Always use `.venv/bin/python` or `.venv/bin/pytest` — the repo installs editable via `pip install -e .`.

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
cd router && npm test                                          # writes tests/RESULTS.md

# the bench dispatcher
./bench run --config configs/variants/07-v3-devstral-all-routes.yaml   # canonical v3 sweep
./bench run --config configs/variants/_template.yaml --dry-run         # plan only
./bench show-config --config configs/variants/07-v3-devstral-all-routes.yaml
./bench env-detect --out results/my-run/env-manifest.json
./bench rescore  results/runs/03-v2-devstral/                          # post-sweep SWE-bench rescore
./bench rejudge  results/runs/02-v2-qwen-fixed-synth/                  # post-sweep Opus re-judge
./bench analyze  results/runs/07-v3-devstral-all-routes/               # aggregate + ARQGC + charts
./bench token-budget results/runs/07-v3-devstral-all-routes/           # 6-scenario token + cost matrix
./bench schema --out configs/schema.json                               # regen JSON Schema
./bench report article                                                 # regenerate reports/ARTICLE etc.
```

## Folder-by-folder inventory

Every directory in the repo and what it contains. If you're a new agent and want to find something, this is the map.

### Top level

| Path | What it is |
| --- | --- |
| `README.md` | OSS landing page — points to ARTICLE, REPRODUCING, decision table |
| `AGENTS.md` | **this file** — canonical agent guide |
| `CLAUDE.md` | Pointer to AGENTS.md (kept so Claude Code auto-loader still resolves) |
| `LICENSE` | MIT (covers all code under `src/`, `router/`, `bin/`, `tests/`) |
| `LICENSE-DATA` | CC-BY-4.0 (covers everything under `results/`, `reports/`, charts, the article) |
| `NOTICE.md` | Third-party attribution — Stanford Minions, lm-eval-harness, benchmark sources |
| `bench` | Shell wrapper that execs `python -m hybrid_coding_eval.cli.bench` (see below) |
| `pyproject.toml` | Python package config: setuptools, deps, pytest, ruff. Declares `bench` console script |
| `requirements.txt` | Pip dependency pins (pytest, pandas, httpx, docker, tiktoken, openai, anthropic, pydantic, pyyaml) |
| `.env.example` | Template — copy to `.env` and fill `OPEN_AI_API_KEY` + optionally `ANTHROPIC_API_KEY` |
| `.gitignore` | Covers `.venv/`, `.env`, `__pycache__/`, `node_modules/`, `*.log`, `minion_logs/`, `.embedder/`, `.ruff_cache/`, `router/logs/*.jsonl` (except `decisions.jsonl`), `vendor/minions/`, and `results/` with a whitelist for shippable artefacts |

### `configs/` — variant configs, pricing, router corpus, JSON schema

```
configs/
├── pricing/pricing_tables.json    # 6 pricing scenarios, SHA256-pinned, dated 2026-04-27
├── router/corpus.json             # 50-example hand-labelled corpus for the embedding-kNN router strategy
├── schema.json                    # auto-generated JSON Schema for BenchConfig (regenerate via ./bench schema)
└── variants/                      # one YAML per sweep — the "drop in a new model" surface
    ├── _template.yaml             # copy this for new sweeps
    ├── _smoke-v3.yaml             # smoke variants for development
    ├── _smoke-r5.yaml
    ├── _smoke-realdev.yaml
    ├── 01-gpt5.5-qwen-v1.yaml     # MVP v1 sweep (run 01)
    ├── 02-gpt5.5-qwen-fixed-synth.yaml
    ├── 03-gpt5.5-devstral.yaml
    ├── 04-r4-devstral-minion.yaml
    ├── 05-r4-devstral-catA.yaml   # variants 05/06 are historical (the runs they produced were cleaned up,
    ├── 06-r4-devstral-catC.yaml   # but the configs are kept as recipes if anyone wants to rerun)
    ├── 07-r4-devstral-seed7.yaml
    ├── 07-v3-devstral-all-routes.yaml  # ← canonical v3 sweep config
    ├── 08-r4-devstral-seed13.yaml
    ├── 09-r3-cached-devstral.yaml
    └── 10-judge-robust.yaml
```

YAML configs are the canonical sweep-definition surface. The schema at `configs/schema.json` is auto-generated from `src/hybrid_coding_eval/core/config/schema.py` — never hand-edit it. Override fields on the CLI with `--set key.path=value` rather than editing the YAML for one-off runs.

### `src/hybrid_coding_eval/` — the Python package

The canonical Python code home. Declared in `pyproject.toml` under `[tool.setuptools.packages.find]` with `where = ["src"]`.

```
src/hybrid_coding_eval/
├── cli/                           # ./bench dispatcher and subcommands
│   ├── bench.py                   # top-level CLI entry — dispatches to subcommand modules
│   ├── run.py                     # ./bench run — the sweep orchestrator
│   ├── analyze.py                 # ./bench analyze — aggregate + ARQGC + charts (calls analysis.all)
│   ├── rescore.py                 # ./bench rescore — post-sweep SWE-bench rescore
│   ├── rejudge.py                 # ./bench rejudge — post-sweep LLM-judge re-run
│   ├── judge.py                   # internal helper used by rejudge
│   ├── report.py                  # ./bench report — regenerates ARTICLE/APPENDIX/...
│   └── env_detect.py              # ./bench env-detect — captures hardware + software snapshot
│
├── core/                          # everything every runner + scorer + analysis depends on
│   ├── experiment.py              # build_task_plan, run_pair — the dispatcher loop
│   ├── metrics.py                 # ResultRow + TokenUsage + Latency + Quality + Routing dataclasses
│   ├── pricing.py                 # token → cost derivation against pricing_tables.json
│   ├── results.py                 # append_row + pair_already_done (raw.jsonl I/O)
│   ├── sandbox.py                 # Docker sandbox helper for functional scorer
│   ├── paths.py                   # repo-root resolver
│   └── config/                    # YAML config schema + loader + variable resolver
│       ├── schema.py              # Pydantic BenchConfig model (source of truth for configs/schema.json)
│       ├── loader.py              # YAML → BenchConfig with env-var ${ENV:VAR} expansion
│       └── resolve.py             # config flag overrides (--set key.path=value)
│
├── runners/                       # one runner per route
│   ├── r1_cloud_only.py           # single chat call to cloud (gpt-5.5)
│   ├── r2_local_only.py           # single chat call to local (devstral:24b via Ollama)
│   ├── r3_hybrid_architect.py     # subprocesses router/pipelines/architect/runner.mjs
│   ├── r4_minion.py               # wraps vendor/minions/minions/minion.py (Stanford Minion)
│   ├── r5_devminion.py            # wraps vendor/minions/minions/minion_code.py (Stanford DevMinion)
│   └── _shared.py                 # proxy_health, token_normalize, chat call helpers
│
├── scorers/                       # one scorer per quality dimension
│   ├── functional_python.py       # extracts code, runs pytest in a Docker sandbox (A, C-bcb, D1, D5)
│   ├── swebench.py                # shells out to the SWE-bench harness (B)
│   ├── llm_judge.py               # claude-opus-4-7 pairwise judge with 5-dim rubric (C-arch, D3, D4)
│   └── Dockerfile.functional_python  # python:3.12-slim + pytest sandbox image
│
├── benchmarks/                    # one adapter per task source
│   ├── humaneval_plus/            # 10 tasks, pinned tasks.jsonl
│   ├── swebench_verified/         # 10 tasks, pinned, has verify_harness.py
│   ├── bigcodebench_hard/         # 5 tasks, pinned
│   ├── custom_arch/               # 5 tasks, pinned (hand-written by authors)
│   └── real_dev/                  # 20 tasks across 5 shapes
│       ├── tasks-d1.jsonl         # 4 small-feature tasks
│       ├── tasks-d2.jsonl         # 4 GitHub-issue patches (functional scorer deferred)
│       ├── scorers.py             # per-task scorer dispatcher
│       └── fixtures/              # one directory per task (d1-*, d2-*, d3-*, d4-*, d5-*)
│                                  # each contains a reference solution, pytest, prompt template
│
├── analysis/                      # post-sweep number-crunching
│   ├── all.py                     # the entry-point; runs everything below
│   ├── aggregate.py               # per-(category, route) means/medians/sums
│   ├── arqgc.py                   # bounded area-under-quality-cost curve
│   ├── decision_matrix.py         # category × route → recommendation
│   ├── decision_matrix_v2.py      # v3-era refresh of decision matrix
│   ├── cost_scenarios.py          # re-price under 6 pricing scenarios
│   ├── token_budget.py            # ./bench token-budget — token-first matrix
│   ├── token_share.py             # cloud_fraction analysis
│   ├── reprice.py                 # standalone re-pricing helper
│   └── judge_robustness.py        # processes the triple-judge audit verdicts
│
└── viz/                           # chart generators
    ├── cost_quality_pareto.py     # the Pareto scatter (cost vs quality)
    └── decision_heatmap.py        # category × route quality/cost heatmaps
```

Each `runners/r*` file is ~80–300 LOC. The R3 runner subprocesses a Node script; everything else is pure Python.

### `router/` — zero-deps Node hybrid proxy

OpenAI-compatible HTTP proxy on `:8787` that every R1/R3/R4/R5 cloud or local call passes through. The `model` field of each request selects a routing strategy (`router/always-local`, `router/heuristic`, `router/cascade`, etc.; seven total). Append `!local`/`!cloud` to force a backend.

```
router/
├── server.mjs                     # the HTTP server; entry point
├── strategies.mjs                 # 7 routing strategies (always-cloud, always-local, rules,
│                                  #   heuristic, llm-classifier, embedding-knn, cascade)
├── pricing.mjs                    # shared pricing table reader (kept in sync with configs/pricing)
├── start.sh                       # convenience starter — loads ../.env, binds 127.0.0.1
├── package.json                   # minimal — declares "node-test" runner only
├── pipelines/architect/           # R3's planner/executor/synth pipeline
│   ├── core.mjs                   # state machine
│   └── runner.mjs                 # CLI entry that R3 subprocesses
├── agentic/                       # reference demo (NOT wired into the v3 sweep)
│   ├── architect.mjs              # standalone demo of the architect pipeline
│   ├── examples/                  # 4 pre-MVP demo runs (preserved for reference)
│   └── README.md                  # describes the demo
├── tests/                         # router's own test sweep (strategies × prompts matrix)
│   ├── prompts.json
│   ├── run-tests.mjs
│   ├── RESULTS.json
│   └── RESULTS.md
├── logs/decisions.jsonl           # historical routing decisions (tracked; new churn gitignored)
└── README.md                      # router-specific README
```

Config is env-driven: `LOCAL_BASE`, `LOCAL_MODEL`, `CLOUD_MODEL`, `CLOUD_API_KEY` (resolves from `OPENAI_API_KEY` or `OPEN_AI_API_KEY`). Binds 127.0.0.1 only; no auth — don't expose.

### `tests/` — pytest suite

29 test files, ~180 fast tests (3 marked `slow` for the SWE-bench Docker harness).

```
tests/
├── analysis/
│   └── test_token_budget.py
├── benchmarks/
│   └── test_real_dev_scaffold.py  # scaffold tests for the real-dev adapter
├── runners/
│   └── test_r5_devminion.py
├── scorers/
│   └── test_real_dev_scorers.py
├── test_r1_cloud_only.py / test_r2_local_only.py / test_r3_hybrid_architect.py
├── test_humaneval_plus.py / test_bigcodebench_hard.py / test_custom_arch.py
├── test_swebench_verified.py / test_swebench_scorer.py (slow)
├── test_functional_python.py / test_sandbox.py
├── test_llm_judge.py
├── test_aggregate.py / test_arqgc.py
├── test_orchestrator.py / test_results.py
├── test_metrics_new_fields.py
├── test_config.py
├── test_env_detect.py
├── test_pricing_parity.py / test_pricing_path_parity.py
└── test_viz.py
```

R1/R3 tests subprocess the router proxy; they `pytest.skip` cleanly if the router is down. SWE-bench tests need Docker + the SWE-bench image, take minutes per test, are marked `slow`.

### `vendor/` — third-party (read-only)

```
vendor/
├── README.md                      # explains what's vendored + how to clone minions
├── lm-eval-harness-judge/         # MT-Bench judge reference (Apache 2.0)
│                                  # — referenced but not imported; we reimplement
└── minions/                       # Stanford Minion library (MIT)
                                   # — gitignored (~8.5 MB); needs separate clone for R4 + R5:
                                   #   cd vendor && git clone https://github.com/HazyResearch/minions.git
```

Treat `vendor/` as immutable. If you find a bug in vendored code, patch our wrapper (`src/hybrid_coding_eval/runners/r5_devminion.py` already monkey-patches DevMinion's JSON extractor), not the vendored source. Long-term, the fix is an upstream PR.

### `reports/` — the published surface (CC-BY-4.0)

The artefacts a reader of the public release consumes.

```
reports/
├── ARTICLE.md                     # 7,600-word standalone comprehensive article ← start here
├── DECISION_TABLE.md              # 8 shapes × 5 routes pass/cost/cloud_fraction grid
├── TOKEN_BUDGET.md                # token-first cost matrix narrative
├── APPENDIX_TASKS.md              # every (task, route, variant) row verbatim (~146k words; query with jq)
├── APPENDIX_SCENARIOS.md          # 6-pricing-scenario $/correct
├── APPENDIX_ROUTES.md             # R1-R5 deep-dive worked examples
└── token_budget.csv               # raw cost-derivation data, one row per (task, route)
```

### `results/` — canonical research data (CC-BY-4.0)

Preserved as-is. Do not edit rows after a sweep; re-score or re-judge produces new per-run directories.

```
results/
├── raw.jsonl                      # MVP merged dataset (180 rows, bit-identical forever)
├── REPORT_v1_mvp.md               # MVP report (frozen)
├── env-manifests/                 # 01–04 hardware snapshots (per-variant)
├── reprice/                       # 6-scenario cost-derivation CSVs (regenerated by analyze)
└── runs/                          # one dir per preserved sweep
    ├── README.md                  # run-by-run index
    ├── 01-v1-qwen-original/       # MVP v1 sweep
    ├── 02-v2-qwen-fixed-synth/    # MVP v2 (Opus judge)
    ├── 03-v2-devstral/            # MVP v2 with devstral local
    ├── 04-r4-minion/              # MVP R4 Minion sweep
    ├── 07-v3-devstral-all-routes/ # ← v3 canonical 250-row sweep
    └── 11-judge-robust-D/         # 96-verdict triple-judge audit on D3+D4
```

Per-run directory contents (`07-v3-devstral-all-routes/` is the canonical example):

```
07-v3-devstral-all-routes/
├── raw.jsonl                      # one ResultRow per (task, route) — the source of truth
├── bench-config.json              # the merged config that produced this run (with SHA256)
├── env-manifest.json              # hardware + software snapshot
├── progress.log                   # per-row progress lines
├── run-notes.md                   # human-written per-run findings
├── outputs/                       # raw model-generated text for each (task, route)
├── aggregate.json                 # per-(category, route) means/medians/sums (regenerable)
├── arqgc.json                     # Bounded ARQGC per (category, route) (regenerable)
├── decision_matrix.md             # category × route quality/cost/wall (regenerable)
├── decision_matrix.json           # machine-readable version
├── token_budget.json              # 6-scenario re-pricing matrix
├── charts/                        # pareto.png, heatmap_quality.png, heatmap_cost.png, ...
└── minion_logs/                   # R4/R5 multi-round transcripts (raw)
```

**Whitelist policy**: the global `.gitignore` ignores all of `results/` and then white-lists only the shippable artefacts (`README.md`, `REPORT.md`, charts, `DECISION_MATRIX.md`). The actual sweep data (`raw.jsonl`, `outputs/`) is local-only — anyone reproducing must rerun. Pre-existing canonical runs (01–04, 07, 11) are tracked because they predate the whitelist; they are immutable from this point forward.

### `docs/` — reference documentation (CC-BY-4.0)

```
docs/
├── ARCHITECTURE.md                # long-form code layout + data flow (13k words)
├── METHODOLOGY.md                 # scoring rubrics + biases acknowledged + what we do/don't claim
├── REPRODUCING.md                 # 17-section step-by-step fresh-clone reproduction guide
├── ROUTING_STRATEGIES.md          # deep dive on the 7 router strategies
├── PRIOR_ART.md                   # May 2026 research synthesis (feeds into ARTICLE.md)
└── audits/
    └── T-22-v3-publish-readiness.md   # final pre-public audit
```

ARCHITECTURE.md is the longest doc — read it if you need to understand the code in depth. METHODOLOGY.md is the doc to read before interpreting any number in `reports/`.

### `examples/` — drop-in walkthrough

```
examples/
├── drop-in-a-new-model.md         # 5-step guide for benchmarking a new model
├── RESULTS.md                     # index of example comparisons
└── run-comparison.mjs             # Node harness for the walkthrough
```

## Architecture — the big picture

Five routes (R1–R5), one shared pricing + scoring + analysis pipeline, two languages glued through a local HTTP proxy.

### Data flow for one experiment row

```text
./bench run --config X.yaml
  → hybrid_coding_eval.cli.bench._cmd_run
  → hybrid_coding_eval.cli.run.main                     # dispatches via argv for back-compat
  → hybrid_coding_eval.core.experiment.build_task_plan() # (category, source, task, route)
  → hybrid_coding_eval.core.experiment.run_pair()        # picks the runner per route
       ├── runners/r1_cloud_only.py      → router/always-cloud → cloud
       ├── runners/r2_local_only.py      → router/always-local → Ollama
       ├── runners/r3_hybrid_architect.py → subprocess router/pipelines/architect/runner.mjs
       │                                    → core.mjs → router proxy (planner/executor/synth)
       ├── runners/r4_minion.py          → vendor/minions/minions/minion.py
       └── runners/r5_devminion.py       → vendor/minions/minions/minion_code.py
  → scorers/*                            # functional_python (Docker sandbox), swebench, llm_judge
  → core/results.append_row()            # one JSON line per (task, route) to <out>/raw.jsonl
```

Rows are flushed after each `(task, route)` completes, so sweeps are crash-resumable via `--resume` (checks `(task_id, route)` pairs already in `raw.jsonl`).

### The router proxy (`router/`, Node zero-deps)

OpenAI-compatible HTTP proxy on `:8787` that every R1/R3/R4/R5 call goes through. The `model` field of the request selects a routing strategy. Append `!local`/`!cloud` to force a backend.

Strategies (in `router/strategies.mjs`):

1. `always-cloud` — control baseline; every request goes cloud.
2. `always-local` — control baseline; every request goes local.
3. `rules` — keyword + regex rules (24 CLOUD\_KEYWORDS, 12 LOCAL\_KEYWORDS, token threshold).
4. `heuristic` — weighted-score classifier; threshold 25; confidence-margin tiebreaker.
5. `llm-classifier` — `qwen3:0.6b` returns SIMPLE/COMPLEX; +50–200 ms latency, stochastic.
6. `embedding-knn` — top-5 cosine-similar examples from a 50-example labelled corpus.
7. `cascade` — heuristic decides first; on low confidence, llm-classifier tiebreaks.

Decisions are appended to `router/logs/decisions.jsonl` — historical file tracked, new per-run churn gitignored.

### R3 two-language boundary

R3 is the one place Python and Node cross: `runners/r3_hybrid_architect.py` subprocesses `router/pipelines/architect/runner.mjs` and parses its JSON stdout. The JS side returns `totals.hybridCostUsd` for cross-check only — **the Python aggregator re-derives cost from tokens** via `core/pricing.py` using `configs/pricing/pricing_tables.json`. **Cost is never persisted** in `raw.jsonl`; only tokens-per-backend. Same runs are re-priceable under any of the 6 scenarios by swapping `pricing.primary`.

### Metrics schema (`core/metrics.py`)

One `ResultRow` per (task, route, seed). Tokens split into `local_*` / `cloud_*` (R2 must always have `cloud_* = 0`; non-zero is a routing bug). Metadata fields: `variant`, `cloud_model_id`, `local_model_id`, `judge_model_id`, `router_classifier_model_id`, `router_strategy`, `seed`, `config_sha`. All optional for back-compat.

### Scorers

- `scorers/functional_python.py` — extracts the first Python code block from the model output, runs pytest in a `python:3.12-slim` Docker sandbox (image `hybrid-eval-python:latest`, built from `Dockerfile.functional_python`) with `--network none`, memory caps, 60 s wall-clock timeout. Used by A, C-bcb, D1, D5.
- `scorers/swebench.py` — shells out to the SWE-bench harness (x86_64 images, ~10 min/task under Rosetta on Apple Silicon). Used by B.
- `scorers/llm_judge.py` — `claude-opus-4-7` (cross-vendor, avoids GPT self-preference) pairwise judge with 5-dimension rubric (correctness, completeness, style, reasoning depth, practicality). A-vs-B + B-vs-A averaged. `temperature=0.0`. Used by C-arch, D3, D4. Skips cleanly if `ANTHROPIC_API_KEY` unset.

### Benchmarks

Five adapters under `src/hybrid_coding_eval/benchmarks/` (HumanEval+, SWE-bench Verified, BigCodeBench-Hard, custom-arch, real-dev D1-D5), each exposing `load_tasks(n=...)` → Task dataclasses with stable `id`. Pinned `tasks.jsonl` committed; `datasets`/`evalplus` only needed if refreshing.

### Analysis pipeline

`analysis.all` runs (in order):

1. `aggregate` — per-(category, route) means/medians/sums.
2. `arqgc` — Bounded area-under-quality-cost curve, capped at p90 of R1 cost per category.
3. `decision_matrix` — category × route → recommendation.
4. `cost_scenarios` — re-price under all 6 scenarios.
5. `token_budget` — token-first matrix.
6. `viz/cost_quality_pareto` + `viz/decision_heatmap` — charts.

## Conventions and gotchas

- **Always call Python via `.venv/bin/python` or `.venv/bin/pytest`**, not bare `python`. The repo installs editable.
- **The router must be running** before any R1/R3/R4/R5 runner or integration test. Tests call `runners._shared.proxy_health()` and `pytest.skip` cleanly when it's down.
- **`tests/test_*` marked `slow`** invoke the SWE-bench Docker harness (minutes per test). Skip with `-m 'not slow'`.
- **Preserved runs are read-only.** `results/raw.jsonl` and `results/runs/{01..04, 07, 11}/` never change bytes. New sweeps go to fresh-numbered dirs (e.g. `12-*/` for the next one).
- **Cost is derived, not stored.** Any `cost_usd_*` field in `raw.jsonl` is a bug. Cost is computed on read via `core/pricing.py`. The 6 pricing scenarios live in `configs/pricing/pricing_tables.json` (SHA256-pinned, dated 2026-04-27).
- **Env keys**: `OPENAI_API_KEY` / `OPEN_AI_API_KEY` accepted (router checks both). `ANTHROPIC_API_KEY` required for the Opus judge path.
- **Task adapters vs categories**: A=HumanEval+, B=SWE-bench Verified, C=BigCodeBench-Hard + custom_arch, D=real-dev (D1 small-feature, D2 GitHub-issue patches, D3 refactor, D4 code-review, D5 small one-shots). See `core.experiment.CATEGORY_SOURCES`.
- **`vendor/`** is vendored third-party source. Read-only. See `NOTICE.md` for licenses.
- **YAML configs under `configs/variants/`** are the canonical way to define a sweep. Override fields on the CLI with `--set key.path=value` rather than editing the YAML for one-shot runs.
- **D2 functional scorer is deferred** — 20 of 250 v3 rows have `functional_pass=None` by design. External GitHub-issue patches need a per-task harness; the existing SWE-bench scorer hard-codes princeton-nlp's HF dataset.
- **R5 has an upstream JSON-extraction fragility** in `vendor/minions/minions/minion_code.py`. Our `runners/r5_devminion.py` patches it; residual brittleness may still bias R5 down.
- **HumanEval+ contamination risk is HIGH** (pre-2021, widely indexed). Treat A as a floor, not a ceiling.
- **The v1 R4 SWE-bench Sphinx wins did not replicate in v3.** Don't quote that headline without checking run 07's actual numbers.

## Where to read next

In priority order:

1. **`reports/ARTICLE.md`** — the canonical v3 article (~7,600 words, standalone, covers methodology + per-shape dives + per-route worked examples + 10 surprising findings + scorecard + reproducibility).
2. `reports/DECISION_TABLE.md` — per-shape × route grid (canonical).
3. `reports/TOKEN_BUDGET.md` — token-first cost matrix.
4. `reports/APPENDIX_{TASKS,SCENARIOS,ROUTES}.md` — forensic detail.
5. `docs/REPRODUCING.md` — copy-paste reproduction on a fresh machine.
6. `docs/METHODOLOGY.md` — scoring rubrics, biases acknowledged.
7. `docs/ROUTING_STRATEGIES.md` — deep-dive on the 7 router strategies.
8. `docs/ARCHITECTURE.md` — long-form code layout + data flow.
9. `docs/PRIOR_ART.md` — research synthesis.
10. `docs/audits/T-22-v3-publish-readiness.md` — pre-public audit.
11. `results/runs/07-v3-devstral-all-routes/run-notes.md` — per-run findings on the canonical v3 sweep.
12. `results/runs/11-judge-robust-D/run-notes.md` — triple-judge robustness audit.
13. `results/REPORT_v1_mvp.md` — MVP report (frozen).

## License + attribution

- **Code** (`src/`, `router/`, `tests/`, `configs/`, `bench`): MIT — see `LICENSE`.
- **Data + reports + figures + article** (`results/`, `reports/`, charts): CC-BY-4.0 — see `LICENSE-DATA`.
- **Third-party**: Stanford Minions (MIT) + lm-eval-harness-judge (Apache 2.0) — see `NOTICE.md` and `vendor/README.md`. Benchmark tasks sampled from HumanEval+ (Apache 2.0), SWE-bench Verified (MIT), BigCodeBench-Hard (Apache 2.0). custom-arch + real-dev tasks hand-written by repo authors (CC-BY-4.0).

Suggested citation: see `reports/ARTICLE.md` §13.
