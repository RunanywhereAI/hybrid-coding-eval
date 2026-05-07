# hybrid-coding-eval

> *A benchmark + harness that answers, with reproducible numbers, the question:*
> ***For my coding task and my hardware — should I run it local, hybrid, or cloud?***

**Status: mono-repo reorg complete.** 200 graded rows across 4 routes, 6 benchmarks-worth of re-priceable scenarios, on one M4 Max laptop. MVP 180 rows + Wave 2 R4-on-Cat-A (10) + R4-on-Cat-C (10) + triple-judge audit (30 verdicts).

## 👉 Start here

- **[`reports/ARTICLE.md`](./reports/ARTICLE.md) — the canonical article. Read this.**
- [`reports/APPENDIX_TASKS.md`](./reports/APPENDIX_TASKS.md) — every `(task, route, variant)` row verbatim: problem, prompt, output, score, judge reasoning.
- [`reports/APPENDIX_SCENARIOS.md`](./reports/APPENDIX_SCENARIOS.md) — multi-scenario decision matrix + $/correct under every pricing tier.
- [`reports/APPENDIX_ROUTES.md`](./reports/APPENDIX_ROUTES.md) — worked example per R1/R2/R3/R4 with full trace.
- [`results/raw.jsonl`](./results/raw.jsonl) — the merged dataset.
- [`results/REPORT_v1_mvp.md`](./results/REPORT_v1_mvp.md) — the MVP report (preserved, frozen).
- [`results/runs/`](./results/runs/) — per-variant subdirectories: run-notes, raw.jsonl, outputs, minion_logs, env-manifest. Preserved as-is.

## What the four routes are

| route | what it does |
|---|---|
| **R1 cloud-only** | one shot to `gpt-5.5` |
| **R2 local-only** | one shot to qwen3.6:27b-coding or devstral:24b via Ollama |
| **R3 hybrid-architect** | cloud plans → per-step heuristic routing → cloud synth |
| **R4 hybrid-minion** | Stanford Minion-style supervisor/worker Q&A; cloud never re-sees raw context |

(A planned R5 — Aider's architect/editor review loop — is the next post-MVP route.)

## The headline

| Category | R1 cloud | Best hybrid | Winner |
|---|:-:|:-:|:-:|
| A — HumanEval+ (10) | 10/10 | R3-devstral 10/10, R2 10/10 | three-way tie; R1 cheapest/fastest |
| B — SWE-bench Verified (10) | 3/10 | **R4 Minion 4/10** at $0.083/task vs R1 $0.126 | **R4** |
| C — architecture/reasoning (10) | ties R3 | R3 ties R1 on judge, wins ARQGC | R3 ≈ R1 |

**Hybrid routing is not categorically worse than cloud-only.** An earlier v1 draft claimed it was; that conclusion was load-bearing on a runner bug (synth-budget exhaustion on reasoning models) and a weak local model on SWE-bench. Fix both, try Stanford's Minion pattern, and hybrid reaches parity on every category and wins outright on SWE-bench. Full story in [`reports/ARTICLE.md`](./reports/ARTICLE.md); MVP report preserved at [`results/REPORT_v1_mvp.md`](./results/REPORT_v1_mvp.md).

## Repo layout

```
hybrid-coding-eval/
├── README.md                      ← you are here
├── results/
│   ├── REPORT.md                  ← 👉 THE one report to read
│   ├── raw.jsonl                  ← 180 rows, merged, variant-tagged
│   ├── env-manifests/             ← hardware profile per variant
│   └── runs/
│       ├── README.md              ← index of the four runs
│       ├── 01-v1-qwen-original/   ← v1 sweep (superseded)
│       ├── 02-v2-qwen-fixed-synth/ ← synth-budget fix + Opus judge
│       ├── 03-v2-devstral/         ← local-model swap
│       └── 04-r4-minion/           ← R4 Minion on SWE-bench
├── docs/
│   ├── PLAN.md                    ← original multi-phase plan
│   ├── METHODOLOGY.md             ← how the eval works, biases acknowledged
│   ├── REPRODUCING.md             ← copy-paste instructions for a fresh machine
│   ├── ARCHITECTURE.md            ← code layout + data flow
│   ├── ROUTING_STRATEGIES.md      ← deep-dive on each route
│   ├── PRIOR_ART.md               ← May 2026 research synthesis
│   ├── OSS_REVIEW.md              ← pre-public audit record
│   ├── RUNANYWHERE_INTEGRATION.md ← future-work design doc
│   ├── article-draft-v1.md        ← long-form article (v1 narrative + v2 postscript)
│   └── history/                   ← pre-MVP archival notes
├── router/                        ← hybrid proxy (Node.js, zero deps, port 8787)
├── runners/                       ← R1/R2/R3/R4 Python runners
├── scorers/                       ← pytest + SWE-bench harness + LLM-judge
├── benchmark/                     ← 4 task adapters (HumanEval+, SWE-bench, BigCodeBench, custom)
├── analysis/                      ← aggregate / ARQGC / decision-matrix / charts
├── lib/                           ← pricing tables, sandbox, metrics schema
├── bin/                           ← CLIs (run-experiment, rescore, rejudge, env-detect)
└── EXTERNAL/
    ├── minions/                   ← Stanford Minion library (MIT, vendored for R4)
    └── lm-eval-harness-judge/     ← MT-Bench judge reference (Apache 2.0)
```

## Quick start

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

cp .env.example .env                         # add OPEN_AI_API_KEY (+ ANTHROPIC_API_KEY if you want the Opus judge)
ollama pull devstral:24b                     # or qwen3.6:27b-coding-mxfp8

./router/start.sh                            # launches the hybrid router proxy on :8787

# smoke sweep (1 task × 3 routes ≈ 10 min)
./bench run --config configs/variants/04-r4-devstral-minion.yaml --smoke

# full sweep — 30 tasks × 4 routes ≈ 4-5h
./bench run --config configs/variants/04-r4-devstral-minion.yaml
./bench rescore  results/runs/04-r4-minion/       # post-sweep SWE-bench rescore
./bench rejudge  results/runs/04-r4-minion/       # post-sweep Opus re-judge (ANTHROPIC_API_KEY)
./bench analyze  results/runs/04-r4-minion/
```

### Drop in a new model

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
# edit variant_tag + models.cloud or models.local, then:
./bench run --config configs/variants/my-model.yaml
./bench analyze results/runs/my-variant/
```

Full instructions in [`docs/REPRODUCING.md`](./docs/REPRODUCING.md). Wall ~5h on M4 Max, ~$15 API spend.

## Where to read next

1. **[`reports/ARTICLE.md`](./reports/ARTICLE.md)** — the canonical article. Read this first.
2. [`reports/APPENDIX_TASKS.md`](./reports/APPENDIX_TASKS.md) — forensic record: every task × route × variant with its problem, prompt, output, score.
3. [`reports/APPENDIX_SCENARIOS.md`](./reports/APPENDIX_SCENARIOS.md) — multi-scenario decision matrix.
4. [`reports/APPENDIX_ROUTES.md`](./reports/APPENDIX_ROUTES.md) — worked examples per R1/R2/R3/R4.
5. [`examples/drop-in-a-new-model.md`](./examples/drop-in-a-new-model.md) — 5-step walkthrough for benchmarking a new model.
6. [`results/REPORT_v1_mvp.md`](./results/REPORT_v1_mvp.md) — the MVP report, preserved verbatim.
7. [`results/runs/README.md`](./results/runs/README.md) — index of the experimental runs.
8. [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) — how the eval works, biases acknowledged.
9. [`docs/REPRODUCING.md`](./docs/REPRODUCING.md) — copy-paste reproduction on a fresh machine.
10. [`docs/ROUTING_STRATEGIES.md`](./docs/ROUTING_STRATEGIES.md) — deep-dive on each route.
11. [`docs/PRIOR_ART.md`](./docs/PRIOR_ART.md) — research synthesis.
12. [`docs/article-draft-v1.md`](./docs/article-draft-v1.md) — v1 narrative (superseded).
13. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — code layout + data flow.
14. [`docs/PLAN.md`](./docs/PLAN.md), [`docs/FINAL_REPORT_PLAN.md`](./docs/FINAL_REPORT_PLAN.md), `docs/T-12-deferred.md`, `docs/T-13-analysis.md`, `docs/audits/T-21-publish-readiness.md` — planning artefacts.

## License and attribution

- **Code** (harness, router, runners, scorers, analysis, viz): MIT — see [`LICENSE`](./LICENSE).
- **Results, metrics, figures, article**: CC-BY-4.0 — see [`LICENSE-DATA`](./LICENSE-DATA).
- **Third-party code and research we build on**: see [`NOTICE.md`](./NOTICE.md) and [`EXTERNAL/README.md`](./EXTERNAL/README.md).

Suggested citation (if you use our numbers):

> Monga, Sanchit and contributors. *hybrid-coding-eval: reproducible cost/latency/quality benchmark for local vs cloud vs hybrid LLM routing on coding tasks.* 2026. https://github.com/RunanywhereAI/hybrid-coding-eval
