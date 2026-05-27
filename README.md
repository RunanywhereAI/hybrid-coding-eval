# hybrid-coding-eval

> *Should this coding task run on my laptop, the cloud, or split between
> them? Answer it empirically, on your hardware, with reproducible numbers.*

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](./LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC--BY--4.0-lightgrey.svg)](./LICENSE-DATA)
[![Version](https://img.shields.io/badge/version-1.5.0-success.svg)](./CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/RunanywhereAI/hybrid-coding-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/RunanywhereAI/hybrid-coding-eval/actions/workflows/ci.yml)

A reproducible benchmark harness that measures four coding agents
(`aider`, `opencode`, `mini-swe-agent`, `cline`) across eight routing
strategies and three local models, against frontier cloud LLMs. v1.4
canonical dataset: **1,644 rows** spanning 3 local models × 4 strategies
× 13 tasks × 3 seeds. Every published number traces back to a single row
in `results/runs/<sweep>/raw.jsonl` priced by a versioned pricing table.

## TL;DR results (v1.4.1)

| Cell                                                | Pass-rate         | Cloud-fraction (tokens) | Notes                                  |
| --------------------------------------------------- | ----------------- | ----------------------- | -------------------------------------- |
| `cline + qwen3.6 + cascade + refactors`             | **24/24 = 100%**  | **10.3%**               | Cleanest hybrid cell in the benchmark  |
| `cline + qwen3.6 + heuristic + refactors`           | 23/24 = 96%       | 15.6%                   | 96% pass at 15.6% cloud tokens         |
| `aider + gemma4 + heuristic + refactors`            | 23/24 = 96% [88, 100] | 15.8%               | v1.4.0 marquee — replicates exactly    |
| `cline + (gemma4 OR qwen3.6) + always-local + puzzles` | 15/15 = 100%   | 0%                      | First 30B local-only Exercism win      |
| `opencode + gemma4 + heuristic + refactors`         | 17/24 = 71%       | 46.3%                   | Gemma4-specific; doesn't transfer      |

Full numbers + CIs + per-cell cost breakdown:
[`docs/release-notes/v1.4.1.md`](./docs/release-notes/v1.4.1.md).

## Prerequisites

This is a benchmark harness — to run it you need the tools the benchmark
actually drives. None of these are bundled. Install them once, then
`scripts/reproduce.sh` handles everything else.

| Tool                    | Why                                                | Install (macOS)               | Install (Linux)                                  |
| ----------------------- | -------------------------------------------------- | ----------------------------- | ------------------------------------------------ |
| **Python 3.11 or 3.12** | Harness + agent runners (aider, cline, mini-swe)   | `brew install python@3.12`    | `sudo apt install python3.12 python3.12-venv`    |
| **Docker**              | Sandbox for the functional Python scorer           | [Docker Desktop](https://www.docker.com/products/docker-desktop) | `sudo apt install docker.io` + add user to `docker` group |
| **Node ≥ 18**           | Router proxy (`router/server.mjs`)                 | `brew install node`           | `sudo apt install nodejs npm`                    |
| **Ollama**              | Serves the local model (gemma4, qwen3, …) on `:11434` | [`ollama.com/download`](https://ollama.com/download) | `curl -fsSL https://ollama.com/install.sh \| sh` |
| **jq**                  | Slicing JSON output in the quickstart commands     | `brew install jq`             | `sudo apt install jq`                            |
| **An `OPEN_AI_API_KEY`**| The cloud half of every hybrid call (gpt-5.5)      | <https://platform.openai.com/api-keys> | same |

Then:

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval

cp .env.example .env                    # then edit .env and fill OPEN_AI_API_KEY
ollama serve &                          # if not already running as a service
ollama pull gemma4:31b                  # ~18 GB; this is the v1.4 canonical local model
```

`scripts/reproduce.sh` checks every prerequisite and prints a precise
install hint if anything is missing, so you don't have to remember this
table.

## Quickstart (~15 minutes)

```bash
# One-command bootstrap — verifies prereqs, installs Python deps,
# builds the Docker sandbox, installs the aider/opencode/cline agents,
# pulls the aux models, runs the 4-pair smoke sweep.
./scripts/reproduce.sh --smoke

# Inspect the smoke result:
./bench analyze results/runs/v1.4-smoke
jq '.cells' results/runs/v1.4-smoke/bootstrap_cis.json
```

If the smoke sweep completes cleanly, the harness is wired up. Then
benchmark a real local model:

```bash
ollama pull gemma4:31b                     # or qwen3-coder:30b / qwen3.6:35b
./scripts/reproduce.sh --config configs/v1.4-canonical-gemma4.yaml \
    --strategies always-cloud,always-local,heuristic,cascade \
    --seeds 42,7,13
# ~10–15 hours on M4 Max 64 GB, ~$30–50 cloud spend at gpt-5.5 list.
```

When it finishes, your numbers should land within the bootstrap CIs of
the canonical v1.4 dataset (download via
`gh release download v1.4.1 -p results-v1.4.1.tar.gz` for comparison).

## What's in the box

| Component                | What                                                                              |
| ------------------------ | --------------------------------------------------------------------------------- |
| **4 coding agents**      | `aider` · `opencode` · `mini-swe-agent` · `cline`                                 |
| **8 routing strategies** | `always-cloud` · `always-local` · `rules` · `heuristic` · `llm-classifier` · `embedding-knn` · `cascade` · `phase-aware` |
| **2 task classes (v1.4)**| `puzzles` (Exercism Python) · `refactors` (real-PR D-tasks); `real-prs` (SWE-bench Verified) lands v1.5 |
| **6 pricing scenarios**  | `gpt-5.5` · `gpt-5` · `gpt-5-mini` · `claude-opus-4-7` · `claude-sonnet-4-6` · `claude-haiku-4-5` |
| **Functional scoring**   | Sandboxed Python via Docker (`--network none`, memory caps, 60s timeout)          |
| **Statistics**           | Per-cell bootstrap 95% CIs on pass-rate, cost, cloud-fraction, wall-ms            |

See [`docs/HYBRID_ROUTING_DESIGN.md`](./docs/HYBRID_ROUTING_DESIGN.md) for the
canonical design doc: what the four agents do, how each routing strategy
decides, what each task class measures, and the result schema.

## How it works (60-second tour)

```text
./bench sweep --config configs/v1.4-canonical-gemma4.yaml
    │
    ├── spawns ONE Node router proxy on :8787
    │   (LOCAL_MODEL + CLOUD_MODEL injected from config)
    │
    └── for each (strategy, seed):
        for each (task, agent):
            agent.run(task, proxy_url=":8787")
                │
                ├── agent makes N LLM calls through the router
                ├── router picks local-vs-cloud per call (current strategy)
                ├── router logs the decision to logs/decisions.jsonl
                ├── tokens come back via OpenAI-shape `usage` object
                │
            scorer runs the diff in a Docker sandbox
            row written to results/runs/<sweep>/<strategy>/seed-<seed>/raw.jsonl

./bench analyze results/runs/<sweep>/
    │
    ├── aggregate.json     — per-cell medians + totals
    ├── bootstrap_cis.json — 95% CIs on pass_rate / cost / cloud_fraction
    ├── decision_matrix.md — Markdown table with "Recommended" column
    └── charts/            — Pareto scatter + quality/cost heatmaps
```

Each agent is a thin wrapper around an externally-maintained tool. This
repo owns the routing, the scoring, the analysis, and the result schema —
it doesn't try to be a coding agent.

## Benchmark a new local model

Three commands:

```bash
ollama pull <new-model>
./scripts/reproduce.sh \
    --config configs/v1.4-canonical-gemma4.yaml \
    --set models.local=<new-model> \
    --set out_dir=results/runs/v1.4-<new-model> \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-<new-model>
```

Then look at the headline cell:

```bash
jq '.cells["refactors::cline::heuristic"].pass_rate' \
   results/runs/v1.4-<new-model>/bootstrap_cis.json
```

`refactors::cline::heuristic` is the canonical "is this model good at
hybrid refactor work?" cell. Compare your point estimate against the
existing v1.4.1 results (96 % qwen3.6 / 92 % qwen3-coder / 96 % gemma4).

The full add-a-model walkthrough lives in
[`docs/HYBRID_ROUTING_DESIGN.md §9`](./docs/HYBRID_ROUTING_DESIGN.md#9-add-a-new-local-model).

## Sweep lifecycle (long sweeps)

For an overnight sweep you can detach + pause + resume:

```bash
./bench start  --config configs/v1.4-canonical-qwen3.6.yaml \
               --strategies always-cloud,always-local,heuristic,cascade \
               --seeds 42,7,13         # detaches, returns immediately
./bench status                          # PID + row count + RUNNING/PAUSED
./bench pause                           # frees the laptop, keeps Ollama warm
./bench resume                          # picks up at the next un-written row
./bench stop                            # also kills Ollama (~19 GB freed)
```

State lives in `/tmp/hcev-sweep.json`. Resume is row-level (`raw.jsonl`
is appended to as rows complete) so a crash mid-sweep loses at most one
row.

## Repo layout

```text
hybrid-coding-eval/
├── README.md                         ← you are here
├── AGENTS.md                         ← canonical guide for AI coding agents
├── CHANGELOG.md                      ← release history
├── CONTRIBUTING.md                   ← how to add a model / agent / strategy
├── SECURITY.md                       ← vuln-report channel
├── LICENSE                           ← MIT (code)
├── LICENSE-DATA                      ← CC-BY-4.0 (datasets, docs prose)
├── LICENSE.md + NOTICE.md            ← per-file license map + attributions
├── bench                             ← top-level CLI dispatcher
├── scripts/reproduce.sh              ← one-command reproducer
├── .github/workflows/ci.yml          ← pytest + ruff
│
├── src/hybrid_coding_eval/
│   ├── core/                         ← config, experiment, metrics, pricing, paths
│   ├── agents/                       ← aider, opencode, mini_swe, cline
│   ├── scorers/                      ← functional (Docker), SWE-bench
│   ├── tasks/                        ← puzzles, refactors, real_prs
│   ├── analysis/                     ← aggregate, bootstrap, decision_matrix, cost_scenarios
│   ├── viz/                          ← Pareto + heatmap charts
│   └── cli/                          ← bench dispatcher + subcommands
│
├── router/                           ← zero-deps Node hybrid proxy
├── configs/
│   ├── v1.4-canonical-{gemma4,qwen3-coder,qwen3.6}.yaml
│   ├── v1.4-smoke.yaml
│   ├── pricing/pricing_tables.json   ← shared by Python and Node
│   └── router/corpus.json            ← embedding-kNN training data
│
├── tests/                            ← pytest (Docker tests marked `slow`)
├── results/                          ← run datasets; v1.4+ released as tarballs
└── docs/
    ├── HYBRID_ROUTING_DESIGN.md      ← THE design doc (strategies + agents + methodology)
    └── release-notes/v1.4.*.md       ← per-release findings
```

## Reproducibility

Every row carries `task_id`, `route`, `router_strategy`, `seed`, `cloud_model_id`,
`local_model_id`, `config_sha`, `hardware_profile_ref`. Costs are derived
from `tokens × pinned pricing` at analyse-time — pricing edits ripple
through `bench analyze` without re-running inference. The pricing table
SHA256 is logged with each pricing-table import.

The Node router and the Python harness both read the same
`configs/pricing/pricing_tables.json` and compute identical costs
(verified by `tests/test_pricing_parity.py`).

## Citation

```bibtex
@misc{monga2026hybridcodingeval,
  author       = {Monga, Sanchit and contributors},
  title        = {hybrid-coding-eval: reproducible cost/latency/quality
                  benchmark for local vs cloud vs hybrid LLM routing on
                  coding tasks},
  year         = {2026},
  howpublished = {\url{https://github.com/RunanywhereAI/hybrid-coding-eval}},
  note         = {Version 1.5.0}
}
```

## License + attribution

- **Code** (`src/`, `router/`, `tests/`, `configs/`, `bench`,
  `scripts/`): MIT — see [`LICENSE`](./LICENSE).
- **Datasets, charts, docs prose** (`results/`, `docs/`): CC-BY-4.0 —
  see [`LICENSE-DATA`](./LICENSE-DATA).
- **Per-file mapping**: [`LICENSE.md`](./LICENSE.md).
- **Third-party attribution**: [`NOTICE.md`](./NOTICE.md).

## Read next

1. [`docs/HYBRID_ROUTING_DESIGN.md`](./docs/HYBRID_ROUTING_DESIGN.md) — the
   single canonical design doc (strategies, agents, schema, methodology).
2. [`docs/release-notes/v1.4.1.md`](./docs/release-notes/v1.4.1.md) — most
   recent findings.
3. [`AGENTS.md`](./AGENTS.md) — folder-by-folder map for AI coding agents
   reading the codebase.
4. [`CONTRIBUTING.md`](./CONTRIBUTING.md) — add a model, agent, strategy,
   or task class.
5. [`SECURITY.md`](./SECURITY.md) — vulnerability-disclosure channel.

Questions or reproducibility issues? File an issue:
<https://github.com/RunanywhereAI/hybrid-coding-eval/issues>
