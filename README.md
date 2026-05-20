# hybrid-coding-eval

> *A benchmark + harness that answers, with reproducible numbers, the question:*
> ***For my coding task and my hardware — should I run it local, hybrid, or cloud?***

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](./LICENSE) [![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC--BY--4.0-lightgrey.svg)](./LICENSE-DATA) [![Version](https://img.shields.io/badge/version-1.4.0-success.svg)](./CHANGELOG.md) [![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/) [![CI](https://github.com/RunanywhereAI/hybrid-coding-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/RunanywhereAI/hybrid-coding-eval/actions/workflows/ci.yml)

**Status (v1.4.0):** Cleanup + production-pipeline release. Drops legacy R1/R2/R3/R4/R5 non-agentic routes; canonical routes are now the five agents: **R6 mini-swe-agent · R7 aider · R8 opencode · R9 claude-code · R10 cline**. `bench sweep` auto-spawns the router proxy from `models.local`, so the reproducer is now four copy-paste commands. 18 tasks (X Exercism Python + D real-developer refactors) × 8 routing strategies × 3 local models — see `configs/v1.4-canonical.yaml`.

**Headline preview** (v1.3.0 carry-over on real-dev D-tasks, to be refreshed by the v1.4 sweep): **gemma4:31b + heuristic = 96% pass-rate [88, 100]** vs always-cloud 100% [100, 100] at 79% cloud_fraction (≈21% token-spend reduction). First hybrid configuration in this benchmark to clear the "equivalent quality at lower cost" bar with statistical significance. v1.4 numbers land with the sweep in `docs/release-notes/v1.4.0.md`.

## Quickstart (~30 minutes)

```bash
# 1. Clone and install
git clone https://github.com/RunanywhereAI/hybrid-coding-eval && cd hybrid-coding-eval
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure + setup
cp .env.example .env                      # add OPEN_AI_API_KEY (+ ANTHROPIC_API_KEY for judge)
./bench setup                             # builds Docker image, pulls aux models, installs aider

# 3. Pull a local model
ollama pull gemma4:31b                    # the v1.4 canonical baseline (~19 GB)

# 4. Smoke + sweep — `bench sweep` auto-spawns the router proxy
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42 --smoke
./bench analyze results/runs/v1.4-canonical/
```

The smoke sweep runs 1 task × the requested strategies through the full pipeline and writes graded rows to `results/runs/v1.4-canonical/<strategy>/seed-42/raw.jsonl`. If it completes cleanly, the harness is configured. Full reproduction: [`docs/REPRODUCING.md`](./docs/REPRODUCING.md).

> **Note:** v1.4's `bench sweep` reads `models.local` from the config and auto-spawns `router/server.mjs` with `LOCAL_MODEL=<model>`. Pass `--external-router` if you want to manage the router yourself (e.g. `(cd router && ./start.sh) &`).

## What's in the box

| Component | What it is |
| --- | --- |
| **5 agentic routes** | R6 mini-swe-agent · R7 aider · R8 opencode · R9 claude-code · R10 cline |
| **18 tasks** | X Exercism Python (10) · D real-developer refactors (8) — see `src/hybrid_coding_eval/benchmarks/` |
| **8 routing strategies** | always-cloud · always-local · rules · heuristic (agent-aware) · llm-classifier · embedding-knn · cascade · cascade-tuned |
| **6 pricing scenarios** | gpt-5.5 · gpt-5 · gpt-5-mini · opus-4.7 · sonnet-4.6 · haiku-4.5 |
| **3 local models in canonical** | gemma4:31b (baseline) · qwen3-coder:30b · qwen2.5-coder:32b |
| **Functional scoring** | Sandboxed Python via Docker (`--network none`, memory caps, wall-clock timeouts) |
| **Judge** | claude-opus-4-7 (cross-vendor; pair-v2 with position-swap bias correction) |
| **Statistics** | Per-(category, route, strategy) cell bootstrap 95% CIs on pass-rate, cost, cloud-fraction, wall-ms |

> v1.4 deletes the legacy non-agentic R1/R2/R3 routes and the experimental R4/R5 Stanford-Minion wrappers. The historical 250-row v3 dataset stays tracked under `results/runs/07-v3-devstral-all-routes/` for reference; new sweeps go through the agentic surface.

## Benchmark a new local model

```bash
ollama pull <new-model>                                            # e.g. ollama pull deepseek-coder-v3:33b
# Edit configs/v1.4-canonical.yaml — change models.local to your tag
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-canonical/
```

Compare your `bootstrap_cis.json` against the v1.4.0 canonical baseline (download via `gh release download v1.4.0 -p results-v1.4.0.tar.gz`). Full walkthrough: [`docs/BENCHMARK_NEW_MODEL.md`](./docs/BENCHMARK_NEW_MODEL.md).

## Headline findings (preview — v1.3.0 carry-over)

> *v1.4 results land with the canonical sweep in [`docs/release-notes/v1.4.0.md`](./docs/release-notes/v1.4.0.md). Numbers below are v1.3.0's gemma4:31b results, retained as a preview of the methodology and shape.*

**gemma4:31b on real-developer D-tasks (n=24/cell, 95% bootstrap CIs):**

| Strategy | Pass-rate | Cloud-frac (tokens) | Notes |
|---|---|---|---|
| always-cloud (gpt-5.5) | **1.00** [1.00, 1.00] | 1.00 | gpt-5.5 ceiling |
| always-local (gemma4:31b) | 0.88 [0.71, 1.00] | 0.00 | gemma4 alone matches cloud within CI |
| **heuristic** (agent-aware) | **0.96** [0.88, 1.00] | 0.79 | **Pareto win** — equivalent quality at ~21% token-spend reduction |
| cascade | 0.88 [0.71, 1.00] | 0.53 | Cheaper but matches always-local |

The v1.3.0 result that "hybrid coding is statistically equivalent to cloud-only on practical refactoring tasks at ~20% lower cloud spend, given the right local model" is the working hypothesis going into v1.4. v1.4 stress-tests it across the full 5-agent surface and 18-task expanded set.

Full v1.3.0 findings: [`personal/iterations/v1.3.0/findings.md`](./personal/iterations/v1.3.0/findings.md) (maintainer's gitignored notes) — also released as the GH release-page artefact for v1.3.0.

## Repo layout

```text
hybrid-coding-eval/
├── README.md                      ← you are here
├── AGENTS.md                      ← canonical guide for AI coding agents
├── CHANGELOG.md                   ← release history (Keep a Changelog)
├── CONTRIBUTING.md                ← how to add a model, task, or strategy
├── LICENSE / LICENSE-DATA / LICENSE.md / NOTICE.md
├── bench                          ← top-level CLI dispatcher
├── .github/workflows/ci.yml       ← CI (ruff + pytest -m 'not slow')
│
├── src/hybrid_coding_eval/
│   ├── core/                      ← config, experiment, metrics, pricing, results, sandbox
│   ├── agents/                    ← R6..R10 agentic-route implementations (post-v1.4 rename of runners/)
│   ├── scorers/                   ← functional (Docker), SWE-bench, LLM judge
│   ├── benchmarks/                ← Exercism Python (X) + real-dev D-tasks
│   ├── analysis/                  ← aggregate, bootstrap CIs, cost-scenarios, token-budget
│   ├── viz/                       ← Pareto + heatmap charts
│   └── cli/                       ← bench, run, sweep, setup, rescore, rejudge, analyze, token-budget
│
├── router/                        ← zero-deps Node hybrid proxy on :8787 (auto-spawned by `bench sweep`)
├── configs/
│   ├── v1.4-canonical.yaml        ← the canonical v1.4 sweep config
│   ├── pricing/pricing_tables.json   ← 6 pricing scenarios, SHA256-pinned
│   ├── router/corpus.json            ← embedding-kNN training data
│   ├── schema.json                   ← auto-generated from BenchConfig
│   └── variants/*.yaml               ← legacy per-variant configs (v1.0–v1.3)
│
├── vendor/                        ← third-party (read-only)
├── tests/                         ← pytest suite (SWE-bench Docker tests marked `slow`)
│
├── results/
│   └── runs/                      ← canonical sweep datasets (raw.jsonl, env-manifest, charts)
│
└── docs/
    ├── REPRODUCING.md             ← copy-paste v1.4 reproduction
    ├── BENCHMARK_NEW_MODEL.md     ← add-a-new-local-model walkthrough
    ├── METHODOLOGY.md             ← scoring rubrics + biases
    ├── ROUTING_STRATEGIES.md      ← 8-strategy deep dive
    ├── AGENTIC_ROUTES.md          ← R6..R10 design + correlation-id attribution
    ├── ARCHITECTURE.md            ← code layout + data flow
    └── release-notes/
        └── v1.4.0.md              ← v1.4.0 release notes (tracked in git)
```

## Reproducibility

Every published number traces back to a `(task_id, route, variant_tag, hardware_profile_ref, git_sha)` tuple in `results/runs/.../raw.jsonl`. Costs are derived from `tokens × pinned pricing` at read time — pricing edits ripple through `./bench token-budget` without re-running inference.

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-canonical/
./bench token-budget results/runs/v1.4-canonical/
```

Step-by-step instructions in [`docs/REPRODUCING.md`](./docs/REPRODUCING.md), including hardware/OS notes, troubleshooting, the four-command quickstart, and a "how to read the results" section that maps each headline number to its exact `bootstrap_cis.json` path.

## Citation

```bibtex
@misc{monga2026hybridcodingeval,
  author       = {Monga, Sanchit and contributors},
  title        = {hybrid-coding-eval: reproducible cost/latency/quality benchmark for local vs cloud vs hybrid LLM routing on coding tasks},
  year         = {2026},
  howpublished = {\url{https://github.com/RunanywhereAI/hybrid-coding-eval}},
  note         = {Version 1.4.0}
}
```

## License and attribution

- **Code** (harness, router, agents, scorers, analysis, viz, CLI, tests): MIT — see [`LICENSE`](./LICENSE).
- **Results, metrics, figures, prose**: CC-BY-4.0 — see [`LICENSE-DATA`](./LICENSE-DATA).
- **Third-party vendored code**: per-upstream — see [`NOTICE.md`](./NOTICE.md) and [`LICENSE.md`](./LICENSE.md).

## Where to read next

1. [`docs/REPRODUCING.md`](./docs/REPRODUCING.md) — four-command v1.4 reproducer + how-to-read-results
2. [`docs/BENCHMARK_NEW_MODEL.md`](./docs/BENCHMARK_NEW_MODEL.md) — add-a-new-local-model walkthrough
3. [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) — scoring rubrics, biases acknowledged, what we do and don't claim
4. [`docs/ROUTING_STRATEGIES.md`](./docs/ROUTING_STRATEGIES.md) — 8-strategy deep dive
5. [`docs/AGENTIC_ROUTES.md`](./docs/AGENTIC_ROUTES.md) — R6..R10 design + correlation-id attribution
6. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — code layout + data flow
7. [`docs/release-notes/v1.4.0.md`](./docs/release-notes/v1.4.0.md) — v1.4.0 canonical findings
8. [`AGENTS.md`](./AGENTS.md) — folder-by-folder guide for AI coding agents

Questions or reproducibility issues? File an issue: <https://github.com/RunanywhereAI/hybrid-coding-eval/issues>
