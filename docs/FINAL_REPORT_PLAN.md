# Final-report execution plan

> **Purpose.** Close the open gaps in `results/REPORT.md`, produce publishable
> tables under *official API per-M-token pricing* across multiple cloud
> scenarios, and deliver one *very detailed* final report that answers, for a
> real developer's coding workload, **when hybrid beats cloud-only, when it
> doesn't, and what each routed token bought you**.
>
> Author: Claude (planning phase). Date: 2026-05-06.

---

## 0. Guardrails that apply to every todo

These are non-negotiable and every agent is briefed on them:

1. **Tokens are the primary observable.** Never write any `cost_usd_*` field
   into `raw.jsonl`. Cost is always *derived* at analysis time from
   `lib/pricing_tables.json` via `lib/pricing.py` and
   `analysis/cost_scenarios.py`. This is already the invariant; the plan
   enforces it.
2. **Official API per-M-token rates only.** No "plan" / "subscription"
   pricing. The pinned rates in `lib/pricing_tables.json` (fetched
   2026-04-27, source `models.dev/api.json`) are the source of truth. Any
   update requires a version bump and is a separate todo (T-05).
3. **Preserved runs are read-only.** `results/runs/01-*`, `02-*`, `03-*`,
   `04-*` and `results/raw.jsonl` (the merged 180 rows) MUST NOT have
   rows rewritten in place. New sweeps go to new directories
   (`results/runs/05-*`, …). Re-pricing is a read-only view on top.
4. **Each todo is a single commit.** After finishing, the agent runs
   `pytest -q -m 'not slow'` (plus any todo-specific verification), stages
   the files it touched (no `git add -A`), and commits with a message
   ending in the co-author trailer used elsewhere in this repo. On
   pre-commit failure: fix and retry — never `--no-verify`.
5. **No router drift between tasks.** If a sweep needs the router proxy,
   start it at todo-begin and shut it down at todo-end (`./router/start.sh`
   is idempotent; logs land in `router/logs/decisions.jsonl` which is
   tracked — commit the decision-log churn with the sweep).
6. **Reproducibility bundle.** Any new sweep writes its own
   `env-manifest.json`, `progress.log`, `raw.jsonl`, `outputs/`, and a
   one-paragraph `run-notes.md` into its run dir — same shape as the
   existing four runs.
7. **No over-scope.** If a todo's agent finds a bug outside the todo's
   scope, it files a follow-up todo (by editing §2 of this doc in the
   commit) rather than expanding its diff.

---

## 1. Sanity check of what we already have

What the 180-row dataset + existing code already proves:

| Question the REPORT set out to answer | Current status | What's missing |
|---|---|---|
| Does hybrid beat cloud on tiny function-completion (Cat A)? | **Answered.** Ties or parity across R1/R2/R3; no hybrid win to claim. | Nothing — keep as sanity floor. |
| Does hybrid beat cloud on real SWE tasks (Cat B)? | **Directionally yes, via R4 Minion** (4/10 vs 3/10, cheaper). | (i) N=10 is weak; (ii) only tested with one local model for R4; (iii) 3-seed CI never computed. |
| Does hybrid match cloud on architecture/reasoning (Cat C)? | **Answered after synth-budget fix.** R3 ties R1 on 4/5 custom-arch (Opus judge). | (i) Only 5 custom-arch tasks; (ii) judge-bias tests missing; (iii) BigCodeBench-Hard gap not diagnosed. |
| How many tokens did we route local vs cloud, per route? | **Data present** in every row (`tokens.local_*` vs `tokens.cloud_*`). | No report section yet turns this into a per-dollar/per-task narrative. |
| What would this have cost on other providers? | **Computable** — `analysis/cost_scenarios.py` does it. | Never published in REPORT as a side-by-side matrix. |
| Does prompt caching change R3's dollar figure? | **Not tested.** R3 still cost-parity with R1, not cost-win. | Need a caching experiment and a re-priced row set. |

**Bottom line: ~70% of the work is data we already have but haven't yet
published cleanly. ~30% is plugging real gaps (bigger N on R4-B, R4 on A
and C, prompt caching, judge-bias, LLM-judge robustness).**

---

## 2. The todos

Each todo is a self-contained unit. Columns:

- **ID** — stable handle used in commit messages (`T-07: …`).
- **Agent type** — which subagent runs it.
- **Inputs / Outputs** — what the agent starts with and what it must
  produce.
- **Done-when** — the acceptance test.
- **Est.** — rough wall-time on M4 Max; does NOT count human review.

Wave A is a verification pass: cheap, parallelisable, unblocks everything
else. Wave B is the new-data sweeps (slower, needs router + Docker). Wave
C is analysis + report generation (depends on A and B). Wave D is the
article + publishing-readiness polish.

### Wave A — audit, schema, and repricing (parallel-safe)

#### T-01 · Schema + invariant audit of the merged dataset
- **Agent.** `codebase-analyzer`
- **Inputs.** `results/raw.jsonl`, `lib/metrics.py`, `lib/results.py`.
- **Outputs.** `docs/audits/T-01-schema-audit.md` containing:
  - Per-variant row counts broken down by (category, route, source).
  - Assertion that **every R2 row has `cloud_prompt+cloud_completion = 0`**
    (routing-bug sentinel from REPORT §8). Any violation listed.
  - Assertion that **no row contains any `cost_*` field** (tokens-first
    invariant).
  - `routing.per_call_backends` coverage — % of rows with a non-empty
    chain, grouped by route.
  - Token-usage histogram per route (prompt / completion / cached /
    reasoning).
- **Done-when.** Audit md committed; zero invariant violations, or every
  violation has a follow-up todo added to this file.
- **Est.** 30 min.

#### T-02 · Pricing-table version stamp + parity re-check
- **Agent.** `general-purpose`
- **Inputs.** `lib/pricing_tables.json`, `router/pricing.mjs`,
  `tests/test_pricing_parity.py`.
- **Outputs.** (i) `lib/pricing_tables.json` with a bumped `_meta.fetched_at`
  *only if* a manual web-fetch of models.dev shows drift — otherwise
  unchanged. (ii) Test assertion added that `_meta.fetched_at` is within
  180 days of today. (iii) `docs/audits/T-02-pricing-audit.md`
  summarising rate deltas versus whatever was pinned on 2026-04-27.
- **Done-when.** `.venv/bin/pytest tests/test_pricing_parity.py -q` green;
  audit md committed.
- **Est.** 20 min.

#### T-03 · Cross-scenario repricing of the 180-row dataset
- **Agent.** `general-purpose`
- **Inputs.** `results/raw.jsonl`, `analysis/cost_scenarios.py`.
- **Outputs.** `results/reprice/cost_by_scenario.csv` — one row per
  `(variant, task_id, route)`, one column per pricing scenario (seven:
  gpt-5.5, gpt-5, gpt-5-mini, gpt-4o, claude-opus-4-7,
  claude-sonnet-4-6, claude-haiku-4-5). Plus
  `results/reprice/summary.md` with `$-per-category-per-route` means
  under each scenario.
- **Done-when.** CSV exists, summary.md committed, `.venv/bin/pytest
  tests/test_results.py -q` green.
- **Est.** 20 min.

#### T-04 · Token-economics split (the "where did the dollars go" answer)
- **Agent.** `general-purpose`
- **Inputs.** `results/raw.jsonl`, `results/reprice/cost_by_scenario.csv`.
- **Outputs.** `results/reprice/token_share.md` with:
  - For each route × category: total cloud tokens, total local tokens,
    ratio, and — under gpt-5.5 — the cost attributable to cloud tokens
    versus the free local tokens.
  - For each route × category: "tokens routed local / total tokens"
    (the routing-efficiency headline per route).
  - A per-step histogram for R3/R4 showing which steps consumed the
    cloud budget.
- **Done-when.** md committed. Numbers cross-check against
  `analysis/aggregate.py` output.
- **Est.** 40 min.

### Wave B — close the data gaps (sequential — each needs the router up)

#### T-05 · R4 Minion on Category A (HumanEval+)
- **Agent.** `feature-dev:code-architect` → spawns implementation.
- **Inputs.** `runners/r4_minion.py`, `benchmark/humaneval_plus/adapter.py`.
- **What to do.** Run R4 across all 10 HumanEval+ tasks. R4 currently
  only executes on Category B; verify its prompt contract works on
  `humaneval_plus` (the Stanford Minion protocol may need the
  "problem_statement" field translated from "prompt"); no runner code
  change unless the sweep errors.
- **Outputs.** `results/runs/05-r4-humaneval/` with the same shape as
  `04-r4-minion/`. Rows tagged `variant: "r4-humaneval"`.
- **Done-when.** 10 rows present; `jq '.quality.functional_pass' ...` shows
  no nulls; `run-notes.md` committed.
- **Est.** ~40 min wall; ~$0.50 API spend at gpt-5.5 rates.

#### T-06 · R4 Minion on Category C (both sub-sources)
- **Agent.** `feature-dev:code-architect` → spawns implementation.
- **Inputs.** Same as T-05 plus `benchmark/bigcodebench_hard`,
  `benchmark/custom_arch`.
- **Notes for the agent.** The Minion protocol was designed for extractive
  Q&A over a context. For `custom_arch` (prose output) we must confirm
  the supervisor/worker loop produces prose — not just yes/no answers.
  If it doesn't, the agent flags it, emits a note, and still records the
  rows with `error="protocol-mismatch"` so we have the honest
  data-point. **Do not silently redesign R4.**
- **Outputs.** `results/runs/06-r4-catc/` (10 rows: 5 bigcodebench_hard +
  5 custom_arch). Rows tagged `variant: "r4-catc"`.
- **Done-when.** 10 rows present or ≤ 10 with errors recorded and noted.
- **Est.** ~1 h wall; ~$1 API spend.

#### T-07 · Three-seed re-run of R4 on Category B
- **Agent.** `general-purpose`
- **Inputs.** Same as the existing `04-r4-minion` run.
- **What to do.** Re-run R4 twice more on SWE-bench Verified (10 tasks)
  with different RNG seeds (`--seed 7`, `--seed 13`). This gives us
  three-sample CIs on the single variant where the REPORT explicitly
  flags `N=10 × 1 sample` as a limitation and the headline win is load-
  bearing (4/10 vs R1 3/10). If the runner doesn't accept `--seed`, add
  it as a first-class flag threaded through the Minion orchestrator
  `temperature`/`top_p` seeds.
- **Outputs.** `results/runs/07-r4-seed7/` and `08-r4-seed13/`. Merge
  into `results/reprice/r4_b_with_ci.csv` (by T-11).
- **Done-when.** 20 additional R4 rows; `run-notes.md` + env manifests
  committed.
- **Est.** ~1 h wall; ~$3 API spend.

#### T-08 · Prompt-caching experiment for R3 (cost-win attempt)
- **Agent.** `feature-dev:code-architect` → spawns a focused diff.
- **Inputs.** `router/agentic/architect-core.mjs`, `runners/_architect_runner.mjs`.
- **What to do.** Turn on OpenAI prompt caching on the *planner prefix*
  and *synth prefix* of R3 (both of which are repeated per step).
  `cached_tokens` already flows into `TokenUsage.cached`, so pricing
  will pick it up. Re-run R3-devstral on Category B's 10 SWE-bench
  tasks; this is the only cell where the cost-parity-not-win finding is
  load-bearing.
- **Outputs.** `results/runs/09-r3-devstral-cached/` with 10 rows tagged
  `variant: "r3-devstral-cached"`. Plus a diff to the router + architect
  code.
- **Done-when.** `cache_read` tokens > 0 on ≥ 7/10 rows (cache actually
  hit). Cost delta vs `03-v2-devstral` recorded in the run-notes.
- **Est.** ~1.5 h (design + implementation + run); ~$1 API spend.

### Wave C — analysis + judge stress-test

#### T-09 · Swap-bias + multi-judge stress-test on custom_arch
- **Agent.** `general-purpose`
- **Inputs.** `scorers/llm_judge.py`, `results/runs/02-v2-qwen-fixed-synth/`.
- **What to do.** Re-run the Opus judge on custom_arch with (a)
  A/B order swapped, (b) Claude Sonnet 4.6 as a second judge, (c)
  GPT-5.5 as a third judge. Compute agreement rate across judges and
  sensitivity to order swap.
- **Outputs.** `results/reprice/judge_robustness.md` + a CSV of all
  pairwise verdicts. If the order-swap flips any R1-vs-R3 verdict, that
  task is flagged as contested in the final REPORT.
- **Done-when.** md + CSV committed. Each task has at least 6 judge
  verdicts (3 judges × 2 orders).
- **Est.** ~45 min; ~$4 API spend.

#### T-10 · Decision matrix with CIs, per scenario
- **Agent.** `general-purpose`
- **Inputs.** Everything produced in Waves A + B.
- **Outputs.** `analysis/decision_matrix_v2.py` and
  `results/reprice/decision_matrix.md`:
  - One 3×4 grid (category × route) per pricing scenario.
  - Cells show pass-rate ± 95% CI (Wilson on N), median tokens routed
    cloud, median tokens routed local, median cost in that scenario,
    median wall-clock.
  - A condensed "which route wins under which scenario" matrix at top.
- **Done-when.** md committed. Every cell has an N > 0 or is marked
  `n/a`.
- **Est.** ~1 h.

#### T-11 · Canonical per-scenario Pareto + heatmap charts
- **Agent.** `general-purpose`
- **Inputs.** T-10 outputs.
- **Outputs.** New charts in `results/reprice/charts/`: pareto-gpt5.5,
  pareto-gpt5-mini, pareto-claude-opus, heatmap-cost, heatmap-quality,
  heatmap-arqgc (one per scenario). Use the existing `analysis/`
  pipeline's style.
- **Done-when.** PNGs checked in; no pyplot warnings in the generation
  log.
- **Est.** ~30 min.

### Wave D — the final report and the article

#### T-12 · Consolidate into a *single* canonical final report
- **Agent.** `feature-dev:code-reviewer` (because this doc must be
  defensible to a skeptical reader).
- **Inputs.** `results/REPORT.md`, everything in `results/reprice/`,
  `docs/METHODOLOGY.md`.
- **Outputs.** `results/FINAL_REPORT.md` — a *new* file that supersedes
  nothing (the existing REPORT.md stays as the historical MVP result).
  Sections:
  1. **The question, restated in token terms.** (tokens-first, API per-M
     pricing, local-vs-cloud routing split.)
  2. **Per-category headline** with CIs from T-07 + T-10.
  3. **Token-economics table** from T-04.
  4. **Multi-scenario decision matrix** from T-10 — the centerpiece.
  5. **Where hybrid wins, where it doesn't**, per route × category ×
     scenario.
  6. **Prompt-caching result** from T-08 — did it flip R3 to a cost win?
  7. **Judge-robustness audit** from T-09 — do the C-category claims
     survive an order swap and a different judge?
  8. **Known limits, now updated** (what's still open after this pass).
  9. **Reproducibility pointer** to `docs/REPRODUCING.md`.
- **Done-when.** Linked from `README.md` under "Start here"; old REPORT
  kept as `results/REPORT_v1_mvp.md` (git mv). `results/FINAL_REPORT.md`
  has no TODO or FIXME.
- **Est.** ~2 h.

#### T-13 · Article postscript update
- **Agent.** `general-purpose`
- **Inputs.** `docs/article-draft-v1.md`, `results/FINAL_REPORT.md`.
- **Outputs.** A second postscript section at the end of the article
  pulling from FINAL_REPORT. Body stays unchanged (it's a narrative
  artifact).
- **Done-when.** Postscript committed, article linted by whatever we use
  (plain markdown for now).
- **Est.** ~45 min.

#### T-14 · Publish-readiness sweep
- **Agent.** `general-purpose`
- **Inputs.** Whole repo.
- **Outputs.** A checklist md at `docs/audits/T-14-publish-readiness.md`
  verifying: (i) every `results/runs/NN-*` dir has a `run-notes.md`;
  (ii) `NOTICE.md` credits every dataset used; (iii) `.env.example`
  matches current env-var names; (iv) router's `logs/decisions.jsonl`
  has been committed (or intentionally .gitignored); (v)
  `results/FINAL_REPORT.md` links are live.
- **Done-when.** Checklist all ticked. Any non-tick item spawns a
  follow-up todo.
- **Est.** ~30 min.

---

## 3. Dependency graph

```
T-01 ─┐
T-02 ─┼─► T-03 ─► T-04 ─┐
      │                 │
T-05 ─┼─► T-07 ─┐        │
T-06 ─┘        │        │
T-08 ─────────►┤        │
               ▼        ▼
               T-10 ◄───T-04
                │
                ├─► T-11 ─┐
                │         │
T-09 ───────────►┤        │
                 ▼        ▼
                 T-12 ◄───T-11
                  │
                  └─► T-13 ─► T-14
```

- **Parallel-safe today:** T-01, T-02, T-03, T-04, T-09.
- **Parallel-safe once router is up:** T-05, T-06, T-07, T-08 (but they
  share the Docker + router host, so serialise if either saturates).
- **Strict sequence:** T-10 → T-11 → T-12 → T-13 → T-14.

---

## 4. Budget

Under **official gpt-5.5 + claude-opus-4-7 API pricing** (the exact
rates pinned in `lib/pricing_tables.json`):

| wave | wall | API $ |
|---|---|---|
| A  | ~2 h  | $0 (re-pricing only; no inference) |
| B  | ~4 h  | ~$5.50 (R4 on A + C + 2 seeds on B + R3-cached) |
| C  | ~2 h  | ~$4 (triple-judge re-score on 5 custom_arch tasks) |
| D  | ~4 h  | $0 (docs) |
| **total** | **~12 h** | **~$10** |

That's ~2/3 of an M4-Max day plus $10 of API. Fits comfortably under the
original MVP budget (REPORT §"Budget used" = ~$12).

---

## 5. What "done" looks like

A reviewer reading `results/FINAL_REPORT.md` cold, without ever running
the code, can answer:

- "For a 20 USD of API spend, how many real SWE-bench tickets could I
  resolve under R1 vs R4?" — **yes**, from the token-economics and
  decision-matrix tables.
- "Would switching my cloud leg from gpt-5.5 to claude-sonnet-4-6
  change which route I should pick on Category C?" — **yes**, from the
  multi-scenario matrix.
- "Does R3's cost-parity become a cost-win with prompt caching on?" —
  **yes, with a number**, from T-08.
- "Are the Category C judge verdicts robust to judge family and order?"
  — **yes, with a number**, from T-09.

---

## 6. What we are explicitly NOT doing in this plan

- **No new hardware tier.** MVP's single-tier caveat stays open. Adding
  a mid-tier M2 16 GB run is post-publication work.
- **No R5 (Aider architect/editor review loop).** PLAN.md already flags
  this as post-MVP. We keep it out-of-scope here so the report ships.
- **No new benchmarks.** We stick to the four already ingested.
- **No change to the tokens-first invariant.** Every change in this plan
  preserves it.

---

## 7. Agent briefing template

When spawning a subagent for any todo, use this shape so context is
self-contained:

```
Task: <T-NN title>
Repo root: /Users/sanchitmonga/development/ODLM/MONOREPOOO/CODING/hybrid-coding-eval
Single commit required; no --no-verify.
Guardrails:
 - Tokens are primary; do not write cost fields into raw.jsonl.
 - Preserved runs (results/runs/01-*, 02-*, 03-*, 04-*) are read-only.
 - Start the router (cd router && ./start.sh) if you need R1/R3/R4.
 - Test gate: .venv/bin/pytest tests/ -q -m 'not slow'.
Inputs: <listed files + any CSV the todo depends on>
Outputs: <exact paths required>
Done-when: <acceptance test>
If you discover a bug outside this todo's scope, add a new
follow-up todo to docs/FINAL_REPORT_PLAN.md §2 in the same commit —
do not expand your diff.
```
