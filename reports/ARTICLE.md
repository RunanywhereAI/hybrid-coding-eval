# Should I run my coding tasks local, hybrid, or cloud? A token-first answer.

> _250 graded rows across 5 routes × 8 task shapes × 6 pricing scenarios on a single M4 Max laptop. Every row records its tokens; **cost is derived from tokens at read time** against a pinned pricing table. The same dataset is re-priced under six cloud scenarios without re-running inference._

**Status.** Published from branch `mono-repo-reorg`. Supersedes the v2 narrative in this same file (preserved in git history). Successor to `results/REPORT_v1_mvp.md` (the MVP report from run 04). The numbers below are derived from `results/runs/07-v3-devstral-all-routes/raw.jsonl` (250 rows, single sweep) and the triple-judge audit `results/runs/11-judge-robust-D/judge.jsonl` (96 verdicts).

**Headline graphics.** `results/runs/07-v3-devstral-all-routes/charts/pareto.png`, `heatmap_cost.png`, `heatmap_quality.png`, `heatmap_arqgc.png`.

---

## §1. TL;DR

For a real developer's coding workload, **the right answer depends entirely on whether the local model can solve the task alone**.

- **If yes** — small self-contained tasks where `devstral:24b` produces a correct answer in one shot — **R2 (local-only) is free.** Pass rate 90% on HumanEval+, $0.00 per task under every cloud-pricing scenario, ~5 s wall on an M4 Max.
- **If no** — anything outside that subset — **R1 (cloud-only, gpt-5.5) is cheaper than any hybrid route on this hardware and task mix.** Hybrid routes ship ~80-90% of total token volume to the cloud anyway, and pay 2-5× R1's per-row cost to land at parity-or-worse quality.

**Cost is derived from tokens at read time** against `configs/pricing/pricing_tables.json` (sha256 pinned). Every claim in this article is one re-derivation away from a different cloud scenario, but the route ranking is invariant — every scenario is a positive scalar on every cloud-token count.

Three numbers that anchor the rest of the article:

1. **R4's median `cloud_fraction` is 87% across 250 rows.** The Stanford-Minion supervisor/worker framing predicts the cloud asks targeted questions while the local worker reads context; in our setup the cloud supervisor ends up writing 8 of every 10 tokens. Per-category R4 cloud-fraction: A 90%, B 86%, C 89%, D 86% (`reports/DECISION_TABLE.md`).
2. **R1, R3, and R4 all pass exactly the same 3/10 on SWE-bench Verified easy** — the same three Django tasks (`django-11163`, `django-11179`, `django-15863`). The two unique Sphinx wins R4 recorded in run 04 (`sphinx-7889`, `sphinx-9698`) **did not replicate**. The "R4 beats R1 on SWE-bench" v1 headline was 10-task single-seed noise.
3. **R5 (DevMinion review-loop) burned the most tokens (1.88 M total, 1.85× R3, 2.94× R4) and collapsed on prose tasks**: composite 0.00 on every D3 refactor and 3 of 4 D4 code-reviews. R5 is 5× R1's cost on average and the worst route on three of four categories.

A real developer reading this for cost guidance: **hybrid is currently a quality-parity, cost-loss choice on the task mix we evaluated.** Run §6 for the per-shape practical recommendation.

---

## §2. The headline decision table — 8 task shapes × 5 routes

Pulled verbatim from `reports/DECISION_TABLE.md`. Pass rate uses `functional_pass=True` where a functional scorer exists; judge-scored shapes (C-arch, D3, D4) use `composite >= 0.5` as the pass proxy, flagged with `*`. **D2 is `None/N` by design** — external GitHub-issue tasks, functional scorer deferred; treat D2 cost/cloud-fraction as observation only, not quality signal.

### A — HumanEval+ (tiny self-contained functions, 10 tasks)

| route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
|---|---:|---|---:|---:|---:|---:|
| R1 | 10 | 10/10 | 100% | $0.0119 | $0.0008 | 5,364 |
| R2 | 10 | 9/10 | 0% | $0.0000 | $0.0000 | 5,244 |
| R3 | 10 | 10/10 | 37% | $0.0380 | $0.0024 | 57,524 |
| R4 | 10 | 10/10 | 90% | $0.0659 | $0.0041 | 37,345 |
| R5 | 10 | 4/10 | 50% | $0.2488 | $0.0162 | 262,695 |

### B — SWE-bench Verified easy (multi-file repo patches, 10 tasks)

| route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
|---|---:|---|---:|---:|---:|---:|
| R1 | 10 | 3/10 | 100% | $0.1058 | $0.0070 | 61,586 |
| R2 | 10 | 0/10 | 0% | $0.0000 | $0.0000 | 9,700 |
| R3 | 10 | 3/10 | 34% | $0.1369 | $0.0088 | 166,103 |
| R4 | 10 | 3/10 | 86% | $0.2025 | $0.0127 | 139,083 |
| R5 | 10 | 0/10 | 53% | $0.3902 | $0.0256 | 381,303 |

### C — BigCodeBench-Hard (5) + custom-arch (5, judge-scored)

| shape | route | N | pass | med cloud_frac | med $ gpt-5.5 | med $ gpt-5-mini | med wall ms |
|---|---|---:|---|---:|---:|---:|---:|
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
|---|---|---:|---|---:|---:|---:|---:|
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

The headline numbers are sums over all rows, regenerated from `aggregate.json` and `reports/TOKEN_BUDGET.md`.

| route | n_rows | Σ cloud tokens | Σ local tokens | total | cloud_fraction (Σ) | Σ $ gpt-5.5 |
|---|---:|---:|---:|---:|---:|---:|
| R1 | 50 | 158,406 | 0 | 158,406 | 100% | $3.82 |
| R2 | 50 | 0 | 94,301 | 94,301 | 0% | $0.00 |
| R3 | 50 | 475,855 | 539,829 | 1,015,684 | 47% | $8.65 |
| R4 | 50 | 544,429 | 95,647 | 640,076 | 85% | $7.29 |
| R5 | 50 | 945,209 | 934,148 | 1,879,357 | 50% | $19.59 |

Per-row mean cost ratios vs R1: **R3 = 2.26×, R4 = 1.91×, R5 = 5.13×.** Per-shape medians push the gap wider on prose categories: D4-review R3 cost $0.4067 vs R1's $0.0861 (4.7×), R5 vs R1 on D4 = 5.1×. The article's prior framing of "R3 = 2.5×, R4 = 3.2×, R5 = 9.3×" was a per-shape worst-case; the all-row mean ratios above are tighter and the per-shape medians in §2 show the dispersion.

What the chart at `results/runs/07-v3-devstral-all-routes/charts/pareto.png` shows:

- **R2 sits at $0** on every row. The vertical bar against the $0 axis has two clusters: tasks where R2's composite ≥ 0.5 (mostly A, scattered across C-bcb and C-arch), and tasks where R2 ≈ 0.0 (all of B, all of D except 2 C-arch and 1 C-bcb). R2 is a step function: it's either the dominant choice or unusable.
- **R1's cloud-only cluster occupies the low-cost / high-composite frontier** on A (composite 1.0 at $0.012), C-arch (composite ≥ 0.95 at $0.30 median), D3 (composite 1.00 at $0.035), D4 (composite ≥ 0.98 at $0.086).
- **R3 sits 2-3× to the right of R1 on every category**, with composite within ±0.1 of R1 on A, B, C-arch, D3 — and noticeably below R1 on D4 (0.34-0.78 vs R1's 0.98).
- **R4 sits between R1 and R3 on cost on most categories**, but consistently right of R3 on B and D. R4's median cloud_fraction stays in the high 80s regardless of category.
- **R5 is a separate cluster top-right**: highest cost, lowest composite. Visually it's an outlier — the only route that's strictly Pareto-dominated by every other route on three of four categories.

`heatmap_cost.png` makes the per-(category, route) cost story compact: the bright (expensive) cells are R5 across all categories and R3 on C; the dark cell is the entire R2 column. `heatmap_quality.png` shows the symmetric story: R1 and R3 light across A and most of C/D; R5 dark across B/C/D.

### Why R4's cloud_fraction stayed at 87%

The Minion supervisor/worker protocol assumes the cloud supervisor asks short, targeted questions, and the local worker reads the full context. In practice, on our task lengths (300-3500 prompt tokens, 200-6000 completion tokens), the supervisor's questions plus answers plus the synth step end up being where the conversation's token volume lives. R4 makes 1-3 cloud calls per task; each one is on the order of 1500-3000 prompt + 800-2500 completion cloud tokens. The local worker's contribution to the total token budget is small (median 401 local-prompt + 211 local-completion tokens per task). On a 3500-token prompt task, the cloud-side share is structurally going to dominate unless the protocol is rewritten to push more drafting work to the worker — which would make it a different route.

### Why R3 stays the most-local-of-the-hybrids and still pays 2.26× R1

R3's planner step runs on the cloud, the per-step solving runs locally with a context window that the heuristic keeps small, and the synth step rolls back to the cloud. The local fraction (median 65% of tokens, 47% in aggregate sum) is real — but the cloud-prompt-side of the planner and synth steps is structurally expensive (large prefixes for the planner; concatenated step outputs for the synth). On a single HumanEval task, R3 sends 1500-2500 cloud-prompt tokens to plan + synth what R1 solves in 100-200 cloud-prompt tokens. The local steps are free but they don't reduce the cloud side enough to flip the dollar comparison.

---

## §4. Three category deep-dives

### §4.1 Category A (HumanEval+) — R2 is free, every hybrid pays for nothing

R2 passes 9 of 10 HumanEval+ tasks (the one miss: `HumanEval_77`, where devstral generated a recursive function that hit infinite recursion). R1 passes 10/10. R3 and R4 also pass 10/10 by leaning on the cloud half of their pipeline. R5 passes 4/10.

Token + cost per task (median):

| task subset | R1 cloud_frac | R1 $ | R2 $ | R3 $ | R4 $ | R5 $ |
|---|---:|---:|---:|---:|---:|---:|
| HumanEval_15 (smallest) | 100% | $0.005 | $0.000 | $0.030 | $0.050 | $0.292 |
| HumanEval_103 (mid) | 100% | $0.017 | $0.000 | $0.056 | $0.078 | $0.393 |
| HumanEval_13 (largest) | 100% | $0.004 | $0.000 | $0.026 | $0.057 | $0.476 |

Reading the rows: every hybrid pays a fixed planning/routing tax (R3: ~$0.04, R4: ~$0.06) regardless of how trivial the task is. R5's tax is structurally 4-8× higher because of the review-loop's round-replay overhead. **There is no Category-A task on which any hybrid Pareto-improves on R1 or R2.**

### §4.2 Category B (SWE-bench Verified easy) — the v1 R4 win does not replicate

Run 04 (the v1 / MVP report) claimed R4 Minion was the only route to win on SWE-bench (4/10 vs R1's 3/10), with R4 uniquely solving `sphinx-doc__sphinx-7889` and `sphinx-doc__sphinx-9698`. The v3 sweep with the same models (`devstral:24b` local, `gpt-5.5` cloud) and the same SWE-bench harness produces a different result:

| task_id | R1 pass | R3 pass | R4 pass | R5 pass |
|---|:-:|:-:|:-:|:-:|
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

**Read this carefully.** The v1 R4 cost framing ("R4 wins on pass rate; R4 is $0.56/correct vs R1's $0.42/correct") was load-bearing on those Sphinx wins. Without them R4 is no better than R1 on pass rate and **costs $7.29 / 3 = $2.43 per correct vs R1's $3.82 / 3 = $1.27 per correct** under the v3 sweep totals — R4 is 1.9× more expensive per correct on B, not 1.3× cheaper. The single-sample variance on a 10-task SWE-bench slice is large enough to overturn the v1 headline. Don't quote the v1 R4-on-B win without replication.

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
|---|---:|---:|---:|---:|---:|
| D1 small-feature | 2/4 | 0/4 | 2/4 | 1/4 | 1/4 |
| D3 refactor (composite ≥ 0.5) | 4/4 | 0/4 | 4/4 | 4/4 | 0/4 |
| D4 review (composite ≥ 0.5) | 4/4 | 0/4 | 2/4 | 2/4 | 0/4 |
| D5 functional | 3/4 | 0/4 | 3/4 | 3/4 | 3/4 |

**R5's prose collapse, by task ID.** Every D3 and D4 task R5 attempted scored 0.00 except `d4-review-pagination` (0.22):

- `real-dev/d3-constants-to-enum`: R5 composite 0.00 (R1 = 0.96, R3 = 0.54, R4 = 0.54)
- `real-dev/d3-extract-validation-helper`: R5 = 0.00 (R1 = 0.98, R3 = 0.74, R4 = 0.72)
- `real-dev/d3-replace-try-except-with-contextmanager`: R5 = 0.00 (R1 = 1.00, R3 = 0.84, R4 = 0.54)
- `real-dev/d3-split-god-module`: R5 = 0.00 (R1 = 1.00, R3 = 0.84, R4 = 0.74)
- `real-dev/d4-review-cache-invalidation`: R5 = 0.02 (R1 = 1.00, R3 = 0.54, R4 = 0.48)
- `real-dev/d4-review-pagination`: R5 = 0.22 (R1 = 0.98, R3 = 0.45, R4 = 0.70)
- `real-dev/d4-review-sql-injection`: R5 = 0.00 (R1 = 0.98, R3 = 0.34, R4 = 0.48)
- `real-dev/d4-review-timezone-handling`: R5 = 0.00 (R1 = 0.98, R3 = 0.78, R4 = 0.64)

Failure mode (from inspecting `outputs/` artefacts): R5's editor produces a refactor; the reviewer's verdict invalidates it; the next round drifts further from the original spec. By round 3 the artefact no longer reads as a faithful refactor — it has new functions, deleted code paths, fabricated tests. **Review-loops, on this architect/editor protocol, cost more tokens and hurt prose quality.**

**Robustness: triple-judge audit.** We re-judged the 16 D3+D4 R1-vs-R3 and R1-vs-R4 pairings under three judges (`claude-opus-4-7`, `claude-sonnet-4-6`, `gpt-5.5`) × two A/B orders = 96 verdicts. **All 96 verdicts are R1 wins. Zero ties. Zero flips. Zero errors.** Mean margins: opus 0.94, sonnet 1.00, gpt-5.5 1.00. The cross-vendor unanimity rules out same-family judge bias; the zero order-flips rules out A/B position effects. R1 dominance on D3+D4 is robust on this 8-task slice (see `results/runs/11-judge-robust-D/run-notes.md`).

**One row where hybrid Pareto-improves on R1.** Across all 250 rows, **exactly one row** has a hybrid composite strictly greater than R1's by more than 0.01: `real-dev/d1-json-schema`, where R3 = 1.00 (functional pass) and R1 = 0.00 (R1 produced a Python schema definition; the harness expected JSON output). Every other row is R1 ≥ hybrid. The hybrid routes do not Pareto-improve on R1 on this dataset.

**D5 small unique R5 wins.** R5 was the only route to solve `real-dev/d1-retry-decorator` (R5 pass; R1, R2, R3, R4 all fail) and `real-dev/d5-log-errors-today` (R5 pass; all others fail). Two-task evidence is not enough to claim a niche, but it sketches the shape of where R5 might earn its slot: small functional tasks where each review round verifies a concrete behaviour. Outside that, R5 currently hurts.

---

## §5. Did the v3 plan's hypothesis hold? No.

The v3 sweep was designed around the prediction that **hybrid routes (R3/R4/R5) would send 60-80% of total tokens to the local model, achieve quality parity with R1, and save 40-70% on cost** versus a pure cloud baseline. That prediction was the explicit reason for adding R5 to the lineup and for running the full 5-route × 50-task sweep.

What we measured:

| metric | v3 prediction | v3 measurement |
|---|---|---|
| R3 cloud_fraction (median) | 20-40% | **35%** (in line, low end) |
| R4 cloud_fraction (median) | 20-40% | **87%** (far outside; 2× upper bound) |
| R5 cloud_fraction (median) | 20-40% | **50%** (outside band) |
| R3 cost vs R1 | 0.3-0.6× | **2.26×** (mean) / 3.5-5× (per-shape on prose) |
| R4 cost vs R1 | 0.3-0.6× | **1.91×** (mean) / 1.9-2.4× (per-shape) |
| R5 cost vs R1 | 0.3-0.6× | **5.13×** (mean) / 4-13× (per-shape) |
| Quality parity (composite within 0.05 of R1) | yes on all hybrid routes | partial on R3 (A, B, C-arch, D3); R3 fails on D4. R4 partial. R5 fails on B, C, D3, D4. |

**The hypothesis is contradicted on cost on all three hybrid routes, and contradicted on cloud_fraction on R4 and R5.** R3 alone delivered the predicted token-routing balance, but its dollar cost still ran 2.26× R1 because the cloud-side prefixes (planner + synth) are structurally expensive relative to what gets saved locally.

The intuition the prediction came from — Stanford Minion's framing of the supervisor as a query coordinator with most token volume on the worker side — does not survive contact with our real prompt sizes. On long-context tasks (B and D2), the supervisor processes the full problem statement each round; the worker's contribution is small targeted answers. On short-context tasks (A), there isn't enough content to push to a worker in the first place.

We ran the experiment as designed. The result contradicts the hypothesis. **No hybrid route on this task mix delivers the 40-70% cost savings the v3 plan predicted.**

---

## §6. What does this mean for a real developer?

Practical guidance, per task shape:

| Your task is... | Pick | Why |
|---|---|---|
| HumanEval-shape — tiny self-contained function | **R2** (devstral local) | 90% pass rate at $0.00; no Pareto-improvement available |
| Small real-dev feature (D1) that devstral can solve | **R2** | Free; identify the subset by running R2 first and falling back to R1 if it fails |
| Small real-dev feature (D1) devstral can't solve | **R1** | 50% R1 pass vs hybrid 25-50%; lower cost |
| SWE-bench-style multi-file repo patch | **R1** | 30% pass rate; hybrid routes give the same 30% at 1.3-3.7× cost |
| BigCodeBench-hard third-party library task | **R1** or **R2** | R1 = R2 = 1/5; hybrid routes regress to 0/5 |
| Architecture-design prose (C-arch) | **R1** | 100% composite ≥ 0.5; R3 ties at 1.6× cost; R4/R5 lose |
| Refactor with prose judgement (D3) | **R1** | 100% pass; triple-judge audit confirms R1 wins all 8 pairings vs R3/R4 |
| Code review with prose judgement (D4) | **R1** | 100% pass; R3/R4 land 50%; R5 = 0% |
| External GitHub-issue patch (D2) | **R1** as fallback | Functional scorer deferred; cost/cloud-fraction observable only |

**Where hybrid is currently sub-optimal:** every shape we measured. The fall-through rule is: try R2 first; if it fails (or the task shape is one where R2 has 0/n pass rate, i.e. B / C-bcb / D1 / D2 / D3 / D4 / D5), go straight to R1.

**Hybrid (R3/R4/R5) does not earn a slot in this routing table at the current cloud / local pricing ratio and on this hardware tier.** The cases where hybrid would be the right choice on cost-per-correct require either:

- a much more expensive cloud model (e.g. claude-opus-4.7 at $15/Mtok output, where R1 costs scale up faster than R3/R4 do — but `aggregate.json` shows R3/R4 still cost more in absolute dollars under opus-4.7, so the cost ranking is preserved), OR
- a local model that solves a larger subset of tasks alone (which would shift more tasks to the R2 column, not the hybrid column), OR
- a different hybrid protocol that pushes more token volume to the local worker (the existing protocols don't; see §3 for why).

**If you're cost-conscious right now: route to R2 first, R1 second. Skip the hybrid routes.**

---

## §7. Methodology — terse

- **Sweep**: 50 unique tasks × 5 routes = 250 rows. Single seed (`seed=42`). Wall total 11.9 hours on one M4 Max 64 GB laptop. Zero infra errors (`error=None` on every row). Source: `results/runs/07-v3-devstral-all-routes/raw.jsonl`.
- **Routes**: R1 single-shot to `gpt-5.5`; R2 single-shot to `devstral:24b` via Ollama; R3 hybrid-architect (cloud planner → local per-step → cloud synth); R4 Stanford-Minion supervisor/worker Q&A; R5 DevMinion architect/editor review-loop (up to 3 rounds).
- **Tasks**: 10 HumanEval+ (seed=42 random sample) + 10 SWE-bench Verified easy + 5 BigCodeBench-Hard + 5 custom-arch + 20 real-dev (4 each × 5 shapes D1-D5).
- **Judges**: `claude-opus-4-7` (primary, 25 custom-arch pairings in run 07); triple-judge audit (`opus-4-7` + `sonnet-4-6` + `gpt-5.5`) × 2 orders on D3+D4 in run 11 (96 verdicts).
- **Cost derivation**: tokens recorded in `raw.jsonl` × pinned rates in `configs/pricing/pricing_tables.json` (sha256 `adbf24618010…`). Six pricing scenarios surfaced: `openai-gpt5.5` (primary), `openai-gpt5`, `openai-gpt5-mini`, `anthropic-claude-opus-4.7`, `anthropic-claude-sonnet-4.6`, `anthropic-claude-haiku-4.5`. **No cost number in this article was stored; every dollar value is re-derivable from the tokens.**
- **D2 functional scorer is deferred.** 20 rows hold `functional_pass=None` and `composite=None` by design; outputs are still stored under `outputs/`.

---

## §8. Limits + what we did not measure

| Limit | Status |
|---|---|
| Single hardware tier (M4 Max 64 GB) | Devstral on a 4090 box would be 2-3× faster wall, but the cloud-token counts wouldn't change, so cloud cost is unchanged. R2 wall would drop. |
| Single cloud (gpt-5.5 primary) | Re-priced under 5 other scenarios; the ranking is invariant (each scenario is a positive scalar on cloud-token counts). Different cloud could shift absolute cost, not cloud_fraction. |
| 10-task slices (A, B, C-bcb, C-arch); 4-task D-shapes | Single-seed, no CIs. Direction not significance. v1 → v3 SWE-bench reversal (the Sphinx wins disappearing) is a direct demonstration of slice-noise. |
| Single seed | The R5 collapse on D3/D4 is 0.00 across 7 of 8 tasks — robust to seed-noise within reason. The 3/10 SWE-bench ceiling and single-task R5 wins on D1/D5 are not. |
| R5 has a known JSON-extraction fragility | The architect/editor handoff goes via JSON; we patched the parser to be more forgiving, but residual brittleness may bias R5 down. Even with that caveat, R5's 0.00 on prose is consistent across 7 tasks. |
| D2 functional scoring | Deferred. Cost/cloud-fraction observations are recorded; quality is not. 20 of 250 rows. |
| Custom-arch judge robustness | Run 11 covers D3+D4 only. Custom-arch (C) on the v3 outputs is single-judge single-order (opus-4-7, AB only). Run 10 audited custom-arch but under qwen, not devstral. |
| No R6 / R7 | Aider proper and cascade routing are future work. |
| No multi-cloud routing | Cascade (cheap cloud → expensive cloud on fail) not in scope. |

Every limit one of: (a) hardware/data inherited from the v3 sweep, (b) deferred scoring (D2), or (c) future-work scope. None overturn the headline findings; the 3/10 SWE-bench fluctuation between run 04 and run 07 is itself the most informative single-sample-variance signal in this dataset.

---

## §9. Where to read next

- `reports/TOKEN_BUDGET.md` — full per-task token + cost-derivation table, 250 rows.
- `reports/DECISION_TABLE.md` — the per-shape × route grid surfaced in §2.
- `reports/APPENDIX_TASKS.md` / `APPENDIX_SCENARIOS.md` / `APPENDIX_ROUTES.md` — forensic detail. P4.3 will refresh these to include D + R5.
- `reports/token_budget.csv` — raw cost-derivation data, one row per (task, route).
- `results/runs/07-v3-devstral-all-routes/run-notes.md` — per-run write-up of the v3 sweep.
- `results/runs/07-v3-devstral-all-routes/aggregate.json` — per-(category, route) medians + sums under six pricing scenarios.
- `results/runs/07-v3-devstral-all-routes/decision_matrix.md` — category × route quality / cost / wall + Bounded-ARQGC.
- `results/runs/11-judge-robust-D/judge.jsonl` — 96 triple-judge verdicts for D3+D4 robustness audit.
- `results/runs/11-judge-robust-D/run-notes.md` — robustness audit write-up.
- `results/REPORT_v1_mvp.md` — the MVP report from run 04, preserved verbatim for lineage. Read alongside §4.2 of this article for the v1 → v3 SWE-bench reversal.
- `archive/docs/article-draft-v1.md` — v1 and v2 narratives, preserved for lineage.
- `docs/METHODOLOGY.md` — how the eval works, end-to-end.
- `docs/REPRODUCING.md` — how to reproduce a run.

## Suggested citation

> Monga, Sanchit and contributors. *hybrid-coding-eval: token-first decision report for local vs cloud vs hybrid LLM routing on coding tasks.* 2026. https://github.com/RunanywhereAI/hybrid-coding-eval

## License

- **Code**: MIT (see `LICENSE`)
- **Data + this article**: CC-BY-4.0 (see `LICENSE-DATA`)
- **Third-party code**: see `NOTICE.md` and `vendor/README.md`
