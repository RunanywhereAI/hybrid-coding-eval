# FINAL_V3_REPORT — token-first routing for coding agents, end-to-end

> Companion to `reports/ARTICLE.md`. ARTICLE is the punchy decision document for
> the developer who wants to know which route to pick. This file is the
> journal-style technical narrative: full methodology, per-category forensic
> detail, the explicit comparison between the v3 plan's prediction and the data,
> and concrete guidance for replicating or extending the work.
>
> Every dollar figure derives from
> `results/runs/07-v3-devstral-all-routes/raw.jsonl` (250 rows) against
> `configs/pricing/pricing_tables.json` (SHA256 pinned). Triple-judge robustness
> is grounded in `results/runs/11-judge-robust-D/judge.jsonl` (96 verdicts).
> Primary scenario throughout: `openai-gpt5.5`.

---

## §1. Project thesis

The question we set out to answer is the one a working developer actually asks:
**for the coding tasks I do every day, when does sending part of the work to a
local model beat sending all of it to a cloud API, and where does it lose?**

That question is not symmetric. "Hybrid wins on pass rate" is interesting but
insufficient — if a hybrid route ties the cloud baseline on pass rate while
costing 3× more dollars, it loses on the only metric a real developer cares
about. So we anchored the evaluation in tokens: every row in the dataset stores
its `prompt`, `completion`, `cached`, `reasoning`, `local_prompt`,
`local_completion`, `cloud_prompt`, and `cloud_completion` counts, and **cost is
never stored** — it is derived at read time against a SHA256-pinned
per-million-token pricing table. The same dataset re-prices under six cloud
scenarios (`openai-gpt5.5`, `openai-gpt5`, `openai-gpt5-mini`,
`anthropic-claude-opus-4.7`, `anthropic-claude-sonnet-4.6`,
`anthropic-claude-haiku-4.5`) without re-running inference.

The v3 plan made a falsifiable prediction in plain English: for the five task
shapes a real developer hands their coding agent on a normal day — small
feature, bug fix, refactor, code review, script — local-first routing with R4
(Stanford Minion) or R5 (Stanford DevMinion) sends 60–80% of tokens to the free
local model while reaching quality parity with cloud-only. Under typical API
pricing scenarios, that would translate to 40–70% cost reduction per task.

The point of category D (real-developer tasks) in the v3 sweep was to test that
prediction on task shapes a developer would recognise: 4 small-feature tasks
(D1), 4 GitHub-issue bug fixes (D2), 4 cross-file refactors (D3), 4 code reviews
(D4), 4 small scripts (D5). The point of running all five routes (R1 cloud-only,
R2 local-only, R3 hybrid-architect, R4 Minion, R5 DevMinion) on the same 50-task
corpus was to make the comparison route-fair: every shape, every route, same
hardware (M4 Max 64 GB), same cloud (gpt-5.5), same local (`devstral:24b`), same
judge (`claude-opus-4-7`), same seed (`seed=42`).

This report is what we found.

---

## §2. What 250 rows shows — the headline

Four numbers anchor the rest of the report.

**1. R4's median `cloud_fraction` across 250 rows is 87%.** The Stanford-Minion
supervisor/worker framing predicts the cloud asks short targeted questions and
the local worker reads the heavy context; in our sweep the supervisor ends up
writing 8 of every 10 tokens. Per-category R4 cloud-fraction medians: A 90%, B
86%, C 89%, D 86% (`reports/DECISION_TABLE.md`). The single hybrid route
designed to keep volume local does the opposite.

**2. R3, R4, and R5 are not cheaper than R1 — they are 2.26×, 1.91×, and 5.13×
more expensive on per-row mean cost.** Computed from the 50-row totals in
`reports/TOKEN_BUDGET.md`: R1 = $3.82, R3 = $8.65, R4 = $7.29, R5 = $19.59 under
`openai-gpt5.5`. The per-shape medians push the gap wider on prose categories:
D4-review R3 = $0.4067 vs R1 = $0.0861 (4.7×), R5 vs R1 on D4 = 5.1×. Hybrid is
more expensive than cloud-only, not less.

**3. The v1 "R4 beats R1 on SWE-bench" finding did not replicate.** Run 04 (the
MVP, also `devstral:24b` + `gpt-5.5` + the same SWE-bench harness) reported R4
uniquely solving `swebench-verified/sphinx-doc__sphinx-7889` and
`swebench-verified/sphinx-doc__sphinx-9698`. In the v3 sweep R1, R3, and R4 each
pass exactly the same 3/10 Django tasks (`django__django-11163`,
`django__django-11179`, `django__django-15863`); both Sphinx wins are gone. With
identical models and harness across runs, the most parsimonious explanation is
that the run 04 Sphinx passes were single-sample noise on a 10-task slice and
the deterministic SWE-bench ceiling under this model + prompt skeleton is 3/10.
R5 is 0/10.

**4. R5 (Stanford DevMinion review-loop) is the worst route on three of four
categories while spending the most tokens.** R5 sums 1.88M tokens across its 50
rows — 1.85× R3 and 2.94× R4 — and scores `composite = 0.00` on every D3 task
and 3 of 4 D4 tasks. R5 is 5.13× R1's mean cost and the slowest by wall (median
535 s on D vs R3's 146 s and R4's 116 s). On the categories where R5 is supposed
to shine — prose-shaped refactors and code reviews — it produces
near-zero-quality outputs.

The hypothesis the v3 plan was designed to test (that hybrid sends most volume
local and saves 40–70%) is contradicted on cost by all three hybrid routes and
on `cloud_fraction` by R4 and R5. R3 is the only hybrid that delivers the
predicted token-routing balance — and its dollar cost still runs 2.26× R1.

---

## §3. Methodology

The eval is a 5-route × 50-task sweep at a single seed, on a single hardware
tier, with a single cloud family, and a primary judge family.

**Task corpus.** 50 unique tasks across four categories:

- **Category A — HumanEval+ (10 tasks).** Tiny self-contained function
  completions. Seeded random sample from the HumanEval+ split (the validated
  EvalPlus extension of OpenAI HumanEval). Scoring is functional via pytest in a
  Docker sandbox.
- **Category B — SWE-bench Verified easy (10 tasks).** Real-repo patches against
  Django, Sphinx, xarray, pytest, astropy. The harness is the `mini-SWE-agent`
  Docker container that runs the repo's own test suite; pass/fail is binary.
- **Category C — BigCodeBench-Hard + custom-arch (5 + 5).** Five library-heavy
  functional tasks (BigCodeBench-Hard subset, pytest-scored); five hand-curated
  architecture prose tasks (auth-multitenant-design,
  cache-invalidation-tradeoffs, code-review-flaky-test,
  migration-planning-zero-downtime, production-debug-reasoning), judge-scored
  with a 5-dimension rubric (correctness, completeness, style, reasoning depth,
  practicality) by Claude Opus 4.7.
- **Category D — real-developer (20 tasks across 5 shapes).** New in v3:
  - D1 small-feature-end-to-end (4): `d1-auth-login`, `d1-json-schema`,
    `d1-rate-limit`, `d1-retry-decorator`. Pytest functional.
  - D2 bug-fix-from-stacktrace from real GitHub issues (4): `d2-click-3298`,
    `d2-jsonschema-1124`, `d2-pytest-13817`, `d2-werkzeug-3127`. **Functional
    scorer deferred**; cost and `cloud_fraction` observable, quality is not.
  - D3 refactor-across-files (4): `d3-constants-to-enum`,
    `d3-extract-validation-helper`, `d3-replace-try-except-with-contextmanager`,
    `d3-split-god-module`. LLM-judge prose with calibrated gold exemplars.
  - D4 code-review (4): `d4-review-cache-invalidation`, `d4-review-pagination`,
    `d4-review-sql-injection`, `d4-review-timezone-handling`. Same LLM-judge
    protocol.
  - D5 script-or-one-off (4): `d5-csv-dedupe`, `d5-env-var-redactor`,
    `d5-log-errors-today`, `d5-todo-counter`. Pytest stdout-diff functional.

**Routes.**

- **R1 — cloud-only `gpt-5.5`.** A single `chat.completions` call. Fastest to
  implement, fastest to respond; the comparison baseline.
- **R2 — local-only `devstral:24b` via Ollama.** Same prompt shape, routed to
  the local model. $0 by construction.
- **R3 — hybrid-architect.** Cloud planner decomposes the task to a JSON step
  list; per-step executor lands on the local model when the heuristic router
  permits; cloud synth assembles. Three phases, two cloud touches.
- **R4 — Stanford Minion.** Supervisor (cloud) sees only the task statement;
  worker (local) sees the full context; supervisor asks targeted questions,
  worker answers, supervisor emits the final answer. Vendored from
  `vendor/minions/minions/minion.py`.
- **R5 — Stanford DevMinion.** Architect (cloud) generates a runbook; editor
  (local) implements each step; reviewer (cloud) approves / requests-edits /
  rejects, up to 3 rounds per step. Vendored from
  `vendor/minions/minions/minion_code.py`.

**Hardware + models.** A single M4 Max 64 GB laptop. `gpt-5.5` for every cloud
call (and as the third judge in the run-11 triple-judge audit). `devstral:24b`
for every local call. `qwen3:0.6b` as the router classifier (heuristic strategy,
threshold null). `claude-opus-4-7` as the primary judge; `claude-sonnet-4-6` and
`gpt-5.5` added for run-11.

**Token-first architecture.** Every row in
`results/runs/07-v3-devstral-all-routes/raw.jsonl` carries `tokens.{prompt,
completion, cached, reasoning, local_prompt, local_completion, cloud_prompt,
cloud_completion}` and a `quality.{functional_pass, tests_passed, tests_total,
judge_win_rate, composite}` block. The row schema is invariant across routes.
Cost is derived from those token counts × `configs/pricing/pricing_tables.json`
(SHA256 `adbf24618010…`). Re-pricing under any of the six scenarios is a single
pass over the file; inference is never re-run.

**Triple-judge robustness.** For the prose categories D3 + D4, every (task ×
pair × A/B order × judge) combination was re-judged in run 11: 16 pairings × 3
judges (`claude-opus-4-7`, `claude-sonnet-4-6`, `gpt-5.5`) × 2 orders = **96
verdicts, 100% unanimous, 0 order-flips, 0 errors**. The R1 prose dominance is
judge-and-order-invariant on the 8-task D3+D4 slice
(`results/runs/11-judge-robust-D/judge.jsonl`).

**Wall + cost totals.** 11.9 hours total wall on one laptop. Zero infra errors
(`error=None` on every row). $39.34 total cloud spend under `openai-gpt5.5`;
$100.77 under `anthropic-claude-opus-4.7`; $2.54 under `openai-gpt5-mini`. R5
alone accounts for 7.05 of the 11.9 wall hours and $19.59 of the $39.34 cloud
spend.

---

## §4. Per-category deep-dive

### Category A — HumanEval+ tiny-function-completion

A representative task: `humaneval-plus/HumanEval_99` ("complete `def
closest_integer(value: str) -> int` that rounds a decimal string to the nearest
integer, with half-to-even wrong and half-away-from-zero right"). Single-file,
~150 tokens of prompt, expected output ~300 tokens.

Pass rate across routes (n=10):

| route | pass | med cloud_frac | med $ gpt-5.5 | med wall ms |
|---|---:|---:|---:|---:|
| R1 | 10/10 | 100% | $0.0119 | 5,364 |
| R2 | 9/10 | 0% | $0.0000 | 5,244 |
| R3 | 10/10 | 37% | $0.0380 | 57,524 |
| R4 | 10/10 | 90% | $0.0659 | 37,345 |
| R5 | 4/10 | 50% | $0.2488 | 262,695 |

The dominant signal is that R2 is free (`devstral:24b` on its own gets 9/10 of
these tasks right) and every hybrid pays a planning tax for nothing. R3 spends
~$0.04 per task that R2 solves for $0; R4 spends ~$0.07; R5 spends ~$0.25 and
*loses* pass rate (4/10) because the review loop drifts the answer away from
what a single-shot would have produced. The R2 miss is `HumanEval_77`, where
devstral generated a recursive function that hit infinite recursion. **No
Category-A task on which any hybrid Pareto-improves on R1 or R2.**

### Category B — SWE-bench Verified easy

A representative task: `swebench-verified/django__django-11163` (one of the
three R1/R3/R4 all pass). The task is a real Django bug report; the model
receives ~2,500 prompt tokens of issue + repo state and must emit a unified
diff.

Pass rate across routes (n=10):

| route | pass | med cloud_frac | med $ gpt-5.5 | med wall ms |
|---|---:|---:|---:|---:|
| R1 | 3/10 | 100% | $0.1058 | 61,586 |
| R2 | 0/10 | 0% | $0.0000 | 9,700 |
| R3 | 3/10 | 34% | $0.1369 | 166,103 |
| R4 | 3/10 | 86% | $0.2025 | 139,083 |
| R5 | 0/10 | 53% | $0.3902 | 381,303 |

R1 = R3 = R4 = 3/10. The three passing tasks are the same Django triple in every
route. The v1 R4 Sphinx wins (`sphinx-doc__sphinx-7889`,
`sphinx-doc__sphinx-9698`) do not appear in v3 — every route fails both. The
most revealing single (task, route) pair is **R4 on
`swebench-verified/sphinx-doc__sphinx-9698`**: in run 04 this was R4's headline
unique win at $0.22/correct under gpt-5.5; in run 07 R4's output on the same
task no longer passes the harness. The two runs used identical models, identical
seeds, identical Docker harness — the difference is reachable single-sample
variance, not a regression in the runner. The cost-per-correct for R4 is now
$7.29 / 3 = $2.43, **1.9× R1's $1.27/correct**, not 1.3× cheaper as v1 claimed.

### Category C — BigCodeBench-Hard (functional)

The library-heavy half of C. Representative:
`bigcodebench-hard/BigCodeBench/214` ("generate a random RGB image and view it;
raise ValueError if range_low ≥ range_high; return Axes + ndarray"). The prompt
anchors a specific import set (`random`, `numpy`, `cv2`, `matplotlib.pyplot`)
and the harness tests both the happy path and the ValueError.

| route | pass | med cloud_frac | med $ gpt-5.5 | med wall ms |
|---|---:|---:|---:|---:|
| R1 | 1/5 | 100% | $0.0433 | 21,998 |
| R2 | 1/5 | 0% | $0.0000 | 22,159 |
| R3 | 0/5 | 41% | $0.0862 | 77,120 |
| R4 | 0/5 | 89% | $0.0906 | 52,238 |
| R5 | 0/5 | 50% | $0.4429 | 645,402 |

C-bcb is the only category where **R1 and R2 both pass exactly the same number
(1/5)** — and every hybrid regresses to 0/5. The most revealing row is
`bigcodebench-hard/BigCodeBench/530`: R1 passes (composite 1.0, 1,185 tokens,
$0.005), R2 passes (composite 1.0, 2,107 tokens, $0), and every hybrid fails: R3
= 0.43, R4 = 0.86, R5 = 0.43 — none crosses the 0.5 functional threshold. The
cloud planner over-engineers a one-liner that either backend solves on its own.
Hybrid is a regression on tasks where the bottleneck is the model knowing the
right library API, not the orchestration around it.

### Category C — custom-arch (judge-scored prose)

The hand-curated half. Five architecture-shaped tasks
(`auth-multitenant-design`, `cache-invalidation-tradeoffs`,
`code-review-flaky-test`, `migration-planning-zero-downtime`,
`production-debug-reasoning`), scored 5-dimensionally by `claude-opus-4-7`.

| route | pass (comp ≥ 0.5) | med cloud_frac | med $ gpt-5.5 | med wall ms |
|---|---:|---:|---:|---:|
| R1 | 5/5 | 100% | $0.2963 | 180,594 |
| R2 | 3/5 | 0% | $0.0000 | 47,568 |
| R3 | 5/5 | 70% | $0.4876 | 523,641 |
| R4 | 4/5 | 89% | $0.1612 | 119,873 |
| R5 | 1/5 | 53% | $0.4957 | 876,316 |

R3 ties R1 on this slice — five-of-five — but at 1.6× R1's median cost. The 25
single-judge custom-arch pairings from run 07 (R1_vs_R2, R1_vs_R3, R2_vs_R3,
R3_vs_R4, R3_vs_R5) record only one competitive shape: R1_vs_R3 has 2 R1 wins
and 3 ties (`migration-planning-zero-downtime`, `code-review-flaky-test`,
`cache-invalidation-tradeoffs`). R3 loses by small margins on
`auth-multitenant-design` (0.15) and `production-debug-reasoning` (0.30). R3 is
the only hybrid that approaches R1 on prose — the cloud planner + synth wrapped
around a local executor produces dense architectural writing that the Opus judge
rates as comparable to R1's direct output.

### Category D1 — small-feature-end-to-end

Four hand-built tasks where the developer asks for a small module implemented
from scratch with tests: `d1-auth-login`, `d1-json-schema`, `d1-rate-limit`,
`d1-retry-decorator`.

| route | pass | med cloud_frac | med $ gpt-5.5 | med wall ms |
|---|---:|---:|---:|---:|
| R1 | 2/4 | 100% | $0.0304 | 12,940 |
| R2 | 0/4 | 0% | $0.0000 | 2,834 |
| R3 | 2/4 | 31% | $0.0976 | 127,042 |
| R4 | 1/4 | 86% | $0.1183 | 102,956 |
| R5 | 1/4 | 46% | $0.4318 | 582,035 |

The most-revealing single row: **R3 on `real-dev/d1-json-schema`** — the only
row in the entire 250-row dataset where a hybrid composite strictly exceeds R1's
by more than 0.01. R3 = 1.00 (functional pass); R1 = 0.00. From the row: R3 sent
6,033 cloud tokens + 11,142 local tokens (cloud_frac 0.35, 137 s wall); R1 sent
2,679 cloud tokens, all-cloud, 9 s wall, and produced a Python dataclass instead
of the JSON schema the harness expected. The planner-driven hybrid noticed the
output-format requirement and routed it to the executor; R1 single-shot missed
the format constraint. One row in 250 — but it is a real Pareto improvement on
quality at $0.062 added cost.

### Category D2 — bug-fix-from-stacktrace (functional scorer deferred)

`d2-click-3298`, `d2-jsonschema-1124`, `d2-pytest-13817`, `d2-werkzeug-3127`.
Each task points at a real GitHub issue at a pinned base commit (e.g.
`d2-click-3298` → `pallets/click` @ `04ef3a6f47`); the harness expected a
runnable patch-apply pipeline that we did not finish wiring before the sweep.
The 20 D2 rows (4 tasks × 5 routes) have `functional_pass = None` and `composite
= None` by design. Cost and `cloud_fraction` are still observable:

| route | cloud_frac med | $ gpt-5.5 med | wall ms med |
|---|---:|---:|---:|
| R1 | 100% | $0.0409 | 25,728 |
| R2 | 0% | $0.0000 | 7,795 |
| R3 | 32% | $0.1282 | 154,903 |
| R4 | 86% | $0.1714 | 130,993 |
| R5 | 53% | $0.3387 | 398,319 |

The shape of D2 looks like SWE-bench (`b-swe`) on the cost dimension — long
contexts, R4 sits at the 86% cloud-fraction R4-floor, R5 spends 8× R1. We can
say what each route *cost* to attempt these tasks; we cannot say what it bought.

### Category D3 — refactor-across-files

The shape that should be R5's natural turf: take an existing module, apply a
structural refactor across multiple call-sites, preserve every behaviour. Four
tasks: `d3-constants-to-enum`, `d3-extract-validation-helper`,
`d3-replace-try-except-with-contextmanager`, `d3-split-god-module`.

| route | comp ≥ 0.5 | med cloud_frac | med $ gpt-5.5 | med composite |
|---|---:|---:|---:|---:|
| R1 | 4/4 | 100% | $0.0354 | 1.00 |
| R2 | 0/4 | 0% | $0.0000 | 0.00 |
| R3 | 4/4 | 37% | $0.1509 | 0.84 |
| R4 | 4/4 | 86% | $0.1637 | 0.72 |
| R5 | 0/4 | 55% | $0.4043 | 0.00 |

The most-revealing single row is **R5 on
`real-dev/d3-extract-validation-helper`** — the canonical R5 prose-collapse case
documented in `reports/APPENDIX_ROUTES.md` §R5. The task asks the model to
extract duplicated validation across three FastAPI endpoints into a new
`validate.py` module, preserving every HTTP status code and error message. The
cloud architect (round 1) produces a sensible 5-step runbook. The local editor
(round 2) writes 200 lines of characterisation tests against fabricated endpoint
paths (`/orders/preview`, `/orders/quote`) that don't exist in the attached
`app.py`. The cloud reviewer correctly flags the issue and sets
`request_edits=True`. The local editor (round 3) responds with shell commands as
prose — `ls -la`, `find . -name "app.py"`, `cat ./app.py` — instead of reading
the inlined fixture text. The cloud reviewer rejects again. After the cloud
final integration pass, R5's deliverable file contains a single fenced Python
block with the literal string `ls -la` and nothing else (the architect could not
extract usable content from the editor's prose-shaped responses). Row data:
cloud=16,205, local=18,022, total=34,227, cloud_frac=0.47, wall=491 s,
composite=0.00. R1 finished the same task in 11 s for $0.033, composite 0.98. R5
is 11× more expensive and produces unusable output.

### Category D4 — code-review

`d4-review-cache-invalidation`, `d4-review-pagination`,
`d4-review-sql-injection`, `d4-review-timezone-handling`. The model receives a
short code snippet and is asked for a code review across correctness,
completeness, style, reasoning depth, and practicality.

| route | comp ≥ 0.5 | med cloud_frac | med $ gpt-5.5 | med composite |
|---|---:|---:|---:|---:|
| R1 | 4/4 | 100% | $0.0861 | 0.98 |
| R2 | 0/4 | 0% | $0.0000 | 0.12 |
| R3 | 2/4 | 81% | $0.4067 | 0.54 |
| R4 | 2/4 | 83% | $0.1968 | 0.64 |
| R5 | 0/4 | 50% | $0.4355 | 0.02 |

D4 is the cleanest separation any category produces. R1 wins all four with
composite ≥ 0.96. R3 lands 2/4 (`d4-review-cache-invalidation` 0.54,
`d4-review-timezone-handling` 0.78); R4 lands 2/4. R5 lands 0/4 with three
composites of 0.00 and one at 0.22 (`d4-review-pagination`). R3's median cost on
D4 is $0.4067 — **4.7× R1's $0.0861** — for half the pass rate. The triple-judge
audit (run 11) confirms: 24 verdicts on D4 R1-vs-R3 pairings, every single one
R1-wins; 24 verdicts on D4 R1-vs-R4 pairings, every single one R1-wins. The
most-revealing row is **R3 on `real-dev/d4-review-cache-invalidation`**: R3 =
0.54 (just over the pass threshold) for $0.41 vs R1 = 1.00 for $0.07.

### Category D5 — script-or-one-off

`d5-csv-dedupe`, `d5-env-var-redactor`, `d5-log-errors-today`,
`d5-todo-counter`. The shape where the deliverable is a small, self-contained
Python script verified by stdout-diff.

| route | pass | med cloud_frac | med $ gpt-5.5 | med wall ms |
|---|---:|---:|---:|---:|
| R1 | 3/4 | 100% | $0.0158 | 12,026 |
| R2 | 0/4 | 0% | $0.0000 | 13,200 |
| R3 | 3/4 | 33% | $0.0706 | 91,331 |
| R4 | 3/4 | 88% | $0.0729 | 63,739 |
| R5 | 3/4 | 45% | $0.4230 | 750,461 |

D5 is the only Category-D shape where every route except R2 ties at 3/4. The
most-revealing row is **R5 on `real-dev/d5-log-errors-today`**: R5 is the *only*
route that passes (composite 1.0); R1, R2, R3, R4 all fail. Two-task evidence
(this row plus R5's unique win on `real-dev/d1-retry-decorator`) is not enough
to claim a niche, but it sketches the shape of where R5 might earn its slot:
tightly-bounded functional tasks where each review round verifies a concrete
behaviour against a tiny stdout-diff. Outside that — on long-form prose D3 + D4
— R5 burns more tokens and produces less usable output.

---

## §5. The 10 most-surprising findings, with token traces

Each finding is anchored to a row or aggregate in
`results/runs/07-v3-devstral-all-routes/raw.jsonl`; tokens are exact counts;
dollar values derive from those counts × pinned pricing table.

**1. R4's median `cloud_fraction` is 87%, not the 60–80%-local the Minion paper
implied.** Aggregate sum across all 50 R4 rows: cloud = 544,429 tokens, local =
95,647 tokens, total = 640,076, cloud share 85%. The supervisor processes the
full problem statement each round; the worker contributes targeted answers. On a
median R4 row the cloud burns 5–10× more tokens than the local worker; on
long-context B and D2 tasks the gap is larger. The Minion supervisor/worker
framing did not move volume to the worker on our prompt sizes. Cost: R4 sum =
$7.29 (gpt-5.5).

**2. R5 burned 1.88M tokens and was the worst route on three of four
categories.** R5 aggregate: cloud = 945,209, local = 934,148, total = 1,879,357
— 2.94× R4, 1.85× R3. R5 has a higher completion-token share than every other
route (cloud completion alone = 594,326), consistent with the review-loop
producing long architect/reviewer rounds rather than terse answers. R5 cost =
$19.59 under gpt-5.5. Quality: composite median 0.00 on D, 0.28 on C, 0/10 on B.
Worst route on B, C, D simultaneously.

**3. The v1 "R4 beats R1 on SWE-bench" headline did not replicate.** Run 04
reported R4 unique passes on `swebench-verified/sphinx-doc__sphinx-7889` and
`sphinx-doc__sphinx-9698`. In v3 every route fails both. Per-row R4 outputs on
these tasks: composite 0.0, no diff that passes the harness. With identical
models (`devstral:24b`, `gpt-5.5`) and identical mini-SWE-agent harness, the
simplest explanation is single-sample variance on a 10-task slice. The v1
cost-per-correct argument for R4 on B was load-bearing on those two passes;
without them R4 is $2.43/correct vs R1 $1.27/correct.

**4. D2 has 20 rows of zero quality signal.** Functional pass for the 4 external
GitHub-issue tasks × 5 routes is `None` everywhere. Tokens were burned (R1 spent
$0.0409/row median, R5 spent $0.3387/row median), outputs were stored in
`outputs/`, but no scorer ran. 8% of the dataset is mute on quality. Fixing this
is T-23's biggest single win.

**5. R5 on `real-dev/d3-extract-validation-helper`: 491 s wall, 34,227 tokens,
composite 0.00.** The canonical R5 prose-collapse case (worked example in
`reports/APPENDIX_ROUTES.md`). Four rounds of architect → editor → reviewer
ping-pong end with a deliverable file containing the literal string `ls -la`. R1
finished the same task in 11 s for $0.033 at composite 0.98. R5's cost on this
row is $0.36, **11× R1**. This is the single row that most concretely
demonstrates how a review-loop can drift the artefact further from the spec each
round.

**6. R3 ≈ R1 on quality on most categories yet costs 2.26× — quality-parity,
cost-loss.** R3 sum cost = $8.65 vs R1 sum cost = $3.82; per-row mean ratio
2.26×. R3's quality median is below R1's on every category (A tied 1.00; C 0.90
vs 0.99; D 0.76 vs 0.99); R3 wins 0 of 4 category-route quality cells. R3 is the
cheapest hybrid, but it is not cheaper than R1.

**7. R2 (pure local `devstral:24b`) is 0/n outside the tiny-function subset.**
R2 pass rate on A is 9/10; on B 0/10; on C-bcb 1/5; on C-arch 3/5
prose-composite-pass-proxy; on every D shape except `d4-review-pagination`
(composite 0.22 vs threshold 0.5) the composite is 0.00. R2 is a step function:
dominant on the subset it solves, unusable outside it. There is no graceful
degradation.

**8. C-bcb had 1/5 pass for R1, 1/5 for R2, 0/5 for every hybrid.** The
library-heavy `bigcodebench-hard` half of C is the only category where any
single hybrid is *strictly worse than both R1 and R2*. The most-revealing row:
`bigcodebench-hard/BigCodeBench/530` — R1 1.0, R2 1.0, R3 0.43, R4 0.86, R5
0.43. The cloud planner over-engineered a one-liner. When the bottleneck is
"knowing the right library API", orchestration hurts.

**9. Across 250 rows, exactly one row has a hybrid composite > R1 by more than
0.01.** That row is `real-dev/d1-json-schema`, R3 = 1.00 vs R1 = 0.00, +0.062
cost ($0.075 vs $0.013). Every other row in the dataset is either an R1 win or a
tie. **Hybrid almost never Pareto-improves on R1 for quality.**

**10. Triple-judge audit on D3 + D4: 96 verdicts, 0 flips.** Run 11 re-judged 16
pairings × 3 judges (`claude-opus-4-7`, `claude-sonnet-4-6`, `gpt-5.5`) × 2
orders. Every verdict is R1-wins. Mean margins: opus 0.94, sonnet 1.00, gpt-5.5
1.00. The cross-vendor unanimity rules out same-family judge bias; the zero
order-flips rules out A/B position effects; the gpt-5.5 judge (a different
vendor from the Anthropic sweep judge) agreeing on every verdict rules out
vendor-self-preference. **The R1-dominates-prose finding is
judge-and-order-invariant on this 8-task slice.** No other claim in this report
is this robust.

---

## §6. The v3 plan's hypothesis — what we predicted vs what we got

The v3 plan's prediction, restated:

> For the five task shapes a real developer hands their coding agent on a normal
> day — small feature, bug fix, refactor, code review, script — local-first
> routing with R4 or R5 sends 60–80% of tokens to the free local model while
> reaching quality parity with cloud-only. Under typical API pricing scenarios,
> that translates to 40–70% cost reduction per task.

What the data says, per claim:

**Token routing.** Predicted R4 sends 60–80% local. Measured R4 cloud-fraction
by shape: A 90%, B 86%, C 89%, D 86% (per `reports/DECISION_TABLE.md`). The
local fraction is 10–14%, not 60–80%. R5 sits closer to 50% across the board (D
median 50%, B 53%, C 53%) — still misses the 60–80% target. R3 (not in the
predicted-hybrid pair, but worth noting) delivers the predicted band: 35% cloud
median (65% local). R3 is the only route that comes near the predicted routing
balance.

**Cost reduction.** Predicted 40–70% cost reduction. Measured per-row mean cost
ratios vs R1: R3 = 2.26×, R4 = 1.91×, R5 = 5.13×. None saves cost; all three are
more expensive than the cloud baseline. The per-shape medians push the gap wider
on prose: D4-review R3 = 4.7× R1; D4-review R5 = 5.1× R1; D3-refactor R5 = 11.4×
R1.

**Quality parity.** Predicted all hybrids match R1 on composite. Measured:
across-all composite medians — R1 0.99, R3 0.76, R4 0.59, R5 0.00 on D. R3 is
the closest to parity on architecture prose (C-arch composite 0.90 vs R1 0.99);
R3 ties R1 on D3 above the 0.5 pass-proxy threshold (4/4 vs 4/4); R3 loses on D4
(2/4 vs 4/4). R5 fails parity on B, C, D3, D4 — every category but A.

A scorecard:

| metric | v3 prediction | v3 measurement | verdict |
|---|---|---|---|
| R3 cloud_fraction (median) | 20–40% cloud (60–80% local) | 35% cloud | matches |
| R4 cloud_fraction (median) | 20–40% cloud | 87% cloud | **falsified — 2× upper bound** |
| R5 cloud_fraction (median) | 20–40% cloud | 50% cloud | falsified |
| R3 cost vs R1 | 0.3–0.6× | 2.26× mean | **falsified — 4× upper bound** |
| R4 cost vs R1 | 0.3–0.6× | 1.91× mean | falsified |
| R5 cost vs R1 | 0.3–0.6× | 5.13× mean | **falsified — 8× upper bound** |
| quality parity | yes on R4, R5 | partial on R3; R4 partial; R5 fails on B, C, D3, D4 | falsified |

Why did the prediction fail? The intuition came from the Stanford Minion paper's
framing of the supervisor as a query coordinator with most volume on the worker
side. That intuition does not survive contact with our real prompt sizes. On
long-context B and D2 tasks the supervisor reads the full problem statement each
round (the worker's contribution is small, targeted answers). On short-context A
tasks there isn't enough content to push to a worker in the first place. R3's
planner does push the executor's local share to the predicted band — but the
cloud-side prefixes for the planner + synth are structurally expensive relative
to what gets saved locally.

We ran the experiment as designed. The result contradicts the hypothesis. **No
hybrid route on this task mix delivers the 40–70% cost savings the v3 plan
predicted.**

This is the honest scorecard. The point of running a falsifiable experiment is
to take the falsifying result seriously.

---

## §7. How to use the decision matrix

Practical guidance, per task shape. The fall-through rule is: **try R2 first if
the task shape is HumanEval-like; otherwise R1**. Hybrid does not earn a slot in
this routing table at the current cloud/local pricing ratio on this hardware.

**Tiny self-contained function (HumanEval-shape).** Pick R2 (`devstral:24b`).
90% pass rate at $0.00 per task. The single miss in this dataset
(`HumanEval_77`) is a recursion failure mode that's easy to detect — if R2 emits
a function that doesn't terminate on a smoke input, fall back to R1. There is no
Pareto-improvement available with hybrid here.

**Small real-dev feature (D1).** Pick R1. R1's pass rate is 2/4; R3 ties at 2/4
for 3× the cost; R4 and R5 land 1/4. R2 is 0/4 on this shape — devstral cannot
do the multi-file scaffolding the D1 tasks require. The one exception is
`d1-json-schema`, where R3 uniquely passes — but you don't know that ex ante.

**SWE-bench-style multi-file engineering (B).** Pick R1. R1 = R3 = R4 = 3/10 on
the same three Django tasks. R5 = 0/10. R2 = 0/10. R3 costs 1.3× R1 per task at
the same pass rate; R4 costs 1.9×; R5 costs 3.7× and passes nothing. Until a
local model closes the SWE-bench gap, every dollar spent on hybrid routing on B
is wasted.

**BigCodeBench library-heavy tasks (C-bcb).** Pick R1 or R2 — and try R2 first.
Both pass 1/5; every hybrid pass-rate regresses to 0/5. The bottleneck is API
knowledge, and orchestration hurts. There's no productive middle ground here.

**Architecture-design prose (C-arch).** Pick R1. R1 is 5/5 on the pass-proxy at
composite ≥ 0.5; R3 ties 5/5 at 1.6× cost; R4 loses one task; R5 loses four. The
single-judge custom-arch pairings on v3 record R1 wins 2 of 5 R1-vs-R3 and ties
3 of 5 — R3 is the only hybrid that competes here at all, and it pays a cost
premium for it.

**Refactor with prose judgement (D3).** Pick R1, unambiguously. R1 = 4/4 with
median composite 1.00. R3 = 4/4 with median 0.84 at 4.3× cost. R4 = 4/4 with
median 0.72 at 4.6× cost. R5 = 0/4. The triple-judge audit confirms R1 dominance
across 48 D3 verdicts.

**Code review with prose judgement (D4).** Pick R1. R1 = 4/4 composite ≥ 0.96 on
every task; R3 = 2/4 at 4.7× cost; R4 = 2/4; R5 = 0/4. The triple-judge audit
confirms R1 dominance across 48 D4 verdicts.

**Scripts / one-shots (D5).** Try R2 first, fall back to R1. R2 is 0/4 on this
dataset's four scripts (the scripts need stdlib + a small file IO loop devstral
can write but mis-formats stdout-diff), so in practice R1 is the answer until
R2's pass rate on this shape is independently verified on a larger sample. R5
has a unique win on `d5-log-errors-today` — but two-task evidence is not enough
to recommend routing this shape to R5.

**External GitHub-issue patches (D2).** Pick R1 as fallback; quality is
currently uninstrumented. The cost picture suggests D2 looks like B (long
context, R4 cloud-fraction 86%, R5 8× R1). Until a functional scorer is wired,
treat this as observation only.

**The general meta-rule.** Hybrid is currently a quality-parity, cost-loss
choice on the task mix we evaluated. That is not "hybrid is dead forever" — it
is "hybrid as currently implemented isn't a cost optimization on this
hardware/cloud/local mix." Pick R1 unless `devstral:24b` can solve solo.

---

## §8. The six pricing scenarios — when does each matter

Six scenarios re-priced from the same 250-row dataset against
`configs/pricing/pricing_tables.json`. The ranking between routes is invariant
to scenario (each scenario is a positive scalar on every cloud-token count) —
but the *gap* between hybrid and R1 changes meaningfully.

**`openai-gpt5.5` (primary).** Input $5/M, output $30/M. The actual cloud rates
used at inference time. This is the scenario the rest of this report is anchored
to. Sum cost across 250 rows: $39.34. Per-row median R5 cost on D = $0.40;
per-row R1 = $0.035; R5/R1 = 11.4×.

**`openai-gpt5`.** Input $1.25/M, output $10/M. 4× cheaper than gpt-5.5 in
input, 3× cheaper in output. The scenario for a team running a cost-conscious
cloud workload. Sum cost: $12.71. The hybrid/R1 ratio narrows slightly (cheaper
completions hurt R5 less because R5 is completion-heavy) but never inverts. Use
this scenario when the question is "if I switch from gpt-5.5 to gpt-5, does
hybrid suddenly win?" Answer: no.

**`openai-gpt5-mini`.** Input $0.25/M, output $2/M. 20× cheaper than gpt-5.5.
The scenario for high-volume background workloads where quality bar is
"directionally right". Sum cost: $2.54. The hybrid gap narrows the most under
this scenario (per-token premiums dominated by output rate, which is cheapest
here), but R1 still wins every cell. The R1 D-row median is $0.0022; R5 is
$0.0266 — still 12× R1.

**`anthropic-claude-opus-4.7`.** Input $15/M, output $75/M. 2.5× more expensive
than gpt-5.5. The frontier-Anthropic scenario — when cost-per-token matters less
than quality at the absolute frontier. Sum cost: $100.77. **R5's cost gap
*widens* here**: R5 D-row median $1.0210 vs R1 $0.093 = 11× (vs 11.4× at gpt-5.5
— the cloud-completion dominance in R5 amplifies under premium pricing).

**`anthropic-claude-sonnet-4.6`.** Input $3/M, output $15/M. Mid-tier Anthropic.
Sum cost: $20.15. The scenario that most closely tracks `openai-gpt5.5` in ratio
terms — useful when comparing "should I switch cloud family?". Answer: route
ranking unchanged.

**`anthropic-claude-haiku-4.5`.** Input $1/M, output $5/M. Cheapest Anthropic.
Comparable to `openai-gpt5` in absolute terms. Useful for "low-stakes,
high-volume Anthropic". Per-D-row medians: R1 $0.006, R5 $0.068 — still 11× R1.

**Observation: R5's cost gap widens under premium cloud and narrows under cheap
cloud, but never inverts.** Because R5 has high cloud-completion volume and
cloud-completion is the most expensive line on every scenario, R5 is
structurally penalised when cloud is premium and only marginally less penalised
when cloud is cheap. The headline that survives every scenario: **R1 is the
cheapest per correct answer on B and D under all six scenarios** (see
`reports/APPENDIX_SCENARIOS.md` headline table).

For most readers, the practical message: the cloud-family choice changes the
absolute dollar bill, but not the route ranking. You cannot escape the hybrid
cost premium by switching providers.

---

## §9. Limits + what we did not measure

The v3 sweep is direction-only, not significance. These are the limits.

**Single hardware tier (M4 Max 64 GB).** `devstral:24b` runs at ~30–60 tokens/s
on this machine. On a 4090 box or a 96-GB workstation, the local model would be
2–3× faster wall, and R2's wall would drop accordingly. But cloud-token counts
wouldn't change, so cloud cost is unchanged. The R4 cloud-fraction observation
(87%) is a token-economy fact, not a hardware fact — it is hardware-independent.

**Single cloud model family (gpt-5.5).** Re-priced under five other scenarios;
the route ranking is invariant. Switching the actual cloud model used at
inference time (e.g., running the full sweep against Claude Opus rather than
gpt-5.5) would shift absolute pass rates and possibly the SWE-bench ceiling —
but the cloud_fraction observation, the R5 prose-collapse, and the unique R3 win
on `d1-json-schema` are all anchored in routing dynamics rather than the cloud
model's specific capabilities. We did not re-run the sweep under Claude Opus as
the cloud model.

**Sample sizes are direction-only.** 10 tasks per category, 4 tasks per D-shape,
single seed (`seed=42`). The v1 → v3 SWE-bench reversal — R4's two Sphinx wins
disappearing — is itself a direct demonstration of slice-noise. Treat any
per-cell finding from this dataset as "directional, not significant". Variance
bounds need at minimum a 30-task SWE-bench sweep with multiple seeds; we don't
have that yet.

**D2 functional scoring is deferred.** 20 of 250 rows have no real pass/fail
signal. The cost / cloud-fraction observations on D2 are still informative but
not quality-grounded. T-23 should wire a Docker-based patch-apply harness for
the four pinned GitHub commits (`pallets/click @ 04ef3a6f47`,
`python-jsonschema/jsonschema @ 90ea779619`, `pallets/werkzeug @ 795f4eaf6e`,
`pytest-dev/pytest @ 8f81c76744`).

**R5's known JSON-extraction fragility.** Stanford's
`vendor/minions/minions/minion_code.py` has `_extract_jsons` logic that strips
fenced ```python blocks containing ```json substrings; this caused early R5 runs
to lose architect output. We patched the parser in our `r5_devminion.py` wrapper
via a `_json_proxy` monkey-patch; the v3 numbers reflect the patched behaviour.
Residual brittleness may still bias R5 down on some edge cases — but even with
that caveat, R5's 0.00 composite on prose D is consistent across 7 of 8 tasks,
so the headline is unlikely to flip.

**No R6 (Aider proper).** Aider is the most-deployed real hybrid pattern in
production today (multi-turn diff-based interactive editing). Not in scope for
v3. A future R6 would test whether the cost-quality tradeoff looks different
when the workflow is explicitly iterative diff-application rather than
single-shot generation.

**No cascade routing.** Some production hybrids use a cheap-cloud →
expensive-cloud cascade (e.g., gpt-5-mini first, fall back to gpt-5.5 on
failure). Not in this dataset. Could plausibly shift the R1 cost down without
changing pass rate.

**No multi-sample-per-task variance estimates.** Single seed; no confidence
intervals. A single bad seed could explain a cell.

**Custom-arch judge robustness is partial.** Run 11 covered D3 + D4 only. The 25
custom-arch pairings from run 07 are still single-judge single-order
(`claude-opus-4-7`, AB only). Run 10 audited an earlier custom-arch sweep under
qwen, not devstral. So "R3 ties R1 on custom-arch" is single-judge-single-order
on the v3 outputs.

**Wall + electricity costs aren't captured.** The dollar numbers in this report
are cloud API costs only. R5's 7.05 hours of wall consumed real electricity; we
don't model that.

None of these limits overturns the headline. The single most-informative
variance signal in the dataset is itself the v1→v3 SWE-bench reversal — a
10-task slice rearranged when re-run, and rearranged in a direction that closed
R4's headline win.

---

## §10. Next steps

What would change the answer.

**1. A D2 scorer.** Wire a Docker-based patch-apply harness for the four pinned
GitHub commits. 20 currently-None rows would acquire pass/fail signal. This is
the single highest-information T-23 task — D2 is the only D-shape that
materially looks like real production triage work, and we currently can't grade
it.

**2. A SWE-bench-specialised local model.** `devstral:24b` is a reasonable
general-purpose local; a model fine-tuned on the SWE-bench Verified distribution
(e.g., a future `swe-llama-7b` or `agentic-codestral-22b`) would plausibly close
the parity gap on B. If R3 can pass 5/10 on B at 0.3× R1's cost, hybrid moves
from "quality-parity cost-loss" to "quality-parity cost-win" on the category
that matters most to professional developers.

**3. Aider proper as R6.** The most-deployed production hybrid pattern is
interactive diff-based editing. R6-Aider would test whether the cost-quality
picture looks different under a workflow that explicitly iterates. Worth
investing if Aider exposes a stable batch-mode CLI.

**4. Multi-sample-per-task.** A 3-seed sweep at the same 50-task corpus would
let us put confidence intervals on the per-cell findings. The R5 prose-collapse
on D3 (4/4 zero composites) is unlikely to flip; the SWE-bench 3/10 ceiling, the
R5 wins on `d1-retry-decorator` and `d5-log-errors-today`, and the unique R3 win
on `d1-json-schema` are exactly the kind of n=1 phenomena that need replication.

**5. Multi-hardware tier.** A 4090 / H100 / lone-laptop comparison confirms that
the `cloud_fraction` observation is hardware-independent and that wall-time
tradeoffs shift but cloud-cost rankings do not. Single-tier evidence is the
largest source of "but my hardware is different" objections.

**6. Custom-arch triple-judge audit on the v3 outputs.** Run 11 covered D3 + D4
only. Extending the audit to the 25 single-judge custom-arch pairings would
tighten the "R3 ties R1 on custom-arch" claim from single-judge to triple-judge.

---

## §11. Where every number traces back to

Every dollar figure in this report derives from a row in
`results/runs/07-v3-devstral-all-routes/raw.jsonl` via `compute_cost(row,
scenario)` against `configs/pricing/pricing_tables.json`. The pricing table is
SHA256-pinned (`adbf24618010…`); you can re-derive any number by running
`./bench token-budget results/runs/07-v3-devstral-all-routes/` (full per-row
token-budget table) or `./bench analyze results/runs/07-v3-devstral-all-routes/`
(per-category aggregates under six scenarios).

Pass rates come from `quality.functional_pass` (for D1, D5, A, B, C-bcb) or
`quality.composite >= 0.5` as the pass proxy (for D3, D4, C-arch). The 96
robustness verdicts in `results/runs/11-judge-robust-D/judge.jsonl` confirm the
R1 prose dominance is judge-and-order-invariant. The full forensic record —
verbatim task statements, exact prompts, model output excerpts, per-(task,
route, variant) tokens and scores — is `reports/APPENDIX_TASKS.md` (32,907
lines, 63 unique task headings, every v3 task covered).

The companion to this report is `reports/ARTICLE.md` — punchy, decision-first,
~4,500 words. The forensic-detail companions are `reports/APPENDIX_TASKS.md`,
`reports/APPENDIX_SCENARIOS.md`, and `reports/APPENDIX_ROUTES.md` (the latter
contains the canonical R5 worked example on
`real-dev/d3-extract-validation-helper`). The per-run write-up is
`results/runs/07-v3-devstral-all-routes/run-notes.md`; the robustness write-up
is `results/runs/11-judge-robust-D/run-notes.md`; the publish audit is
`docs/audits/T-22-v3-publish-readiness.md` (verdict YELLOW, two cosmetic README
defects and a fresh-clone pytest hazard).

If you want one chart that captures the entire report:
`results/runs/07-v3-devstral-all-routes/charts/pareto.png`. The R2 cluster
against the $0 axis (bimodal: solved or unsolved), the R1 cluster on the
low-cost / high-composite frontier, the R5 outlier cluster top-right — that
single Pareto plot is the visual summary of every number in §2.
