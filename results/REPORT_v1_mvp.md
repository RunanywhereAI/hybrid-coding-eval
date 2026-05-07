# Hybrid vs cloud-only for coding tasks — final report

> **This is the ONE report to read.** Everything else in this repo is either source data, per-run detail, or historical context that fed into this document.

_Dataset: `results/raw.jsonl` (180 rows across 4 run variants)._
_Per-run detail: `results/runs/NN-*/` (four numbered sub-directories, one per variant, each self-contained with its own raw.jsonl, outputs, progress log, env manifest)._
_Reproduce: see `docs/REPRODUCING.md`._

---

## The question we set out to answer

> For real developer coding tasks, when does hybrid local+cloud routing beat cloud-only, and where does it lose?

Three sub-questions, measured across 30 public and hand-curated coding tasks:

- **cost** — $ paid to OpenAI / Anthropic APIs.
- **quality** — pass rate on functional tasks (pytest / SWE-bench harness) and LLM-judge verdict on reasoning/architecture tasks.
- **latency** — wall-clock to completion on an M4 Max laptop.

## What we tested

**30 tasks, stratified:**

| category | source | count | scorer |
|---|---|---:|---|
| A — tiny function-completion | HumanEval+ (seed=42 random sample) | 10 | pytest in Docker sandbox |
| B — real software engineering | SWE-bench Verified easy tier | 10 | mini-swe-agent Docker harness |
| C — architecture / reasoning | 5 BigCodeBench-Hard (pytest) + 5 custom arch (LLM-judge) | 10 | mix |

**4 routes:**

| id | description |
|---|---|
| R1 | single-shot to `gpt-5.5` cloud |
| R2 | single-shot to qwen3.6:27b-coding (or devstral:24b) local via Ollama |
| R3 | cloud planner → per-step heuristic router → cloud synth |
| R4 | Stanford Minion supervisor/worker Q&A (cloud supervisor, local worker) |

**2 local-model variants** for R2 and R3: qwen3.6:27b-coding-mxfp8 and devstral:24b. Single hardware tier (M4 Max 64 GB).

---

## The one big table — pass rate per (category, route)

| Task | R1 cloud | R2 qwen | R2 devstral | R3 qwen | R3 devstral | R4 Minion |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| **A — HumanEval+ (10)** | **10/10** | **10/10** | 9/10 | 8/10 | **10/10** | — |
| **B — SWE-bench Verified (10)** | 3/10 | 1/10 | 0/10 | 1/10 | 3/10 | **4/10** |
| **C — BigCodeBench-Hard (5)** | 2/5 | 1/5 | 1/5 | 2/5 | 2/5 | — |
| **C — custom-arch (5, Opus judge)** | ties w/ R3 | loses R1 | loses R1 | **ties w/ R1** | — | — |

Median cost & wall per task on category B (SWE-bench), gpt-5.5 pricing:

| route | cost/task | wall/task | passes |
|---|---:|---:|---:|
| R1 | $0.126 | 67 s | 3/10 |
| R3-devstral | $0.144 | 194 s | 3/10 |
| **R4 Minion** | **$0.083** | 155 s | **4/10** |

**R4 is the first route that's both cheaper AND more accurate than R1 cloud-only.**

---

## The three findings that matter

### 1. R4 (Minion Q&A) beats R1 on SWE-bench

4/10 pass vs R1 3/10. R4 uniquely solves `sphinx-doc/sphinx-7889` and `sphinx-doc/sphinx-9698` that no other route solves.

Why it works: the cloud supervisor asks the local worker *targeted questions* about the repository instead of replaying full repo context on every step. Less cloud-prompt bloat, more attention on the bug.

Caveat: 10 tasks × 1 sample. A 30-task sweep would tighten the confidence interval. The direction is strong enough to queue a bigger run.

### 2. R3 ≈ R1 on architecture/reasoning (after fixing a runner bug)

Claude Opus 4.7 judge rates R3 equivalent to R1 on 4 of 5 hand-curated architecture tasks, with R3 winning ARQGC (area under quality-cost curve) at 0.934 vs R1 0.510.

What changed from earlier drafts: the v1 sweep reported R3 losing on C because gpt-5.5's reasoning_tokens consumed the entire 2,500-token synth budget, producing 0-byte outputs. Bumping synth budget to 16,000 tokens fixes it — full prose outputs, judge rates them equivalent to R1.

### 3. Stronger local model fixes R3 on SWE-bench

Swapping qwen3.6:27b-coding → devstral:24b (SWE-bench-specialised 24B checkpoint) takes R3 from 1/10 → 3/10 on SWE-bench, matching R1. Also fixes two HumanEval+ regressions qwen-R3 had (spec-loss and indentation bugs).

Cost parity with R1, not yet a Pareto improvement — cloud planner+synth overhead dominates the dollar figure. Shrinking those prefixes is the next optimisation target.

---

## Revised headline

Earlier drafts of this report claimed "R3 hybrid-architect is Pareto-dominated on every category at every pricing tier." That claim was load-bearing on (a) a runner bug and (b) a weak local model for SWE-bench. Close those and the picture inverts:

- R3 with Devstral as local model **matches** R1 on SWE-bench and on HumanEval+.
- R3 with the synth-budget bug fixed **matches** R1 on architecture/reasoning.
- R4 with Stanford's Minion protocol **beats** R1 outright on SWE-bench.

**Hybrid patterns are not uniformly worse than cloud-only.** They ARE harder to get right — you need the correct budget, a capable-enough local model, and a pattern (R4) that doesn't replay context on every step. Once those are in place, hybrid routing reaches parity or wins.

---

## How to navigate the repo

If you want to read more, in priority order:

1. **This file** — the single canonical report.
2. **`results/runs/NN-*/REPORT.md` or `run-notes.md`** (in each run dir) — per-variant write-up, scoped to that specific run's data.
3. **`docs/METHODOLOGY.md`** — how the eval works, biases acknowledged.
4. **`docs/REPRODUCING.md`** — copy-paste steps for a fresh machine.
5. **`docs/PLAN.md`** — original project plan (planning artifact, not findings).
6. **`docs/ARCHITECTURE.md`** — code layout + data flow.
7. **`docs/ROUTING_STRATEGIES.md`** — deeper dive on each route.
8. **`docs/PRIOR_ART.md`** — May 2026 research synthesis (benchmarks, local-model perf, hybrid architectures).
9. **`docs/article-draft-v1.md`** — earlier long-form article with postscript. Narrative artifact; this REPORT is authoritative for numbers.

## How to navigate the data

- **`results/raw.jsonl`** — the single merged dataset, 180 rows, every row tagged with a `"variant"` field (`v1-qwen`, `v2-qwen-fixed`, `v2-devstral`, `r4-minion`).
- **`results/env-manifests/`** — hardware profile for each variant. Three distinct profiles.
- **`results/runs/NN-*/`** — the original per-variant directories, with their raw.jsonl, outputs, progress.log, judge.jsonl. Self-contained — you can drop a reader into any one of these dirs and it has everything needed to understand that variant.

## The four runs, in order

| # | directory | dataset | key finding |
|---|---|---|---|
| 01 | `runs/01-v1-qwen-original/` | 90 rows (30 × R1, R2, R3) qwen local, gpt-5 judge | **v1 conclusion — later invalidated.** R3 synth-budget bug produced 0-byte outputs on 4/5 custom-arch. Claim "R3 loses on every category" was driven by the bug + weak local model. |
| 02 | `runs/02-v2-qwen-fixed-synth/` | 20 rows (10 × R1+R3 on category C) with bumped synth budget + Claude Opus 4.7 judge | **Synth bug closed.** R3 outputs are now 20-30 KB real prose; Opus judges R3 ≈ R1 on 4/5 architecture tasks. |
| 03 | `runs/03-v2-devstral/` | 60 rows (30 × R2+R3) with devstral:24b local | **Local-model swap rescues R3 on B.** R3-devstral hits 3/10 on SWE-bench Verified — matches R1. Also fixes qwen R3 regressions on HumanEval+. |
| 04 | `runs/04-r4-minion/` | 10 rows (10 × R4) on SWE-bench Verified | **Minion beats cloud-only.** R4 = 4/10 pass, cheaper + more accurate than R1. First route to Pareto-improve on R1. |

---

## Known limits + honest caveats

- **N=10 per category** is direction, not significance. Queue a 30-task sweep before publishing any of this externally.
- **Single hardware tier** (M4 Max 64 GB). Numbers shift on smaller laptops or bigger GPUs.
- **Single cloud model family** (OpenAI gpt-5.5). Claude Opus 4.7 serves only as judge.
- **R4 tested only on SWE-bench.** We don't know how Minion performs on A or C.
- **The Minion library has a flaky JSON extractor** that we monkey-patch in `runners/r4_minion.py`; orchestrator retries cover most of it, but a longer sweep would surface the true flake rate.
- **No R5 (Aider architect/editor review loop).** Next post-MVP item.
- **Cost parity on B is not yet a cost win.** R3's cloud planner+synth overhead dominates. Prompt-caching on those prefixes is the next optimisation.

---

## Budget used

- **Wall clock:** ~5h total across all 4 runs on one M4 Max.
- **API spend:** ~$12 (OpenAI + Anthropic judge).
- **Local compute:** qwen3.6:27b ~10 tok/s; devstral:24b similar.
- **Disk:** ~4 MB model outputs + ~400 KB analysis artefacts + 15 GB Ollama models.
