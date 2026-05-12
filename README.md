# hybrid-coding-eval

> *A benchmark + harness that answers, with reproducible numbers, the question:*
> ***For my coding task and my hardware — should I run it local, hybrid, or cloud?***

**Status: v3 sweep complete.** 250 graded rows across 5 routes (R1, R2, R3, R4, R5) and 8 task shapes (A HumanEval+, B SWE-bench Verified, C BigCodeBench + custom-arch, D1-D5 real-developer-tasks). M4 Max + devstral:24b local + gpt-5.5 cloud + claude-opus-4-7 judge. Plus a 96-verdict triple-judge robustness audit on D3+D4.

## 👉 Start here

- **[`reports/ARTICLE.md`](./reports/ARTICLE.md) — the canonical article (7,600+ words, comprehensive). Read this.**
- [`reports/DECISION_TABLE.md`](./reports/DECISION_TABLE.md) — per-shape × route pass / cost / cloud-fraction grid.
- [`reports/TOKEN_BUDGET.md`](./reports/TOKEN_BUDGET.md) — token-first headline; every cost is derived from stored tokens × pinned pricing.
- [`reports/APPENDIX_TASKS.md`](./reports/APPENDIX_TASKS.md) — every `(task, route, variant)` row verbatim: problem, prompt, output, score, judge reasoning.
- [`reports/APPENDIX_SCENARIOS.md`](./reports/APPENDIX_SCENARIOS.md) — multi-scenario decision matrix + $/correct under every pricing tier.
- [`reports/APPENDIX_ROUTES.md`](./reports/APPENDIX_ROUTES.md) — worked example per R1/R2/R3/R4/R5 with full trace.
- [`results/runs/07-v3-devstral-all-routes/`](./results/runs/07-v3-devstral-all-routes/) — the v3 sweep: 250 rows, run-notes, raw.jsonl, outputs, charts, aggregate.json.
- [`results/runs/11-judge-robust-D/`](./results/runs/11-judge-robust-D/) — 96 triple-judge verdicts; D3+D4 robustness audit.
- [`results/runs/`](./results/runs/) — index of all runs (MVP 01-04 + v3 sweep 07 + robustness audit 11).

## What the five routes are

| route | what it does |
| --- | --- |
| **R1 cloud-only** | one shot to `gpt-5.5` |
| **R2 local-only** | one shot to `devstral:24b` via Ollama |
| **R3 hybrid-architect** | cloud plans → per-step heuristic routing → cloud synth |
| **R4 hybrid-minion** | Stanford Minion-style supervisor/worker Q&A; cloud never re-sees raw context |
| **R5 hybrid-devminion** | Stanford DevMinion architect/editor review loop, up to 3 rounds; cloud architect → local editor → cloud reviewer |

## The headline

Per-shape decision distilled from [`reports/DECISION_TABLE.md`](./reports/DECISION_TABLE.md) (8 shapes × 5 routes, 250 rows, gpt-5.5 cloud / devstral:24b local).

| Shape | Best route | Why |
| --- | --- | --- |
| A — HumanEval+ (10) | **R2** (or R1) | R2 9/10 at $0.000; R1 10/10 at $0.012. Every hybrid pays 3-20× for no quality gain. |
| B — SWE-bench Verified (10) | **R1** | R1 = R3 = R4 = 3/10 (same 3 Django tasks). Hybrid pays 1.3-3.7× for parity. R5 = 0/10. |
| C-bcb — BigCodeBench-Hard (5) | **R1** or **R2** | R1 = R2 = 1/5. Hybrid regresses to 0/5. |
| C-arch — custom-arch prose (5) | **R1** | R1 5/5\* at $0.30; R3 5/5\* at $0.49 (1.6×); R4 4/5\*; R5 1/5\*. |
| D1 — small features (4) | **R2** fall-through to **R1** | R1 = R3 = 2/4; hybrid pays 3-14× per task. R2 = 0/4 — use only if R2 first try works. |
| D2 — GitHub-issue patches (4) | **R1** | Functional scorer deferred; cost / cloud-fraction observable only. |
| D3 — refactor prose (4) | **R1** | R1 = R3 = R4 = 4/4\*. Triple-judge audit (96 verdicts) confirms R1 wins all 8 D3+D4 pairings vs R3/R4 unanimously, zero order-flips. R5 = 0/4\*. |
| D4 — code-review prose (4) | **R1** | R1 4/4\*; R3 / R4 2/4\*; R5 0/4\*. R1 4.7× cheaper than R3 on this shape. |
| D5 — small one-shots (4) | **R1** (or **R2** first try) | R1 = R3 = R4 = R5 = 3/4. R5 wins `d5-log-errors-today` alone — niche evidence. |

`*` = judge-scored shape, pass proxy is `composite ≥ 0.5`.

**Hybrid routes reach quality parity with R1 on most categories but cost 2-5× more per task** because the actual token routing keeps 80%+ of conversation on the cloud (R4 median cloud_fraction is 87%, not the 20-40% the protocol predicted). R5 (DevMinion review-loop) burned the most tokens (1.88 M total, 5.13× R1's per-row cost) and collapsed on every D3 + 3 of 4 D4 prose tasks. The v3 sweep also reversed run 04's "R4 beats R1 on SWE-bench" headline: that Sphinx win did not replicate. Full story in [`reports/ARTICLE.md`](./reports/ARTICLE.md); v3 dataset at [`results/runs/07-v3-devstral-all-routes/raw.jsonl`](./results/runs/07-v3-devstral-all-routes/raw.jsonl); MVP report preserved at [`results/REPORT_v1_mvp.md`](./results/REPORT_v1_mvp.md).

## Repo layout

```text
hybrid-coding-eval/
├── README.md                          ← you are here
├── CLAUDE.md                          ← project guide for AI assistants (read this first if you're an LLM)
├── LICENSE                            ← MIT (code)
├── LICENSE-DATA                       ← CC-BY-4.0 (results, metrics, figures, article)
├── NOTICE.md                          ← third-party attribution
├── bench                              ← top-level CLI dispatcher (./bench run / analyze / rescore / …)
├── pyproject.toml
├── requirements.txt
├── .env.example                       ← template for OPEN_AI_API_KEY + ANTHROPIC_API_KEY
│
├── src/hybrid_coding_eval/            ← canonical Python package
│   ├── core/                          ← config, experiment, metrics, pricing, results, sandbox
│   ├── runners/                       ← R1..R5 route implementations
│   ├── scorers/                       ← functional (Docker), SWE-bench, LLM judge
│   ├── benchmarks/                    ← HumanEval+, SWE-bench Verified, BigCodeBench-Hard, custom-arch, real-dev D1-D5
│   ├── analysis/                      ← aggregate, ARQGC, decision-matrix, cost-scenarios
│   ├── viz/                           ← Pareto + heatmap charts
│   └── cli/                           ← bench, run, rescore, rejudge, analyze, token-budget, report, schema, env-detect
│
├── router/                            ← zero-deps Node hybrid proxy on :8787
│   ├── server.mjs, strategies.mjs, pricing.mjs
│   ├── pipelines/architect/           ← R3's planner/executor/synth pipeline (subprocess-invoked from Python)
│   └── logs/decisions.jsonl           ← historical routing decisions (per-run churn is gitignored)
│
├── configs/
│   ├── pricing/pricing_tables.json    ← 6-scenario pricing table (shared Python + Node source of truth)
│   ├── router/corpus.json             ← embedding-kNN training data for the smart-routing strategy
│   ├── schema.json                    ← auto-generated from BenchConfig (./bench schema)
│   └── variants/*.yaml                ← one config per sweep — drop-in surface for new models
│
├── vendor/                            ← read-only third-party
│   ├── minions/                       ← Stanford Minion library (MIT) — wrapped by R4 and R5
│   └── lm-eval-harness-judge/         ← MT-Bench judge reference (Apache 2.0)
│
├── tests/                             ← pytest suite (SWE-bench Docker tests marked `slow`)
│
├── reports/                           ← the published surface
│   ├── ARTICLE.md                     ← 👉 the canonical v3 article (~7,600 words, comprehensive)
│   ├── DECISION_TABLE.md              ← per-shape × route grid
│   ├── TOKEN_BUDGET.md                ← token-first cost derivation
│   ├── APPENDIX_TASKS.md              ← every (task, route, variant) row
│   ├── APPENDIX_SCENARIOS.md          ← multi-scenario $/correct
│   └── APPENDIX_ROUTES.md             ← R1..R5 worked examples
│
├── results/                           ← preserved research data (read-only)
│   ├── raw.jsonl                      ← MVP merged dataset (180 rows, bit-identical forever)
│   ├── REPORT_v1_mvp.md               ← MVP report (frozen)
│   ├── env-manifests/                 ← per-variant hardware profiles
│   ├── reprice/                       ← cost-scenario re-pricing CSVs (sources APPENDIX_SCENARIOS)
│   └── runs/
│       ├── README.md                  ← index of runs
│       ├── 01-v1-qwen-original/       ← MVP v1 sweep
│       ├── 02-v2-qwen-fixed-synth/    ← MVP v2 (synth-budget fix + Opus judge)
│       ├── 03-v2-devstral/            ← MVP v2 with local-model swap to devstral
│       ├── 04-r4-minion/              ← MVP R4 Minion sweep on SWE-bench
│       ├── 07-v3-devstral-all-routes/ ← v3 sweep: 250 rows, 5 routes × 8 shapes
│       └── 11-judge-robust-D/         ← 96-verdict triple-judge audit on D3+D4
│
├── examples/                          ← "drop in a new model" walkthrough + comparison harness
│   ├── drop-in-a-new-model.md         ← 5-step guide
│   ├── RESULTS.md                     ← index of example comparisons
│   └── run-comparison.mjs             ← harness for example runs
│
├── docs/                              ← reference documentation
│   ├── ARCHITECTURE.md                ← code layout + data flow
│   ├── METHODOLOGY.md                 ← scoring rubrics, biases acknowledged, what we do and don't claim
│   ├── REPRODUCING.md                 ← copy-paste reproduction on a fresh machine
│   ├── ROUTING_STRATEGIES.md          ← deep-dive on the 7 router strategies
│   ├── PRIOR_ART.md                   ← May 2026 research synthesis
│   └── audits/T-22-v3-publish-readiness.md   ← final publish-readiness audit
│
```

## Quick start

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

cp .env.example .env                         # add OPEN_AI_API_KEY (+ ANTHROPIC_API_KEY for the Opus judge)
ollama pull devstral:24b                     # or any other local model

./router/start.sh                            # launches the hybrid router proxy on :8787

# smoke sweep (1 task × 3 routes ≈ 10 min)
./bench run --config configs/variants/07-v3-devstral-all-routes.yaml --smoke

# full sweep — 50 tasks × 5 routes ≈ 8-12h on M4 Max
./bench run --config configs/variants/07-v3-devstral-all-routes.yaml
./bench rescore  results/runs/07-v3-devstral-all-routes/    # post-sweep SWE-bench rescore
./bench rejudge  results/runs/07-v3-devstral-all-routes/    # post-sweep Opus re-judge (ANTHROPIC_API_KEY)
./bench analyze  results/runs/07-v3-devstral-all-routes/    # aggregate + ARQGC + charts
./bench token-budget results/runs/07-v3-devstral-all-routes/  # 6-scenario token+cost matrix
```

### Drop in a new model

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
# edit variant_tag + models.cloud or models.local, then:
./bench run --config configs/variants/my-model.yaml
./bench analyze results/runs/my-variant/
```

`./bench show-config --config configs/variants/my-model.yaml` prints the merged config + SHA256.
`./bench run --dry-run …` prints the plan without executing.

Full instructions in [`docs/REPRODUCING.md`](./docs/REPRODUCING.md). Wall ~8-12h on M4 Max for the full v3 sweep, ~$15 API spend.

## Where to read next

1. **[`reports/ARTICLE.md`](./reports/ARTICLE.md)** — the canonical v3 article (~7,600 words, comprehensive). Includes methodology, per-shape deep-dives, per-route worked examples, 10 surprising findings, hypothesis scorecard, limits, reproducibility, citations. **Read this first.**
2. [`reports/DECISION_TABLE.md`](./reports/DECISION_TABLE.md) — per-shape × route grid (pass / cost / cloud-fraction).
3. [`reports/TOKEN_BUDGET.md`](./reports/TOKEN_BUDGET.md) — token-first headline; every cost is derived from tokens at read time.
4. [`reports/APPENDIX_TASKS.md`](./reports/APPENDIX_TASKS.md) — forensic record: every task × route × variant with problem, prompt, output, score.
5. [`reports/APPENDIX_SCENARIOS.md`](./reports/APPENDIX_SCENARIOS.md) — multi-scenario decision matrix.
6. [`reports/APPENDIX_ROUTES.md`](./reports/APPENDIX_ROUTES.md) — worked examples per R1/R2/R3/R4/R5.
7. [`docs/REPRODUCING.md`](./docs/REPRODUCING.md) — copy-paste reproduction on a fresh machine (~4,800 words).
8. [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) — scoring rubrics + biases acknowledged.
9. [`docs/ROUTING_STRATEGIES.md`](./docs/ROUTING_STRATEGIES.md) — deep-dive on the 7 router strategies.
10. [`docs/PRIOR_ART.md`](./docs/PRIOR_ART.md) — May 2026 research synthesis.
11. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — code layout + data flow.
12. [`docs/audits/T-22-v3-publish-readiness.md`](./docs/audits/T-22-v3-publish-readiness.md) — final publish-readiness audit.
13. [`results/runs/07-v3-devstral-all-routes/run-notes.md`](./results/runs/07-v3-devstral-all-routes/run-notes.md) — v3 sweep, per-run findings.
14. [`results/runs/11-judge-robust-D/run-notes.md`](./results/runs/11-judge-robust-D/run-notes.md) — triple-judge robustness audit (96 verdicts).
15. [`results/REPORT_v1_mvp.md`](./results/REPORT_v1_mvp.md) — the MVP report, preserved verbatim.
16. [`results/runs/README.md`](./results/runs/README.md) — index of experimental runs.
17. [`examples/drop-in-a-new-model.md`](./examples/drop-in-a-new-model.md) — 5-step walkthrough for benchmarking a new model.
18. [`AGENTS.md`](./AGENTS.md) — canonical agent guide: folder-by-folder inventory + architecture + conventions, for any AI agent working in the repo.

## License and attribution

- **Code** (harness, router, runners, scorers, analysis, viz): MIT — see [`LICENSE`](./LICENSE).
- **Results, metrics, figures, article**: CC-BY-4.0 — see [`LICENSE-DATA`](./LICENSE-DATA).
- **Third-party code and research we build on**: see [`NOTICE.md`](./NOTICE.md) and [`vendor/README.md`](./vendor/README.md).

Suggested citation (if you use our numbers):

> Monga, Sanchit and contributors. *hybrid-coding-eval: reproducible cost/latency/quality benchmark for local vs cloud vs hybrid LLM routing on coding tasks.* 2026. <https://github.com/RunanywhereAI/hybrid-coding-eval>
