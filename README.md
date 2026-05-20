# hybrid-coding-eval

> *A benchmark + harness that answers, with reproducible numbers, the question:*
> ***For my coding task and my hardware — should I run it local, hybrid, or cloud?***

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](./LICENSE) [![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC--BY--4.0-lightgrey.svg)](./LICENSE-DATA) [![Version](https://img.shields.io/badge/version-1.0.0-success.svg)](./CHANGELOG.md) [![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**Status (v1.1.0):** Agentic-routes release. Adds the **R8 opencode** route — a real ReAct loop with Read/Write/Edit/Bash/Grep/Glob tools, routed through this repo's proxy so the agent's per-turn local-vs-cloud choice is part of the experiment. The v1.0.0 R1–R5 surface is unchanged. `heuristic` strategy is now agent-aware (detects ReAct loops and scores the latest delta; falls through to the v1.0.0 logic byte-identically for plain chat).

Production pipeline: a new local coding model drops → `ollama pull <model>` → `./bench setup` → `./bench sweep --config configs/variants/_template-agentic.yaml` → publishable results across SWE-bench Verified + HumanEval+ + Exercism + real-developer tasks. See [`docs/BENCHMARK_NEW_MODEL.md`](./docs/BENCHMARK_NEW_MODEL.md).

See [`CHANGELOG.md`](./CHANGELOG.md) for the v0.x → v3.x → v1.0.0 → v1.1.0 lineage. Per-tag datasets bundle as GitHub release tarballs — `gh release download v<tag>`.

## Quickstart (~30 minutes)

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval

python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

cp .env.example .env                    # add OPEN_AI_API_KEY (+ ANTHROPIC_API_KEY for the judge)
ollama pull devstral:24b                # primary local model (~14 GB)

./bench setup                           # one-shot: clones vendor/minions, builds Docker image, pulls aux models
(cd router && ./start.sh) &             # launches the hybrid router proxy on :8787

./bench run --config configs/variants/_template.yaml --smoke
```

The smoke sweep runs 1 task × 3 routes through the full pipeline and writes 9 graded rows to `results/runs/<variant>/raw.jsonl`. If it completes cleanly, the harness is configured. Full reproduction in [`docs/REPRODUCING.md`](./docs/REPRODUCING.md).

## What's in the box

| Component | What it is |
| --- | --- |
| **6 routes** | R1 cloud-only · R2 local-only · R3 hybrid-architect · R4 Stanford-Minion · R5 Stanford-DevMinion · **R8 opencode (agentic)** · R6 mini-swe-agent + R7 Aider (experimental in v1.1) |
| **9 task shapes** | A HumanEval+ · B SWE-bench Verified · C-bcb BigCodeBench-Hard · C-arch custom-arch prose · D1–D5 real-developer tasks · **X Exercism Python (new in v1.1)** |
| **7 routing strategies** | always-cloud · always-local · rules · heuristic (agent-aware in v1.1) · llm-classifier · embedding-knn · cascade |
| **6 pricing scenarios** | gpt-5.5 · gpt-5 · gpt-5-mini · opus-4.7 · sonnet-4.6 · haiku-4.5 |
| **6 local models tested** | devstral:24b · qwen3-coder:30b · qwen2.5-coder:32b · glm-4.7-flash · gemma4:31b · qwen3.6:27b-coding-mxfp8 · qwen3.6:35b-A3B-MoE |
| **Functional scoring** | Sandboxed Python via Docker with `--network none`, memory caps, wall-clock timeouts |
| **SWE-bench scoring** | Upstream Princeton harness, pinned commit |
| **Judge** | claude-opus-4-7 (cross-vendor; pair-v2 with position-swap bias correction) |

## Benchmark a new local model in 5 minutes

```bash
ollama pull <new-model>:Nb                       # e.g. ollama pull qwen3.7-coder:30b
cp configs/variants/_template-agentic.yaml configs/variants/26-my-model.yaml
$EDITOR configs/variants/26-my-model.yaml         # change models.local: to your tag
./bench sweep --config configs/variants/26-my-model.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42
./bench analyze results/runs/26-my-model/
```

Compare your `bootstrap_cis.json` against the canonical v1.1 baseline (download `gh release download v1.1.K -p results-v1.1.K.tar.gz`). Full walkthrough: [`docs/BENCHMARK_NEW_MODEL.md`](./docs/BENCHMARK_NEW_MODEL.md).

## Headline findings (v1.1.3 canonical, R8 opencode + qwen3-coder + gpt-5.5)

5 Exercism Python tasks × 4 strategies × 3 seeds = 60 rows. 95% bootstrap CIs (n=15/cell). Download: `gh release download v1.1.3 -p results-v1.1.3-canonical.tar.gz`.

| Strategy | pass_rate | cloud_tok | local_tok | cloud_frac (calls) |
|---|---|---|---|---|
| always-cloud (gpt-5.5) | **1.00** [1.00, 1.00] | 16,094 | 0 | 1.00 |
| always-local (qwen3-coder:30b) | 0.00 [0.00, 0.00] | 0 | 2,916 | 0.00 |
| **heuristic** (agent-aware) | 0.00 [0.00, 0.00] | 2,064 | 1,439 | 0.50 |
| **cascade** | 0.00 [0.00, 0.00] | 447 | 2,774 | 0.10 |

v1.1.3 fixed the qwen3-coder + Ollama tool-message format issue from v1.1.2 (see [CHANGELOG](./CHANGELOG.md) v1.1.3 + [docs/AGENTIC_ROUTES.md](./docs/AGENTIC_ROUTES.md)). The hybrid strategies now actually run the agent loop end-to-end with real cloud/local token splits. The remaining 0% hybrid pass-rate is now a **local-model quality gap** — qwen3-coder:30b can run the agent loop but on tool-result interpretation turns it writes prose instead of the tool_calls needed to make progress. Routing infrastructure: ✓. Local-model code-edit quality: open for v1.2.

## Headline findings (v3.3 sweep — non-agentic)

- **Qwen3-Coder:30B is the universal local winner.** Best $/correct on R3 (hybrid-architect) at $0.229/correct across the 33-variant sweep, beating devstral:24b, qwen2.5-coder:32b, glm-4.7-flash, and the Qwen 3.6 generation on aggregate quality-per-dollar.
- **Cascade is the universal best routing strategy** with a threshold around 15 on the difficulty heuristic. Beats heuristic, llm-classifier, embedding-kNN, and the rules-based router across all 6 cloud-pricing scenarios.
- **LLM-classifier (qwen3:0.6b) is broken on SWE-bench across all 5 cloud sizes.** Documented limitation, kept in the strategy list for completeness.
- **Multi-step hybrid routing (R3/R4/R5) loses to R1 on most non-A categories.** Hybrid reaches quality parity with cloud-only on most shapes but pays 2–5× more per task because actual token routing keeps 80%+ of conversation on the cloud (R4 median cloud_fraction is 87%, not the 20–40% the protocol predicted).

The canonical 250-row publication sweep is at [`results/runs/07-v3-devstral-all-routes/`](./results/runs/07-v3-devstral-all-routes/); the 33-variant v3.3 sweep is the broader corpus under [`results/runs/`](./results/runs/).

## Repo layout

```text
hybrid-coding-eval/
├── README.md                      ← you are here
├── AGENTS.md                      ← canonical guide for AI coding agents working in this repo
├── CHANGELOG.md                   ← release history (Keep a Changelog format)
├── CONTRIBUTING.md                ← how to add a model, task, or routing strategy
├── CODE_OF_CONDUCT.md             ← Contributor Covenant 2.1
├── LICENSE / LICENSE-DATA / LICENSE.md / NOTICE.md
├── bench                          ← top-level CLI dispatcher
├── .github/                       ← issue templates, PR template, CI workflow
│
├── src/hybrid_coding_eval/
│   ├── core/                      ← config, experiment, metrics, pricing, results, sandbox
│   ├── runners/                   ← R1..R5 route implementations
│   ├── scorers/                   ← functional (Docker), SWE-bench, LLM judge
│   ├── benchmarks/                ← HumanEval+, SWE-bench, BigCodeBench, custom-arch, real-dev D1–D5
│   ├── analysis/                  ← aggregate, ARQGC, decision-matrix, cost-scenarios
│   ├── viz/                       ← Pareto + heatmap charts
│   └── cli/                       ← bench, run, setup, rescore, rejudge, analyze, token-budget, …
│
├── router/                        ← zero-deps Node hybrid proxy on :8787
├── configs/
│   ├── pricing/pricing_tables.json   ← 6-scenario pricing (Python + Node source of truth)
│   ├── router/corpus.json            ← embedding-kNN training data
│   ├── schema.json                   ← auto-generated from BenchConfig
│   └── variants/*.yaml               ← one config per sweep (drop-in surface for new models)
├── vendor/                        ← third-party (minions auto-cloned by setup; lm-eval-harness-judge vendored)
├── tests/                         ← pytest suite (SWE-bench Docker tests marked `slow`)
│
├── results/
│   ├── REPORT_v1_mvp.md           ← MVP report (frozen)
│   └── runs/                      ← all canonical sweep datasets (raw.jsonl, env-manifest, run-notes, charts)
│
├── docs/
│   ├── REPRODUCING.md             ← copy-paste reproduction
│   ├── METHODOLOGY.md             ← scoring rubrics + biases
│   ├── ROUTING_STRATEGIES.md      ← 7-strategy deep dive
│   ├── ARCHITECTURE.md            ← code layout + data flow
│   ├── HYBRID_ROUTER_DESIGN.md
│   ├── PRIOR_ART.md               ← 2026 research synthesis
│   └── audits/T-22-v3-publish-readiness.md
│
└── examples/
    ├── drop-in-a-new-model.md     ← 5-step walkthrough
    ├── RESULTS.md
    └── run-comparison.mjs
```

## How to extend

Drop in a new model in 90 seconds:

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
# edit two lines (variant_tag + models.cloud or models.local), then:
./bench run --config configs/variants/my-model.yaml
./bench analyze results/runs/my-model/
```

Full walkthrough in [`examples/drop-in-a-new-model.md`](./examples/drop-in-a-new-model.md). To add a new routing strategy, benchmark, or scorer, see [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Reproducibility

Every published number traces back to a `(task_id, route, variant_tag, hardware_profile_ref, git_sha)` tuple in `results/runs/.../raw.jsonl`. Costs are derived from `tokens × pinned pricing` at read time — pricing edits ripple through `./bench token-budget` without re-running inference.

Reproducing the canonical v3 sweep (250 rows, ~8–12 h on M4 Max, ~$40 OpenAI + ~$0.50 Anthropic):

```bash
./bench run --config configs/variants/07-v3-devstral-all-routes.yaml
./bench rescore  results/runs/07-v3-devstral-all-routes/
./bench rejudge  results/runs/07-v3-devstral-all-routes/
./bench analyze  results/runs/07-v3-devstral-all-routes/
./bench token-budget results/runs/07-v3-devstral-all-routes/
```

Step-by-step instructions in [`docs/REPRODUCING.md`](./docs/REPRODUCING.md), including hardware/OS notes, troubleshooting, and post-sweep analysis pipeline.

## Citation

```bibtex
@misc{monga2026hybridcodingeval,
  author       = {Monga, Sanchit and contributors},
  title        = {hybrid-coding-eval: reproducible cost/latency/quality benchmark for local vs cloud vs hybrid LLM routing on coding tasks},
  year         = {2026},
  howpublished = {\url{https://github.com/RunanywhereAI/hybrid-coding-eval}},
  note         = {Version 1.0.0}
}
```

## License and attribution

- **Code** (harness, router, runners, scorers, analysis, viz, CLI, tests): MIT — see [`LICENSE`](./LICENSE).
- **Results, metrics, figures, prose**: CC-BY-4.0 — see [`LICENSE-DATA`](./LICENSE-DATA).
- **Third-party vendored code**: per-upstream — see [`NOTICE.md`](./NOTICE.md) and [`LICENSE.md`](./LICENSE.md) for the file-type breakdown.

## Where to read next

1. [`docs/REPRODUCING.md`](./docs/REPRODUCING.md) — copy-paste reproduction on a fresh machine
2. [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) — scoring rubrics, biases acknowledged, what we do and don't claim
3. [`docs/ROUTING_STRATEGIES.md`](./docs/ROUTING_STRATEGIES.md) — deep-dive on the 7 router strategies
4. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — code layout + data flow
5. [`docs/PRIOR_ART.md`](./docs/PRIOR_ART.md) — 2026 research synthesis
6. [`results/runs/`](./results/runs/) — all canonical sweep datasets
7. [`examples/drop-in-a-new-model.md`](./examples/drop-in-a-new-model.md) — 5-step walkthrough for benchmarking a new model
8. [`AGENTS.md`](./AGENTS.md) — folder-by-folder guide for AI coding agents working in this repo

Questions or reproducibility issues? File an issue: <https://github.com/RunanywhereAI/hybrid-coding-eval/issues>
