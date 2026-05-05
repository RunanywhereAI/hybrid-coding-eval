# hybrid-coding-eval

> *A benchmark + harness that answers, with reproducible numbers, the question:*
> ***For my coding task and my hardware — should I run it local, hybrid, or cloud?***

This project measures **cost × quality × latency** across five routing strategies on a curated set of public coding benchmarks (HumanEval+, MBPP+, BigCodeBench-Hard, SWE-bench Verified, LiveCodeBench, Aider Polyglot). Same task, same scoring, five routes — local-only, cloud-only, two architect-mode hybrids, and the Aider-style architect/editor split — measured on whatever hardware you've got.

The output is a **decision matrix**: given (task category, hardware tier) → recommended route + expected cost + expected quality.

**Status: planning + research phase.** This README will get a real quick-start once the MVP runner lands. For now: read [`PLAN.md`](./PLAN.md) and [`docs/PRIOR_ART.md`](./docs/PRIOR_ART.md).

---

## Why this exists

Every coding-tool vendor claims their hybrid setup saves 30–80 %. **None of them publish reproducible numbers on a benchmark you can run yourself.** The literature on routing has matured — Stanford's Minions, Aider's architect/editor, Cursor's Tab/Composer, RouteLLM, FrugalGPT, CodePRM — but the measurements are inside paywalls or controlled lab settings.

This project's contribution is small but specific: **a public, reproducible harness that runs the same task through five distinct routes on commodity hardware and emits a per-task score sheet**. We use upstream benchmark harnesses (mini-SWE-agent, EvalPlus, Aider's bench, BigCodeBench's eval) so the quality scoring isn't ours to defend — it's the same number SWE-bench's leaderboard uses.

---

## What the five routes are

| route | what it does | the comparison it provides |
|---|---|---|
| **R1 cloud-single** | one shot to gpt-5.5 (or claude-opus-4-7) | the floor for cost + the ceiling for quality |
| **R2 local-only** | one shot to qwen3.6-27b-coding (or whatever fits your hardware) | "is local good enough?" measured directly |
| **R3 hybrid-architect** | cloud plans → per-step heuristic routing → cloud synth | what we built first; has known synth-replay tax |
| **R4 hybrid-minion** | Stanford Minion-style stateful Q&A; cloud never sees raw context | designed to fix R3's tax |
| **R5 local + cloud-review** | Aider's architect/editor pattern + DevMinion's review loop | the most-deployed real hybrid in production |

For each task, every route writes:
- `output.txt` — the generated code/answer
- `metrics.json` — cost (USD broken down), latency, token counts, decision trace
- `quality.json` — functional test results, judge scores, composite

---

## Quick repo layout

```
hybrid-coding-eval/
├── README.md            ← this file
├── PLAN.md              ← detailed multi-phase plan (read this next)
├── docs/
│   ├── PRIOR_ART.md     ← synthesised research findings (May 2026)
│   ├── METHODOLOGY.md   ← (TBW) how the eval works, biases acknowledged
│   ├── REPRODUCING.md   ← (TBW) how to run on your own machine
│   └── DECISIONS.md     ← (TBW) design choices + rationale
├── benchmark/           ← task fixtures + adapters to upstream harnesses
├── runners/             ← R1–R5 implementations
├── scorers/             ← functional + LLM-judge + composite
├── env/                 ← hardware envelope detection + tier-aware model selection
├── results/<date>-<machine>/  ← run artefacts
├── viz/                 ← Pareto plots + decision-matrix heatmaps
├── research/            ← raw deep-research outputs (source for PRIOR_ART.md)
└── article/             ← the published artefact
```

---

## Headlines from the prior-art synthesis

(Full numbers in [`docs/PRIOR_ART.md`](./docs/PRIOR_ART.md).)

- **The frontier-vs-open gap on real software-engineering tasks (SWE-bench Verified) is now ~5 percentage points** when the open model is task-specialised (Devstral-Small-2-24B at 72.2 % vs Claude Opus 4.6 at 77.2 %). Routing decisions matter, but the gap to close is smaller than people think.
- **The contamination-resistant gap is wider** — on LiveCodeBench Hard, GPT-5 sits at 68.4 % vs Qwen3-Coder 55.9 % (13 pp). Hybrid routing earns its keep on novel reasoning, less so on saturated function generation.
- **Production hybrid systems claim 30–60 % cost reduction** consistently. 60–80 % numbers exist but come from blog-post anecdotes, not papers.
- **Q5_K_M is the quantization sweet spot for coding** at 98 % quality retention. NVFP4 is fast but drops 18 pp on hard reasoning — avoid for coding.
- **Memory bandwidth, not core count, is the dominant predictor of local tok/s on Apple Silicon.** M3 Max 64 GB beats M4 Pro 48 GB on large-model inference. Counter-intuitive, frequently wrong-bought.
- **Break-even on a Mac M4 Pro 48 GB is ~5 months for a light dev, <1 month for a heavy dev.** RTX 4090 used at $1,180 is the sweet spot for serious individual deployment.
- **The known failure modes of hybrid in production**: token-limit prediction failures, calibration drift, session-state inconsistency, synth-budget exhaustion on reasoning models. Our eval should expose all four.

---

## What's done so far

- ✅ Project scaffolded
- ✅ Research run (4 parallel deep-research queries via Exa + Perplexity sonar-deep-research) saved under `research/`
- ✅ [`docs/PRIOR_ART.md`](./docs/PRIOR_ART.md) synthesis (citations to research/)
- ✅ [`PLAN.md`](./PLAN.md) finalised with 45-task MVP benchmark + 5 routes + Bounded-ARQGC headline metric
- ⏳ Next: MVP build (~1 week of focused work — see PLAN.md §9)

---

## Origin

Spun out of routing work in the [opencode hybrid router](../opencode/router/), which produced a 3-task article (`opencode/hybridarchitecturearticle.md`) demonstrating the cost-quality tradeoff. The article was honest but anecdotal — three projects, one hardware tier, manual quality review. This project is the rigorous version: more tasks, multiple hardware tiers, automated functional scoring on a public benchmark, peer-reviewable metric.

The opencode router itself is one of the integration targets: route R3 calls into it directly. Routes R1, R2, R4, R5 are independent.

---

## License (planned)

MIT for harness code; CC-BY-4.0 for results / dataset / article. Not yet finalised — see [`PLAN.md` §13](./PLAN.md) open question 2.
