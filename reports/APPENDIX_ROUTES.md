# Appendix C — per-route worked examples

A single worked example per route, showing the full path from problem
statement → prompt sent → model output → score. Complements
`reports/APPENDIX_TASKS.md` which covers *every* row.

---

## R1 — cloud-only (gpt-5.5)

**How it works.** Single `chat.completions` call to gpt-5.5 via the
router's `always-cloud` pseudo-model. No planning, no routing
decisions. Fastest to implement, fastest to respond.

**Worked example: `humaneval-plus/HumanEval_99` (Cat A).**

- Problem: complete `def closest_integer(value: str) -> int` that
  rounds a decimal string to the nearest integer, with half-to-even
  wrong and half-away-from-zero right.
- Prompt: the full docstring-adorned function stub wrapped in the
  R1 template (see `APPENDIX_TASKS.md` for the prompt reconstruction).
- Output: a single fenced Python block with the completion.
- Score: **PASS** (1/1 pytest).
- Tokens: cloud=527 (prompt=175, completion=352, reasoning=163).
- $ under gpt-5.5: $0.0114.

**Where R1 shines.** Cat A — every HumanEval+ row passes under R1 in
the MVP dataset. Small tasks fit in one cloud call. No hybrid
overhead justifies itself here.

**Where R1 loses.** Cat B at 3/10. Real software-engineering tasks
need multi-turn exploration; a single-shot prompt to gpt-5.5 often
misses the required file context.

---

## R2 — local-only (devstral:24b / qwen3.6:27b)

**How it works.** Single call to the local Ollama model via
`router/always-local`. 100% local, $0 cloud cost.

**Worked example: `humaneval-plus/HumanEval_13` (Cat A).**

- Problem: greatest common divisor of two ints.
- Prompt: same R1 template, but routed to devstral:24b.
- Output: devstral's completion. Structurally clean because it's a
  small self-contained task.
- Score: PASS (all HumanEval+ tests pass).
- Tokens: local=621 (prompt=182, completion=439).
- $ under every scenario: $0.00.

**Where R2 shines.** Cat A matches R1 at 9/10 — the local model is
fully capable on small function-completion tasks. Zero cost.

**Where R2 loses.** Cat B at 1/20 across both local models. The
24B / 27B models don't have enough reasoning context for real SWE-bench
issues. Also weaker on novel library APIs in Cat C BigCodeBench.

---

## R3 — hybrid architect (cloud planner → executor → cloud synth)

**How it works.** Three-phase pipeline:

1. **Planner** — gpt-5.5 decomposes the task into a JSON array of
   steps. Each step has `router_hint: auto|local|cloud`.
2. **Executor** — for each step, the heuristic router picks cloud or
   local based on the step's content (complexity keywords, token
   count, tool use). Most steps go local.
3. **Synth** — gpt-5.5 takes the step outputs and writes the final
   deliverable.

**Worked example: `custom-arch/auth-multitenant-design` (Cat C,
Opus-judged).**

- Problem: design a multi-tenant auth system with Postgres RLS,
  hybrid JWT+refresh, and named pitfalls.
- Planner output: 8 steps (analyse requirements, schema, RLS, JWT,
  login flow, refresh flow, pitfalls, assemble).
- Router trace: steps 1–6 routed local; step 7 + synth routed cloud.
- Output: 8 KB of prose with inline SQL + JWT claim diagrams.
- Score (Opus judge, T-14 triple-verify): **tie** with R1.
- Tokens: cloud=24,561 (planner+synth), local=19,382 (exec steps).
- $ under gpt-5.5: $0.72 / row.

**Where R3 shines.** Cat C custom_arch — ties R1 on 4/5 prose tasks
under Opus judge, confirmed under Sonnet + gpt-5.5 judges (T-14). The
local executor handles the schema/JWT generation; cloud planner +
synth hold the plan together.

**Where R3 loses.** Cat B at 4/20 (both local models). The heuristic
router sends too many steps local on SWE-bench, where even the easy
tier needs cloud-grade reasoning at each step. The cost also piles up
— R3 is the most expensive route in absolute dollars ($12.20 total
across 69 rows on gpt-5.5).

**The prompt-caching claim.** §6 of the article explains why
enabling `router.prompt_cache: true` doesn't actually reduce cost:
OpenAI's cache needs a 1024-token prefix match and R3's static
prompts are 400 + 80 tokens. See `archive/docs/T-13-analysis.md`.

---

## R4 — Minion (cloud supervisor asks local worker targeted questions)

**How it works.** Port of Stanford's Minion protocol
(`vendor/minions/minions/minion.py`). Two agents:

1. **Supervisor** — cloud (gpt-5.5) — sees the *task* (not the full
   context) and decides what to ask the worker.
2. **Worker** — local (devstral:24b) — sees the *full context* (the
   repo / problem statement / long prose), answers the supervisor's
   questions, provides the final answer when the supervisor says
   `provide_final_answer`.

Supervisor never re-reads the full context. Local worker never
re-asks the task. This is the key token-economy win: context stays
local, queries go over the cloud.

**Worked example: `swebench-verified/sphinx-doc__sphinx-7889` (Cat B).**

- Problem: Django-style issue in Sphinx. Bug report ~2 KB.
- Minion round 1: supervisor reads the short problem statement, asks
  worker "what's the current behavior when generic-types are used as
  argument defaults? Show me the relevant code path."
- Worker round 1: reads the repo + commit, answers with the specific
  lines + ~50 tokens of explanation.
- Minion round 2: supervisor asks for a patch proposal.
- Worker round 2: generates a unified diff.
- Minion round 3: supervisor says `provide_final_answer` with the diff.
- Score: **PASS** (one of the 4/10 R4 victories).
- Tokens: cloud=14,965 (supervisor back-and-forth), local=1,908
  (worker's full-context reads).
- $ under gpt-5.5: $0.22 / row.

See `results/runs/04-r4-minion/minion_logs/` for the verbatim
multi-round Q&A transcripts on every row.

**Where R4 shines.** Cat B — 4/10 pass, one more than R1. Specifically
wins on `sphinx-doc/sphinx-7889` and `sphinx-doc/sphinx-9698` that no
other route solves. The targeted-question pattern works when the
problem hides inside a long repo context.

**Where R4 loses.** Cat A — matches R2 at 9/10, loses to R1 at 10/10.
Cat C BigCodeBench — 1/5, worst of any route. The Minion protocol
has no advantage when the answer is a library-API choice the local
model doesn't know anyway. custom_arch under R4 (4/5 in run 07) is
judge-scored; the triple-judge robustness audit in run 11 covered
only D3+D4 — custom_arch verdicts remain single-judge single-order.

**v3 caveat.** Run 07 (the canonical v3 sweep) showed R4's median
cloud_fraction is **87%**, not the 60–80% target the original Minion
paper implied. The supervisor still does most of the drafting; the
local worker is consulted for context, not for output volume. See
`reports/ARTICLE.md` §4 for the token-economics replication note.

---

## R5 — Stanford DevMinion architect/editor review-loop

**Why we built R5.** The R5 DevMinion route is the most aggressive
hybrid in this study: it tries to keep the local model in the
driver's seat for the actual writing (the "editor" role) while a
cloud architect plans and a cloud reviewer gates each step.
R5 — unlike R4 — passes drafts back and forth across rounds, so
context is replayed and tokens compound. The v3 sweep was the
first time R5 ran on all four categories.

**How it works.** Port of Stanford's DevMinion protocol
(`vendor/minions/minions/minion_code.py`, MIT-licensed). Three
phases, both clients pointed at the local router proxy on `:8787`:

```text
       ┌─────────────────────────┐
       │   cloud architect       │   gpt-5.5 (router/always-cloud)
       │   generates runbook     │
       │   = list of N steps     │
       └────────────┬────────────┘
                    │ per step
                    ▼
       ┌─────────────────────────┐
       │   local editor          │   devstral:24b (router/always-local)
       │   implements step k     │
       └────────────┬────────────┘
                    │ deliverable
                    ▼
       ┌─────────────────────────┐
       │   cloud reviewer        │   gpt-5.5
       │   approve | request     │
       │   edits | reject step   │
       └────────────┬────────────┘
                    │
       ┌──── request_edits? ─────┐
       │            (yes)        │
       │  loop ≤ max_edit_rounds │
       │  (default 3) per step   │
       │            (no)         │
       │       move on to k+1    │
       └─────────────────────────┘
                    │ all steps done
                    ▼
       ┌─────────────────────────┐
       │  cloud final review +   │
       │  integration pass       │
       └─────────────────────────┘
```

1. **Architect** — cloud — writes a *runbook*: ordered steps,
   acceptance criteria, technology-stack assumptions. JSON payload.
2. **Editor** — local — for each step, produces code + docs + (when
   applicable) tests, dropped into a per-task workspace directory
   (`outputs/<slug>_R5_workspace/`).
3. **Reviewer** — cloud — reads the step output and the workspace
   delta, returns `approve | request_edits | reject` plus
   strengths/issues/suggestions. On `request_edits` the editor
   retries with the feedback, up to `max_edit_rounds=3`. The full
   per-step record (every attempt + every review) is persisted in
   `outputs/<slug>_R5_logs/<slug>_dev_session.json`.

R5 is dense by construction — median total calls per row = **8** in
the v3 sweep, vs R4's median of 4 and R3's 10.5 — but the absolute
token volume is the highest of any route (1.88 M total tokens across
the 250 v3 rows; **2.94× R4 and 1.85× R3**). DevMinion replays
context between reviewer and editor at every round.

**Worked example: `real-dev/d3-extract-validation-helper` (Cat D, D3).**

Picked because it's the canonical R5 "prose-collapse" failure mode
on a real-developer refactor task. The task asks the model to
extract duplicated validation across three FastAPI endpoints into a
new `validate.py` module, preserving behaviour. R5 collapsed
completely (`composite=0.00`, `judge_win_rate=0.00`).

- **Problem.** Refactor a small FastAPI app with three endpoints
  that each duplicate the same email/quantity/sku validation
  block. Extract into `validate.py` with explicit helpers
  (`validate_email`, `validate_quantity`, `validate_sku`,
  `validate_order_payload`). Preserve every HTTP status code and
  error message. Source license: CC-BY-4.0.

- **Round 1 — architect (cloud).** Generates a 5-step runbook:
  (1) characterization tests, (2) extract validation helpers, (3)
  refactor `app.py` callsites, (4) verify pytest passes, (5)
  documentation. Each step has its own acceptance criteria.
  Reasonable so far.

- **Round 2 — editor step 1 (local).** Devstral writes a 200-line
  `tests/test_validation_characterization.py` — but invents the
  three endpoint paths as `/orders`, `/orders/preview`,
  `/orders/quote`. The actual app has `/orders`, `/orders` (PUT),
  and `/orders/cancel`. It also fabricates an
  `EXPECTED_INVALID_RESULTS` dict with status codes (400, 422) and
  error-body shapes that bear no resemblance to the real app's
  Pydantic-driven responses. The local editor never actually
  inspects the attached `app.py`.

- **Round 2 — reviewer (cloud).** Correctly flags the issues —
  "expected results not actually captured from the unmodified
  application"; "pytest version mismatch in the sandbox prevents
  validation"; "no evidence the endpoint paths are correct." Sets
  `request_edits=True`.

- **Round 3 — editor retry (local).** Devstral responds with shell
  commands as prose (`ls -la`, `find . -name "app.py"`,
  `cat ./app.py`) instead of actually reading the inlined fixture
  text in the prompt. Hallucinates the same endpoint paths and
  validation-error dictionary as round 1, dressed up with comments
  saying it "captured" them. Reviewer rejects again.

- **Round 4 — editor retry (local).** Same shape; small wording
  changes; still no real engagement with the app code.

- **Final integration (cloud).** Architect attempts to assemble a
  final deliverable from the failed steps. The final R5 output
  file is a single fenced Python block containing the literal
  string `ls -la` and nothing else (the architect couldn't extract
  a usable deliverable from the editor's prose-shaped responses).

- **Score.** Opus judge: `composite=0.00`, `judge_win_rate=0.00`
  (lost every pairwise comparison in `judge-robust-D`).
- **Tokens.** total=34,227 — cloud=16,205 (4,910 prompt + 11,295
  completion) and local=18,022 (12,674 prompt + 5,348 completion).
- **Cloud fraction.** 47% — the editor's local context-replays
  account for more than half the tokens.
- **Wall.** 491 s (R1 finished the same task in 11 s).
- **$ under gpt-5.5.** $0.36 / row — **11× more than R1's $0.033**
  on the same task. R1 scored 5.0/5.0 on the same Opus rubric.

The full session log lives at
`results/runs/07-v3-devstral-all-routes/outputs/real-dev__d3-extract-validation-helper_R5_logs/real-dev__d3-extract-validation-helper_dev_session.json`
and the workspace deliverables (the editor's intermediate files)
at `outputs/real-dev__d3-extract-validation-helper_R5_workspace/`.

**Where R5 shines.** Category A — best bounded-ARQGC at the $8.465
budget (0.185 vs R3's 0.046), thanks to the four HumanEval+ rows
that R5 happened to solve. Even there the per-row quality median
is **0.00** — R5 either succeeds completely or collapses to zero.

**Where R5 loses.** Categories B, C, D — prose-collapse pattern
dominates. On D3 + D4 (eight judge-scored refactor / review tasks),
R5 produces 0/8 acceptable outputs and burns the most tokens of any
route doing it. R5 is the worst route on B (0/10 pass vs R1/R3/R4
at 3/10) and the slowest by wall (median 535 s on D vs R3's 146 s
and R4's 116 s).

**Why the collapse?** Two compounding factors visible in the
session logs:

1. **Local editor doesn't ground.** Devstral, even with the
   inlined fixture text in the prompt, frequently invents file
   layouts, endpoint paths, and tests. The shell-tool prose
   (`ls -la`, `cat app.py`) shows the editor expecting a *tool-use*
   protocol it doesn't actually have.
2. **Cloud reviewer reinforces hallucinations.** When the reviewer
   says "your captured results are wrong", the editor re-emits the
   same wrong content with apologetic wrapping rather than
   re-reading the original prompt. After 3 rounds the architect's
   integration pass has nothing to integrate.

See `vendor/minions/minions/minion_code.py` for the upstream
protocol implementation. Per-task session logs and workspaces are
under `results/runs/07-v3-devstral-all-routes/outputs/`.

---

## Comparison at a glance

| | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| cloud calls | 1 | 0 | 1 (plan) + 1 (synth) | 1+ per round | 1 architect + N×review |
| local calls | 0 | 1 | 0–N (per step) | 1 per round | N×editor |
| tokens routed local (v3 median) | 0% | 100% | 65% | 13% | 50% |
| Cat A pass | 10/10 | 9/10 | 10/10 | 10/10 | **4/10** |
| Cat B pass | 3/10 | 0/10 | 3/10 | 3/10 | **0/10** |
| Cat C functional pass | 1/5 (bcb) | 1/5 | 0/5 | 0/5 | 0/5 |
| Cat D pass (D1+D5 fn-scored, n=8) | 5/8 | 0/8 | 5/8 | 4/8 | 4/8 |
| $/correct Cat B (gpt-5.5) | $0.42 | — | $0.72 | $0.56 | — (0 correct) |
| $/correct Cat D (gpt-5.5) | $0.17 | — | $0.69 | $0.78 | **$2.04** |
| Strong suit | $/correct floor | $0 cost floor | architectural prose | context-heavy SWE | nothing systematic |

---

## Where each route lives in the codebase

| Route | Python runner | Node / vendor helpers |
|---|---|---|
| R1 | `src/hybrid_coding_eval/runners/r1_cloud_only.py` | `router/server.mjs` |
| R2 | `src/hybrid_coding_eval/runners/r2_local_only.py` | `router/server.mjs` |
| R3 | `src/hybrid_coding_eval/runners/r3_hybrid_architect.py` | `router/pipelines/architect/runner.mjs`, `router/pipelines/architect/core.mjs` |
| R4 | `src/hybrid_coding_eval/runners/r4_minion.py` | `vendor/minions/minions/minion.py` (vendored) |
| R5 | `src/hybrid_coding_eval/runners/r5_devminion.py` | `vendor/minions/minions/minion_code.py` (vendored) |

All five runners expose the same `run(task, …) → ResultRow` surface
so the orchestrator (`hybrid_coding_eval.core.experiment.run_pair`) is
route-agnostic.
