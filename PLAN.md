# hybrid-coding-eval — project plan

A standalone, open-sourceable project that answers — with data, not vibes — the question:

> *Given a coding task, should I run it on a local model, in the cloud, or hybrid? And how much does each option actually cost in $ and quality?*

The plan is structured so the project can be built in three phases (MVP, V1, V2). Each phase produces something publishable on its own. The article (`hybridarchitecturearticle.md`) gets rewritten from the V1 dataset.

---

## 0. Why this exists / what's wrong with the current state

What we have today (`opencode/examples/`):
- 3 coding tasks
- 2 routing approaches per task (cloud-only single-shot, hybrid architect)
- Cost & latency captured accurately
- Quality assessed by **eyeballing the output** for ~5 minutes per task

What's missing:
- Real benchmark coverage. 3 tasks isn't a finding, it's an anecdote.
- Quality scoring that isn't subjective.
- Multiple routing strategies compared (we only tested architect; not Minion-style stateful, not RAG-style, not single-shot-via-router/heuristic).
- Hardware-portable reproduction. Today the examples assume our specific M4 Max + 64 GB setup.
- Use-case taxonomy. The article gives a vague "hybrid wins when you decompose" — but for *which* task types specifically?

The new project fixes all five.

---

## 1. The framing question, restated

Three primary axes the project measures:

1. **Quality** — does the output do what was asked, correctly?
2. **Cost** — $ paid to cloud APIs (local = $0 at the margin)
3. **Latency** — wall-clock to completion

Two cross-cutting axes:

4. **Use case** — task type × task size × context dependency × quality bar
5. **Hardware envelope** — does this even run on the user's machine?

The project's deliverable is a *decision matrix*: given (task type, hardware) → (best routing strategy, expected cost, expected latency, expected quality). With reproducible numbers.

---

## 2. Use-case taxonomy

Coding tasks differ along several axes. The project tags every task with a multi-axis category:

| axis | values |
|---|---|
| **size** (output tokens) | tiny (≤500), small (500–2 K), medium (2–8 K), large (8–25 K), huge (25 K+) |
| **task type** | function-completion, refactor (single-file), refactor (multi-file), debug, write-tests, explain, design/architecture, migrate, code-review, build-from-scratch |
| **context dependency** | standalone (no prior context), file-local, module-local, repo-wide (long context) |
| **quality bar** | demo (works once), prototype (handles happy path), production (correct + tested + reviewed) |
| **interactivity** | interactive (developer waits), batch (overnight ok) |
| **tool need** | none, single-tool, multi-tool-loop |

A task in the benchmark = one cell in this hypercube. We don't aim to fill every cell — we aim to fill enough that decision boundaries become legible.

---

## 3. The benchmark — task design

### Where tasks come from

Three sources, in priority order:

1. **Adapt established public benchmarks** (validated by the community, pre-built harnesses) — *strongly preferred*. From the research run we'll know which of these are most usable: HumanEval+, MBPP+, BigCodeBench-Hard, SWE-bench Verified, Aider Polyglot, LiveCodeBench, RepoBench, ClassEval, plus any 2025–2026 additions. Wherever possible we run the upstream harness and just record cost+latency+quality alongside.
2. **Hand-curated tasks** that probe specific cells in the taxonomy that public benchmarks don't cover (architectural design, long-form explanation, code review). ~15–20 tasks.
3. **Replay of real coding sessions** (anonymised) — eventually. V2 ambition.

### Initial task set (MVP, 45 tasks — finalised after `docs/PRIOR_ART.md`)

Pulled from established benchmarks. Each comes with a runnable harness, so functional scoring is solved for ~37 of the 45.

| count | source | category | scorer | upstream harness |
|---:|---|---|---|---|
| 10 | **HumanEval+** random sample | tiny • function-completion • standalone | functional (pytest) | `evalplus.github.io` |
| 5 | **MBPP+** random sample | tiny • function-completion • standalone | functional (pytest) | `evalplus.github.io` |
| 10 | **BigCodeBench-Hard** random sample | medium • library-intensive • module-local | functional (pytest) | `huggingface.co/spaces/bigcode/bigcodebench` |
| 5 | **SWE-bench Verified** easy tier ⭐ | medium-large • multi-file • repo-wide • agentic | functional (`mini-SWE-agent` runs repo's own tests in Docker) | `swebench.com` |
| 5 | **LiveCodeBench** (latest month, contamination-free) | medium • reasoning-heavy | functional (test outputs) | `livecodebench.github.io` |
| 5 | **Aider Polyglot** (one per language: C++, Go, Java, JS, Py, Rust) | medium • code-editing • 2-attempt | functional (Exercism tests) | `aider.chat/docs/leaderboards` |
| 3 | hand-curated architecture / explanation | medium • design • standalone | LLM-judge (claude-opus-4-7 pairwise) | n/a — custom |
| 2 | our existing 3 (todo-api, url-shortener) | large • build-from-scratch | LLM-judge | n/a — custom |
| **45** | **total** |  |  |  |

⭐ **SWE-bench Verified easy tier is the gold-standard tier** — real agentic coding on real GitHub issues. The `mini-SWE-agent` harness runs each task in a Docker container with the repo's own test suite, giving binary pass/fail. Frontier scores: Claude Opus 4.6 77.2 %, GPT-5 74.9 %, Devstral-Small-2-24B 72.2 % — meaning the gap between best open and best cloud is **5 pp** here. This is the most important tier for our routing eval.

**LiveCodeBench-latest is the credibility tier** — contamination-free since it's freshly scraped from LeetCode/AtCoder/Codeforces. The 13-pp gap there (GPT-5 68.4 % vs Qwen3-Coder 55.9 %) is where hybrid routing genuinely matters.

If you have less time / budget for V0: trim to 25 tasks (5 HumanEval+, 5 MBPP+, 5 BigCodeBench-Hard, 5 SWE-bench, 5 Aider Polyglot). Skip LiveCodeBench until V1.

---

## 4. The runners — four routing approaches

Every task runs through the same four pipelines. Each writes outputs in a uniform shape.

| id | description | implementation status |
|---|---|---|
| **R1 cloud-single** | Single-shot to flagship cloud model (gpt-5.5 or claude-opus-4-7). The "what most people do today" baseline. | exists (`examples/run-comparison.mjs:runCloudOnly`) |
| **R2 local-only** | Single-shot to qwen3.6:27b-coding-mxfp8 (or whatever fits the user's hardware). The "free but limited" baseline. | needs implementation — small wrapper |
| **R3 hybrid-architect** | Cloud planner → per-step router/heuristic executor → cloud synth. The pipeline we already have. | exists (`router/agentic/architect.mjs`) |
| **R4 hybrid-minion** | Stanford Minions-style stateful Q&A: cloud asks targeted questions, local reads context and answers, no output replay. | new — port of `EXTERNAL/minions/minions/minion.py` to our proxy |
| **R5 local+cloud-review** ⭐ | Aider's architect/editor pattern: cloud plans + reviews; local writes code; cloud requests fixes if review fails. **The single most-deployed real hybrid pattern in production.** | new — port of `aider --architect` + `EXTERNAL/minions/minions/minion_code.py` (`DevMinion` review/fix loop) |

R4 and R5 are the new architectural levers the project is testing.

- R4 directly addresses the synth-replay tax that hurt R3 in our existing article (cloud no longer sees full step concatenation; instead asks targeted questions).
- R5 is the most credible reference architecture in production today (Aider) plus the iterative review loop from Stanford's DevMinion. Worth measuring head-to-head.

Each runner produces:
- `output.txt` — the final answer / generated code
- `metrics.json` — cost (USD, broken down), latency (wall + per-step), token counts
- `events.json` — full trace (one entry per LLM call)

---

## 5. The scorers — how we measure quality

This is the hardest part of the project. Three layers, in increasing rigor:

### 5a. Functional scoring (gold standard)

For tasks that come with tests (HumanEval+, MBPP+, BigCodeBench, SWE-bench): just run the tests. Pass/fail/partial-pass. Already-built upstream harnesses do this.

This handles ~25 of our 30 MVP tasks with ground-truth scoring.

### 5b. LLM-as-judge (for unscorable tasks)

For tasks without tests (architecture-design, code review, explanation):

- Submit `(prompt, output_A, output_B)` to an *impartial* judge model — probably `claude-opus-4-7` (different family from the routes being tested, which are gpt-5.5-based).
- Use a structured rubric per task type (correctness, completeness, style, reasoning quality).
- Pairwise + bias-corrected: A-vs-B and B-vs-A both, average the verdict. Avoids position bias.
- Capture both the score and the judge's reasoning.

Known pitfalls to defend against (will be in the methodology section):
- Length bias (judges prefer longer answers)
- Style bias (judges prefer their own writing style)
- Self-promotion (judges prefer outputs from their own family)

Counter-measures: Bradley-Terry aggregation, swap-test, multi-judge ensemble.

### 5c. Human spot-check (for credibility, not scale)

For 5–10% of tasks, a real human (us) reviews the output. Catches obvious LLM-judge errors. Recorded as ground-truth annotations on the dataset.

### 5d. Composite score

Per task: `quality_score ∈ [0, 1]`. For functional tasks = % of tests passing. For judge-scored = average of pairwise win-rate. For mixed-test-judge tasks = weighted average. The paper-ready format.

### 5e. Headline aggregate metric — **Bounded-ARQGC** (adopted from IPRBench)

Across the entire benchmark we report the **Bounded Area-under Quality-Cost Curve** metric proposed by IPRBench (Jiang et al., 2024). Conceptually:

- For each route, plot the cost-vs-quality Pareto curve across all tasks (sorted by ascending cost).
- Compute the AUC under the quality axis, bounded by a maximum acceptable cost.
- A higher Bounded-ARQGC means "more quality per dollar across the workload."

This gives us **one number per route** that summarises the cost-quality tradeoff rigorously. It's already used in routing literature so reviewers will recognise it. Implementation: ~50 LoC of pandas / numpy.

Paper-ready output: a single bar chart of Bounded-ARQGC across R1–R5, plus the underlying per-task scatter for transparency.

---

## 6. What gets measured per (task, route) pair

A single experiment cell:

```
task_id           HumanEval/0
route             R3 (hybrid-architect)
hardware_profile  M4-Max-64GB-qwen3.6-27b-coding-mxfp8

cost
  total_usd       0.012
  cloud_input_usd 0.001
  cloud_output_usd 0.011
  local_usd       0.000   (annotated: assumes laptop hardware sunk cost)

latency
  wall_ms         8240
  median_step_ms  823
  longest_step_ms 1500

tokens
  prompt          1234
  completion      567
  cached          0
  reasoning       89

quality
  functional      1.0     (test passed)
  judge_pairwise  null    (not used for this task)
  composite       1.0
  human_spot      null

routing
  total_calls     5
  local_calls     4
  cloud_calls     1
  decisions[]     <route trace>
```

Persisted as one JSONL row per cell. Aggregations and charts compute from there.

---

## 7. Hardware envelope handling

A real concern: someone running this on a 16 GB MacBook Air can't load qwen3.6:27b. The project ships a `bench env-detect` step that:

1. Inspects the host: total RAM, GPU/Metal/CUDA presence, free disk.
2. Selects the best local model that fits, from a tiered list:
   - **64 GB+ Apple Silicon / 24 GB+ NVIDIA**: qwen3.6:27b-coding-mxfp8 (or qwen3-coder:30b-a3b)
   - **32 GB Apple / 16 GB NVIDIA**: qwen3-coder:14b or qwen2.5-coder:14b
   - **16 GB Apple / 8 GB NVIDIA**: qwen2.5-coder:7b
   - **8 GB / CPU-only**: qwen2.5-coder:1.5b — quality will suffer; flagged.
3. Records the chosen model in every result row, so cross-machine reports stay honest about which model produced which number.

For published reports we'd run on at least 3 hardware tiers (high / mid / low) so readers can see the trade-off curve.

This also gives us *one* of the article's most useful sections: a table of "if you have hardware X, here's the best you can get out of hybrid routing."

---

## 8. Project layout

```
hybrid-coding-eval/
├── README.md                 — quick start + the article
├── PLAN.md                   — this file
├── docs/
│   ├── METHODOLOGY.md        — how the eval works, biases acknowledged
│   ├── REPRODUCING.md        — how to run on your own machine
│   ├── DECISIONS.md          — design choices + rationale
│   └── PRIOR_ART.md          — synthesised research findings (auto-generated from research/)
├── benchmark/
│   ├── tasks.yaml            — task registry (id, source, category, files, scoring)
│   ├── humaneval-plus/       — adapter to upstream harness
│   ├── mbpp-plus/            — same
│   ├── bigcodebench/         — same
│   ├── swe-bench-verified/   — same
│   ├── aider-polyglot/       — same
│   ├── custom/               — our hand-curated tasks
│   │   ├── arch-design-multitenant-postgres/
│   │   ├── code-review-pr-1234/
│   │   └── …
│   └── _adapters/            — common interfaces
├── runners/
│   ├── R1_cloud_single.mjs
│   ├── R2_local_only.mjs
│   ├── R3_hybrid_architect.mjs
│   ├── R4_hybrid_minion.mjs
│   └── shared.mjs            — proxy URL, cost capture, output framing
├── scorers/
│   ├── functional.mjs        — runs upstream test harnesses
│   ├── llm_judge.mjs         — claude-opus-4-7 pairwise judge
│   ├── human_spot.mjs        — reads our annotations file
│   └── compose.mjs           — combines into a composite score
├── env/
│   ├── detect.mjs            — hardware envelope detection
│   ├── tiers.yaml            — model recommendations per tier
│   └── prereq-check.mjs      — Ollama installed? proxy running? key present?
├── results/
│   └── <date>-<machine>/
│       ├── results.jsonl     — one row per (task, route) cell
│       ├── results.parquet   — same in columnar form for analysis
│       └── report.md         — generated from results.jsonl
├── viz/
│   ├── pareto.py             — quality-vs-cost scatter
│   ├── decision-matrix.py    — heatmap of best route per (task category, hardware tier)
│   └── per-task.py           — drill-down tables
├── bin/
│   ├── bench                 — main CLI
│   ├── ingest-public         — pulls in HumanEval+/MBPP+/etc.
│   └── publish-report        — writes the article + uploads
├── research/
│   ├── _run_research.py      — research wrapper (currently running)
│   ├── 01_coding_eval_benchmarks/
│   ├── 02_local_coding_model_performance/
│   ├── 03_hybrid_coding_architectures_with_empirics/
│   └── 04_hardware_reality_and_cost_calibration/
└── article/
    └── hybridarchitecturearticle.md  — the published artefact
```

---

## 9. Phasing — what to ship when

### Phase MVP (1 week of focused work)

Goal: replace the current 3-task article with a 30-task version that has functional scoring on most of it.

- Pull in HumanEval+ adapter (5–10 tasks)
- Pull in MBPP+ adapter (5 tasks)
- Wire R1 (cloud-single) and R3 (hybrid-architect) — already exist
- Add R2 (local-only) — small wrapper on the proxy
- Add R4 (hybrid-minion, simplest variant) — port the Minion singular protocol from `EXTERNAL/minions`
- Functional scorer for HumanEval+/MBPP+ (off-the-shelf)
- Simple aggregate report
- One hardware tier (M4 Max 64 GB)
- Update the article with V1 numbers

### Phase V1 (2nd week)

Goal: usable by anyone; first publishable version of the article + project.

- Add BigCodeBench-Hard (5 tasks, harness)
- Add SWE-bench Verified easy tier (5 tasks — these are the gold-standard agent-loop tasks)
- LLM-as-judge for the 5 hand-curated unscorable tasks
- Hardware envelope detection + tier-aware model selection
- Pareto charts + decision matrix
- Methodology doc that calls out every bias we know about
- Public README with copy-paste reproduction instructions

### Phase V2 (later, ambition)

- Multi-hardware tier runs (small / mid / large) → side-by-side
- Replay-of-real-sessions mode
- Cost prediction (the inference-estimator pattern from Minions)
- Alternate routers in benchmark (cascade, embedding-kNN, llm-classifier — currently only heuristic gets tested)
- Distributed / community-contributed runs (people upload their own results)

---

## 10. Honest risks and biases (the article will address each)

1. **Benchmark contamination**. Many open benchmarks are in pre-2024 training data. Models can memorise. We'll prefer benchmarks that publish clean test splits (LiveCodeBench's date-bounded format is best). Document which tasks are at risk.
2. **LLM-as-judge biases**. Length bias, style bias, self-preference. Counter-measures noted in §5b.
3. **Single-hardware testing**. MVP runs on M4 Max only. Findings won't fully generalise. We say so plainly.
4. **Cost = cloud $ only**. We don't include electricity, hardware amortisation, or developer time. Those are real costs but harder to standardise. Methodology doc explicitly notes this.
5. **Task selection bias**. We choose tasks; the choice is itself a finding. Try to use random samples from public benchmarks where possible.
6. **Routing drift**. Heuristic threshold is calibrated for opencode-style usage. Different envelopes might shift it. Each route's config is logged in results.
7. **Quality is multi-dimensional**. A single composite score is a lossy summary. We'll publish per-axis breakdowns alongside.
8. **Latency is wall-clock**. Doesn't account for parallel orchestration. Marked in metrics.

---

## 11. The article that comes out the other end

`hybridarchitecturearticle.md` (already drafted; gets rewritten from V1 data):

1. **Hook**: a sample decision matrix showing 3-4 strikingly different best-routes across task categories.
2. **The framing question** (cost × quality × hardware envelope).
3. **What we actually measured** (~30 tasks × 4 routes × 1 hardware = ~120 runs; expand in V1).
4. **Where each route wins** — per category, with the data.
5. **The interesting finds** — anti-intuitive results from the matrix; failures (like the synth-blew-its-budget exp 3 finding); honest losses for hybrid.
6. **Open questions** — what V2 would answer.
7. **Reproduce yourself** — `git clone … && bench run` link.
8. **Prior art** — credit to Minions, Aider, RouteLLM, etc., synthesised from research.

The viral-friendly framing: "We graded 30 coding tasks across local / cloud / hybrid on a real laptop. Here's the matrix that tells you what to use."

---

## 12. Where we are right now (status)

- ✅ Project scaffolded at `/Users/sanchitmonga/development/ODLM/MONOREPOOO/CODING/hybrid-coding-eval/`
- 🟡 Research run firing (4 parallel deep-research queries; ~5–15 min)
  - 01 — coding eval benchmarks
  - 02 — local coding model performance
  - 03 — hybrid coding architectures with empirical results
  - 04 — hardware reality and cost calibration
- ⏳ Next once research returns: synthesise into `docs/PRIOR_ART.md`, refine task selection in §3 with whatever the strongest benchmarks turn out to be, then start MVP build.

---

## 13. Open questions for human review (before MVP build)

1. **Project name**. `hybrid-coding-eval` is descriptive. Alternatives: `coderoute-eval`, `where-does-local-win`, `localvscloud-coding`. Final name affects repo URL + brand.
2. **Open-source license**. MIT for the harness code; CC-BY-4.0 for the dataset / results / article? (Standard split.)
3. **Public repo or private fork first**. Suggestion: build in private until the V1 data is honest, then flip public + announce.
4. **Cloud baseline model**. We've been using gpt-5.5. Should we also run claude-opus-4-7 as a second cloud baseline? Doubles cloud cost but gives a more complete picture.
5. **Hardware tier reach**. MVP only tests M4 Max. V1 needs at least one mid-tier (M2 16 GB? RTX 4090?). Where do we get those machines?

These don't block the MVP but should be settled before V1 ships publicly.
