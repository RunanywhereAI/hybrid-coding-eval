# results/runs/ — experimental runs, preserved

Each subdirectory here is one complete, self-contained run. They're numbered in chronological + causal order (each run reacted to findings from the previous).

**If you just want the answer:** read [`../../reports/ARTICLE.md`](../../reports/ARTICLE.md). It summarises all runs.

**If you want per-run detail:** each directory below has its own `raw.jsonl`, `outputs/`, `progress.log`, `env-manifest.json`, `run-notes.md`. Drop in, understand that variant in isolation.

## The runs

| # | directory | when | dataset | the finding |
|---|---|---|---|---|
| 01 | `01-v1-qwen-original/` | 2026-05-05 | 90 rows, all 30 tasks × R1, R2, R3, qwen local, gpt-5 judge | **The v1 sweep.** Reported "R3 is Pareto-dominated on every category." Later invalidated — driven by a synth-budget bug + weak local model on SWE-bench. |
| 02 | `02-v2-qwen-fixed-synth/` | 2026-05-05 | 20 rows, category C × R1, R3, qwen local, **Claude Opus 4.7 judge** | **Closed the synth-budget bug.** R1 and R3 no longer produce 0-byte outputs on reasoning-heavy tasks. Opus (cross-vendor) judge rates R3 ≈ R1 on 4/5 custom-arch tasks. |
| 03 | `03-v2-devstral/` | 2026-05-06 | 60 rows, all 30 tasks × R2, R3, **devstral:24b local** | **Local-model swap test.** R3-devstral hits 3/10 on SWE-bench Verified — matches R1 cloud-only. Also fixes the qwen R3 regressions on HumanEval+. |
| 04 | `04-r4-minion/` | 2026-05-06 | 10 rows, SWE-bench × R4 (Stanford Minion protocol) | **R4 beats R1 on SWE-bench.** 4/10 pass, cheaper + more accurate than cloud-only. First route to Pareto-improve on R1. (Note: did not replicate in v3 — see run 07.) |
| 07 | `07-v3-devstral-all-routes/` | 2026-05-11 | 250 rows, 50 tasks × 5 routes, devstral local, gpt-5.5 cloud, claude-opus-4-7 judge | **The v3 sweep.** First time R5 (DevMinion review-loop) ran on the full grid + category D (real-developer tasks). Hybrid hypothesis refuted: R4 cloud_fraction is 87%, cost ratios R3/R4/R5 = 2.26×/1.91×/5.13× R1. The run-04 "R4 beats R1 on SWE-bench" headline did not replicate (R1=R3=R4=3/10 on the same Django triple). |
| 11 | `11-judge-robust-D/` | 2026-05-11 | 96 verdicts: 8 D3+D4 tasks × 2 pairings × 3 judges × 2 orders | **D3/D4 robustness audit.** 16/16 pairings unanimous; 0/16 order-flip. Confirms the v3 finding that R1 dominates on prose categories is judge-and-order-invariant. |

## What each run directory contains

Common structure (not every file is present in every run):

```
runs/NN-*/
├── raw.jsonl            ← THE data rows for this run (one JSON per (task, route))
├── outputs/             ← raw model-generated text for each (task, route)
├── progress.log         ← orchestrator's per-row progress line
├── run.log              ← orchestrator stdout (pre-scoring)
├── env-manifest.json    ← hardware + software snapshot at run time
├── aggregate.json       ← per-cell medians/means (regenerable via analysis.all)
├── arqgc.json           ← Bounded-ARQGC per (category, route) (regenerable)
├── decision_matrix.md   ← category × route → recommendation (regenerable)
├── charts/              ← Pareto, heatmaps, per-category (regenerable)
├── judge.jsonl          ← LLM-judge pairings (for category C runs only)
├── manual_audit.md      ← 5-row human spot-check (run 01 only)
├── ERRORS.md            ← infrastructure errors log (run 01 only)
└── REPORT.md / run-notes.md  ← per-run write-up (run 01 has the full v1 report)
```

**Which files are data, and which are derived:**

- `raw.jsonl`, `outputs/`, `judge.jsonl`, `env-manifest.json`, `progress.log` → SOURCE DATA. Cannot be regenerated.
- `aggregate.json`, `arqgc.json`, `decision_matrix.md`, `charts/*.png` → DERIVED. Regenerate any time via `python -m analysis.all results/runs/NN-*/`.

## How runs relate to the merged dataset

`../raw.jsonl` (one level up) is the merge of runs 01–04 (the MVP 180 rows). Run 07 is NOT merged into that file — it lives only in its own subdir's `raw.jsonl`. Each post-MVP run dir is self-contained. Analysis scripts in `src/hybrid_coding_eval/analysis/` read the MVP merged file PLUS every post-MVP run dir, without double-counting.

| run | variant tag in merged dataset | rows | added to `../raw.jsonl`? |
|---|---|---:|:-:|
| 01 | `v1-qwen` | 90 | ✅ |
| 02 | `v2-qwen-fixed` | 20 | ✅ |
| 03 | `v2-devstral` | 60 | ✅ |
| 04 | `r4-minion` | 10 | ✅ |
| 07 | `v3-devstral` | 250 | ❌ (in `07-v3-devstral-all-routes/` only) |
| 11 | `judge-robust-D` | 96 verdicts | ❌ (in `11-judge-robust-D/judge.jsonl` only) |
| **MVP merged rows** | | **180** |  |
| **v3 sweep rows** | | **250** (run `07-v3-devstral-all-routes/`, self-contained) |  |

## A note about run 01's REPORT.md

`runs/01-v1-qwen-original/REPORT.md` is kept verbatim (with a deprecation banner) to preserve the v1 narrative for history. **Its main-body claims about R3 being Pareto-dominated are wrong** — that conclusion did not survive the v2 runs (02–04). The v1 file stays because:

- It records what we thought at the end of the v1 sweep.
- Its §12 addendum documents the caveats and forecasted where v2 would change things — which is exactly what happened.
- Deleting it erases the reasoning trail a reader needs to understand why the canonical reports say what they say.

For current claims, prefer `../../reports/ARTICLE.md` (v3) and `../REPORT_v1_mvp.md` (MVP-frozen).
