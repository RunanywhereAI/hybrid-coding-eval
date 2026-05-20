# Agentic routes (R6 / R7 / R8) — design + integration guide

Introduced in **v1.1.0**. These routes wrap real ReAct loops (subprocess `opencode` / `aider` / `mini-swe-agent`) and route the agent's per-turn LLM calls through this repo's proxy on :8787 — so the **agent's local-vs-cloud decisions are part of the experiment**. The non-agentic R1–R5 from v1.0.0 are unchanged.

| Route | Tool | Status in v1.1 | Tasks the canonical sweep covers |
| --- | --- | --- | --- |
| **R8** | [opencode](https://github.com/anomalyco/opencode) | **Primary (canonical)** | SWE-bench Verified · HumanEval+ · Exercism · real-dev D1/D5 |
| R6 | [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | Experimental | — (not in canonical) |
| R7 | [Aider](https://github.com/Aider-AI/aider) | Experimental | — (not in canonical) |

R6 and R7 ride along on every shared refactor (correlation-id attribution, agent-aware heuristic) but their canonical sweeps + Docker-scoring polish are deferred to v1.2.

---

## How an agentic route works

Each runner is a thin Python wrapper around a CLI subprocess:

```
┌──────────────────┐    subprocess     ┌────────────────────────┐
│  R8 runner       │ ───────────────▶  │  opencode run -m       │
│  (Python)        │                   │   hybrid-router/router │
│                  │                   │   /<strategy>/run-<id> │
└──────────────────┘                   └────────────┬───────────┘
        ▲                                           │ LiteLLM
        │                                           ▼
        │                              ┌────────────────────────┐
        │                              │  router proxy :8787    │
        │  reads decisions.jsonl       │  (Node)                │
        │  filtered on bench_run_id    │                        │
        │                              │  Decides per-call:     │
        │                              │    local | cloud       │
        │                              └────────────┬───────────┘
        │                                           │
        │                                           ▼
        │                              ┌────────────────────────┐
        │                              │  local Ollama  /  cloud│
        │                              │  (qwen3-coder / gpt-5.5)│
        │                              └────────────────────────┘
        │
        └─── tokens + routing → ResultRow → raw.jsonl
```

Per-task flow:

1. Generate a 12-hex `bench_run_id` (`uuid.uuid4().hex[:12]`) — a correlation id for this single `(task, route, strategy)` invocation.
2. Copy the fixture into a per-run scratch dir. Build the prompt.
3. Subprocess the agent CLI with model id = `router/<strategy>/run-<bench_run_id>` (R8 uses the `hybrid-router/router/...` prefix; R6/R7 use `openai/router/...` for LiteLLM compatibility).
4. The agent loop fires N requests at the proxy. Each request's `model` field carries `<strategy>/run-<id>`. The proxy parses out the run id, picks `local` or `cloud` based on `<strategy>`, forwards the request, and appends a row to `router/logs/decisions.jsonl` with `bench_run_id` echoed.
5. After the subprocess returns, the runner walks `decisions.jsonl` filtered on `bench_run_id == <id>` and rebuilds the per-call `TokenUsage` + `Routing` for the row.
6. Score the agent's edits in the scratch dir via the existing `scorers.functional_python` Docker sandbox (R8) — the same `hybrid-eval-python:latest` image R1/R2/R3 use, with `--network none`, memory caps, wall-clock timeouts.

The model-field encoding (`router/<strategy>/run-<id>`) is **the** trick that makes attribution exact across overlapping runs. v4 pilot used a timestamp-window match against `decisions.jsonl` and produced cross-run leakage when two strategy=heuristic sweeps overlapped. v1.1 fixes that.

---

## The `heuristic` strategy is now agent-aware

`router/strategies.mjs` ships one `heuristic` function (in `STRATEGIES.heuristic`). Internally it splits two ways:

- **Agent calls** (detected by `isAgentCall(messages, ctx)`): score the **latest message** ("delta") plus phase signals.
  - First call of loop (no prior assistant) → `+15` (planning bias → cloud)
  - Previous assistant had `tool_calls` → `−8` (this is a tool-result interpretation)
  - Latest message role is `tool`/`function` → `−12` (definitely interpretation)
  - Code blocks in delta · cloud-keyword hits → added to score
  - Threshold (default 12) → cloud above, local below. Override via `ROUTER_AGENT_HEURISTIC_THRESHOLD`.

- **Non-agent calls**: fall through to `legacyHeuristic` (the v1.0.0 implementation, preserved private). Byte-identical to v1.0.0 for plain chat prompts. Zero numerical drift on v3.3 numbers.

Agent detection (`isAgentCall`):

- **Primary** (structural): any message with `role: "tool"` / `role: "function"` OR any assistant message with non-empty `tool_calls[]`. Fires reliably from turn 2 of any modern agent.
- **Secondary** (first-turn-only): system prompt contains a known agent marker. Built-in list covers mini-swe-agent / Aider / opencode / Claude Code / Cursor / Cline / Warp / Roo Code / Continue. Extend at runtime with `ROUTER_AGENT_SYSTEM_MARKERS=foo,bar`.

`cascade` strategy is also agent-aware — it calls the new `heuristic` for the primary score, then tie-breaks borderline cases with `llm-classifier` as before.

---

## Adding a new agentic tool

Pattern, in 4 steps:

1. **System marker.** Add a substring unique to your tool's system prompt to `DEFAULT_AGENT_SYSTEM_MARKERS` in `router/strategies.mjs`. Or just set `ROUTER_AGENT_SYSTEM_MARKERS=YourTool` at runtime to test.
2. **Runner**, modeled after `src/hybrid_coding_eval/runners/r8_opencode.py`:
   - Generate `bench_run_id = generate_run_id()` from `runners._agent_attribution`.
   - Build the model field with `model_string(strategy, bench_run_id, prefix=...)`.
   - Subprocess your CLI with the model id + a scratch dir.
   - Call `attribute_from_decisions_log(run_id=..., strategy=..., started_at=..., finished_at=...)`.
   - Score the scratch dir via the existing Docker sandbox.
3. **Dispatch.** Add the route to `ROUTES` + `_runner_for` in `core/experiment.py` and update the `RouteStrategy` Literal + `--router-strategy` choices for the new route's strategy axis.
4. **Smoke.** Add a variant config under `configs/variants/`, run `./bench run --config X.yaml --smoke`, verify a row lands.

The v1.2 plan adds R9 for the next agentic tool we integrate (Claude Code / Cursor / Warp candidates).

---

## Reproducibility contract

For any agentic-route row:

```
(task_id, route, router_strategy, bench_run_id, hardware_profile_ref, git_sha)
```

is recoverable from the row alone. `bench_run_id` joins the row's tokens/routing back to the underlying `decisions.jsonl` slice — so even if the global decisions log is large, you can reconstruct per-call backends for one run by filtering on the id.

For non-agentic R1–R5 rows: same contract minus `bench_run_id` (those calls don't carry one). v3.3 rows are unaffected.

---

## Known model-compatibility limitations (as of v1.1.1)

The v1.1.0 code release works end-to-end. The v1.1.1 iteration sweep surfaced a real model-compatibility issue between **qwen3-coder:30b** (the v1.1 default local) and **opencode** that affects every hybrid strategy that routes a post-tool-call interpretation to local:

| Direction | Issue | Fix shipped in | Status |
| --- | --- | --- | --- |
| local → router → opencode | qwen3-coder emits `tool_calls[].function.arguments` as a JSON object; opencode requires JSON-encoded string. | v1.1.1 — `normalizeToolCallsInChunk()` in `router/server.mjs` | ✓ fixed |
| opencode → router → qwen3-coder | opencode's outgoing `assistant.tool_calls[].function.arguments` is a JSON-encoded **string** (OpenAI-standard); Ollama's qwen3-coder renderer crashes on strings with `"Value looks like object, but can't find closing '}' symbol"`. Also: opencode's multi-part `tool` content arrays (`[{type:"text",text:...}]`) confuse Ollama's struct-typed parser. | v1.1.3 — `translateForLocal()` in `router/server.mjs` (parse arguments back to object; flatten array content to string) | ✓ fixed |

**Empirical state** (v1.1.3 canonical, 60 rows on 5 Exercism Python tasks × 4 strategies × 3 seeds):

| Strategy | pass_rate | cloud / local tokens | What's happening |
|---|---|---|---|
| always-cloud (gpt-5.5) | **1.00** | 16K / 0 | Universal pass; gpt-5.5 drives opencode cleanly |
| always-local (qwen3-coder:30b) | 0.00 | 0 / 2.9K | Agent loop runs but local model writes prose, not code edits |
| **heuristic** (agent-aware) | 0.00 | 2K / 1.4K | Real hybrid: ~59% cloud / 41% local; loop completes; local turns produce prose instead of tool_calls |
| cascade | 0.00 | 0.5K / 2.8K | Heavily local-leaning; same prose-instead-of-tool-call failure |

So in v1.1.3 the hybrid **infrastructure** works correctly — `heuristic` makes the right routing decisions (first turn cloud for planning, post-tool-call local for cheap interpretation) and BOTH sides respond cleanly. The bottleneck has moved from **tool-message format** (fixed) to **local-model quality on tool-use interpretation turns**.

Concretely: when the heuristic routes a "post-tool-call interpretation" step to qwen3-coder:30b, the model often replies with friendly prose ("I see there's a file..., would you like me to...") instead of the tool_call needed to advance the agent loop. opencode's reaction is `reason: "stop"` and the agent gives up before solving the task.

v1.2 candidates for unblocking: qwen3-coder:480b (larger local), DeepSeek-R1 (better tool-use), or instructing the local model with stronger "you must use tools to make progress" priming via a router-level system-prompt augmentation.

## See also

- `docs/ROUTING_STRATEGIES.md` — full strategy taxonomy (deep dive on heuristic's score weights, env-var knobs)
- `docs/BENCHMARK_NEW_MODEL.md` — the production-pipeline use case ("a new model dropped, benchmark it")
- `docs/REPRODUCING.md` — fresh-clone reproduction recipe
- `src/hybrid_coding_eval/runners/_agent_attribution.py` — the shared `bench_run_id` helper
- `router/strategies.mjs` — the strategy implementations (heuristic + cascade + others)
- `router/tests/agent-heuristic.test.mjs` — 20 unit tests covering the agent-aware heuristic
