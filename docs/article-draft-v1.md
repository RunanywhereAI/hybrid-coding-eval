# [v1 DRAFT] Hybrid local/cloud routing for coding agents: the data says don't bother (yet)

> ⚠️ **Superseded twice — first by the v2 postscript (inline below), now by the v3 canonical
> article.** The canonical publication is [`reports/ARTICLE.md`](../reports/ARTICLE.md) which
> presents the same data under a multi-scenario decision matrix with Wilson 95% CIs and
> includes the new R4-on-Cat-A + R4-on-Cat-C sweeps. This file is kept for lineage only.
>
> **Read order for the current claims:** 1) `reports/ARTICLE.md` · 2) `reports/APPENDIX_TASKS.md`
> (every row's prompt + output + score) · 3) `reports/APPENDIX_SCENARIOS.md` · 4)
> `reports/APPENDIX_ROUTES.md`. The MVP `results/REPORT.md` is preserved verbatim at
> `results/REPORT_v1_mvp.md`.


We built a hybrid local/cloud routing system for coding agents. Ran it on 30 public-benchmark and hand-curated tasks spanning tiny-function-completion (HumanEval+), real software engineering (SWE-bench Verified), and architecture/reasoning (BigCodeBench-Hard + 5 hand-curated design tasks). **On every category, the hybrid route was Pareto-dominated by plain cloud-only and plain local-only.** It's slower, more expensive, and it introduces quality regressions that neither of its constituent parts have — including on the one category the hybrid pipeline was explicitly designed to win (SWE-bench).

This supersedes a [previous write-up](#) based on 3 hand-curated tasks where the framing was "hybrid is 1.3-3.2× more expensive on small tasks, but saves 60%+ when you decompose anyway." The cost finding replicates. The "saves 60%+" framing was a comparison against a straw-man all-cloud decomposition that no rational user would run; under a fair head-to-head the savings vanish.

Raw numbers, scoring harnesses, and per-task outputs are in [`results/full-sweep/REPORT.md`](../results/full-sweep/REPORT.md). Everything below is reproducible from a single `raw.jsonl` file.

---

## What we tested

30 tasks, stratified:

- **A — HumanEval+** (10 tasks). Tiny function completion, ≤20 LOC, pytest-scored.
- **B — SWE-bench Verified** (10 tasks). Real PRs against real repos, scored by `mini-swe-agent` running the repo's own test suite in Docker.
- **C — BigCodeBench-Hard + custom architecture** (5 + 5). BigCodeBench is pytest-scored; the custom-arch tasks are scored by a bias-corrected pairwise LLM-judge.

Three routes:

- **R1 — cloud-only** — every call to `gpt-5.5-2026-04-23`. Control.
- **R2 — local-only** — every call to `qwen3.6:27b-coding-mxfp8` on an M4 Max via Ollama.
- **R3 — hybrid-architect** — cloud planner decomposes the task; each step gets routed local-or-cloud by a heuristic; a cloud synthesiser stitches the outputs. The router under test.

Single hardware tier (M4 Max, 64 GB). Five pricing scenarios; default is `openai-gpt5.5`. Full protocol in [`results/full-sweep/REPORT.md`](../results/full-sweep/REPORT.md).

---

## Headline results (all 30 tasks, final)

| Category | R1 pass | R2 pass | R3 pass | R1 $ median | R3 $ median | R3 wall vs R1 |
|---|---|---|---|---|---|---|
| A (HumanEval+, N=10) | **10/10** | **10/10** | 8/10 | $0.011 | $0.033 (3.1×) | 17× slower |
| B (SWE-bench Verified, N=10) | **3/10** | 1/10 | 1/10 | $0.126 | $0.146 (1.2×) | 4.7× slower |
| C (BigCodeBench-Hard + custom-arch, N=10) | 0.51 mean¹ | 0.64 mean¹ | 0.29 mean¹ | $0.143 | $0.206 (1.4×) | 6.1× slower |

¹ Category C uses a composite of functional pass (BigCodeBench) and LLM-judge verdict (custom-arch). The absolute composite mean is dragged down by a runner bug — see §"Where hybrid loses on C" below.

**R3 never wins.** Not on A (where it was expected to lose but we measured how badly), not on B (where the architecture was supposed to help), and not on C (where decomposition was supposed to help most of all). On every category, at every pricing tier, R1 is cheaper and better than R3, and R2 is free and comparably good or only slightly worse.

---

## Category A — hybrid loses cleanly on tiny function-completion (expected, now measured)

Both R1 and R2 pass all 10 tasks. R3 passes 8 — it fails `HumanEval/15` and `HumanEval/103`, both of which R1 and R2 solve.

- **`HumanEval/103` — spec loss during planning.** Task: `rounded_avg(n, m)` returns the rounded average of integers from `n` through `m` as a binary string. The planner decomposed the task into 6 steps; along the way the spec was restated as "midpoint of n and m" — wrong. The synthesiser accepted the wrong reformulation. R1 and R2 each read the docstring directly and got it right.
- **`HumanEval/15` — synthesiser indentation bug.** The synthesiser stitched per-step code without re-aligning whitespace. The output has a 4-space-indent `if` followed by a 5-space-indent `return` — `IndentationError` on parse.

Both failure modes are structural to the plan-execute-synth pattern. The planner is the last LLM to see the unmodified prompt; if it drops or rewrites a constraint, the rest of the pipeline cannot recover.

R3 on A used **15× more tokens, 17× longer wall time, 3.1× higher cost** than R1 — and scored lower. Under alternative pricing the cost ratio holds: `gpt-5-mini` → R3 is still 2.9× R1; `claude-opus-4.7` → R3 is still 3.2× R1. Vendor swap doesn't rescue hybrid on tiny tasks.

---

## Category B — hybrid loses on real software engineering (not expected)

This is the category R3 was designed for. Long-context reasoning, multi-file edits, decomposable into "locate file, read symbol, write patch, write test, verify". Quality ceiling is well below 1.0 (state-of-the-art SWE-bench Verified pass rates are ~77% for frontier models, ~72% for best specialised open models). Plenty of room for hybrid routing to add value instead of subtracting.

It still loses. Per-task matrix:

| task | R1 | R2 | R3 |
|---|---|---|---|
| astropy-7166 | **P** | F | F |
| django-11163 | P | F | P |
| **django-11179** | P | **P** | **F** |
| django-13512 | F | F | F |
| django-15315 | F | F | F |
| django-15863 | F | F | F |
| pydata-xarray-4356 | F | F | F |
| sphinx-7889 | F | F | F |
| sphinx-9698 | F | F | F |
| sphinx-9711 | F | F | F |

Final: R1 3/10, R2 1/10, R3 1/10.

**`django-11179` is the single most instructive row in the entire dataset.** R1 passes with 141 prompt / 4,265 completion tokens. R2 passes with **304 total tokens** — qwen produced a correct 1-line-change unified diff on the first try. R3 fails the same task after burning 12,992 local + 4,084 cloud prompt + 2,811 local + 3,646 cloud completion tokens (23,533 total). The hybrid pipeline took a trivially-correct local solve and turned it into a 23k-token failure. The SWE-bench harness reported `patching file django/db/models/deletion.py ... hunk #1 FAILED` — R3's synth produced a diff whose hunks didn't apply cleanly. The plan-execute-synth layer introduced enough reformulation that the final patch became subtly wrong.

On every B task that R1 passes, R3 either ties or loses. R3 does not solve a single task that the baselines don't already solve.

---

## Where hybrid loses on C — and where the scoring is compromised

C is the category that's most useful *and* most damaged by a runner bug. 4 of 5 hand-curated architecture tasks showed **R1 and R3 producing 0-byte outputs** because `gpt-5.5`'s reasoning_tokens consumed the entire `max_tokens=2500` budget, leaving nothing for actual text output.

Example: `custom-arch/auth-multitenant-design` R1 row, from `raw.jsonl`:

```jsonc
"tokens": {"completion": 8000, "reasoning": 8000, ...},
"output_ref": "...auth-multitenant-design_R1.txt"  // 0 bytes
```

The model was billed for 8,000 completion tokens (8,000 of which were reasoning). Zero ended up in the written text. This is an implementation bug in how we call the reasoning-tokens API, not a routing finding. But until the bug is fixed, any C-category benchmark that includes open-ended prose tasks will systematically depress R1 and R3 relative to R2, because R2 doesn't route through the OpenAI reasoning pathway and doesn't hit this failure.

The one complete three-way judgment we have — `cache-invalidation-tradeoffs` — is revealing despite the other four rows being contaminated. R1 (with useful output) wins 5.0/5 vs R2 4.0/5 on a 5-dimension rubric. The judge caught substantive wins for R1: atomicity gaps in write-through, CDC lag/order/loss edge cases, replica-lag pitfalls that R2 missed. **R3 on the same task produced empty output** — so the one cell where gpt-5.5's advantage showed up cleanly, R3 didn't even get to compete.

BigCodeBench-Hard (the pytest-scored half of C): R1 2/5, R2 1/5, R3 1/5. The one common pass is `BigCodeBench/530` across all three routes. R3 added nothing.

---

## Where the cost actually goes

Token totals across the full 30-task sweep:

| Route | cloud prompt | cloud completion | local prompt | local completion | total |
|---|---:|---:|---:|---:|---:|
| R1 | 7,037 | 92,774 | 0 | 0 | 99,811 |
| R2 | 0 | 0 | 7,708 | 20,842 | 28,550 |
| R3 | 159,700 | 107,748 | 234,838 | 89,340 | **591,626** |

R3 burns **5.9× more total tokens than R1** and **20.7× more than R2**. The structural reason: each step in the architect loop receives (planner output) + (all prior step outputs) + (current step spec). On a median 6-step R3 run on A, prompt tokens scale superlinearly; average prompt-tokens-per-call lands around 850 on a task whose correct answer is 15 lines of Python. B tasks see similar overhead — 12k local-prompt tokens per task, most of which is context replay.

"62% of R3's tokens are local" sounds like "cost-cheap." It isn't. The 38% cloud fraction still adds up to 2.8k cloud prompt + 2.3k cloud completion per task on A, which is 5× what R1 spends on a single call.

---

## Decision matrix

With 30 tasks and three routes scored:

| If your task is… | Use route… | Why |
|---|---|---|
| Tiny function-completion (HumanEval-shape) on a cloud budget | **R1** | 1.0 pass-rate, $0.011 median, 4.7 s wall. Uncontested. |
| Tiny function-completion where you can absorb ~17 s latency | **R2** | 1.0 pass-rate at $0 marginal cost. |
| Real multi-file engineering (SWE-bench-shape) | **R1** | 3/10 pass for $0.126 median. R3 gets 1/10 for $0.146. |
| Architecture / design / code-review reasoning | **R1 (once the synth-budget bug is fixed) or R2** | R1 has the reasoning headroom; R2 is the most consistent working output today. |
| "I just want to try hybrid for something" | **not R3 as built** | Every category, every budget, R3 is worse. |

R3 is not recommended for anything we measured.

---

## What would change this finding

Honest list of things that might flip the result, in decreasing likelihood:

1. **Fix the synth-budget bug for `gpt-5.5`.** ~1 hour of work. Would let R1 and R3 produce real output on custom-arch tasks, and probably let R3 claw back some C-category ground.
2. **Swap qwen3.6:27b-coding-mxfp8 for a SWE-bench-specialised local model** (Devstral-Small-2-24B is the obvious candidate — 72% on SWE-bench-Verified, 5pp behind Claude Opus). A stronger local model means more steps can stay local without quality regressions; R3's architecture would finally have a reason to exist.
3. **A learned router.** Current heuristic is rule-based. An embedding-kNN router calibrated on this dataset plus more could shift more steps local without degrading quality.
4. **Tasks whose size exceeds R1's single-call capacity.** None of our 30 tasks require decomposition. A 200k-token refactor would force the comparison.
5. **A different hybrid pattern.** R3 is plan→execute→synth. Minions-style stateful Q&A (R4 in our original plan) and Aider's architect/editor review loop (R5) are architecturally different and might have different cost-quality curves. We haven't tested those.

None of these are load-bearing for the MVP claim: **as-implemented hybrid-architect on M4 Max using gpt-5.5 + qwen3.6:27b is worse than both baselines on every measured axis.**

---

## Where this lands

The 3-task pilot's headline — "hybrid is 1.3-3.2× more expensive than single-shot cloud on small tasks" — replicates at 30 tasks. The new finding is harder-hitting: on the category hybrid was designed for (SWE-bench), it *still* loses to both baselines. The local-tokens-are-free economics don't beat the decomposition overhead of the pipeline as shipped.

Three things about the headline that matter for anyone tempted to deploy a hybrid router in production today:

- **R3's cloud-token count is dominated by planner + synth prefixes**, not by hard executor steps. If your optimisation target is $/task, shrinking those prefixes (prompt-caching, aggressive truncation of prior-step context) is where the gain is. Routing more steps local doesn't help until you fix the structural prompt bloat.
- **R3 introduces regressions the baselines don't have** — indentation bugs, spec rewrites, failed-patch-application. The architect is actively degrading answers, not just increasing overhead.
- **R2 is underrated.** On the one SWE-bench task R2 passes, it does so with 304 total tokens. On the custom-arch code-review task, R2 produced a genuinely useful 1,500-word analysis. Qwen3.6:27b-coding on a laptop is not the limiter; the hybrid pipeline is.

For HumanEval-shaped workloads: use R1 if you're paying per token, R2 if you're not. For SWE-bench-shaped workloads today: use R1 — and hope future iterations of the hybrid pipeline earn their keep. We'll re-run the benchmark with the synth-budget bug fixed and a learned router in the next round and see if the direction changes.

---

## Postscript — the direction DID change

After publishing the above we ran the fix round two readers asked for: (1) bump the reasoning-model completion budget so R1 and R3 stop producing 0-byte synth outputs; (2) re-judge with `claude-opus-4-7` cross-vendor instead of the same-family `gpt-5` fallback; (3) swap the local model from `qwen3.6:27b-coding-mxfp8` to `devstral:24b` (a SWE-bench-specialised checkpoint). We also shipped R4 — a Stanford Minion-style supervisor/worker hybrid, running on SWE-bench only.

What shifted (full numbers in [`results/full-sweep/REPORT.md`](../results/full-sweep/REPORT.md) §12):

- **Category C ties.** Opus's pairwise judge calls R3 ≈ R1 on all 5 hand-curated architecture tasks (tie on 4, R1 slight win on 1). R3 was only losing because reasoning tokens ate the 2500-completion budget on the synth call; with `maxTokens=16000` the synth actually produces 20-30 KB of prose and the judge rates it equivalent to R1's single-shot output.
- **Category B gets competitive.** R3-with-Devstral passes 3/10 on SWE-bench Verified — matches R1 cloud-only at $0.144/task (vs $0.126 R1). Quality parity, 62% local tokens. Not yet cheaper, but also not the blowout R3-with-qwen was.
- **R4 wins outright on SWE-bench.** 4/10 pass rate on the same 10 tasks — R4 uniquely solves `sphinx-7889` and `sphinx-9698` that no other route does. Median wall 155s, cost ~$0.08/task — both cheaper and more accurate than R1. The mechanism: Minion's supervisor asks targeted Q&A to the local worker instead of replaying full context to the cloud on every step; less cloud bloat, more attention on the bug.
- **Qwen R3 regressions on A disappear with Devstral.** R3-devstral 10/10 on HumanEval+, no spec-loss on /103, no indentation bug on /15. The pipeline wasn't inherently destructive — it was amplifying qwen3.6's specific weaknesses.

**Revised headline:** hybrid patterns are not uniformly worse than cloud-only. The v1 claim "R3 is Pareto-dominated on every category" was driven by a runner bug (synth budget) + a weak local model for SWE-bench + a narrow decomposition pattern (plan-execute-synth). Close those three things and the picture flips: **R3 ties R1 on architecture/reasoning**, **R3-devstral matches R1 on SWE-bench**, and **R4 (Minion-style Q&A) beats R1 on SWE-bench**.

We're not claiming R4 is the right default today — 10 tasks is not enough to declare a winner. But the direction of the finding now points the other way: hybrid routing *can* be Pareto-improving if the implementation doesn't fight itself. The open question for the next round is: does R4 hold on a 30-task SWE-bench sweep, and does a learned router let R3 close the cost gap?
