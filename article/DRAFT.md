# Hybrid local/cloud routing for coding agents: the data says don't bother (yet)

We built a hybrid local/cloud routing system for coding agents. Ran it on 30 public-benchmark tasks. On the 10 tasks we have final data for, hybrid is Pareto-dominated by plain cloud-only *and* plain local-only — on every axis. It's slower, more expensive, and it introduces quality regressions that neither of its constituent parts have.

This supersedes a [previous write-up](#) based on 3 hand-curated tasks where the framing was "hybrid is 1.3-3.2× more expensive on small tasks, but saves 60%+ when you decompose anyway". The cost finding held up under replication. The "saves 60%+" framing was a comparison against a straw-man all-cloud decomposition that nobody would actually run. What we have now is a proper benchmark.

The dataset is incomplete — SWE-bench Verified runs are still going, BigCodeBench-Hard hasn't started. The category where hybrid *should* win (multi-file engineering with real decomposability) is the one we can't yet speak to. Everything below about HumanEval+ (Category A) is final.

---

## What we tested

30 tasks, stratified:

- **A — HumanEval+** (10 tasks). Tiny function completion, ≤20 LOC, assertion-scored.
- **B — SWE-bench Verified** (10 tasks). Real PRs against real repos, patch-applied and tested.
- **C — BigCodeBench-Hard + custom architecture** (5 + 5). Multi-file, LLM-judged.

Three routes:

- **R1 — cloud-only** — every call to `gpt-5.5-2026-04-23`. Control.
- **R2 — local-only** — every call to `qwen3.6:27b-coding-mxfp8` on an M4 Max via Ollama.
- **R3 — hybrid-architect** — cloud planner decomposes the task, each step gets routed local-or-cloud by heuristic, cloud synthesiser stitches the outputs. The router under test.

Single hardware tier (M4 Max, 64 GB). Five pricing scenarios, default is `openai-gpt5.5`. Full protocol in [`results/full-sweep/REPORT.md`](../results/full-sweep/REPORT.md).

---

## Headline findings (Category A, N=10)

On tiny function-completion tasks, hybrid lost to both cloud-only and local-only on every axis that matters.

| Metric | R1 cloud | R2 local | R3 hybrid |
|---|---:|---:|---:|
| Functional pass rate | **1.00** | **1.00** | **0.80** |
| Median wall time | 4.7 s | 17.5 s | **78.2 s** |
| Median cost (gpt-5.5) | $0.011 | $0.000 | $0.033 |
| Mean total tokens | 463 | 357 | 7,014 |

Four things jumped out:

**1. Both single-shot routes hit 100% pass rate. Hybrid hit 80%.** HumanEval+ is easy enough that both `gpt-5.5` and `qwen3.6:27b` saturate it at single-shot. The hybrid pipeline — which uses the same underlying models as R1 and R2 — scores lower than either of them in isolation.

**2. 62% of hybrid's tokens were served locally, yet hybrid cost 3× more than cloud-only.** The architect routed 43,441 of 70,137 tokens to the local box. "Local-majority" sounds like "cost-cheap". It isn't. The 38% that stayed cloud (2,670 tokens/task mean, mostly planner + synthesiser) was 5.8× the cloud-priced tokens R1 uses in a single call. Local-majority ≠ cloud-cheap.

**3. Hybrid is 16× slower and uses 15× the tokens to produce worse answers.** Median R3 run: 6 calls, 4,893 prompt tokens, 78 seconds wall. Median R1 run: 1 call, 137 prompt tokens, 4.7 seconds. The context-replay cost of the architect pattern (each step sees the plan + all prior step outputs + current step spec) is fixed per step; on a 15-line function it has nothing to amortise against.

**4. Hybrid introduced quality regressions neither R1 nor R2 had.** This is the one we did not expect. On the 2 tasks R3 failed, *both R1 and R2 succeeded*. Same base models, same prompt. The hybrid pipeline is actively degrading quality below both of its parts.

---

## The two R3-only failures

### HumanEval/103 — spec loss during planning

The task: `rounded_avg(n, m)` returns the rounded average of the integers from `n` through `m` as a binary string.

- **R1** (single cloud call): `sum(range(n, m+1)) / (m-n+1)` → round → `bin()`. Passes.
- **R2** (single local call): same approach, same correctness. Passes.
- **R3** (architect loop, 7 calls, 114 s): planner decomposed into 6 steps. Step-workers saw the docstring. The synthesiser emitted:

```python
avg = (n + m) / 2
```

That's the midpoint of two numbers, not the average across the range. Wrong on `rounded_avg(20, 33)`. The docstring said "average from n through m"; decomposition lost the distinction between "average of the range" and "(n+m)/2". The cloud synthesiser accepted the wrong reformulation.

This is a spec-loss failure introduced by decomposing an atomic task.

### HumanEval/15 — synthesis-layer indentation bug

The task: `string_sequence(n)` returns `"0 1 2 ... n"` as a space-separated string.

Both R1 and R2 emit the one-liner `return ' '.join(str(i) for i in range(n+1))`. R3 emits something like:

```python
def string_sequence(n):
    if n < 0: return ''
     return ' '.join(str(i) for i in range(n + 1))
```

Spot the bug: the `if` line has 4-space indent, the `return` line has 5. `IndentationError` at import. Every test fails on parse, not on logic.

This is the cloud synthesiser stitching step outputs without whitespace normalisation. Mechanical, fixable — and present as shipped.

Both failures are fixable in `router/agentic/architect.mjs`. Both are fair game for the measurement: the router as shipped has these failure modes.

---

## Where the cost actually goes

Mean tokens per task on Category A:

| Route | Prompt | Completion | Total | vs R1 |
|---|---:|---:|---:|---:|
| R1 | 144 | 319 | 463 | 1.0× |
| R2 | 160 | 197 | 357 | 0.8× |
| R3 | 5,115 | 1,899 | 7,014 | **15.1×** |

The 15× blow-up is context replay. Each step in the architect loop receives (planner output) + (all prior step outputs) + (current step spec). On a median 6-step R3 run, prompt tokens scale superlinearly; the average prompt-tokens-per-call lands around 815 on a task whose ground-truth answer is 15 lines of Python.

This is the structural reason hybrid loses on small tasks. The per-step context replay is fixed overhead, and on atomic tasks there is nothing to amortise it against.

Under alternative pricing the ratio holds. `gpt-5-mini` at the cheap end: R3 is still 3× R1. `claude-opus-4.7` at the expensive end: R3 is still ~3× R1. Changing the vendor does not rescue hybrid on tiny tasks.

---

## What we can't yet say

Category B (SWE-bench Verified) is where R3 was designed to win:

- Long completions, where local tokens pay off most (R2/R3 marginal cost ≈ $0 per local token).
- Genuinely decomposable tasks — locate file, read symbol, write patch, write test, verify — unlike HumanEval's one-pass generate.
- A quality ceiling that is nowhere near saturated. State-of-the-art SWE-bench Verified pass rates are well below 1.0, so a hybrid loop has room to add value instead of strictly subtracting.

So far we have **one** scored B run. R1 on `sphinx-doc/sphinx-7889`: 7,008 completion tokens, 96.7 s wall, $0.21 under `gpt-5.5`, $0.53 under `claude-opus-4.7`. That's a ~20× per-task cost jump from A — exactly the regime where hybrid routing should start to earn its keep.

We cannot claim anything about hybrid on B yet. R3 hasn't completed a B task. If hybrid wins anywhere, it wins here, and we're still running that experiment.

Category C hasn't started.

---

## Decision matrix

| If you are doing… | Use route… | Because… |
|---|---|---|
| Tiny function-completion (HumanEval-shaped) on a cloud budget | **R1** | Single-shot cloud: fastest, cheapest, saturates quality. |
| Tiny function-completion where you can tolerate ~17 s latency and want zero marginal cost | **R2** | Local `qwen3.6:27b` matches quality on HumanEval+ at $0. |
| Tiny function-completion with a hybrid router | **not R3** | 15× tokens, 16× wall, 3× cost, worse quality. |
| Real software engineering (SWE-bench-shaped) | **insufficient data** | Only R1 has a scored run. Report will be refreshed when B lands. |
| Architecture / design reasoning | **no data yet** | Category C has not started. |

With the data we have today, R3 is not recommended for anything. R1 is the safe default. R2 is the cheap default if you can absorb the latency. R3's thesis is not yet disproven — it just isn't tested on the tasks where it could win.

Note the Category A contamination caveat. HumanEval is in every major model's training corpus since 2022. "R2 matches R1 on HumanEval+" is at least partially a memorisation result. We chose HumanEval+ as a control, not a benchmark — the expectation was that both saturate. The novelty test is Category C, when it runs.

---

## What we'd change

From the failure modes observed:

- **Gate R3 on task size.** A pre-classifier — "this is ≤1 function ≤20 LOC → route straight to R1 or R2, skip the architect" — would eliminate every R3 regression we saw.
- **Spec-preservation check in the synthesiser.** One extra cloud call: "does my final output satisfy the original docstring and tests?" would have caught HumanEval/103.
- **Whitespace normalisation in the synthesiser.** Fixes HumanEval/15-class failures mechanically.
- **Learned router.** Replace the current heuristic (`local if score>=25`) with a classifier trained on `(task features → optimal route)` from this run plus future runs. The heuristic is a snapshot, not an end state.

Also on the list: prompt caching on the planner/synth prefixes (they re-send stable context every call), truncating or summarising prior-step context in executor prompts (the dominant prompt-token cost), and a second hardware tier so the M4-Max-pinned results stop dictating the picture.

---

## Reproducibility

Full protocol, raw runs, pricing scenarios, ARQGC discussion, and limitations in [`results/full-sweep/REPORT.md`](../results/full-sweep/REPORT.md). Regenerate all aggregates from `raw.jsonl` with `python -m analysis.all results/full-sweep/`.

---

## Where this lands

The headline from the original 3-task write-up — *"hybrid is 1.3-3.2× more expensive than single-shot cloud on tasks cloud can do in one call"* — replicates. We have N=10 functional tests now instead of N=3 eyeball comparisons, and the direction is the same.

The new finding is qualitative, not quantitative: hybrid doesn't just cost more on small tasks, it produces *worse code* on small tasks. When R2 alone solves a problem and R3 — which uses R2 as one of its components — gets it wrong, that's a pipeline bug, not a model bug. The architect's decomposition is destroying information on tasks it shouldn't have been dispatched to in the first place.

The interesting question is still open: does the architecture pay off on tasks genuinely worth decomposing? We'll refresh this when B and C complete. Until then: for HumanEval-shaped workloads, don't reach for the hybrid router. Use R1 if you're paying per token, R2 if you're not.
