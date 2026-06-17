# Hybrid routing design

> Single-source reference for **what** this benchmark measures, **how** the
> router decides local-vs-cloud, **which** coding agents we run, and **why**
> the numbers in `docs/release-notes/` are defensible. If you're new, read
> top-to-bottom; if you're benchmarking a new model, jump to [§9](#9-add-a-new-local-model).

---

## 1. The question

> Given one developer-class laptop (M-series Mac, 64 GB), one local LLM, and
> access to a frontier cloud LLM — for which coding task shapes is it worth
> routing some calls locally instead of sending everything to the cloud?

We answer it empirically. For every cell `(local-model, agent, task-class,
strategy, seed)` we run the same set of tasks and report:

- **Pass-rate** — fraction of tasks that pass functional tests, with a
  non-parametric bootstrap 95% CI.
- **Cost** — USD spent on the cloud LLM, derived from token counts and a
  versioned pricing table.
- **Cloud fraction** — Σ cloud tokens ÷ Σ all tokens. Token-based, never
  call-count-based (call-count is gamed by cascade/llm-classifier meta-calls).
- **Wall time** — median wall-clock ms per task.

Every number in `docs/release-notes/*.md` is a slice of those four numbers
across 1,644 rows in v1.4.

---

## 2. Architecture, one diagram

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                      ./arena sweep --config X.yaml                       │
│                                                                          │
│  ┌─────────────────────┐                                                 │
│  │  cli/bench.py       │  spawns one Node router proxy with              │
│  │  (orchestrator)     │  LOCAL_MODEL + CLOUD_MODEL injected             │
│  └─────────┬───────────┘                                                 │
│            │                                                             │
│            ▼                                                             │
│  ┌─────────────────────┐         ┌──────────────────────────┐            │
│  │  core/experiment.py │ for each│  agents/<agent>.py        │           │
│  │  build_task_plan +  │ (task,  │  (one runner per agent —  │ subprocess│
│  │  run_pair() loop    │  agent) │  aider / opencode / mini- │           │
│  └─────────┬───────────┘─────────►  swe-agent / cline)       │           │
│            │                     └─────────────┬────────────┘            │
│            │                                   │                         │
│            │           OpenAI-compatible HTTP  ▼                         │
│            │                          ┌────────────────────────┐         │
│            │                          │ router/server.mjs      │         │
│            │                          │ + router/strategies.mjs│         │
│            │                          │ (decides local|cloud)  │         │
│            │                          └─────┬──────────┬───────┘         │
│            │                                │          │                 │
│            │                                ▼          ▼                 │
│            │                            Ollama      OpenAI               │
│            │                          (local model) (cloud model)        │
│            │                                                             │
│            ▼                                                             │
│  ┌─────────────────────┐                                                 │
│  │ scorers/functional_ │  Docker sandbox runs the agent's diff           │
│  │ python (sandbox)    │  against the fixture's pytest suite             │
│  └─────────┬───────────┘                                                 │
│            ▼                                                             │
│  results/runs/<sweep>/raw.jsonl   (one ResultRow per task × agent ×      │
│                                    strategy × seed; tokens never cost,   │
│                                    cost is derived at analyse-time)      │
└─────────────────────────────────────────────────────────────────────────┘
```

The Python orchestrator owns the experiment loop. The Node router owns the
routing decision. The two communicate via OpenAI-compatible HTTP, which lets
every off-the-shelf coding agent talk to the router as if it were OpenAI.

---

## 3. The four coding agents

We measure **agent-loop routes** only — agents that own their own multi-turn
tool use. The repo doesn't try to be one. Each agent is a battle-tested,
externally-maintained tool we wrap thinly.

| Agent              | Loop style                | Strengths                                          | Caveats                                              |
| ------------------ | ------------------------- | -------------------------------------------------- | ---------------------------------------------------- |
| `aider`            | architect → editor        | Tight diffs, parsable patches                      | Markdown-fence parse bug on some local models        |
| `opencode`         | free-form tool calls      | High ceiling when tool calls are clean             | gemma4-specific in v1.4 — qwen variants fail parsing |
| `mini-swe-agent`   | minimalist bash-only ReAct| Closest to SWE-bench reference; small surface area | Needs Docker for SWE-bench Verified                  |
| `cline`            | Plan / Act with 8-14 turns| Iteration wins puzzles + refactors at 30B local    | Highest token cost per cell                          |

Each wrapper lives in `src/hybrid_arena/agents/<agent>.py` and exposes
one `run(task, *, proxy_url, ...) -> ResultRow` function. The orchestrator
calls them through `core/experiment.py:_runner_for(agent)`.

Why not Cursor / Continue / Cody? They were considered and dropped because
either (a) they don't expose a headless CLI, or (b) they require a managed
account. The four agents above can all be driven from a script with no UI.

---

## 4. The eight routing strategies

The router proxy reads each request, picks a backend (local or cloud), and
forwards the body. Strategies live in `router/strategies.mjs`. The Python
side never knows which backend served a call — it only sees the token
counts in the OpenAI usage object.

| Strategy           | Decision rule                                                                  | Use when                                 |
| ------------------ | ------------------------------------------------------------------------------ | ---------------------------------------- |
| `always-cloud`     | Send every request to the cloud model. Control.                                | Baseline — set the ceiling               |
| `always-local`     | Send every request to the local model. Control.                                | Baseline — set the floor                 |
| `rules`            | Keyword + regex rules (e.g. "refactor" → local)                                | Demos / debugging                         |
| `heuristic`        | Weighted scoring on prompt length, code-block count, agent state               | First strategy to actually try in prod   |
| `llm-classifier`   | One `qwen3:0.6b` call returns `SIMPLE` or `COMPLEX`                            | When you trust a tiny model's taste      |
| `embedding-knn`    | `nomic-embed-text` query → kNN vote against a 50-example labelled corpus       | Stable, no-LLM-overhead routing          |
| `cascade`          | Heuristic decides first; on borderline confidence, llm-classifier tie-breaks   | Highest pass-rate hybrid in v1.4         |
| `phase-aware`      | Like heuristic, but with an `aider-architect-step` bonus for `aider`           | Aider-specific tuning                    |

`cascade-tuned` is the same as `cascade` with the `ROUTER_CASCADE_THRESHOLD`
env var injected per pass — used for the v1.3 threshold sweep.

Every routing decision is appended to `router/logs/decisions.jsonl` with the
score, reason, and the picked backend. That file is the single source of
truth for routing audits.

### Append `!local` / `!cloud` to force

Any agent can override the strategy on a single call by appending `!local`
or `!cloud` to the `model` field. We use this in tests; agents in normal
sweeps don't.

---

## 5. Task classes

| Class       | Source                            | Shape                                                  | Count in v1.4 |
| ----------- | --------------------------------- | ------------------------------------------------------ | ------------- |
| `puzzles`   | Exercism Python (via Aider polyglot benchmark) | Single-function, single-file tasks with hidden tests   | 5             |
| `refactors` | Hand-written real-PR patterns     | Multi-file refactor / review / script tasks (D1+D5 in v1.4 canonical; v1.5 adds 4 D6 hard implementation challenges) | 12 (8 + 4 D6) |
| `real-prs`  | SWE-bench Verified subset         | Repo-level patches against Docker testbeds              | (v1.6+ work; adapter shipped) |

Each task adapter lives in `src/hybrid_arena/tasks/<class>/`. A task is
a small dataclass: `id`, `fixture_path`, `prompt`, `run_cmd`. Scoring is per
class — `puzzles` uses pytest in a Docker sandbox; `refactors` uses a
dispatcher in `tasks/refactors/scorers.py` that picks the right per-task
checker (e.g. "does the diff add the rate-limit guard?").

---

## 6. The result schema

Every row in `results/runs/<sweep>/raw.jsonl` is a `ResultRow` (see
`src/hybrid_arena/core/metrics.py`):

```python
@dataclass
class ResultRow:
    task_id: str                 # 'exercism-python/grep'
    category: str                # 'puzzles' | 'refactors' | 'real-prs'
    route: str                   # 'aider' | 'opencode' | 'mini-swe-agent' | 'cline'
    router_strategy: str | None  # 'heuristic' | 'cascade' | ...
    seed: int | None             # deterministic seed stamped by the orchestrator
    hardware_profile_ref: str    # 'Apple M4 Max|64GB|git<sha>|mh<self-hash>'

    tokens: TokenUsage           # prompt / completion / cached / local_* / cloud_*
    latency: Latency             # wall_ms + per_call_ms[]
    quality: Quality             # functional_pass, tests_passed/total, composite
    routing: Routing             # total_calls, local_calls, cloud_calls

    cloud_model_id: str | None   # 'gpt-5.5' — stamped from BenchConfig.models.cloud
    local_model_id: str | None   # 'gemma4:31b'
    config_sha: str | None       # SHA256 of the BenchConfig that produced the row
    error: str | None            # set when the runner failed (timeout, parse, etc.)
```

Three invariants:

1. **Tokens are persisted, cost is derived.** No row contains a `cost_usd`
   field; cost is computed on read against `configs/pricing/pricing_tables.json`.
   That lets you re-price an old dataset against new pricing scenarios.
2. **`always-local` rows always have `cloud_* = 0`.** Non-zero cloud tokens
   in an `always-local` row is a routing bug.
3. **`error` is set ↔ tokens are zero ↔ quality is all-None.** Error rows
   are excluded from bootstrap CIs by `analysis.bootstrap`.

---

## 7. The analysis pipeline

`./arena analyze <sweep_dir>` runs these in order:

1. `aggregate.py` — per-`(category, route, strategy)` medians and totals.
2. `bootstrap.py` — 95% percentile CIs per cell (non-parametric, 1k resamples).
   Computes `pass_rate`, `cost_usd`, `cloud_fraction`, and `wall_ms`. Stratifies
   by `(category, route, router_strategy)` by default; pools across seeds.
3. `decision_matrix.py` — renders the cell × strategy table as Markdown,
   with a "recommended" column = highest pass-rate at the lowest tying cost.
4. `cost_scenarios.py` — re-prices every row under five pricing scenarios
   so callers can answer "what would this have cost on gpt-5-mini?".
5. `viz/cost_quality_pareto.py` + `viz/decision_heatmap.py` — PNG charts.

Every step is idempotent and re-readable. Re-running on the same `raw.jsonl`
produces byte-identical JSON outputs.

---

## 8. The pricing table

Cloud spend is **always** computed from tokens × pricing rates. The rates
live in `configs/pricing/pricing_tables.json` (USD per 1,000,000 tokens):

```json
{
  "rates_per_m": {
    "gpt-5.5":                    { "input": 5.0,  "output": 30.0, "cache_read": 0.5 },
    "anthropic-claude-opus-4.7":  { "input": 15.0, "output": 75.0, "cache_read": 1.5 },
    "__local__":                  { "input": 0.0,  "output": 0.0,  "cache_read": 0.0 }
  }
}
```

`router/pricing.mjs` reads the same JSON file. Parity is verified by
`tests/test_pricing_parity.py` — the router and the Python harness compute
identical costs for any usage payload.

Cost formula:

```text
usd = (prompt − cached) × input/1e6 + cached × cache_read/1e6 + completion × output/1e6
```

`completion_tokens` already includes `reasoning_tokens` — they're surfaced
in the row for transparency only, not added again.

---

## 9. Add a new local model

Drop-in recipe for benchmarking a new local model against the v1.4 canonical
matrix:

```bash
ollama pull <new-model>
./arena setup                # idempotent; first run only
./arena sweep \
    --config configs/v1.4-canonical-gemma4.yaml \
    --set models.local=<new-model> \
    --set out_dir=results/runs/v1.4-<new-model> \
    --strategies always-cloud,always-local,heuristic,cascade \
    --seeds 42,7,13
```

`./arena setup` checks prereqs (Docker, Ollama, Node, API keys) and
builds the sandbox image / installs the agent CLIs. Long-form lifecycle
commands (`./arena start` / `pause` / `resume` / `stop` / `status`) are
documented inline at `./arena --help` and exist so you can detach the
sweep and reclaim the laptop.

Expected runtime on an M4 Max 64 GB: 10–15 hours, ≈ $30–50 cloud spend at
gpt-5.5 list price. The router auto-spawns from `models.local`; you don't
need a separate router terminal.

When the sweep completes:

```bash
./arena analyze results/runs/v1.4-<new-model>
jq '.cells["refactors::cline::heuristic"].pass_rate' \
   results/runs/v1.4-<new-model>/bootstrap_cis.json
```

That cell — `cline + your-model + heuristic + refactors` — is the headline
number. Compare against the v1.4.1 release notes for context.

> **Cell-key naming.** Cell keys use the same human-readable task-class
> name end-to-end: `puzzles::aider::heuristic`,
> `refactors::cline::cascade`, `real-prs::mini-swe-agent::always-local`.
> Pre-v1.4.3 datasets used single-letter codes (`A`/`B`/`D`); those keys
> are retired — re-render legacy datasets with the v1.4.3+ harness to
> migrate.

---

## 10. What we deliberately do NOT do

- **No LLM-as-judge for prose tasks.** Functional-pass only. The v1.0–v1.3
  experiments with Opus-as-judge are documented in CHANGELOG but the judge
  scorer was deleted in v1.4 — it added too much variance for too little
  signal on coding tasks.
- **No Continue / Cursor / Cody.** No headless CLI ⇒ no reproducible
  driver ⇒ no apples-to-apples cell in the matrix.
- **No "average across vendors" cost claims.** Every cost number in the
  release notes is gpt-5.5 specifically. The `cost_scenarios` re-pricing
  exists for what-if analysis only.
- **No statistical claims past 95% CI.** The dataset is small (24-row cells
  are typical); we publish CIs and let readers decide.
- **No router-side caching.** The cloud's prompt-cache hits are visible in
  `cached_tokens` and charged at `cache_read`, but the router never inserts
  its own cache layer that could leak across sweeps.

---

## 11. Limitations + threats to validity

- **One laptop, M4 Max 64 GB.** Memory bandwidth (546 GB/s) and the 30B-class
  quantization sweet spot are both Apple-Silicon-specific. A 4090 + Linux
  will trade more compute for less RAM; numbers may swing.
- **18 tasks per cell.** Bootstrap CIs reflect that — 96% on 24 rows has a
  CI of roughly [88, 100]. Treat single-point claims with appropriate
  skepticism; cite the CI.
- **Python-only fixtures.** TypeScript / Go / Java are obvious next steps;
  they would change the routing-strategy weights (heuristic's "code block
  count" heuristic is regex-keyed on Python markers).
- **Cloud model is gpt-5.5 across all sweeps.** Anthropic Opus / Sonnet
  cells haven't been run end-to-end; they exist in the pricing table for
  re-pricing the gpt-5.5 datasets, not for direct comparison.
- **Aider's markdown-fence parser** rejects some valid completions; the
  v1.4.0 "23/24 = 96%" cell loses 1/24 to this bug, not a model failure.

---

## 12. Pointers

- Add a new agent → write a `src/hybrid_arena/agents/<name>.py` with
  a `run(task, *, proxy_url, ...) -> ResultRow` function, register it in
  `core/experiment.py:_runner_for`, add `<name>` to the `Agent` literal in
  `core/config/schema.py`. Tests live in `tests/agents/test_<name>.py`.
- Add a new strategy → write a function in `router/strategies.mjs`,
  register it in the `STRATEGY_REGISTRY` at the bottom of that file, add
  the name to `RouteStrategy` in `core/config/schema.py`.
- Add a new task class → create `src/hybrid_arena/tasks/<class>/`
  with `adapter.py` (loads tasks) and `scorers.py` (scores a row); add the
  class name to `CATEGORY_SOURCES` in `core/experiment.py` and `TaskClass`
  in `core/config/schema.py`.
- Add a new pricing scenario → append to `configs/pricing/pricing_tables.json`
  and to `PRICING_SCENARIOS` in `analysis/cost_scenarios.py`. Both Python
  and Node pick it up automatically.

The full repo map lives in `AGENTS.md` for AI coding agents reading the
codebase; `README.md` is the human-facing entry point.
