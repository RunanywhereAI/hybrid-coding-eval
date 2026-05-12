# Should I run my coding tasks local, hybrid, or cloud? A token-first answer.

> _250 graded rows across 5 routes × 8 task shapes × 6 pricing scenarios on a single M4 Max laptop. Every row records its tokens; **cost is derived from tokens at read time** against a pinned pricing table. The same dataset is re-priced under six cloud scenarios without re-running inference._

**Status (2026-05-11).** Published from branch `mono-repo-reorg`, tag `v3-public-candidate`. Successor to [`../results/REPORT_v1_mvp.md`](../results/REPORT_v1_mvp.md) (the MVP report from run 04). The numbers below are derived from [`../results/runs/07-v3-devstral-all-routes/raw.jsonl`](../results/runs/07-v3-devstral-all-routes/raw.jsonl) (250 rows, single sweep) and the triple-judge audit [`../results/runs/11-judge-robust-D/judge.jsonl`](../results/runs/11-judge-robust-D/judge.jsonl) (96 verdicts).

**Headline graphics.** `../results/runs/07-v3-devstral-all-routes/charts/pareto.png`, `heatmap_cost.png`, `heatmap_quality.png`, `heatmap_arqgc.png`.

**Hardware + model envelope.** All numbers below are for: **M4 Max 64 GB MacBook**, **`devstral:24b`** as the local model (Ollama), **`gpt-5.5`** as the cloud model (OpenAI), **`claude-opus-4-7`** as the judge (Anthropic), pricing snapshot **2026-04-27** from `models.dev`. **Findings are explicitly conditional on this hardware/model triple** — re-run with a different mix and the cost ratios change. The route ranking, however, is invariant across the six pricing scenarios we tested.

---

## §1. TL;DR

For a real developer's coding workload, **the right answer depends entirely on whether the local model can solve the task alone**.

- **If yes** — small self-contained tasks where `devstral:24b` produces a correct answer in one shot — **R2 (local-only) is free.** Pass rate 90% on HumanEval+, $0.00 per task under every cloud-pricing scenario, ~5 s wall on an M4 Max.
- **If no** — anything outside that subset — **R1 (cloud-only, `gpt-5.5`) is cheaper than any hybrid route on this hardware and task mix.** Hybrid routes ship ~80-90% of total token volume to the cloud anyway, and pay 2-5× R1's per-row cost to land at parity-or-worse quality.

**Cost is derived from tokens at read time** against [`configs/pricing/pricing_tables.json`](../configs/pricing/pricing_tables.json) (sha256 pinned). Every claim in this article is one re-derivation away from a different cloud scenario, but the route ranking is invariant — every scenario is a positive scalar on every cloud-token count.

Three numbers that anchor the rest of the article:

1. **R4's median `cloud_fraction` is 87% across 250 rows.** The Stanford-Minion supervisor/worker framing predicts the cloud asks targeted questions while the local worker reads context; in our setup the cloud supervisor ends up writing 8 of every 10 tokens. Per-category R4 cloud-fraction: A 90%, B 86%, C 89%, D 86%.
2. **R1, R3, and R4 all pass exactly the same 3/10 on SWE-bench Verified easy** — the same three Django tasks (`django-11163`, `django-11179`, `django-15863`). The two unique Sphinx wins R4 recorded in run 04 (`sphinx-7889`, `sphinx-9698`) **did not replicate** under identical models and harness. The "R4 beats R1 on SWE-bench" v1 headline was 10-task single-seed noise.
3. **R5 (DevMinion review-loop) burned the most tokens (1.88 M total, 1.85× R3, 2.94× R4) and collapsed on prose tasks**: composite 0.00 on every D3 refactor and 3 of 4 D4 code-reviews. R5 is 5.13× R1's mean cost and the worst route on three of four categories.

A real developer reading this for cost guidance: **hybrid is currently a quality-parity, cost-loss choice on the task mix we evaluated.** Skip to §7 for the per-shape practical recommendation.

---

## §2. The headline decision table — 8 task shapes × 5 routes

Pulled verbatim from [`DECISION_TABLE.md`](./DECISION_TABLE.md). Pass rate uses `functional_pass=True` where a functional scorer exists; judge-scored shapes (C-arch, D3, D4) use `composite >= 0.5` as the pass proxy, flagged with `*`. **D2 is `None/N` by design** — external GitHub-issue tasks, functional scorer deferred (see §10); treat D2 cost/cloud-fraction as observation only, not quality signal.

### A — HumanEval+ (tiny self-contained functions, 10 tasks)

| route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| R1 | 10 | 10/10 | 100% | $0.0119 | $0.0008 | 5,364 |
| R2 | 10 | 9/10 | 0% | $0.0000 | $0.0000 | 5,244 |
| R3 | 10 | 10/10 | 37% | $0.0380 | $0.0024 | 57,524 |
| R4 | 10 | 10/10 | 90% | $0.0659 | $0.0041 | 37,345 |
| R5 | 10 | 4/10 | 50% | $0.2488 | $0.0162 | 262,695 |

### B — SWE-bench Verified easy (multi-file repo patches, 10 tasks)

| route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| R1 | 10 | 3/10 | 100% | $0.1058 | $0.0070 | 61,586 |
| R2 | 10 | 0/10 | 0% | $0.0000 | $0.0000 | 9,700 |
| R3 | 10 | 3/10 | 34% | $0.1369 | $0.0088 | 166,103 |
| R4 | 10 | 3/10 | 86% | $0.2025 | $0.0127 | 139,083 |
| R5 | 10 | 0/10 | 53% | $0.3902 | $0.0256 | 381,303 |

### C — BigCodeBench-Hard (5) + custom-arch (5, judge-scored)

| shape | route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| C-bcb | R1 | 5 | 1/5 | 100% | $0.0433 | $0.0029 | 21,998 |
| C-bcb | R2 | 5 | 1/5 | 0% | $0.0000 | $0.0000 | 22,159 |
| C-bcb | R3 | 5 | 0/5 | 41% | $0.0862 | $0.0054 | 77,120 |
| C-bcb | R4 | 5 | 0/5 | 89% | $0.0906 | $0.0057 | 52,238 |
| C-bcb | R5 | 5 | 0/5 | 50% | $0.4429 | $0.0286 | 645,402 |
| C-arch | R1 | 5 | 5/5\* | 100% | $0.2963 | $0.0197 | 180,594 |
| C-arch | R2 | 5 | 3/5\* | 0% | $0.0000 | $0.0000 | 47,568 |
| C-arch | R3 | 5 | 5/5\* | 70% | $0.4876 | $0.0316 | 523,641 |
| C-arch | R4 | 5 | 4/5\* | 89% | $0.1612 | $0.0104 | 119,873 |
| C-arch | R5 | 5 | 1/5\* | 53% | $0.4957 | $0.0325 | 876,316 |

### D — real-developer (20 tasks across 5 shapes)

| shape | route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| D1 small-feature | R1 | 4 | 2/4 | 100% | $0.0304 | $0.0018 | 12,940 |
| D1 small-feature | R2 | 4 | 0/4 | 0% | $0.0000 | $0.0000 | 2,834 |
| D1 small-feature | R3 | 4 | 2/4 | 31% | $0.0976 | $0.0062 | 127,042 |
| D1 small-feature | R4 | 4 | 1/4 | 86% | $0.1183 | $0.0073 | 102,956 |
| D1 small-feature | R5 | 4 | 1/4 | 46% | $0.4318 | $0.0280 | 582,035 |
| D2 gh-issue | R1 | 4 | None/4 | 100% | $0.0409 | $0.0026 | 25,728 |
| D2 gh-issue | R2 | 4 | None/4 | 0% | $0.0000 | $0.0000 | 7,795 |
| D2 gh-issue | R3 | 4 | None/4 | 32% | $0.1282 | $0.0083 | 154,903 |
| D2 gh-issue | R4 | 4 | None/4 | 86% | $0.1714 | $0.0111 | 130,993 |
| D2 gh-issue | R5 | 4 | None/4 | 53% | $0.3387 | $0.0222 | 398,319 |
| D3 refactor | R1 | 4 | 4/4\* | 100% | $0.0354 | $0.0022 | 13,667 |
| D3 refactor | R2 | 4 | 0/4\* | 0% | $0.0000 | $0.0000 | 3,036 |
| D3 refactor | R3 | 4 | 4/4\* | 37% | $0.1509 | $0.0097 | 219,453 |
| D3 refactor | R4 | 4 | 4/4\* | 86% | $0.1637 | $0.0100 | 125,883 |
| D3 refactor | R5 | 4 | 0/4\* | 55% | $0.4043 | $0.0266 | 461,580 |
| D4 review | R1 | 4 | 4/4\* | 100% | $0.0861 | $0.0056 | 46,556 |
| D4 review | R2 | 4 | 0/4\* | 0% | $0.0000 | $0.0000 | 19,088 |
| D4 review | R3 | 4 | 2/4\* | 81% | $0.4067 | $0.0262 | 270,419 |
| D4 review | R4 | 4 | 2/4\* | 83% | $0.1968 | $0.0120 | 158,609 |
| D4 review | R5 | 4 | 0/4\* | 50% | $0.4355 | $0.0283 | 597,710 |
| D5 functional | R1 | 4 | 3/4 | 100% | $0.0158 | $0.0010 | 12,026 |
| D5 functional | R2 | 4 | 0/4 | 0% | $0.0000 | $0.0000 | 13,200 |
| D5 functional | R3 | 4 | 3/4 | 33% | $0.0706 | $0.0045 | 91,331 |
| D5 functional | R4 | 4 | 3/4 | 88% | $0.0729 | $0.0046 | 63,739 |
| D5 functional | R5 | 4 | 3/4 | 45% | $0.4230 | $0.0273 | 750,461 |

Reading the cells row-wise: R2 is the cheapest where it works (A, C-bcb on `BigCodeBench/530`, a few D5/C-arch tasks); R1 is the cheapest non-zero-cost option everywhere else; every hybrid route costs 2-12× R1's per-task median on the same cell with no compensating quality gain.

---

## §3. Token-first Pareto — where the tokens went

Headline aggregate, regenerated from [`aggregate.json`](../results/runs/07-v3-devstral-all-routes/aggregate.json) and [`TOKEN_BUDGET.md`](./TOKEN_BUDGET.md):

| route | n_rows | Σ cloud tokens | Σ local tokens | total | cloud_fraction (Σ) | Σ $ gpt-5.5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R1 | 50 | 158,406 | 0 | 158,406 | 100% | $3.82 |
| R2 | 50 | 0 | 94,301 | 94,301 | 0% | $0.00 |
| R3 | 50 | 475,855 | 539,829 | 1,015,684 | 47% | $8.65 |
| R4 | 50 | 544,429 | 95,647 | 640,076 | 85% | $7.29 |
| R5 | 50 | 945,209 | 934,148 | 1,879,357 | 50% | $19.59 |

Per-row mean cost ratios vs R1: **R3 = 2.26×, R4 = 1.91×, R5 = 5.13×**. Per-shape medians push the gap wider on prose categories: D4-review R3 cost $0.4067 vs R1's $0.0861 (4.7×), R5 vs R1 on D4 = 5.1×.

### §3.1 Cloud-fraction by shape × route

| | A | B | C | D | median across all |
| --- | ---: | ---: | ---: | ---: | ---: |
| R1 | 100% | 100% | 100% | 100% | 100% |
| R2 | 0% | 0% | 0% | 0% | 0% |
| R3 | 37% | 34% | 57% | 35% | **35%** |
| R4 | 90% | 86% | 89% | 86% | **87%** |
| R5 | 50% | 53% | 53% | 50% | **50%** |

R3 is the only hybrid that delivers the predicted 60-80% local balance (35% cloud = 65% local). R4's 87% cloud falsifies the v3 prediction by 2× the upper bound. R5 sits at 50% cloud, but absolute token volume (1.88M) is 3× R4's, so the relative balance is misleading: R5 is local-heavy but more expensive than R4 because of multi-round context replay.

### §3.2 Why R4's cloud_fraction stayed at 87%

The Stanford Minion supervisor/worker protocol assumes the cloud supervisor asks short, targeted questions, and the local worker reads the full context. In practice, on our task lengths (300-3500 prompt tokens, 200-6000 completion tokens), the supervisor's questions plus answers plus the synth step end up being where the conversation's token volume lives. R4 makes 1-3 cloud calls per task; each one is on the order of 1500-3000 prompt + 800-2500 completion cloud tokens. The local worker's contribution to the total token budget is small (median 401 local-prompt + 211 local-completion tokens per task). On a 3500-token prompt task, the cloud-side share is structurally going to dominate unless the protocol is rewritten to push more drafting work to the worker.

### §3.3 Why R3 is the most-local-of-the-hybrids and still pays 2.26× R1

R3's planner step runs on the cloud, the per-step solving runs locally with a context window the heuristic keeps small, and the synth step rolls back to the cloud. The local fraction (median 65% of tokens, 47% in aggregate sum) is real — but the cloud-prompt-side of the planner and synth steps is structurally expensive. On a single HumanEval task, R3 sends 1500-2500 cloud-prompt tokens to plan + synth what R1 solves in 100-200 cloud-prompt tokens. The local steps are free but they don't reduce the cloud side enough to flip the dollar comparison.

### §3.4 Six pricing scenarios — invariance

The same 250-row token dataset re-priced under six scenarios:

| scenario | total $ | R1 | R2 | R3 | R4 | R5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| openai-gpt5.5 (primary) | $39.34 | $3.82 | $0.00 | $8.65 | $7.29 | $19.59 |
| openai-gpt5 | $12.71 | $1.24 | $0.00 | $2.79 | $2.36 | $6.32 |
| openai-gpt5-mini | $2.54 | $0.25 | $0.00 | $0.56 | $0.47 | $1.26 |
| anthropic-opus-4.7 | $100.77 | $9.79 | $0.00 | $22.17 | $18.69 | $50.12 |
| anthropic-sonnet-4.6 | $20.15 | $1.96 | $0.00 | $4.43 | $3.74 | $10.02 |
| anthropic-haiku-4.5 | $8.31 | $0.81 | $0.00 | $1.83 | $1.54 | $4.13 |

**R1 < R4 < R3 < R5 on cost under every scenario.** The ranking is invariant because each scenario applies a positive scalar to cloud tokens and zero to local tokens. The hybrid/R1 cost ratio widens under premium pricing (opus-4.7: R5 = 5.12× R1) and narrows under cheap pricing (gpt5-mini: R5 = 5.04× R1), but never inverts. The full table is in [`APPENDIX_SCENARIOS.md`](./APPENDIX_SCENARIOS.md) and raw data in [`token_budget.csv`](./token_budget.csv).

---

## §4. Three category deep-dives

### §4.1 Category A (HumanEval+) — R2 is free, every hybrid pays for nothing

R2 passes 9 of 10 HumanEval+ tasks. The one miss: `HumanEval_77`, where devstral generated a recursive function that hit infinite recursion on negative inputs — a smoke-test would catch it. R1 passes 10/10. R3 and R4 also pass 10/10 by leaning on the cloud half of their pipeline. R5 passes 4/10 (the editor's review loop is too aggressive on tasks with a single correct one-liner answer).

Token + cost per task (median):

| task subset | R1 cloud_frac | R1 $ | R2 $ | R3 $ | R4 $ | R5 $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HumanEval_15 (smallest) | 100% | $0.005 | $0.000 | $0.030 | $0.050 | $0.292 |
| HumanEval_103 (mid) | 100% | $0.017 | $0.000 | $0.056 | $0.078 | $0.393 |
| HumanEval_13 (largest) | 100% | $0.004 | $0.000 | $0.026 | $0.057 | $0.476 |

Every hybrid pays a fixed planning/routing tax (R3: ~$0.04, R4: ~$0.06) regardless of how trivial the task is. R5's tax is structurally 4-8× higher because of the review-loop's round-replay overhead. **There is no Category-A task on which any hybrid Pareto-improves on R1 or R2.**

*Contamination caveat.* HumanEval+ predates 2021 and is widely-indexed; expect HIGH memorization across all routes. Treat A as a floor under which no route can fall on this hardware, not a ceiling.

### §4.2 Category B (SWE-bench Verified easy) — the v1 R4 win did not replicate

Run 04 (the v1 MVP) claimed R4 Minion was the only route to win on SWE-bench (4/10 vs R1's 3/10), with R4 uniquely solving `sphinx-doc__sphinx-7889` and `sphinx-doc__sphinx-9698`. The v3 sweep with the same models and the same SWE-bench harness produces a different result:

| task_id | R1 | R3 | R4 | R5 |
| --- | :-: | :-: | :-: | :-: |
| `django__django-11163` | yes | yes | yes | no |
| `django__django-11179` | yes | yes | yes | no |
| `django__django-15863` | yes | yes | yes | no |
| `django__django-13512` | no | no | no | no |
| `django__django-15315` | no | no | no | no |
| `sphinx-doc__sphinx-7889` | no | no | **no** | no |
| `sphinx-doc__sphinx-9698` | no | no | **no** | no |
| `sphinx-doc__sphinx-9711` | no | no | no | no |
| `pydata__xarray-4356` | no | no | no | no |
| `astropy__astropy-7166` | no | no | no | no |

R1 = R3 = R4 = 3/10, on the same three Django tasks. The two Sphinx wins R4 claimed in run 04 are not there. R5 is 0/10.

**Read this carefully.** The v1 R4 cost framing ("R4 wins on pass rate; $0.56/correct vs R1's $0.42/correct") was load-bearing on those Sphinx wins. Without them R4 is no better than R1 on pass rate and **costs $7.29 / 3 = $2.43 per correct vs R1's $3.82 / 3 = $1.27 per correct** under the v3 sweep totals — R4 is 1.9× more expensive per correct on B, not 1.3× cheaper. The single-sample variance on a 10-task SWE-bench slice is large enough to overturn the v1 headline. Don't quote the v1 R4-on-B win without replication.

Cost per task on B is dominated by long completion tokens (SWE-bench answers are full file patches). R1's median B-row sends 269 prompt tokens and gets back ~3500 completion tokens. R3 fans this out to ~12-15K local-prompt + ~3-7K cloud-prompt + ~2-7K cloud-completion — every leg gets fed the full diff context.

### §4.3 Category D — real-developer tasks, where prose handicaps hybrid

D is the v3 sweep's new category. 20 tasks across 5 shapes:

- **D1** (4 small-feature) — auth login, JSON-schema, rate-limit, retry decorator
- **D2** (4 GitHub-issue patches) — click, jsonschema, pytest, werkzeug (functional scorer deferred)
- **D3** (4 refactors, judge-scored) — constants→enum, extract helper, try-except→contextmanager, split god-module
- **D4** (4 code reviews, judge-scored) — cache invalidation, pagination, SQL injection, timezone handling
- **D5** (4 small one-shots) — csv-dedupe, env-var-redactor, log-errors-today, todo-counter

**Per-D-shape pass rate (D2 not shown; deferred):**

| shape | R1 | R2 | R3 | R4 | R5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| D1 small-feature | 2/4 | 0/4 | 2/4 | 1/4 | 1/4 |
| D3 refactor (composite ≥ 0.5) | 4/4 | 0/4 | 4/4 | 4/4 | 0/4 |
| D4 review (composite ≥ 0.5) | 4/4 | 0/4 | 2/4 | 2/4 | 0/4 |
| D5 functional | 3/4 | 0/4 | 3/4 | 3/4 | 3/4 |

**R5's prose collapse, by task ID.** Every D3 and D4 task R5 attempted scored 0.00 except `d4-review-pagination` (0.22):

- `real-dev/d3-constants-to-enum`: R5 0.00 (R1 = 0.96, R3 = 0.54, R4 = 0.54)
- `real-dev/d3-extract-validation-helper`: R5 = 0.00 (R1 = 0.98, R3 = 0.74, R4 = 0.72)
- `real-dev/d3-replace-try-except-with-contextmanager`: R5 = 0.00 (R1 = 1.00, R3 = 0.84, R4 = 0.54)
- `real-dev/d3-split-god-module`: R5 = 0.00 (R1 = 1.00, R3 = 0.84, R4 = 0.74)
- `real-dev/d4-review-cache-invalidation`: R5 = 0.02 (R1 = 1.00, R3 = 0.54, R4 = 0.48)
- `real-dev/d4-review-pagination`: R5 = 0.22 (R1 = 0.98, R3 = 0.45, R4 = 0.70)
- `real-dev/d4-review-sql-injection`: R5 = 0.00 (R1 = 0.98, R3 = 0.34, R4 = 0.48)
- `real-dev/d4-review-timezone-handling`: R5 = 0.00 (R1 = 0.98, R3 = 0.78, R4 = 0.64)

**Failure mode** (from inspecting `outputs/` artefacts on `real-dev/d3-extract-validation-helper`): R5's editor produces a refactor; the reviewer's verdict invalidates it; the next round drifts further from the original spec. By round 3 the artefact no longer reads as a faithful refactor — it has new functions, deleted code paths, fabricated tests. The final integration step writes the literal string `ls -la` as the deliverable (the only usable content from the editor's last round). **Review-loops, on this architect/editor protocol, cost more tokens and hurt prose quality.**

**Robustness: triple-judge audit.** We re-judged the 16 D3+D4 R1-vs-R3 and R1-vs-R4 pairings under three judges (`claude-opus-4-7`, `claude-sonnet-4-6`, `gpt-5.5`) × two A/B orders = 96 verdicts. **All 96 verdicts are R1 wins. Zero ties. Zero flips. Zero errors.** Mean margins: opus 0.94, sonnet 1.00, gpt-5.5 1.00. The cross-vendor unanimity rules out same-family judge bias; the zero order-flips rules out A/B position effects. R1 dominance on D3+D4 is robust on this 8-task slice (see [`../results/runs/11-judge-robust-D/run-notes.md`](../results/runs/11-judge-robust-D/run-notes.md)).

**One row where hybrid Pareto-improves on R1.** Across all 250 rows, **exactly one row** has a hybrid composite strictly greater than R1's by more than 0.01: `real-dev/d1-json-schema`, where R3 = 1.00 (functional pass) and R1 = 0.00. R1 produced a Python schema definition; the harness expected JSON output. Every other row is R1 ≥ hybrid. The hybrid routes do not Pareto-improve on R1 on this dataset.

**Two D5/D1 unique R5 wins.** R5 was the only route to solve `real-dev/d1-retry-decorator` (R5 pass; R1, R2, R3, R4 all fail) and `real-dev/d5-log-errors-today` (R5 pass; all others fail). Two-task evidence is not enough to claim a niche, but it sketches the shape of where R5 might earn its slot: small functional tasks where each review round verifies a concrete behaviour. Outside that, R5 currently hurts.

---

## §5. The 10 most surprising findings

Numbered in order of magnitude — biggest surprise first.

1. **R4's cloud_fraction is 87%, not 20-40%.** The Minion paper's framing put most token volume on the local worker; in our setup the cloud supervisor writes 8 of 10 tokens. The supervisor reads the full problem statement each round; the worker contributes small targeted answers. On long-context tasks (B, D2), the supervisor structurally dominates.

2. **R5 (DevMinion) cost 5.13× R1 mean and is the worst route on three of four categories.** Designed for tasks where multi-round review should help (refactors, code reviews). The opposite happened: R5 scored 0.00 composite on every D3 task and 3 of 4 D4 tasks, while burning 1.88M tokens (2.94× R4).

3. **The "R4 beats R1 on SWE-bench" v1 headline did not replicate.** Run 04 claimed R4 was 4/10 on B (Sphinx wins over R1's 3/10). Run 07 with identical models and harness: R1 = R3 = R4 = 3/10 on the same three Django tasks. The two Sphinx wins are gone. Single-sample 10-task slice variance overturned the v1 headline.

4. **1 row in 250 has any hybrid composite > R1 by more than 0.01.** That row is `real-dev/d1-json-schema`, where R3 = 1.00 (output-format-aware) and R1 = 0.00 (single-shot Python instead of JSON). Every other row is R1 ≥ hybrid. The hybrid routes do not Pareto-improve on R1 on this dataset.

5. **96 triple-judge verdicts on D3/D4 are 100% unanimous.** Three judges (opus-4-7, sonnet-4-6, gpt-5.5), two A/B orders, 16 pairings = 96 verdicts. All 96 are R1 wins. Zero ties. Zero flips. R1 prose dominance is judge-and-order-invariant on this slice — the strongest robustness signal in the dataset.

6. **C-bcb regression where R1 and R2 both pass, all hybrids fail.** Task `BigCodeBench/530` (random RGB image generator): R1 composite 1.0, R2 1.0, R3 0.43, R4 0.86, R5 0.43. The cloud planner over-engineered a one-liner. Hybrid is a *regression* on tasks where the bottleneck is library-API knowledge, not orchestration.

7. **R5 has two unique functional wins.** `real-dev/d1-retry-decorator` and `real-dev/d5-log-errors-today` — R5 passes, every other route fails. Two-task evidence isn't a niche, but it shows where the review loop might earn its keep: small functional tasks where each round verifies a concrete behaviour.

8. **R3 ties R1 on three C-arch tasks at 1.6× the cost.** `auth-multitenant-design`, `migration-planning-zero-downtime`, `cache-invalidation-tradeoffs`: R3 composite ≥ 0.95, matching R1. But R3 spent $0.49 median vs R1's $0.30. Quality parity is real; cost parity is not.

9. **The cost ranking is invariant across all 6 pricing scenarios.** R1 < R4 < R3 < R5 holds under gpt-5.5, gpt-5, gpt-5-mini, opus-4.7, sonnet-4.6, haiku-4.5. The hybrid/R1 ratio widens under premium pricing but never inverts.

10. **Zero infrastructure errors on 250 rows.** Every row in `raw.jsonl` has `error=null`. No timeouts, no API failures, no Docker crashes. The harness is reliable enough that the findings reflect model+protocol behaviour, not infrastructure noise.

---

## §6. Did the v3 plan's hypothesis hold? No.

The v3 sweep was designed around the prediction that **hybrid routes (R3/R4/R5) would send 60-80% of total tokens to the local model, achieve quality parity with R1, and save 40-70% on cost** versus a pure cloud baseline. That prediction was the explicit reason for adding R5 to the lineup and for running the full 5-route × 50-task sweep.

What we measured:

| metric | v3 prediction | v3 measurement |
| --- | --- | --- |
| R3 cloud_fraction (median) | 20-40% | **35%** (in line, low end) |
| R4 cloud_fraction (median) | 20-40% | **87%** (far outside; 2× upper bound) |
| R5 cloud_fraction (median) | 20-40% | **50%** (outside band) |
| R3 cost vs R1 | 0.3-0.6× | **2.26×** (mean) / 3.5-5× (per-shape on prose) |
| R4 cost vs R1 | 0.3-0.6× | **1.91×** (mean) / 1.9-2.4× (per-shape) |
| R5 cost vs R1 | 0.3-0.6× | **5.13×** (mean) / 4-13× (per-shape) |
| Quality parity (composite within 0.05 of R1) | yes on all hybrid routes | partial on R3 (A, B, C-arch, D3); R3 fails on D4. R4 partial. R5 fails on B, C, D3, D4. |

**The hypothesis is contradicted on cost on all three hybrid routes, and contradicted on cloud_fraction on R4 and R5.** R3 alone delivered the predicted token-routing balance, but its dollar cost still ran 2.26× R1 because the cloud-side prefixes (planner + synth) are structurally expensive relative to what gets saved locally.

The intuition the prediction came from — Stanford Minion's framing of the supervisor as a query coordinator with most token volume on the worker side — does not survive contact with our real prompt sizes. On long-context tasks (B and D2), the supervisor processes the full problem statement each round; the worker's contribution is small targeted answers. On short-context tasks (A), there isn't enough content to push to a worker in the first place.

We ran the experiment as designed. The result contradicts the hypothesis. **No hybrid route on this task mix delivers the 40-70% cost savings the v3 plan predicted.** That's the most important finding in this dataset.

---

## §7. What does this mean for a real developer?

Practical guidance, per task shape:

| Your task is... | Pick | Why |
| --- | --- | --- |
| HumanEval-shape — tiny self-contained function | **R2** (devstral local) | 90% pass rate at $0.00; no Pareto-improvement available |
| Small real-dev feature (D1) that devstral can solve | **R2** | Free; identify the subset by running R2 first and falling back to R1 if it fails |
| Small real-dev feature (D1) devstral can't solve | **R1** | 50% R1 pass vs hybrid 25-50%; lower cost |
| SWE-bench-style multi-file repo patch | **R1** | 30% pass rate; hybrid routes give the same 30% at 1.3-3.7× cost |
| BigCodeBench-hard third-party library task | **R1** or **R2** | R1 = R2 = 1/5; hybrid routes regress to 0/5 |
| Architecture-design prose (C-arch) | **R1** | 100% composite ≥ 0.5; R3 ties at 1.6× cost; R4/R5 lose |
| Refactor with prose judgement (D3) | **R1** | 100% pass; triple-judge audit confirms R1 wins all 8 pairings vs R3/R4 |
| Code review with prose judgement (D4) | **R1** | 100% pass; R3/R4 land 50%; R5 = 0% |
| External GitHub-issue patch (D2) | **R1** as fallback | Functional scorer deferred; cost/cloud-fraction observable only |

**The fall-through rule:** try R2 first; if it fails (or the task shape is one where R2 has 0/n pass rate, i.e. B / C-bcb / D1 / D2 / D3 / D4 / D5), go straight to R1. **Skip the hybrid routes.**

**Hybrid (R3/R4/R5) does not earn a slot in this routing table at the current cloud/local pricing ratio and on this hardware tier.** The cases where hybrid would be the right choice on cost-per-correct require either:

- a much more expensive cloud model (e.g. claude-opus-4.7 at $15/Mtok output, where R1 costs scale up faster than R3/R4 do — but `aggregate.json` shows R3/R4 still cost more in absolute dollars under opus-4.7, so the cost ranking is preserved), OR
- a local model that solves a larger subset of tasks alone (which would shift more tasks to the R2 column, not the hybrid column), OR
- a different hybrid protocol that pushes more token volume to the local worker (the existing protocols don't; see §3 for why).

**If you're cost-conscious right now: route to R2 first, R1 second. Skip the hybrid routes.**

---

## §8. Methodology — comprehensive

### §8.1 The 5 routes — how each works

**R1 — cloud-only.** Single `chat.completions` call to `gpt-5.5`. No routing, no latency overhead. All tokens cloud; `cloud_fraction = 100%` by definition. Implementation: [`src/hybrid_coding_eval/runners/r1_cloud_only.py`](../src/hybrid_coding_eval/runners/r1_cloud_only.py) (~80 LOC). Median row: 527 cloud tokens, $0.012, ~5 s wall.

**R2 — local-only.** Single call to `devstral:24b` via Ollama (`http://127.0.0.1:11434/v1/chat/completions`). No cloud, no API cost. All tokens local; `cloud_fraction = 0%` by definition. Implementation: [`src/hybrid_coding_eval/runners/r2_local_only.py`](../src/hybrid_coding_eval/runners/r2_local_only.py) (~80 LOC). Median row: 621 local tokens, $0.00, ~5 s wall.

**R3 — hybrid-architect** (cloud planner → local executor → cloud synth). Three-phase pipeline:
1. `gpt-5.5` decomposes the task into 3-8 numbered steps (JSON output).
2. Each step is routed by the heuristic router (token count + keyword hits + code-block presence); most steps go to `devstral:24b`.
3. `gpt-5.5` synthesizes the final answer from the step outputs.

Implementation: [`src/hybrid_coding_eval/runners/r3_hybrid_architect.py`](../src/hybrid_coding_eval/runners/r3_hybrid_architect.py) (Python) subprocessing [`router/pipelines/architect/runner.mjs`](../router/pipelines/architect/runner.mjs) (Node, ~250 LOC). Cost is re-derived in Python from tokens; the JS side's `totals.hybridCostUsd` is a cross-check only.

**R4 — hybrid-minion** (Stanford Minion supervisor/worker Q&A). Supervisor (`gpt-5.5`) sees only the task statement; worker (`devstral:24b`) sees the full context. The supervisor asks targeted questions, the worker answers from context. Up to 3 rounds. Wraps [`vendor/minions/minions/minion.py`](../vendor/minions/minions/minion.py) (MIT, Stanford HazyResearch). Implementation: [`src/hybrid_coding_eval/runners/r4_minion.py`](../src/hybrid_coding_eval/runners/r4_minion.py) (~200 LOC).

**R5 — hybrid-devminion** (architect/editor/reviewer review-loop). Architect (`gpt-5.5`) generates a runbook (a list of code-change steps with rationale). Editor (`devstral:24b`) implements each step. Reviewer (`gpt-5.5`) approves, edits, or rejects, up to 3 rounds per step. Final integration step (`gpt-5.5`) emits the deliverable. Wraps [`vendor/minions/minions/minion_code.py`](../vendor/minions/minions/minion_code.py) (MIT). Implementation: [`src/hybrid_coding_eval/runners/r5_devminion.py`](../src/hybrid_coding_eval/runners/r5_devminion.py) (~300 LOC).

### §8.2 The 8 task shapes — what each measures

**A — HumanEval+ (10 tasks).** Tiny single-function completions: 150-300 token prompts, expected output is a complete Python function. Scoring: pytest in a Docker sandbox. Contamination risk: HIGH (pre-2021, widely indexed). Source: EvalPlus (Apache 2.0); seed=42 random sample. Pinned at [`src/hybrid_coding_eval/benchmarks/humaneval_plus/tasks.jsonl`](../src/hybrid_coding_eval/benchmarks/humaneval_plus/tasks.jsonl).

**B — SWE-bench Verified easy (10 tasks).** Real GitHub-issue patches across django, sphinx, xarray, astropy. 2-3 K token prompts (problem statement + repo context). Output: unified diff. Scoring: SWE-bench Docker harness (x86_64 images, ~10 min/task under Rosetta on M4 Max). Contamination risk: MEDIUM (post-cutoff for some tasks). Source: princeton-nlp/SWE-bench_Verified (MIT).

**C-bcb — BigCodeBench-Hard (5 tasks).** Library-heavy functional tasks: numpy, cv2, matplotlib, sklearn calls. 800-2000 token prompts. Scoring: pytest in sandbox. Hand-picked 5 tasks where the local model historically struggled. Source: bigcode/bigcodebench (Apache 2.0).

**C-arch — custom-arch (5 tasks, judge-scored).** Architecture-design prose: `auth-multitenant-design`, `cache-invalidation-tradeoffs`, `code-review-flaky-test`, `migration-planning-zero-downtime`, `production-debug-reasoning`. Hand-written by authors. 200-500 token prompts. Output: 500-2000 word architectural narrative. Scoring: `claude-opus-4-7` judge with 5-dimension rubric (correctness, completeness, style, reasoning depth, practicality), A-vs-B and B-vs-A averaged.

**D1 — small-feature (4 tasks).** Real-developer-shape small features: auth login, JSON schema, rate-limit decorator, retry decorator. Output: complete Python module + tests. Scoring: pytest. Pinned at [`src/hybrid_coding_eval/benchmarks/real_dev/fixtures/`](../src/hybrid_coding_eval/benchmarks/real_dev/fixtures/).

**D2 — GitHub-issue patches (4 tasks).** Real closed issues on pallets/click, jsonschema, werkzeug, pytest-dev. Output: unified diff. **Functional scorer deferred** — external GH issues aren't in the princeton-nlp SWE-bench dataset; a per-task harness is needed. Cost and cloud-fraction are observable; `functional_pass` and `composite` are `None` by design. T-23 in the future-work tracker.

**D3 — refactor (4 tasks, judge-scored).** `constants-to-enum`, `extract-validation-helper`, `replace-try-except-with-contextmanager`, `split-god-module`. Models read a small input file and produce a refactor. Judge-scored with the same rubric as C-arch.

**D4 — code-review (4 tasks, judge-scored).** Models review a small block of code and identify bugs. Topics: cache invalidation, pagination, SQL injection, timezone handling. Judge-scored.

**D5 — small one-shots (4 tasks).** Tiny one-file scripts: `csv-dedupe`, `env-var-redactor`, `log-errors-today`, `todo-counter`. Output: a Python script that reads stdin and writes stdout. Scoring: stdout-diff after pytest.

### §8.3 The 7 router strategies (brief)

The router proxy at [`router/strategies.mjs`](../router/strategies.mjs) supports seven routing strategies, addressable via the `model` field of each request. In this paper's runs (07, 11), R3 uses `heuristic`, R4/R5 use forced `always-cloud` for supervisor/reviewer roles and `always-local` for worker/editor roles. No actual router strategy tuning was done in v3 — that's future work.

1. **`always-cloud`** — control baseline; every request goes to cloud.
2. **`always-local`** — control baseline; every request goes to local.
3. **`rules`** — keyword + regex rules (24 CLOUD\_KEYWORDS, 12 LOCAL\_KEYWORDS), prompt-length threshold.
4. **`heuristic`** — weighted-score classifier (tokens × 0.4 + keyword hits × 0.3 + code-block count × 0.2 + tool count × 0.1), threshold 25, confidence-margin tiebreaker.
5. **`llm-classifier`** — `qwen3:0.6b` LLM call returns SIMPLE/COMPLEX, +50-200 ms latency, stochastic.
6. **`embedding-knn`** — top-5 cosine-similar examples from a 50-example hand-labelled corpus, vote by accumulated similarity.
7. **`cascade`** — heuristic decides first; on confidence < threshold, llm-classifier tiebreaks. Pays the LLM cost only on borderline cases.

Full deep-dive on each strategy: [`../docs/ROUTING_STRATEGIES.md`](../docs/ROUTING_STRATEGIES.md).

### §8.4 What's tested vs what's available

The 7 strategies listed above all exist in code; **the v3 sweep exercises only one**. The full status:

| strategy | exercised in v3 sweep? | where it would fire |
| --- | --- | --- |
| `always-cloud` | yes, in R1 (by definition) | every R1 call |
| `always-local` | yes, in R2 (by definition) | every R2 call |
| `heuristic` | **yes — R3 executor + synthesizer** | per-step routing in R3 |
| `rules` | no | could replace R3's heuristic |
| `llm-classifier` | no | could replace R3's heuristic |
| `embedding-knn` | no | could replace R3's heuristic |
| `cascade` | no | could replace R3's heuristic |

R4 (Minion) and R5 (DevMinion) do not use the routing strategies at all. Their protocols hardwire roles to backends: supervisor / architect / reviewer always cloud (`router/always-cloud`), worker / editor always local (`router/always-local`). There is no per-turn decision point in the Minion/DevMinion protocols where a strategy could fire. **The strategies only apply to R3**, which is the only route that decomposes a task into steps and picks a backend per step.

Four strategies (`rules`, `llm-classifier`, `embedding-knn`, `cascade`) are implemented and reachable via the proxy but were not exercised in v3 because R3's Python runner historically passed `router/heuristic` to the architect subprocess regardless of the config's `router.strategy` field. That wiring is fixed in v3.2: `config.router.strategy` now flows to R3, and `configs/variants/12-16-r3-strategy-*.yaml` ship 5 sweep configs that exercise each strategy on the same 50-task v3 set. Running those produces a fresh ~250-row strategy-sweep dataset; results will be folded into a future article revision when they land. The cost and quality differences between strategies on this hardware/model mix remain an open empirical question.

### §8.5 Scoring — functional, SWE-bench, LLM-judge

**Functional scorer** (A, C-bcb, D1, D5): generated code is extracted from the model output (first Python code block), written to a `python:3.12-slim` Docker container with `--network none`, 60 s wall-clock timeout, 512 MB memory cap, and pytest is run. Image at [`src/hybrid_coding_eval/scorers/Dockerfile.functional_python`](../src/hybrid_coding_eval/scorers/Dockerfile.functional_python). Composite = `tests_passed / tests_total`.

**SWE-bench harness** (B): generated diff is applied to the repo at the pinned base SHA, then the project's test suite runs under the SWE-bench Docker image. Binary pass/fail (`resolved=true` → composite 1.0). x86_64 images run under Rosetta on Apple Silicon (~10 min/task).

**LLM-judge** (C-arch, D3, D4): `claude-opus-4-7` (cross-vendor; avoids GPT self-preference per Zheng et al. 2306.05685) compares outputs pairwise (A-vs-B + B-vs-A averaged). 5-dimension rubric per task. Disagreement between orders halves the margin. `temperature=0.0`. Composite = win-rate across all pairings on the 5-dim rubric.

**Triple-judge audit** (run 11, D3+D4 only): 16 pairings × 3 judges (opus-4-7, sonnet-4-6, gpt-5.5) × 2 orders = 96 verdicts. Cross-vendor + order-flipped robustness check. Result: all 96 R1-wins, zero ties, zero flips.

### §8.6 Cost derivation under 6 pricing scenarios

Cost is **never stored** in `raw.jsonl`. Every row records tokens-per-backend (`local_prompt`, `local_completion`, `cloud_prompt`, `cloud_completion`, `cache_read`, `cache_write`). Cost is derived at read-time:

```
cost = (cloud_prompt − cache_read) × input_rate
     + cache_read × cache_read_rate
     + cloud_completion × output_rate
     + local_*   × 0    # local is $0 by construction
```

`input_rate`, `cache_read_rate`, `output_rate` come from [`configs/pricing/pricing_tables.json`](../configs/pricing/pricing_tables.json) (sha256 pinned, dated 2026-04-27, sourced from models.dev). Six scenarios are surfaced; the same dataset can be re-priced against any of them by `./bench token-budget` and `./bench analyze --pricing <scenario>`.

The six scenarios:

| scenario | input $/M | output $/M |
| --- | ---: | ---: |
| `openai-gpt5.5` (primary) | $5.00 | $30.00 |
| `openai-gpt5` | $1.25 | $10.00 |
| `openai-gpt5-mini` | $0.25 | $2.00 |
| `anthropic-claude-opus-4.7` | $15.00 | $75.00 |
| `anthropic-claude-sonnet-4.6` | $3.00 | $15.00 |
| `anthropic-claude-haiku-4.5` | $1.00 | $5.00 |

Local cost is set to $0 by construction. This is a simplification — the actual marginal cost of running `devstral:24b` on an M4 Max is roughly $0.005-0.01 per task (electricity + amortization). See §10 for the full caveat.

### §8.7 What we measure and what we do not claim

**We measure** token counts per backend, quality (pass/fail or composite), wall-clock, cost derivable under 6 pricing scenarios, on 250 rows (50 unique tasks × 5 routes, single seed 42), on one hardware tier (M4 Max 64 GB).

**We do not measure** statistical significance (N=1 per cell), multi-hardware tiers (M4 Max only), other cloud models (gpt-5.5 only, re-priced under 5 alternatives but not re-run), other local models (devstral:24b only), real development with multi-file context + tool loops + iteration (curated tasks only), external validity beyond this hardware/model triple.

**We do not claim** that hybrid routing is bad in principle. We claim that on this hardware, with these models, on this task mix, the three hybrid protocols we evaluated do not deliver the cost savings their designs predict. A different hybrid protocol — Aider's architect/editor without the review loop, or a cascade-with-validator — might. We did not test those.

---

## §9. Per-route worked examples

One concrete (task, route) trace per route, with token counts. Full per-route worked examples in [`APPENDIX_ROUTES.md`](./APPENDIX_ROUTES.md).

### R1 — `HumanEval_99` (complete `closest_integer`)

- Prompt: 527 tokens (function signature + docstring + example test cases)
- Cloud call: 1
- Cloud tokens: 527 prompt + 184 completion = 711 total
- Wall: 4.8 s
- Cost (gpt-5.5): $0.0114
- Quality: PASS (pytest 4/4)

R1 is the deterministic baseline. Reproduces in single-digit seconds.

### R2 — `HumanEval_13` (GCD)

- Prompt: 246 tokens
- Local call: 1
- Local tokens: 246 prompt + 375 completion = 621 total
- Wall: 4.2 s
- Cost: $0.00
- Quality: PASS

R2 wins on these self-contained algorithmic tasks because devstral has the pattern memorized.

### R3 — `custom-arch/auth-multitenant-design`

- Prompt: 312 tokens (problem statement)
- Phase 1 (planner, cloud): 312 prompt + 480 completion = 792 cloud tokens
- Phase 2 (executor, local): 4 steps × ~5K local-prompt + ~600 local-completion = 19,400 local tokens
- Phase 3 (synth, cloud): 23,200 cloud-prompt + 580 cloud-completion = 23,780 cloud tokens
- Cloud_fraction: 24,572 / (24,572 + 19,400) = 56%
- Wall: 521 s
- Cost (gpt-5.5): $0.486
- Quality: composite 1.00 (judge says R3 ties R1)

R3 ties R1 on prose quality at 1.6× the cost. The synth-step is where most cloud tokens go — it re-reads the concatenated step outputs.

### R4 — `humaneval-plus/HumanEval_103`

- Prompt: 285 tokens
- Round 1: supervisor cloud (1.4K prompt + 280 completion), worker local (1.8K prompt + 410 completion)
- Round 2: supervisor cloud (2.1K prompt + 320 completion), worker local (380 prompt + 180 completion)
- Final synth: cloud 3.4K prompt + 240 completion
- Cloud tokens: 7,740. Local tokens: 2,770. Cloud_fraction: 74%
- Wall: 38 s
- Cost (gpt-5.5): $0.078
- Quality: PASS

R4 spends 7.7× R1's cloud tokens to land at the same outcome on a tiny task.

### R5 — `real-dev/d3-extract-validation-helper` (canonical R5 collapse)

- Prompt: 612 tokens (small Python module + refactor task)
- Architect (cloud, runbook gen): 612 prompt + 1.2K completion
- Round 1 editor (local): 4.1K prompt + 2.8K completion → output X
- Round 1 reviewer (cloud): 5.3K prompt + 480 completion → "incorrect, see lines 12-18"
- Round 2 editor (local): 6.0K prompt + 3.1K completion → output Y (still wrong; shell commands appear)
- Round 2 reviewer (cloud): 6.8K prompt + 510 completion → "still incorrect"
- Round 3 editor (local): 7.7K prompt + 3.4K completion → output `ls -la`
- Round 3 reviewer (cloud): 8.2K prompt + 290 completion → "give up"
- Final integration (cloud): 1.4K prompt + 320 completion → deliverable is `ls -la`
- Cloud tokens: 16,200. Local tokens: 18,000. Cloud_fraction: 47%
- Wall: 491 s (8.2 min)
- Cost (gpt-5.5): $0.361
- Quality: composite 0.00

Compare R1 on the same task: 12 s wall, $0.033, composite 0.98. R5 spent 11× the cost and 41× the wall-clock to deliver `ls -la`.

---

## §10. Limits + biases acknowledged

| Limit | Status |
| --- | --- |
| **Single hardware tier** (M4 Max 64 GB) | Findings explicitly conditional. R2 wall would drop on bigger hardware; cloud-token counts wouldn't change so cloud cost is hardware-independent. |
| **Single cloud model** (gpt-5.5 primary) | Re-priced under 5 other scenarios; the ranking is invariant. A *different* cloud (gemini, deepseek) was not tested. |
| **Single local model** (devstral:24b) | A larger or smaller local model would shift the R2-vs-rest boundary. We did not test alternatives. |
| **10-task slices, single seed** | N=1 per cell. The v1 → v3 SWE-bench Sphinx reversal is itself a direct demonstration of slice-noise. Direction not significance. |
| **R5 has a known JSON-extraction fragility** | The architect/editor handoff goes via JSON; we patched the parser to be more forgiving, but residual brittleness may bias R5 down. Even with this caveat, R5's 0.00 composite on prose is consistent across 7 of 8 D3+D4 tasks — robust to extraction noise. |
| **D2 functional scoring deferred** | 20 of 250 rows have `functional_pass=None`. Cost/cloud-fraction observable; quality not. T-23 in future work. |
| **Custom-arch judge robustness only partial** | Run 11 covers D3+D4 only. Custom-arch (C) on v3 outputs is single-judge single-order (opus-4-7, AB only). The previous run 10 audited custom-arch but under qwen, not devstral. |
| **HumanEval+ contamination** | HIGH risk; treat as a floor not a ceiling. |
| **Custom-arch is hand-curated by authors** | Judge-audited to mitigate. Skeptic can re-judge with a new rubric. |
| **Local cost is $0 by construction** | Marginal cost on M4 Max is ~$0.005-0.01 per task (electricity + amortization). Not zero. The ranking does not flip if you add this — R1 is still cheaper per correct on B and D than every hybrid. |
| **Benchmark ≠ real development** | Curated, self-contained tasks with single prompts. Real work has multi-file context, tool loops, iteration, debugging from error output, documentation fetches. We do not cover those. |
| **No Aider proper, no cascade routing** | Future work. The hybrid landscape we tested is three protocols; there are more. |

Every limit is one of: (a) hardware/data inherited from the v3 sweep, (b) deferred scoring (D2), or (c) future-work scope. None overturn the headline findings; the 3/10 SWE-bench fluctuation between run 04 and run 07 is itself the most informative single-sample-variance signal in this dataset.

---

## §11. Reproducibility

Everything in this article is reproducible from a fresh clone of [github.com/RunanywhereAI/hybrid-coding-eval](https://github.com/RunanywhereAI/hybrid-coding-eval) at tag `v3-public-candidate`. Full step-by-step in [`../docs/REPRODUCING.md`](../docs/REPRODUCING.md); summary here:

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval && git checkout v3-public-candidate
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .
ollama pull devstral:24b
docker build -f src/hybrid_coding_eval/scorers/Dockerfile.functional_python -t hybrid-eval-python:latest .
echo "OPEN_AI_API_KEY=sk-..." > .env  # plus ANTHROPIC_API_KEY for judge
cd vendor && git clone https://github.com/HazyResearch/minions.git && cd ..  # R4 + R5
(cd router && ./start.sh) &  # router on :8787
./bench run --config configs/variants/07-v3-devstral-all-routes.yaml
```

Wall: 8-12 h on M4 Max. Cost: ~$40 OpenAI + ~$0.50 Anthropic. The same config + same hardware reproduces identical token counts and deterministic quality scores.

**Re-pricing without re-running.** Already have the 250-row dataset? Re-price it under any of the 6 scenarios:

```bash
./bench token-budget results/runs/07-v3-devstral-all-routes/
```

Outputs `reports/token_budget.csv` + a per-task table under all 6 scenarios. **Cost is never stored; you re-derive it.**

**Drop in a new model.** Want to test `gpt-4o` or a different local model? `cp configs/variants/_template.yaml configs/variants/my-model.yaml`, edit 2 lines, `./bench run`. 90 seconds of config + however long the sweep takes.

**Cross-checking your numbers against ours.** After your sweep, `diff` your `raw.jsonl` against the committed one — tokens and `quality.functional_pass` should match byte-identically on the same hardware. Wall-clock drifts with system load. Judge scores match if `temperature=0.0` (it is by default).

---

## §12. Where to read next

- [`DECISION_TABLE.md`](./DECISION_TABLE.md) — the per-shape × route grid surfaced in §2 (canonical).
- [`TOKEN_BUDGET.md`](./TOKEN_BUDGET.md) — full per-task token + cost-derivation table, 250 rows under 6 scenarios.
- [`APPENDIX_SCENARIOS.md`](./APPENDIX_SCENARIOS.md) — multi-scenario decision matrix and $/correct under every pricing tier.
- [`APPENDIX_ROUTES.md`](./APPENDIX_ROUTES.md) — full worked examples per R1..R5 with token-by-token trace.
- [`APPENDIX_TASKS.md`](./APPENDIX_TASKS.md) — forensic per-row record (large; query with jq, not read end-to-end).
- [`token_budget.csv`](./token_budget.csv) — raw cost-derivation data, one row per (task, route).
- [`../results/runs/07-v3-devstral-all-routes/run-notes.md`](../results/runs/07-v3-devstral-all-routes/run-notes.md) — per-run write-up of the v3 sweep.
- [`../results/runs/07-v3-devstral-all-routes/aggregate.json`](../results/runs/07-v3-devstral-all-routes/aggregate.json) — per-(category, route) medians + sums under six pricing scenarios.
- [`../results/runs/07-v3-devstral-all-routes/decision_matrix.md`](../results/runs/07-v3-devstral-all-routes/decision_matrix.md) — category × route quality / cost / wall + Bounded-ARQGC.
- [`../results/runs/11-judge-robust-D/judge.jsonl`](../results/runs/11-judge-robust-D/judge.jsonl) — 96 triple-judge verdicts for D3+D4 robustness audit.
- [`../results/runs/11-judge-robust-D/run-notes.md`](../results/runs/11-judge-robust-D/run-notes.md) — robustness audit write-up.
- [`../results/REPORT_v1_mvp.md`](../results/REPORT_v1_mvp.md) — the MVP report from run 04, preserved verbatim for lineage.
- [`../docs/METHODOLOGY.md`](../docs/METHODOLOGY.md) — full methodology, end-to-end.
- [`../docs/ROUTING_STRATEGIES.md`](../docs/ROUTING_STRATEGIES.md) — deep dive on the 7 router strategies.
- [`../docs/PRIOR_ART.md`](../docs/PRIOR_ART.md) — research synthesis.
- [`../docs/REPRODUCING.md`](../docs/REPRODUCING.md) — copy-paste reproduction guide.

---

## §13. Citations + license

**Suggested citation:**

> Monga, Sanchit and contributors. *hybrid-coding-eval: token-first decision report for local vs cloud vs hybrid LLM routing on coding tasks.* 2026. <https://github.com/RunanywhereAI/hybrid-coding-eval>. Tag: `v3-public-candidate`.

**License.**

- **Code** (harness, router, runners, scorers, analysis, viz): MIT — see [`../LICENSE`](../LICENSE).
- **Results, metrics, figures, this article**: CC-BY-4.0 — see [`../LICENSE-DATA`](../LICENSE-DATA).

**Third-party code we vendor.**

- Stanford Minions (`vendor/minions/`): MIT — wrapped by R4 and R5. See [HazyResearch/minions](https://github.com/HazyResearch/minions).
- lm-eval-harness judge reference (`vendor/lm-eval-harness-judge/`): Apache 2.0 — referenced but not imported; we reimplement so the rubric can be per-task.

**Benchmarks we sample tasks from.**

- HumanEval+ — EvalPlus, Apache 2.0.
- SWE-bench Verified — princeton-nlp, MIT.
- BigCodeBench-Hard — bigcode-project, Apache 2.0.
- custom-arch (5 tasks) — hand-written by Sanchit Monga, CC-BY-4.0.
- real-dev D1-D5 (20 tasks) — hand-written by Sanchit Monga with reference solutions and pytest, CC-BY-4.0.

**Models we evaluate.**

- gpt-5.5 (cloud) — OpenAI.
- gpt-5, gpt-5-mini — OpenAI (re-pricing scenarios only).
- devstral:24b (local) — Mistral AI via Ollama.
- qwen3:0.6b (router classifier, in scope for some strategies) — Alibaba.

**Judge.**

- claude-opus-4-7 (primary), claude-sonnet-4-6, gpt-5.5 (triple-judge audit) — Anthropic and OpenAI.

Full attribution table in [`../NOTICE.md`](../NOTICE.md).

---

*This article is published from the open-source [hybrid-coding-eval](https://github.com/RunanywhereAI/hybrid-coding-eval) repository. Issues and reproducibility questions: <https://github.com/RunanywhereAI/hybrid-coding-eval/issues>.*
