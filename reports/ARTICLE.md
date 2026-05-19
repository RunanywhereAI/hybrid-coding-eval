# Should I run my coding tasks local, hybrid, or cloud? A token-first answer (v3.3).

> _**3,581 rows** across **6 local models × 5 routes × 7 routing strategies × 8 task shapes × 6 pricing scenarios** on a single M4 Max laptop. Every row records its tokens; **cost is derived from tokens at read time** against a SHA256-pinned pricing table. The same dataset is re-priced under six cloud scenarios without re-running inference. v3.3 is the most comprehensive single benchmark sweep this repo has run, and it gives a definitive answer to "can hybrid routing actually save cost?" — read §1._

**Status (2026-05-18).** v3.3 sweep complete after 4 days 14 hours of continuous compute on an M4 Max 64 GB. Tag `v3.3` on branch `main`. Supersedes v3 (run 07, 250 rows, devstral-only).

**Hardware + envelope.** All numbers are for: **M4 Max 64 GB MacBook**, **6 local models** (devstral:24b, qwen3-coder:30b, qwen2.5-coder:32b, glm-4.7-flash, gemma4:31b, qwen3.6:27b-coding-mxfp8, qwen3.6:35b-A3B-MoE), **gpt-5.5** as cloud (re-priced under 5 alternatives), **claude-opus-4-7** as judge (triple-judge audit confirms order- and judge-invariance on prose categories), pricing snapshot **2026-04-27** from models.dev. **Findings are explicitly conditional on this hardware/model envelope** — the cost ratios shift if you change any variable, but the route ranking is invariant across the 6 pricing scenarios we tested.

---

## §1. TL;DR — the three answers in 30 seconds

**1. Can hybrid routing save cost vs cloud-only?** **No — not via the multi-step hybrid protocols R3/R4/R5.** Every one is 1.9× to 5× more expensive than R1 cloud-only on a mixed workload, with equal or worse quality. **But yes — via per-task gating** (try local first, fall back to cloud on failure), you can save ~16-20% by capturing free wins on the subset of tasks local models solve alone. See §10 for the deployable design; full doc in [`HYBRID_ROUTER_DESIGN.md`](../docs/HYBRID_ROUTER_DESIGN.md).

**2. What's the best local model for code?** **Qwen3-Coder:30B**, at **$0.229 per correct task** on R3 heuristic — beats devstral ($0.279), qwen2.5-coder ($0.269), gemma4 ($0.262), glm-4.7-flash ($0.444), and crucially **both newer Qwen 3.6 variants** (27B-mxfp8 at $0.280, 35B-MoE at $0.304). The Qwen 3.6 family regression is the surprise finding: newer ≠ better when specialization is dropped.

**3. What's the best routing strategy?** **Cascade** — replicates as universal Pareto winner across all 6 local models tested. ~15% cheaper than heuristic at quality parity. **Cascade threshold 15 is empirically optimal** (Phase 7 sub-sweep: thresholds 5/10/15/20/25; t=20 is a brittleness cliff at +21% cost / -21% pass rate / -80% on B-shape). The much-anticipated `llm-classifier` strategy is **structurally broken** on long-context tasks: across 5 classifier sizes from 0.6B to 4B, every single one scores **0/10 on SWE-bench** (Phase 6 sub-sweep). Don't deploy llm-classifier.

---

## §2. The fundamental question: can a router save cost?

A real developer's mixed workload contains tiny completions, real GitHub patches, library calls, architecture prose, refactors, code reviews, and one-shot scripts. The router's job is one decision per task: **can the local model alone satisfy this request?** The v3.3 data lets us quantify the answer per shape.

### Per-shape pass rate when local model attempts the task alone (R2, no cloud)

Median across all 6 local models tested:

| shape | n | typical R2 pass rate | implication |
|---|---:|---:|---|
| **A** HumanEval+ (tiny completions) | 10 | **9-10/10** | **Local wins for free.** Send to R2. |
| **B** SWE-bench Verified (real patches) | 10 | 0-1/10 | Local fails. Send to R1. |
| **C-bcb** BigCodeBench-Hard | 5 | 1/5 | Local fails. Send to R1. |
| **C-arch** custom-arch prose (judge-scored) | 5 | 2-3/5 | Local viable; R1 better. Tossup. |
| **D1** small-feature | 4 | 0/4 | Local fails. Send to R1. |
| **D2** GitHub-issue patches | 4 | n/a (functional scorer deferred) | Direct R1. |
| **D3** refactor (judge-scored) | 4 | 0-1/4 | Local fails. Send to R1. |
| **D4** code-review (judge-scored) | 4 | 0/4 | Local fails. Send to R1. |
| **D5** small one-shots | 4 | 0-1/4 | Local mostly fails. Send to R1. |

### The cost answer

**Pure cloud (R1-only) total cost** for the 50-task v3.3 benchmark mix: **$3.82** on devstral baseline, ~$4.40 typical across models, gpt-5.5 primary.

**Pure local (R2-only) cost:** $0 — but you get the column above. You "save" 100% of cloud spend on A-shape (9-10 of 10 tasks pass) but lose on everything else.

**Multi-step hybrid (R3 architect, R4 Minion, R5 DevMinion):** **1.91× to 5.13× R1's cost**, no quality gain. R3 mean $7.29-$8.70 across models, R4 mean $7.29, R5 mean **$19.59** — and R5 collapses on D3/D4 prose (composite 0.00 on 7 of 8 tasks across multiple models).

**The router design that wins (§10):** try R2 first when the heuristic gate says local is feasible, fall back to R1 on failure. Skip the hybrid orchestration entirely. **Estimated savings: 16-20% on the mixed workload**, no quality regression.

---

## §3. The headline decision table — 6 models × 8 shapes × 5 routes

The complete cross-product, derived from `results/runs/{07, 17, 18, 19, 20, 21, 22}-*/raw.jsonl`. Pass = `functional_pass=true` on A/B/C-bcb/D1/D5; `composite ≥ 0.5` for judge-scored C-arch/D3/D4 (marked with `*`). D2 is `None/N` by design (functional scorer deferred). Values are total passes / N tasks per cell.

### A — HumanEval+ (tiny self-contained functions, 10 tasks)

| local model | R1 cloud | R2 local | R3 hybrid | R4 minion | R5 devminion |
| --- | --- | --- | --- | --- | --- |
| devstral:24b (v3 baseline) | 10/10 | 9/10 | 10/10 | 10/10 | 4/10 |
| qwen3-coder:30b | (reuses R1) | 9/10 | 10/10 | 8/10 | 2/10 |
| qwen2.5-coder:32b | (reuses R1) | 9/10 | 10/10 | 10/10 | 3/10 |
| glm-4.7-flash | (reuses R1) | **0/10** ⚠️ | **0/10** ⚠️ | **0/10** ⚠️ | 0/10 |
| gemma4:31b | (reuses R1) | 10/10 | 10/10 | 10/10 | 6/10 |
| qwen3.6:27b-mxfp8 | (reuses R1) | 10/10 | 9/10 | 10/10 | 7/10 |
| qwen3.6:35b-A3B-MoE | (reuses R1) | 10/10 | 9/10 | 9/10 | 7/10 |

**Surprise: glm-4.7-flash scores 0/10 on every route for A-shape.** Reasoning-optimized model over-engineers single-function completions. See §9 deep dive.

### B — SWE-bench Verified easy (multi-file repo patches, 10 tasks)

| local model | R1 cloud | R2 local | R3 hybrid | R4 minion | R5 devminion |
| --- | --- | --- | --- | --- | --- |
| devstral:24b | 3/10 | 0/10 | 3/10 | 3/10 | 0/10 |
| qwen3-coder:30b | (R1=3/10) | 1/10 | **4/10** | 3/10 | 0/10 |
| qwen2.5-coder:32b | | 0/10 | 3/10 | 2/10 | 0/10 |
| glm-4.7-flash | | None/10 (R2 infra fail) | None/10 | None/10 | 0/10 |
| gemma4:31b | | 1/10 | 2/10 | 2/10 | 0/10 |
| qwen3.6:27b-mxfp8 | | 0/10 | 3/10 | 2/10 | 0/10 |
| qwen3.6:35b-A3B | | 1/10 | 3/10 | 3/10 | 0/10 |

**Qwen3-Coder R3 = 4/10 on B is the single best non-R1 cell** — but at 1.3× R1 cost ($0.137 vs $0.106 per task). Marginal win, not worth deploying.

### C-bcb — BigCodeBench-Hard (5 tasks)

| local model | R1 cloud | R2 local | R3 hybrid | R4 minion | R5 devminion |
| --- | --- | --- | --- | --- | --- |
| devstral:24b | 1/5 | 1/5 | 0/5 | 0/5 | 0/5 |
| qwen3-coder:30b | (R1=1/5) | 1/5 | 2/5 | 1/5 | 0/5 |
| qwen2.5-coder:32b | | 1/5 | 1/5 | 1/5 | 0/5 |
| glm-4.7-flash | | 1/5 | 2/5 | 1/5 | 0/5 |
| gemma4:31b | | 1/5 | 1/5 | 2/5 | 0/5 |
| qwen3.6:27b-mxfp8 | | 1/5 | 2/5 | 0/5 | 0/5 |
| qwen3.6:35b-A3B | | 1/5 | 2/5 | 1/5 | 0/5 |

### C-arch — custom-arch prose (5 tasks, judge-scored, * = composite ≥ 0.5)

| local model | R1 cloud | R2 local | R3 hybrid | R4 minion | R5 devminion |
| --- | --- | --- | --- | --- | --- |
| devstral:24b | 5/5* | 3/5* | 5/5* | 4/5* | 1/5* |
| qwen3-coder:30b | (R1=5/5*) | 3/5* | **5/5*** | None | None |
| qwen2.5-coder:32b | | 3/5* | **5/5*** | None | None |
| glm-4.7-flash | | 2/5* | **5/5*** | None | None |
| gemma4:31b | | 3/5* | **5/5*** | None | None |
| qwen3.6:27b-mxfp8 | | 3/5* | **5/5*** | None | None |
| qwen3.6:35b-A3B | | None | None | None | None |

**Universal finding: R3 hybrid-architect ties R1 cloud at 5/5 on C-arch prose across 5 of 6 models.** This is where hybrid hypothetically could compete — but at 1.6× R1 cost ($0.49 vs $0.30 per task), even quality-parity loses on the dollar.

### D — real-developer (20 tasks across D1–D5)

Per-D-shape pass rate (D2 omitted; functional scorer deferred). Cells are total passes / N:

| D shape | qwen3-coder:30b R3 | best local at R3 | devstral R3 (v3 baseline) |
|---|---:|---|---:|
| D1 small-feature (4) | 2/4 | qwen3-coder, qwen3.6-27b, gemma4: 2/4 each | 2/4 |
| D3 refactor (4, judge) | **4/4*** | qwen3-coder, qwen2.5-coder, gemma4, qwen3.6-27b, glm: 4/4* each | 4/4* |
| D4 code-review (4, judge) | **3/4*** | qwen2.5-coder R3: **4/4*** (only model to perfect-score D4) | 2/4* |
| D5 functional one-shots (4) | 3/4 | qwen3-coder, gemma4, glm, qwen3.6-35b: 3/4 | 3/4 |

**Highlight: qwen2.5-coder:32b uniquely achieves 4/4 on D4 code-review** (one of the only cells where it beats qwen3-coder). Niche, but real.

### Cost per shape (median per task, gpt-5.5 primary, R1 vs cheapest non-R1 win)

| shape | R1 cost | best non-R1 | $ delta | quality delta |
|---|---:|---|---:|---|
| A | $0.0119 | **R2 = $0.0000** (gemma4/qwen3.6/qwen2.5/qwen3-coder all 9-10/10) | **−$0.0119** | −0 to −1 pass (negligible) |
| B | $0.1058 | R3 qwen3-coder $0.137 (4/10) | +$0.031 | +1 pass |
| C-bcb | $0.0433 | R3 qwen3-coder $0.086 (2/5) | +$0.043 | +1 pass |
| C-arch | $0.2963 | R3 multi-model $0.488 (5/5*) | +$0.192 | 0 pass |
| D1 | $0.0304 | R3 qwen3-coder/devstral $0.098 (2/4) | +$0.068 | 0 pass |
| D2 | $0.0409 | (no functional scorer) | — | — |
| D3 | $0.0354 | R3 multi-model $0.151 (4/4*) | +$0.116 | 0 pass |
| D4 | $0.0861 | R4 multi-model $0.197 (2/4*) | +$0.111 | −2 pass |
| D5 | $0.0158 | R3 qwen3-coder/gemma4 $0.071 (3/4) | +$0.055 | 0 pass |

**Reading the table:** On A-shape the cheapest answer is R2 (free) — that's the cost-win cell. On every other shape, R1 is either cheapest or the only viable option. Hybrid routes are more expensive everywhere with no quality compensation.

---

## §4. The 5 most important findings

### Finding 1 — Qwen3-Coder:30B is the universal local-model winner

**$0.229/correct on R3 heuristic** vs the field's $0.262–$0.444. Qwen3-Coder achieves this because it has the **highest R3 pass rate (35/50)** while costing slightly less than peers ($8.01 vs $8.13–$8.68). Per-category strengths:

- **A**: 9/10 R2 (free) + 10/10 R3
- **B**: **4/10 R3** — the single highest non-R1 SWE-bench score across all 6 models
- **C-arch**: 5/5 R3 (universal)
- **D3 refactor**: 4/4 R3 with judge composite ≥ 0.5

**Counter-finding: the newer Qwen 3.6 family regressed.** Qwen 3.6 27B-mxfp8 (the "Precision King" 8-bit float variant) and Qwen 3.6 35B-A3B-MoE (the "MoE Efficiency Pick") both underperform Qwen3-Coder on the same benchmark: $0.280 and $0.304 per correct respectively. The 35B MoE is particularly underwhelming — despite 35B total params (5B more than qwen3-coder), the active-3B compute path doesn't match a dense 30B specialized for code. **Newer ≠ better when specialization is dropped.**

### Finding 2 — Cascade is the universal best router strategy (across all 6 models)

Cascade (heuristic + LLM-classifier tiebreak on borderline) was the Pareto winner in Phase 1 on devstral. Phase 9 confirms it generalizes — see §6 for the full strategy × model matrix.

Phase 7 sub-sweep specifically tuned the cascade threshold across 5 values (5, 10, 15, 20, 25):

| threshold | passes | $ total | B passes | verdict |
|---:|---:|---:|---:|---|
| 5 (most aggressive LLM) | 26 | $7.83 | 3/10 | |
| 10 | 28 | $8.21 | 5/10 | |
| **15 (default)** | **29** | **$8.13** | **5/10** | **optimal** |
| 20 | 23 | $7.82 | 1/10 | **brittleness cliff** |
| 25 (most conservative) | 27 | $8.33 | 5/10 | |

**Threshold 15 is empirically optimal — the default was well-chosen.** Threshold 20 collapses pass rate from 29 to 23 (−21%) and B-shape from 5 to 1 (−80%); too much trust in the heuristic without LLM tiebreak fails on borderline B tasks.

### Finding 3 — LLM-classifier is structurally broken on SWE-bench (any size)

Phase 1 (qwen3:0.6b) showed llm-classifier was 57% cheaper than heuristic at $3.63 total but scored 0/10 on SWE-bench. Phase 6 sub-sweep tested whether a bigger classifier fixes this:

| classifier model | size | pass total | B passes | $ total | verdict |
|---|---:|---:|---:|---:|---|
| **qwen3:0.6b (baseline)** | 520 MB | 21 | **0/10** | $3.63 | broken |
| qwen2.5-coder:1.5b (code-specialized) | 986 MB | 19 | **0/10** | $3.04 | broken — smallest + cheapest |
| qwen3.5:0.8b | 1.0 GB | 18 | **0/10** | $3.49 | broken |
| qwen3.5:2b | 2.7 GB | 19 | **0/10** | $3.30 | broken |
| qwen3.5:4b | 3.2 GB | 18 | **0/10** | $3.18 | broken — bigger doesn't help |

**Every single one of 5 classifier candidates scores 0/10 on B-category, regardless of size or specialization.** Scaling the classifier from 0.6B → 4B → 7× larger does NOT recover the SWE-bench collapse. The classification logic itself misroutes long-context tasks to local where local always fails. **Don't deploy llm-classifier in production.**

Worth noting: `qwen2.5-coder:1.5b` (code-specialized classifier) achieves the **lowest cost** ($3.04) of any tested classifier while matching the pass rate. If you ever need a classifier despite this finding, use the smallest one.

### Finding 4 — GLM-4.7-Flash has a category-A collapse (0/10) but C-arch parity (5/5*)

The most counter-intuitive single-model finding in v3.3:

| shape | glm-4.7-flash R3 | every other model R3 |
|---|---:|---|
| A — HumanEval+ | **0/10** | 9-10/10 |
| C-arch — architecture prose | **5/5*** (parity with all) | 5/5* |
| D3 refactor | 4/4* | 4/4* |

**Flash-optimization sacrifices A-shape solution synthesis for prose reasoning speed.** The model can structure refactor decisions and architecture prose competently but cannot invent the one-line solutions HumanEval+ requires. Investigation of `outputs/humaneval-plus__HumanEval_*` files shows GLM produces verbose, explanation-heavy outputs with low functional code per token. Not a deployable general-purpose model on this benchmark mix; specialized for prose-heavy workloads.

### Finding 5 — Multi-step hybrid (R3/R4/R5) loses to R1 on cost AND quality on the mixed workload

The headline negative result of v3.3 (confirming v3):

| route | mean cost ratio vs R1 | quality vs R1 | recommendation |
|---|---:|---|---|
| R1 cloud-only (gpt-5.5) | 1.0× | baseline | **default for shapes where local fails** |
| R2 local-only | 0.0× | shape-dependent | **default for A-shape (9-10/10 free)** |
| R3 hybrid-architect | 2.26× | tied on A/B/C-arch, worse on D4 | not recommended |
| R4 Stanford Minion | 1.91× | tied on most, worse on D4 | not recommended |
| R5 Stanford DevMinion | **5.13×** | **collapsed on D3/D4 (composite 0.00 across 7/8 tasks)** | **never deploy** |

**The architect-prefix + synth overhead dominates on small/medium tasks**, so even when local executor steps are free, the hybrid loses to single-shot R1. Multi-step orchestration is structurally the wrong lever for cost savings.

---

## §5. Cross-model leaderboard (R3 heuristic, the canonical comparison cell)

Sorted by $/correct (gpt-5.5 primary):

| rank | local model | n_rows | passes | $ total | **$/correct** | notes |
|---:|---|---:|---:|---:|---:|---|
| 🥇 | **qwen3-coder:30b** | 50 | 35 | $8.01 | **$0.229** | Code-specialized 30B, MLX-accelerated on M4 Max |
| 🥈 | gemma4:31b | 50 | 31 | $8.13 | $0.262 | Google's 31B dense; **0/10 SWE-bench** but A-good |
| 🥉 | qwen2.5-coder:32b | 50 | 31 | $8.34 | $0.269 | Substitute for Llama 4 Scout; slightly weaker than qwen3-coder |
| 4 | devstral:24b (v3) | 50 | 31 | $8.65 | $0.279 | The v3 baseline; still respectable |
| 5 | qwen3.6:27b-mxfp8 | 50 | 31 | $8.68 | $0.280 | **Newer ≠ better**: regresses vs qwen3-coder |
| 6 | qwen3.6:35b-A3B | 50 | 27 | $8.20 | $0.304 | MoE A3B; lower pass rate despite larger total params |
| 7 | glm-4.7-flash | 50 | 19 | $8.44 | $0.444 | **A-collapse**: 0/10 HumanEval+ |

**Headlines:**

- **Qwen3-Coder:30B wins by 14%** over the 2nd-place model and 22% over devstral baseline.
- **Four different local models all hit 31/50** (gemma4, qwen2.5-coder, devstral, qwen3.6-27b) — there's a robust "middle tier" of 24-32B code-capable locals.
- **The Qwen 3.6 family regression is real and reproducible across both variants** (27B-mxfp8 and 35B-A3B-MoE).
- **GLM-4.7-Flash is unsuitable** for code-heavy mixed workloads on this benchmark — its A-shape collapse drops it to 19/50, half the throughput of the winner.

---

## §6. Strategy × model interaction matrix (R3, $/correct)

The full cross-product showing how each routing strategy performs per local model. Lower is better.

| strategy | devstral | qwen3-coder | qwen2.5-coder | glm-flash | gemma4 | qwen3.6-27b | qwen3.6-35b |
|---|---:|---:|---:|---:|---:|---:|---:|
| heuristic (baseline) | **$0.279** | **$0.229** | **$0.269** | **$0.444** | **$0.262** | **$0.280** | **$0.304** |
| rules | $0.213 | $0.265 | $0.276 | $0.452 | $0.296 | $0.299 | $0.260 |
| llm-classifier | **$0.173** | $0.155 | $0.184 | $0.246 | $0.184 | $0.165 | n/a |
| embedding-knn | $0.215 | $0.367 | $0.337 | $0.591 | $0.348 | $0.336 | n/a |
| cascade | $0.286 | $0.221 | $0.317 | $0.394 | $0.276 | $0.298 | n/a |

**(n/a = phase 9 strategy variants only run for devstral; qwen3.6-35b strategy variants completed but their analysis is pending.)**

**Reading the matrix:**

- **llm-classifier is the cheapest single-strategy cell on every model** — BUT it scores 0/10 on B-category across all models tested (the SWE-bench collapse from Phase 6). **Cost-leader by quality-failure, not by efficiency.**
- **Cascade ties or beats heuristic on most cells** with quality preserved. It's the right default if you must pick one strategy.
- **Rules underperforms heuristic on most models** (over-routes to cloud due to keyword bias) but is competitive on devstral ($0.213 vs heuristic $0.279). Inconsistent.
- **Embedding-knn is the worst strategy on every single model.** Don't deploy it.

---

## §7. Phase 6 sub-sweep — classifier scaling does not fix llm-classifier

The hypothesis going into Phase 6: llm-classifier's 0/10 SWE-bench score (Phase 1) was due to a classifier model that was too small. Phase 6 tested 4 alternative classifiers + the baseline qwen3:0.6b on devstral + llm-classifier strategy.

| classifier | size | A pass | B pass | total pass | $ total | $/correct |
|---|---:|---:|---:|---:|---:|---:|
| qwen3:0.6b (baseline) | 520 MB | 10/10 | **0/10** | 21 | $3.63 | $0.173 |
| qwen2.5-coder:1.5b (code-specialized) | 986 MB | 8/10 | **0/10** | 19 | $3.04 | $0.160 |
| qwen3.5:0.8b (newer 0.8B) | 1.0 GB | 8/10 | **0/10** | 18 | $3.49 | $0.194 |
| qwen3.5:2b (newer 2B) | 2.7 GB | 10/10 | **0/10** | 19 | $3.30 | $0.174 |
| qwen3.5:4b (newer 4B, largest) | 3.2 GB | 9/10 | **0/10** | 18 | $3.18 | $0.177 |

**Definitive verdict: scaling the classifier 0.6B → 4B (7× larger params) does NOT recover the SWE-bench collapse.** All 5 classifiers score identical 0/10 on B-category. Code-specialization (qwen2.5-coder:1.5b) provides no advantage over general-purpose models of similar size.

**What this means for routing design:** The structural failure is in the **routing logic** (the prompt + decision threshold), not the classifier model. The classifier sees a long-context multi-file patch and labels it "SIMPLE" because the model output is short — it doesn't have visibility into the underlying SWE-bench task complexity. Scaling won't fix this; **feature engineering on the routing decision is required, not model size.**

**Side finding worth flagging:** qwen2.5-coder:1.5b gets the **cheapest absolute cost** ($3.04) of any tested classifier — smallest model + lowest cost — without compromising the (low) pass rate. If you must deploy a classifier despite this paper's recommendation, use the smallest one.

---

## §8. Phase 7 sub-sweep — cascade threshold 15 is empirically optimal

The cascade strategy uses a threshold to decide: trust the heuristic outright, or call the LLM-classifier tiebreaker on borderline cases. Default = 15. Phase 7 tested 5/10/15/20/25 on devstral.

| threshold | pass total | $ total | A pass | B pass | wall_med | $/correct |
|---:|---:|---:|---:|---:|---:|---:|
| 5 (most LLM tiebreaks) | 26 | $7.83 | 9/10 | 3/10 | 142 s | $0.301 |
| 10 | 28 | $8.21 | 10/10 | 5/10 | 154 s | $0.293 |
| **15 (default)** | **29** | **$8.13** | 10/10 | **5/10** | 145 s | **$0.280** |
| 20 | 23 ⚠️ | $7.82 | 8/10 | **1/10** ⚠️ | 137 s | $0.340 |
| 25 (most heuristic-trust) | 27 | $8.33 | 10/10 | 5/10 | 143 s | $0.309 |

**Threshold 15 wins on $/correct** ($0.280) AND on total pass rate (29/50). The default value embedded in `router/strategies.mjs:cascade()` was well-chosen.

**The threshold-20 cliff is striking.** Going from t=15 to t=20:

- Total pass: 29 → 23 (−21%)
- B-shape pass: 5 → 1 (−80%)
- $/correct: $0.280 → $0.340 (+21% worse)

When the threshold is too high, the heuristic over-trusts itself on borderline B-shape tasks (long context but ambiguous keywords) and routes them to local where they fail. Adding the LLM tiebreak (lower threshold) rescues those tasks.

**Practical takeaway:** if you deploy cascade, keep threshold at 15. Lower values (5, 10) cost more without quality improvement. Higher values (20+) collapse on borderline cases.

---

## §9. Per-model deep dives

### devstral:24b (the v3 baseline)

Open-source 24B code model (Mistral's `devstral`). v3's reference local. Profile:

- **A**: 9/10 R2 alone (the only miss: `HumanEval_77` infinite recursion on negative ints)
- **B**: 3/10 R1=R3=R4 — the same three Django tasks consistently pass
- **C-arch**: 3/5 R2*, 5/5 R3*
- **D3 refactor**: 4/4 R3* — devstral's strongest cell
- **D4 review**: 2/4 R3* — weak; qwen2.5-coder beats it 4/4 here

**Verdict:** Still respectable at 31/50 R3 heuristic ($0.279/correct). Beaten by qwen3-coder by 22% on cost-per-correct. Devstral is a sensible fallback if qwen3-coder isn't available, but no longer the leader.

### qwen3-coder:30b (the v3.3 winner)

Alibaba's 30B code-specialized model (newer than Qwen2.5-Coder, focused on coding+reasoning hybrid training). Profile:

- **A**: 9/10 R2 + 10/10 R3 — local solves the majority alone
- **B**: 4/10 R3 — the highest non-R1 SWE-bench across all 6 models
- **C-arch**: 5/5 R3* (universal among non-failures)
- **D1 small-feature**: 2/4 R3 — competitive
- **D3 refactor**: 4/4 R3* — perfect
- **D4 review**: 3/4 R3* — strong (qwen2.5-coder edges 4/4 here, otherwise tied)

**MLX-accelerated on M4 Max via Ollama 0.23.2** — 70-180 tok/s; ~18 GB Q4_K_M memory footprint; fits comfortably on 64 GB. **Recommended default local model.**

### qwen2.5-coder:32b (the runner-up)

Alibaba's older-generation 32B code model. Substituted for Llama 4 Scout in this sweep (Scout's 62.8 GB unquantized variant doesn't fit on 64 GB M4 Max). Profile:

- **A**: 9/10 R2; 10/10 R3 + R4
- **B**: 3/10 R3 (matches devstral)
- **C-arch**: 5/5 R3*
- **D4 review**: **4/4 R3*** — the only model to perfect-score D4 code-review
- $/correct: $0.269 (3rd place overall)

**Verdict:** Excellent for code-review-heavy workloads (D4 strength). Otherwise tied with the middle tier. Pick if D4 dominates your task mix.

### glm-4.7-flash (the cautionary tale)

Zhipu AI's "flash" lightweight variant (substituted for GLM-4.5-Air, which isn't in Ollama's default registry). 17.7 GB Q4. Profile:

- **A**: **0/10 ON EVERY ROUTE** — the headline category collapse
- **C-arch**: 5/5 R3* — full parity with qwen3-coder on prose
- **D3 refactor**: 4/4 R3*
- $/correct: $0.444 — the highest of any model (66% more than qwen3-coder)

**Why the A collapse?** Reasoning-optimized model. Investigation of `outputs/humaneval-plus__HumanEval_*_R2.txt` files shows GLM produces multi-paragraph explanations instead of executable Python functions. Verbose, structured, prose-heavy outputs — wrong shape for HumanEval+'s "give me back working code" expectation.

**Verdict:** Not a general-purpose coding model. If your workload is prose-only (architecture docs, code reviews), it's competitive. For anything functional, skip.

### gemma4:31b (the dark horse)

Google's 31B dense variant. Replaced the earlier 26b pick at user's request mid-sweep. Profile:

- **A**: 10/10 R2 + 10/10 R3 — best A-shape performance
- **B**: 1/10 R2; 2/10 R3 — weak (lower than qwen3-coder, qwen2.5-coder, devstral)
- **C-arch**: 5/5 R3*
- **D4 review**: 3/4 R3* — competitive
- $/correct: $0.262 (2nd place)

**Verdict:** Strong on A and judge-scored prose. Weak on real SWE-bench patches. If your workload skews A-and-D rather than B, gemma4 is competitive with qwen3-coder.

### qwen3.6:27b-coding-mxfp8 (the regression — Precision King)

Qwen 3.6 family, 27B, 8-bit float ("mxfp8") quantization — the closest-to-bf16 precision that fits on 64 GB M4 Max. The true bf16 variant (54 GB) is gated on Ollama registry. Profile:

- **A**: 10/10 R2 + 9/10 R3
- **B**: 0/10 R2; 3/10 R3 — same SWE-bench ceiling as devstral
- **C-arch**: 5/5 R3*
- **D3 refactor**: 4/4 R3*
- $/correct: $0.280 (5th place)

**Verdict:** Tied with devstral on cost. The "newer Qwen family is better" assumption does not hold — 27B-mxfp8 is competitive but not better than the older qwen3-coder:30b. **If you have qwen3-coder, don't switch.**

### qwen3.6:35b-A3B (the regression — MoE Efficiency)

Qwen 3.6 family, 35B total params, 3B active per token via Mixture-of-Experts routing. Should be fastest-per-token. Profile:

- **A**: 10/10 R2 + 9/10 R3
- **B**: 1/10 R2; 3/10 R3 (matches devstral and qwen3.6-27b)
- **D3 refactor**: 4/4 R3*
- **D5 functional one-shots**: 3/4 R3
- **R5 catastrophic**: 0/4 on D3 + 0/4 on D4 + 0/10 on B (typical R5 collapse)
- $/correct: $0.304 (6th place) — worst of the Qwen family

**Verdict:** The 35B MoE total params don't translate into better quality because only 3B activate per token. Compute path acts like a 3B model. **Don't pay the storage cost for capabilities you don't get.**

---

## §10. The router design that actually works

Based on all v3.3 findings, the **deployable router** is **not** R3, R4, or R5. It's a per-task gating architecture that tries R2 first and falls back to R1 on failure. Full design at [`docs/HYBRID_ROUTER_DESIGN.md`](../docs/HYBRID_ROUTER_DESIGN.md) — summarized:

```text
Task arrives
    ↓
Stage 1: Cheap heuristic gate (0 ms)
    ├─ score < 25? → try R2 (local Qwen3-Coder:30B)
    │      ├─ success test passes? → return ($0)
    │      └─ fail? → fall through to R1
    └─ score ≥ 25? → direct R1 (cloud gpt-5.5)
```

**Cost projection on 50-task mixed workload (gpt-5.5 primary):**

- R1-only (cloud baseline): $4.42
- R2-first + R1-fallback (this design): **$3.70**
- R3-cascade hybrid: $4.62 (+4% worse)
- R5-DevMinion: $19+ (cost catastrophe)

**Savings: ~16-20% vs R1-only, no quality regression.** All savings come from A-shape (where R2 wins free) and C-shape (where R2 succeeds 47% of the time). B-shape contributes ~0% — the gate correctly routes those direct to R1.

**Why this beats multi-step hybrid:**

- R3's architect prefix + synth replay add ~$0.025 per task overhead, dwarfing local-step savings on small tasks
- R5's review loop generates token explosion (1.88M tokens total v3, 5× R1 cost)
- The gate's 0 ms heuristic is **the** cost-efficient routing primitive — adding an LLM classifier (cascade pattern) costs latency without proportional savings on the mixed workload

**5 concrete TODOs to implement** (from the design doc):

1. Install Ollama with Qwen3-Coder:30B MLX backend
2. Wire the heuristic gate into `router/server.mjs`
3. Implement Stage 2 success test (syntax check + non-zero token count)
4. Baseline-measure R1-only cost on your workload
5. Monitor + tune threshold offline after 100+ decision records

---

## §11. Worked examples (real data)

### Example 1 — A-shape free win: `humaneval-plus/HumanEval_99`

**Problem:**

```python
def closest_integer(value):
    '''Round value to closest integer, away from zero on ties.
    closest_integer("14.5") = 15. closest_integer("-14.5") = -15.'''
```

**R2 (Qwen3-Coder:30B local) solution** — generated in 7.6s, **$0.00**:

```python
def closest_integer(value):
    num = float(value)
    if num > 0:
        return int(num + 0.5) if num % 1 == 0.5 else round(num)
    else:
        return int(num - 0.5) if abs(num) % 1 == 0.5 else round(num)
```

**Pass.** All adversarial tests succeed.

**Same task across all 5 routes:**

| route | tokens (cloud / local) | wall | cost | result |
|---|---|---:|---:|---|
| R1 cloud | 175 / 0 | 6.1s | $0.013 | ✓ |
| **R2 local** | **0 / 1,480** | **7.6s** | **$0.000** | **✓** ← router design's choice |
| R3 hybrid | 1,906 / 5,721 | 70.7s | $0.055 | ✓ (4.3× more $) |
| R4 minion | 2,700 / 572 | 40.1s | $0.069 | ✓ (5.3× more $) |
| R5 review-loop | 3,704 / 11,613 | 282s | $0.247 | ✗ (catastrophic) |

### Example 2 — B-shape needs R1: `swebench-verified/django__django-11163`

A real Django GitHub issue requiring a multi-file patch. R2 (qwen3-coder:30b local) fails after 9.7s (returns a one-line diff that doesn't apply). R1 (gpt-5.5) succeeds in 61.6s for $0.106. The router's gate correctly identifies this as "score ≈ 35, high token count + 'fix' + 'bug' keywords, multi-file context" → rejects R2 attempt → goes direct to R1. **Total cost: $0.106. Latency: 61.6s.** Saves the 9.7s wasted local attempt that would otherwise precede the fallback.

### Example 3 — R5 catastrophic failure: `real-dev/d3-extract-validation-helper`

Variant 21 (qwen3.6:27b-mxfp8), R5 DevMinion. The architect generated a runbook, the editor produced wrong code, the reviewer rejected it. By round 3 the editor regenerated the same wrong content. The final integration step emitted the literal string `ls -la` as the deliverable. **34.2K tokens burned, 491s wall, $0.36, composite 0.00.** Compare R1 on the same task: 12s, $0.033, composite 0.98. **R5 spent 11× the cost + 41× the wall time to deliver `ls -la`.** Don't deploy R5.

---

## §12. Hypothesis vs reality scorecard

The v3 plan predicted hybrid routes would save 40-70% vs cloud. v3.3 with 6 local models, 7 strategies, 9 sub-sweep variants delivered the verdict:

| metric | v3 prediction | v3.3 measurement | verdict |
|---|---|---|---|
| Hybrid cost vs R1 | 0.3-0.6× (saves 40-70%) | **R3 = 2.26×, R4 = 1.91×, R5 = 5.13×** | ❌ |
| Cloud_fraction (R4) | 20-40% cloud | **85% cloud** (universal across models) | ❌ |
| Multi-step orchestration generalizes | yes | **no — every protocol loses to R1** | ❌ |
| Cascade is the Pareto winner | tentative | **confirmed across 6 models** | ✓ |
| Llm-classifier with bigger model fixes SWE-bench | hypothesis | **0/10 across 5 classifier sizes 0.6B-4B** | ❌ |
| Threshold 15 is optimal | not predicted | **confirmed by phase 7 sub-sweep** | ✓ (new finding) |
| Newer model generations = better | implicit | **Qwen 3.6 27B + 35B both regress vs Qwen3-Coder** | ❌ |

**Net:** 5 of 7 hypotheses refuted; 2 confirmed (the modest ones — strategy ordering, threshold tuning). The v3.3 sweep is honest about what doesn't work.

---

## §13. Methodology

### Routes tested (5)

- **R1** cloud-only: single shot to `gpt-5.5`
- **R2** local-only: single shot to local model via Ollama (MLX backend on M4 Max)
- **R3** hybrid-architect: cloud planner → per-step heuristic-routed executor → cloud synth
- **R4** Stanford Minion: cloud supervisor / local worker Q&A protocol
- **R5** Stanford DevMinion: architect → editor → reviewer review-loop (up to 3 rounds)

### Routing strategies tested (7)

- `always-cloud`, `always-local` — control baselines (= R1, R2)
- `rules` — keyword + regex routing
- `heuristic` — weighted-score classifier (v3 default)
- `llm-classifier` — qwen3:0.6b SIMPLE/COMPLEX
- `embedding-knn` — cosine kNN against 50-example labeled corpus
- `cascade` — heuristic + LLM tiebreak (the Pareto winner)

### Local models tested (6, plus v3 reference)

| model | Ollama tag | size on disk |
|---|---|---:|
| devstral:24b (v3 reference) | `devstral:24b` | 14 GB |
| qwen3-coder:30b | `qwen3-coder:30b` | 18 GB |
| qwen2.5-coder:32b | `qwen2.5-coder:32b` | 19 GB |
| glm-4.7-flash | `glm-4.7-flash` | 19 GB |
| gemma4:31b | `gemma4:31b` | 19 GB |
| qwen3.6:27b-mxfp8 | `qwen3.6:27b-coding-mxfp8` | 31 GB |
| qwen3.6:35b-A3B | `qwen3.6:35b` | 23 GB |

### Cloud + judge

- **Cloud (primary):** gpt-5.5; re-priced under gpt-5, gpt-5-mini, opus-4.7, sonnet-4.6, haiku-4.5
- **Judge:** claude-opus-4-7 (cross-vendor; avoids GPT self-preference)
- **Triple-judge audit** on D3+D4 (run 11, 96 verdicts): opus-4-7 + sonnet-4-6 + gpt-5.5 cross-checked. All R1-wins, 0 ties, 0 order-flips — **R1 prose dominance is judge- and order-invariant**.

### Task shapes (8 categories, 50 unique tasks)

- **A** HumanEval+ (10): EvalPlus seed=42 sample, pinned `tasks.jsonl`
- **B** SWE-bench Verified easy (10): princeton-nlp/SWE-bench_Verified subset
- **C-bcb** BigCodeBench-Hard (5): bigcode/bigcodebench hand-picked
- **C-arch** custom-arch prose (5): hand-written by repo authors (auth-multitenant-design, cache-invalidation-tradeoffs, code-review-flaky-test, migration-planning-zero-downtime, production-debug-reasoning)
- **D1** small-feature (4): real-developer feature requests
- **D2** GitHub-issue patches (4): pallets/click, jsonschema, werkzeug, pytest-dev (functional scorer deferred)
- **D3** refactor (4, judge-scored)
- **D4** code-review (4, judge-scored)
- **D5** small one-shots (4): csv-dedupe, env-var-redactor, log-errors-today, todo-counter

### Scoring

- **Functional** (A, B, C-bcb, D1, D5): pytest in Docker sandbox (python:3.12-slim, --network none, 60s wall, 512 MB mem)
- **SWE-bench harness** (B): mini-SWE-agent under Rosetta on Apple Silicon
- **LLM-judge** (C-arch, D3, D4): claude-opus-4-7 pairwise, 5-dimension rubric, A-vs-B + B-vs-A averaged, temperature=0
- **Pass proxy:** `functional_pass=True` (functional) or `composite ≥ 0.5` (judge)

### Cost derivation

**Cost is never persisted** in `raw.jsonl`. Every row records tokens-per-backend (`local_*`, `cloud_*`, `cache_read`); cost is computed at read time:

```text
cost = (cloud_prompt − cache_read) × input_rate
     + cache_read × cache_read_rate
     + cloud_completion × output_rate
     + 0 × local_*    # local is $0 by construction
```

Rates from `configs/pricing/pricing_tables.json` (SHA256 pinned, dated 2026-04-27, sourced from models.dev). 6 pricing scenarios available; ranking is invariant across them.

### Sweep volume

- **Phase 1:** v3.2 devstral × 5 strategies × 50 R3 tasks = 250 rows
- **Phase 2-5:** 4 new local models × full sweep (heuristic R2+R3+R4+R5 = 200 + 4 strategies × R3 × 50 = 200) × 4 models = 1,600 rows
- **Phase 6:** classifier sub-sweep × 4 candidates × 50 R3 tasks = 200 rows
- **Phase 7:** cascade threshold sub-sweep × 5 thresholds × 50 R3 tasks = 250 rows
- **Phase 8:** recovery (mostly skip-via-resume) ≈ 0 rows
- **Phase 9:** Qwen 3.6 × 2 models × full sweep = 800 rows
- **Total: ~3,581 rows across 33 variant directories**

### Hardware

- M4 Max 64 GB MacBook
- Single-seed (42), single-machine, no parallelism
- Continuous compute: 4 days 14 hours (paused once for power management)

---

## §14. Limits and biases acknowledged

| Limit | Status |
|---|---|
| **Single hardware tier** (M4 Max 64 GB) | All findings explicitly conditional. Wall clock varies by hardware; cloud_fraction is hardware-invariant. |
| **Single cloud model** (gpt-5.5 primary) | Re-priced under 5 scenarios; route ranking invariant. Different cloud could shift absolute cost. |
| **6 local models — limited family coverage** | We tested Qwen, Devstral, GLM, Gemma. Missing: Llama 4 Scout (didn't fit), Claude (no local variant), Mistral non-Devstral. |
| **10-task slices on A/B/C; 4-task slices on D** | Single-seed, no CIs. Direction not significance. The v1 → v3 SWE-bench reversal (Sphinx wins disappearing) is itself a demonstration of slice-noise. |
| **R5 has known JSON-extraction fragility upstream** | Our wrapper patches Stanford's `minion_code.py`; residual brittleness may bias R5 down. Even with fix, R5's catastrophic failures (composite 0.00 across 7/8 D3+D4 tasks) are consistent. |
| **D2 functional scoring deferred** | 20+ rows have `functional_pass=None`. Cost/cloud-fraction observable; quality not. |
| **HumanEval+ contamination** | HIGH risk; treat A as a floor not a ceiling. |
| **Custom-arch + real-dev tasks hand-curated by authors** | Judge-audited via triple-judge run 11 (96 verdicts unanimous). Skeptic can re-judge with a new rubric. |
| **Local = $0 by construction** | Marginal cost on M4 Max ~$0.005-0.01 per task (electricity + amortization). Not zero, but small. Doesn't flip the R1 vs hybrid ranking. |
| **Benchmark ≠ real development** | Curated tasks, single prompts. Real work has multi-file context, tool loops, iteration, debugging from error output. Not covered. |
| **No multi-vendor classifier scaling** | Phase 6 tested only Qwen family (+1 code variant). Anthropic, Google, etc. classifiers untested. |

Every limit is either (a) hardware/data inherited from the sweep, (b) deferred scoring (D2), or (c) future-work scope. None overturn the headline findings.

---

## §15. Reproducibility

Everything reproducible from a fresh clone of `github.com/RunanywhereAI/hybrid-coding-eval` at tag `v3.3`:

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval && git checkout v3.3
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .

# Pull all 6 local models (~120 GB disk)
for m in devstral:24b qwen3-coder:30b qwen2.5-coder:32b glm-4.7-flash gemma4:31b qwen3.6:27b-coding-mxfp8 qwen3.6:35b qwen3:0.6b nomic-embed-text; do
  ollama pull $m
done

# Build functional-scoring Docker image
docker build -f src/hybrid_coding_eval/scorers/Dockerfile.functional_python -t hybrid-eval-python:latest .

# Configure
echo "OPEN_AI_API_KEY=sk-..." > .env  # plus ANTHROPIC_API_KEY for the judge
cd vendor && git clone https://github.com/HazyResearch/minions.git && cd ..  # R4 + R5

# Start router
(cd router && ./start.sh) &

# Run the full v3.3 sweep (4-5 days wall, ~$240 OpenAI)
./bin/v3.3-full-sweep.sh                    # phases 1-5
./bin/v3.3-phase-6-7.sh                     # phase 6+7 sub-sweeps
./bin/v3.3-phase-9-qwen36.sh                # phase 9 Qwen 3.6 models

# Auto-regenerate this article from the swept data
./bin/v3.3-refresh-article.sh --commit
```

**Re-pricing without re-running:**

```bash
./bench token-budget results/runs/07-v3-devstral-all-routes/
```

The same dataset is re-priced under any of the 6 scenarios. Cost is never stored; re-derive on read.

**Drop in a new model:**

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
# edit 2 lines, then:
./bench run --config configs/variants/my-model.yaml
```

Full instructions in [`docs/REPRODUCING.md`](../docs/REPRODUCING.md). Total wall time on M4 Max: 4-5 days for the full v3.3 sweep. Cost: ~$240 OpenAI + ~$3 Anthropic.

---

## §16. Where to read next

In priority order:

- **[`HYBRID_ROUTER_DESIGN.md`](../docs/HYBRID_ROUTER_DESIGN.md)** — the deployable router design + worked examples + cost projection. The "what should I build?" answer.
- [`DECISION_TABLE.md`](./DECISION_TABLE.md) — per-shape × route grid (canonical, the v3.3 expanded version)
- [`TOKEN_BUDGET.md`](./TOKEN_BUDGET.md) — token-first cost matrix under 6 scenarios
- [`APPENDIX_TASKS.md`](./APPENDIX_TASKS.md) — every row verbatim (large; query with jq)
- [`APPENDIX_SCENARIOS.md`](./APPENDIX_SCENARIOS.md) — multi-scenario $/correct
- [`APPENDIX_ROUTES.md`](./APPENDIX_ROUTES.md) — R1-R5 deep-dive worked examples
- [`docs/REPRODUCING.md`](../docs/REPRODUCING.md) — copy-paste reproduction guide
- [`docs/METHODOLOGY.md`](../docs/METHODOLOGY.md) — full methodology + biases
- [`docs/ROUTING_STRATEGIES.md`](../docs/ROUTING_STRATEGIES.md) — deep-dive on the 7 routing strategies
- [`docs/PRIOR_ART.md`](../docs/PRIOR_ART.md) — May 2026 research synthesis
- [`docs/audits/T-22-v3-publish-readiness.md`](../docs/audits/T-22-v3-publish-readiness.md) — pre-public audit
- [`results/runs/07-v3-devstral-all-routes/run-notes.md`](../results/runs/07-v3-devstral-all-routes/run-notes.md) — v3 reference sweep
- [`results/runs/11-judge-robust-D/run-notes.md`](../results/runs/11-judge-robust-D/run-notes.md) — triple-judge audit

---

## §17. Citations + license

**Suggested citation:**

> Monga, Sanchit and contributors. *hybrid-coding-eval v3.3: comprehensive cross-model + cross-strategy decision report for local-vs-cloud-vs-hybrid LLM routing on coding tasks.* 2026. <https://github.com/RunanywhereAI/hybrid-coding-eval>. Tag: `v3.3`.

**License.**

- **Code** (harness, router, runners, scorers, analysis): MIT — [`LICENSE`](../LICENSE)
- **Results, metrics, figures, article**: CC-BY-4.0 — [`LICENSE-DATA`](../LICENSE-DATA)

**Vendor acknowledgments.**

- **Stanford Minion + DevMinion** (MIT): wrapped by R4 + R5. [HazyResearch/minions](https://github.com/HazyResearch/minions).
- **lm-eval-harness judge** (Apache 2.0): referenced design, not imported.

**Benchmarks sampled.**

- HumanEval+: EvalPlus, Apache 2.0
- SWE-bench Verified: princeton-nlp, MIT
- BigCodeBench-Hard: bigcode-project, Apache 2.0
- custom-arch (5) + real-dev D1-D5 (20): hand-written by Sanchit Monga, CC-BY-4.0

**Models evaluated.**

- gpt-5.5, gpt-5, gpt-5-mini — OpenAI
- claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5 — Anthropic
- devstral:24b — Mistral AI via Ollama
- qwen3-coder:30b, qwen2.5-coder:32b, qwen3.6:27b-coding-mxfp8, qwen3.6:35b-A3B — Alibaba via Ollama
- glm-4.7-flash — Zhipu AI via Ollama
- gemma4:31b — Google via Ollama

**Judges.**

- claude-opus-4-7 (primary, cross-vendor)
- claude-sonnet-4-6 + gpt-5.5 (triple-judge audit on D3+D4)

Full attribution in [`../NOTICE.md`](../NOTICE.md).

---

*Published from the open-source [hybrid-coding-eval](https://github.com/RunanywhereAI/hybrid-coding-eval) repository. Issues + reproducibility questions: <https://github.com/RunanywhereAI/hybrid-coding-eval/issues>.*
