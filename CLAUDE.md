# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **reproducible benchmark harness** (not a product) that compares local vs cloud vs hybrid LLM routing on coding tasks. One developer laptop, one cloud model, one local model, four routes, 30 tasks. The canonical results live in `results/REPORT.md`; the canonical dataset is `results/raw.jsonl`. Experimental runs are **preserved as-is** under `results/runs/NN-*/` — do not edit rows after a sweep, re-score or re-judge instead (see §Scripts below).

## Common commands

Python env is pinned at 3.11/3.12. Tests, runners, and analysis all assume `.venv/bin/python`.

```bash
# env setup (one-time)
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .

# run all fast tests (SWE-bench Docker tests are marked slow)
.venv/bin/pytest tests/ -q -m 'not slow'

# one test file / one test
.venv/bin/pytest tests/test_r3_hybrid_architect.py -q
.venv/bin/pytest tests/test_aggregate.py::test_name -q

# start the router proxy (port 8787) — REQUIRED before running any R1/R3/R4 runner
(cd router && ./start.sh)
curl -s http://127.0.0.1:8787/healthz | jq .        # sanity

# router's own test sweep (strategies × prompts matrix)
cd router && node test/run-tests.mjs                # writes test/RESULTS.md

# full experiment sweep (30 tasks × 4 routes, ~4–5 h, ~$15)
.venv/bin/python bin/run-experiment.py --out results/full-$(date +%Y%m%d)
.venv/bin/python bin/run-experiment.py --smoke                         # 9-row smoke
.venv/bin/python bin/run-experiment.py --routes R1,R2 --categories A,B # subset
.venv/bin/python bin/run-experiment.py --out results/X --resume        # resume after crash
.venv/bin/python bin/run-experiment.py --dry-run                       # plan only

# post-sweep rescoring (uses preserved outputs/ dir — no re-inference)
.venv/bin/python bin/rescore-swebench.py results/<run>
.venv/bin/python bin/rejudge-custom-arch.py results/<run>              # needs ANTHROPIC_API_KEY

# full analysis pipeline (aggregate + ARQGC + decision matrix + charts)
.venv/bin/python -m analysis.all results/<run>/
```

## Architecture — the big picture

Four routes (R1–R4), one shared pricing + scoring + analysis pipeline, two languages glued through a local HTTP proxy.

### Data flow for one experiment row

```text
bin/run-experiment.py
  → lib/experiment.build_task_plan()     # (category, source, task, route) tuples
  → lib/experiment.run_pair()            # dispatches to the runner per route
       ├── runners/r1_cloud_only.py      # direct OpenAI call (no router)
       ├── runners/r2_local_only.py      # direct Ollama call via router's always-local
       ├── runners/r3_hybrid_architect.py→ subprocess: runners/_architect_runner.mjs
       │                                    → router/agentic/architect-core.mjs
       │                                    → router proxy (planner/executor/synth)
       └── runners/r4_minion.py          # Stanford Minion protocol, vendored in EXTERNAL/minions
  → scorers/*                            # functional_python (Docker sandbox), swebench, llm_judge
  → lib/results.append_row()             # one JSON line to <out>/raw.jsonl, flushed immediately
```

Rows are flushed after each (task, route) so sweeps are crash-resumable via `--resume` (checks `(task_id, route)` pairs already in `raw.jsonl`).

### The router proxy (`router/`, Node zero-deps)

An OpenAI-compatible HTTP proxy on `:8787` that every R1/R3/R4 call goes through. The `model` field of the request selects a routing strategy (`router/always-local`, `router/heuristic`, `router/cascade`, etc. — seven total, defined in `router/strategies.mjs`). Append `!local` or `!cloud` to force a backend. Every decision is appended to `router/logs/decisions.jsonl`; **this file is committed** and tracked (current `git status` may show unstaged modifications — do not `git add` casual test runs into commits unless that's the point of the change).

Config is env-driven (`LOCAL_BASE`, `LOCAL_MODEL`, `CLOUD_MODEL`, `CLOUD_API_KEY` resolving from `OPENAI_API_KEY` or `OPEN_AI_API_KEY`). `start.sh` loads `../.env`. The proxy binds `127.0.0.1` only and has **no auth** — don't expose it.

### R3 two-language boundary

R3 is the one place Python and Node cross: `r3_hybrid_architect.py` subprocesses `_architect_runner.mjs` and parses its JSON stdout. The JS side returns `totals.hybridCostUsd` for cross-check only — **the Python aggregator re-derives cost from tokens** via `lib/pricing.py` using the pinned table `lib/pricing_tables.json` (dated 2026-04-27). **Cost is never persisted** in `raw.jsonl`; only tokens-per-backend are. This is deliberate so the same runs can be re-priced later.

### Metrics schema (`lib/metrics.py`)

One `ResultRow` per (task, route). Tokens are split into `local_*` / `cloud_*` (R2 must always have `cloud_*` = 0; a non-zero there is a routing bug). `Quality` fields are Optional because not every scorer applies to every task. `Routing.per_call_backends` preserves the per-step attribution chain for R3/R4.

### Scorers

- `scorers/functional_python.py` runs generated code in a `python:3.12-slim` Docker sandbox (image `hybrid-eval-python:latest`, built from `scorers/Dockerfile.functional_python`) with `--network none`, mem caps, and a wall-clock timeout. Host never touches model output directly.
- `scorers/swebench.py` shells out to the SWE-bench harness (x86_64 images, ~10 min per task under Rosetta on Apple Silicon).
- `scorers/llm_judge.py` uses Anthropic Opus as the judge for Category C architecture/reasoning tasks. Skips cleanly if `ANTHROPIC_API_KEY` is unset.

### Benchmarks (`benchmark/`)

Four adapters, each exposing `load_tasks(n=...)` returning task dataclasses with a stable `id`. Pinned `tasks.jsonl` snapshots are committed; `datasets`/`evalplus` are only needed to refresh them.

### Analysis (`analysis/`)

`analysis.all` runs the full pipeline: `aggregate` (means/medians per category × route) → `arqgc` (bounded area-under-quality-cost curve, capped at p90 of R1 cost per category) → `decision_matrix` (human-readable md) → `cost_scenarios` (re-price under alternate pricing tables) → charts under `charts/`.

## Conventions and gotchas

- **Always call Python via `.venv/bin/python` or `.venv/bin/pytest`**, not bare `python`. The repo installs as editable (`pip install -e .`) and relies on that.
- **The router must be running** before any R1/R3/R4 runner or integration test. Tests that need it call `runners._shared.proxy_health()` and `pytest.skip` cleanly when it's down — don't swap in mocks.
- **`tests/test_*` marked `slow`** invoke the SWE-bench Docker harness (minutes per test). Skip them in normal CI with `-m 'not slow'`.
- **Preserved runs are read-only.** Under `results/runs/NN-*/`, never edit `raw.jsonl` or outputs in place — `rescore-swebench.py` / `rejudge-custom-arch.py` produce new fields; if the underlying inference needs to change, make a new run directory.
- **Cost is derived, not stored.** Anything that writes a `cost_usd_*` field into `raw.jsonl` is a bug — costs are computed on read by `analysis/*` and `lib/pricing.py`.
- **Env keys:** both `OPENAI_API_KEY` and `OPEN_AI_API_KEY` are accepted (router resolves in that order). `ANTHROPIC_API_KEY` is required only for the Opus judge path.
- **Task adapters vs category letters:** A=HumanEval+, B=SWE-bench Verified, C=BigCodeBench-Hard + custom_arch. See `lib/experiment.CATEGORY_SOURCES`.
- **`EXTERNAL/`** is vendored third-party source (Stanford `minions` for R4, `lm-eval-harness-judge` reference). Treat as read-only; licenses are tracked in `NOTICE.md`.
- **Status is "MVP complete."** The repo is a finished artifact, not an active product. Changes should prioritize reproducibility and transparency of the preserved runs over new features.

## Where to read next

- `docs/ARCHITECTURE.md` — full code layout + data flow (long).
- `docs/METHODOLOGY.md` — scoring rubrics, contamination analysis, what the eval does and doesn't claim.
- `docs/REPRODUCING.md` — copy-paste reproduction on a fresh machine.
- `docs/ROUTING_STRATEGIES.md` — deep dive on each of the seven router strategies and the four routes.
- `results/REPORT.md` — canonical results.
