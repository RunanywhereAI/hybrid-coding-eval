# Using the RunAnywhere SDK as opencode's local-inference backend

> **TL;DR.** Out of the six target surfaces that ship in the RunAnywhere SDK monorepo (Swift, Kotlin, React Native, Flutter, Web/WASM, raw C++), **only the C++ `runanywhere-server` binary is a viable Ollama-replacement for opencode**. It already exposes a complete OpenAI-compatible HTTP API (`/v1/chat/completions` with SSE streaming, `/v1/models`, `/health`, native `<tool_call>{…}</tool_call>` parsing). Everything else in the SDK is tied to either a mobile app surface (Swift / Kotlin / RN / Flutter) or a browser surface (Web/WASM) and has no headless server mode. The integration shape is "spawn `runanywhere-server` as a subprocess, point opencode's router at it instead of Ollama on `localhost:11434`." The two material caveats are (a) **per-model request serialization** — one `runanywhere-server` instance with one model runs requests one at a time, no KV-cache batching — and (b) **no per-request hot-swap** — to use a tiny router model alongside the 30B coder model you must keep both resident in RAM (totals ~18.5 GB on a 64 GB box, fits fine).

This document explains all of that with file:line citations into the SDK, builds out the integration shape, and is honest about what won't work.

---

## Audience and constraints

- opencode is the TypeScript/Bun monorepo at `/Users/sanchitmonga/development/ODLM/MONOREPOOO/CODING/opencode/`. It currently uses Ollama on `localhost:11434` for local inference, fronted by the hybrid router proxy at `router/server.mjs` (port 8787) which routes between local and `gpt-5.5`.
- Hardware is M4 Max, 64 GB RAM, macOS. The local model is `qwen3-coder:30b` (~18 GB GGUF Q4) plus a small router model (`qwen3:0.6b`, ~520 MB) used by the LLM-classifier and cascade strategies.
- The router proxy speaks OpenAI HTTP. Whatever local backend we pick **must** speak `POST /v1/chat/completions` with SSE streaming and tool-call passthrough, or we wrap it.
- We want the local backend to support running for hours on a developer laptop. Cold-start cost amortises; per-request latency does not.

---

## 1. Which target?

The SDK monorepo lives at `/Users/sanchitmonga/development/ODLM/MONOREPOOO/runanywhere-sdks3/runanywhere-sdks/`. Top-level layout:

```
core/                C++ Public ABI   (ra_*.h headers, the canonical surface)
engines/             inference engines (llamacpp, onnx, sherpa, whisperkit, metalrt, genie, …)
sdk/swift/           SwiftPM package   (Package.swift)
sdk/kotlin/          Android Gradle    (build.gradle.kts)
sdk/web/             browser/WASM      (npm: @runanywhere/web)
sdk/ts/              React Native      (npm: @runanywhere/core)
sdk/dart/            Flutter           (pub: runanywhere)
solutions/openai-server/   the C++ binary we want      ← *this one*
```

### The verdict per target

| Target | Build artefact | Headless / server? | Verdict for opencode |
|---|---|---|---|
| **C++ `runanywhere-server`** | `solutions/openai-server/server_main.cpp` → standalone CLI binary | **Yes — full OpenAI-compatible server** | ✅ **Use this.** Drop-in for Ollama. |
| Swift (iOS / macOS) | XCFramework (`sdk/swift/Binaries/RACommonsCore.xcframework`) | No | ❌ Mobile/desktop GUI use case. Not a server, no clean Node integration. |
| Kotlin (Android) | AAR + JNI .so | No | ❌ Android-only. |
| React Native | npm `@runanywhere/core` | No | ❌ React Native bridge to native modules; not for headless Node. |
| Flutter | pub `runanywhere` | No | ❌ Flutter app target, not server. |
| Web / WASM | `@runanywhere/web` (browser globals: `window`, `fetch`) | No | ❌ Browser-only output, no Node server runtime. |

**Why C++ wins is also why everything else loses:** opencode is a TypeScript/Bun headless tool that already speaks HTTP to a local model. The Swift / Kotlin / RN / Flutter / Web targets all assume an app-process owner — they don't ship a server, and embedding any of them in Node requires a per-platform native bridge, an Objective-C++ shim, an Android Service, or a WASM-in-Node port that doesn't exist. The C++ openai-server is **already a server, by design, in C++, with a stable CLI**, and is what every other target ultimately bottoms out on anyway (the Swift and Kotlin SDKs delegate LLM inference to the same `engines/llamacpp/llamacpp_plugin.cpp` core via JNI / C ABI).

---

## 2. The C++ `runanywhere-server` in detail

**Source layout:**

```
solutions/openai-server/
├── server_main.cpp              ← CLI entrypoint (argv parsing, model loading, signal handling)
├── openai_server.cpp            ← HTTP routing (cpp-httplib) for /v1/chat/completions, /v1/models, /health
├── openai_handler.cpp           ← chat-completion lifecycle (decode → SSE-emit → tool_call parse)
├── server_session_registry.cpp  ← std::unordered_map<model_id, ra_llm_session_t*>
└── CMakeLists.txt               ← `add_executable(runanywhere-server server_main.cpp)`  (line 76)
```

**HTTP surface** (from `openai_server.cpp` lines 68–118):
- `GET /` — server info
- `GET /health` — `{"ok":true,"model_loaded":bool}`
- `GET /v1/models` — list of registered model IDs
- `POST /v1/chat/completions` — streaming + non-streaming
- `POST /v1/completions` — legacy completion API
- `OPTIONS *` — CORS preflight

**Streaming.** `openai_handler.cpp:330` calls httplib's `set_chunked_content_provider()`; tokens stream as `data: {"choices":[{"delta":{"content":"…"}}]}\n\n` chunks until a final `data: [DONE]\n\n` (line 362). This matches what opencode's router already passes through byte-for-byte.

**Tool calls.** `openai_handler.cpp:273` calls `ra_tool_call_parse(col.text.c_str(), &parsed)` and, when the model emits `<tool_call>{…}</tool_call>` (or LFM2's `<|tool_call_start|>…<|tool_call_end|>`), packages the result into the OpenAI `tool_calls[]` array shape (lines 285–289). The grammar / parser lives at `core/Public/ra_tool.h:73-149`. **Result: opencode gets OpenAI-shape tool calling for free**, no client-side reparsing needed.

**Auth.** Optional `--api-key <secret>` enables `Authorization: Bearer …` checking at `openai_server.cpp:44-53`. Unset by default — fine for `127.0.0.1`-only.

**CLI surface** (verified against `server_main.cpp:1-60`):

```
runanywhere-server --model <path.gguf>
                   [--model-id <id>]      # default: derived from filename
                   [--port <n>]           # default: 8080
                   [--host <addr>]        # default: 0.0.0.0   ⚠ see edge case below
                   [--api-key <secret>]
```

When `--model` is absent or the file doesn't exist, the server still starts and the generation routes return `503 no llm session registered` (per the docstring at `server_main.cpp:7-13`). Useful for HTTP-surface integration tests, useless for actually answering chat completions.

---

## 3. Build it on the M4 Max

```sh
cd /Users/sanchitmonga/development/ODLM/MONOREPOOO/runanywhere-sdks3/runanywhere-sdks

# Configure presets (verified to exist in CMakePresets.json):
#   base macos-debug macos-release macos-tsan linux-debug linux-release ios-release
#   ios-simulator-release android-release wasm-release
cmake --preset macos-release
cmake --build --preset macos-release --target runanywhere-server -j

# Binary lands at:
ls build/macos-release/solutions/openai-server/runanywhere-server
```

**About Metal.** llama.cpp's Metal backend is what gives M-series Macs their `n_gpu_layers=-1` speedup. The agent's reading of the public CMake didn't find an explicit `RA_ENABLE_METAL=ON` flag, so this is the **first thing to verify after building**: run the binary, run a short generation, watch Activity Monitor → GPU. If the GPU isn't pinned, you're on CPU-only and you'll get ~6–8 tok/s on a 30B model instead of the 15–20 tok/s you'd see with Metal. If you need Metal, the fix is in the llama.cpp submodule's CMake (`-DGGML_METAL=ON`), not in `solutions/openai-server/`.

---

## 4. Integration with opencode's router proxy (the actual swap)

Today, the router defaults to:

```sh
LOCAL_BASE=http://127.0.0.1:11434/v1     # Ollama
LOCAL_MODEL=qwen3-coder:30b
```

Migration is two env-var changes plus running the server. **No proxy code changes are needed** — opencode's router talks plain OpenAI HTTP to whatever's at `LOCAL_BASE`.

```sh
# Step 1: convert Qwen3-Coder-30B to GGUF Q4_K_M (if you don't already have it from Ollama).
#   Ollama caches models in ~/.ollama/models/ as GGUF blobs; you can either copy the
#   blob out of Ollama's manifest store, or pull a quantised .gguf from HuggingFace
#   (Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF or similar).

# Step 2: launch runanywhere-server bound to localhost only:
./build/macos-release/solutions/openai-server/runanywhere-server \
  --model ~/models/qwen3-coder-30b-a3b-q4_k_m.gguf \
  --model-id qwen3-coder-30b \
  --host 127.0.0.1 \
  --port 11500 &

# Step 3: point opencode's router at it (start.sh env vars):
LOCAL_BASE=http://127.0.0.1:11500/v1 \
LOCAL_MODEL=qwen3-coder-30b \
./router/start.sh
```

Smoke test:

```sh
curl -s http://127.0.0.1:11500/v1/models | jq
curl -s http://127.0.0.1:11500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-coder-30b","messages":[{"role":"user","content":"reply OK"}],"stream":false,"max_tokens":8}'
```

If both work, the proxy will route to the runanywhere-server exactly as it does to Ollama. The 7 routing strategies (rules, heuristic, llm-classifier, embedding-knn, cascade, etc.) are unchanged — they're agnostic to which OpenAI-compatible backend is on the other side.

**One thing to watch:** the runanywhere-server binds `0.0.0.0` by default (`server_main.cpp:36`). On a laptop on a coffee-shop wifi, that exposes inference to the network. **Always pass `--host 127.0.0.1`** unless you actually want a LAN-shared server.

---

## 5. Concurrency model — the gotcha

This is the most important section in this doc. Skim everything else; read this.

### 5a. One model, multiple parallel requests → serialised

Each `ra_llm_session_t*` owns a single `llama_context` (`engines/llamacpp/llamacpp_plugin.cpp:41-48`) and `ra_llm_generate()` is a blocking call (`core/Public/ra_primitives.h:236`). There is **no per-request KV-cache batching**. If two opencode windows fire two `chat/completions` against the same model at the same time:

```
window-1  window-2
   │         │
   ▼         ▼
   POST     POST   ──▶  cpp-httplib accepts both TCP connections
                          (max_connections respected — openai_server.cpp:137)
                          but only one runs through ra_llm_generate() at a time.
                          Window-2 sits in the httplib worker queue, taking the
                          full window-1 latency before its first token.
```

That's **fine** for single-developer use (you're typing at human speed) and **bad** for any "many concurrent agents" pattern. Concretely:

- Two opencode windows open, both casually used: latency lands roughly where you'd expect — your own typing rate is the throttle.
- One opencode session driving an agentic loop with multiple tool-calls in flight: also fine, opencode serialises model calls inside an agent turn.
- The **architect/editor** (`router/agentic/architect.mjs`) does sequential per-step model calls — also fine.
- A test sweep that fires 7 strategies × 17 prompts in parallel: would queue serially behind a single 30B session. Don't do that — fire sequentially.
- Multi-user / multi-tenant on a shared server: **not a fit.** If you need that, you want vLLM or TGI, not RunAnywhere's openai-server.

**Comparison to Ollama.** Ollama ≥ 0.3 supports `OLLAMA_NUM_PARALLEL` to share a single model across N concurrent contexts (each with its own KV slice). RunAnywhere's openai-server **does not** today. If parallel-on-one-model is a hard requirement, this is one place opencode would regress moving from Ollama to runanywhere-server.

### 5b. Multiple different models simultaneously → yes, but you build it

The HTTP surface is wired for many models (`server_session_registry.h:49` is `std::unordered_map<string, ra_llm_session_t*>`, and `openai_server.cpp` dispatches by the request's `"model"` field). But the stock `server_main.cpp` only registers **one** session — see `server_main.cpp:122-123`:

```c
ra_solution_openai_server_register_session(args.model_id.c_str(), session);
ra_solution_openai_server_set_default_model(args.model_id.c_str());
```

To run *both* `qwen3-coder-30b` and `qwen3:0.6b` (router-classifier model) inside one process, **you need to fork `server_main.cpp`** to load N models and register each:

```c
// pseudo-code
for (auto& m : args.models) {                  // --model can repeat
    ra_llm_session_t* s = nullptr;
    ra_session_config_t cfg = make_cfg(m.path);
    ra_llm_create(&s, &cfg);
    ra_solution_openai_server_register_session(m.id.c_str(), s);
}
ra_solution_openai_server_set_default_model(args.models[0].id.c_str());
```

This is ~30 lines of patch in `server_main.cpp`. It's the right long-term answer.

**Cheaper, today, no SDK fork:** run **two `runanywhere-server` processes**, one per model, on different ports.

```sh
# Big coder model, port 11500
./runanywhere-server --model qwen3-coder-30b.gguf --model-id qwen3-coder-30b --host 127.0.0.1 --port 11500 &

# Tiny router model, port 11501
./runanywhere-server --model qwen3-0.6b.gguf       --model-id qwen3-router    --host 127.0.0.1 --port 11501 &
```

Then in `router/strategies.mjs`, the `llmClassifier` strategy points at the second port instead of the same port:

```diff
- const ollamaBase = ctx.localBase.replace(/\/v1$/, "");
- const res = await fetch(`${ollamaBase}/api/chat`, { … });    // qwen3:0.6b lives next to the coder model
+ const routerBase = ctx.routerBase || "http://127.0.0.1:11501/v1";
+ const res = await fetch(`${routerBase}/chat/completions`, { … });  // separate port, separate process
```

(With the in-process multi-model fork, both models share one server and `model` field disambiguates. Cleaner, more memory-efficient — both processes don't pay separate `cpp-httplib` overhead — but you have to ship the patch.)

### 5c. Memory math for keeping both loaded

| component | RAM |
|---|---|
| `qwen3-coder-30b` GGUF Q4_K_M weights | ~17 GB |
| KV cache @ 32K context, batch 1 | ~1.5 GB |
| `qwen3-0.6b` GGUF Q4 / Q8 weights | ~0.4–0.6 GB |
| KV cache for router model @ 4K context | ~0.05 GB |
| llama.cpp + cpp-httplib runtime | ~0.5 GB |
| **Total resident** | **~19.5 GB** |

On 64 GB you're at ~30 % occupancy. Plenty of room for opencode (Bun + TUI + tool processes), Chrome, etc. For comparison, your current Ollama setup also keeps both models in cache, so this isn't a regression.

---

## 6. Other edge cases worth thinking about

### 6a. Cold start

- `ra_llm_create()` is synchronous and dominates startup. For a 30B Q4 GGUF on NVMe + mmap, expect **5–15 s** the first time, **<2 s** after the OS page cache is warm.
- During cold start, `/health` returns `model_loaded:false`. Either gate the router on `/health` (won't ship traffic until the model is up) or accept the first request will see a `503 no llm session registered` for a few seconds.
- The first generation after model load also pays a one-time cost for KV-cache allocation and `ggml_backend` init. Budget another ~1 s.

### 6b. OOM and pressure

- If `ra_llm_create()` can't allocate, it returns `RA_ERR_MODEL_LOAD_FAILED` (`engines/llamacpp/llamacpp_plugin.cpp:77`). The server stays up, returns `503` for chat; the proxy will see this as an upstream error and fall back to cloud (which is the right behaviour but worth confirming with a contrived test).
- macOS will silently overcommit and swap to SSD before refusing. Once that starts, generation drops from ~15 tok/s to ~0.1 tok/s. The router won't know. **Mitigation:** run `vm_stat 1` in a side terminal during long sessions; if `Pageouts/sec` is non-zero you're paging. Easiest safety net: don't open a Chrome with 200 tabs in parallel.

### 6c. Two opencode windows / port conflict

- `runanywhere-server` doesn't multiplex models, so if window-1 spawned its own server on `:11500` and window-2 wants its own server it must pick a different port (`:11502`, `:11504`, …) or fail to bind.
- Cleanest: make the runanywhere-server a **shared, long-running** local service — launchd / brew services / a screenrc / `nohup` — and have all opencode instances point at the same `LOCAL_BASE`.
- Per-window-spawned servers will each pay the 18 GB RAM cost. On 64 GB, two simultaneously loaded coder models eats your free memory and you'll start paging. Don't.

### 6d. Hot-swap (using a small model after every big-model call)

Not supported per request. Three options, in increasing engineering cost:

1. **Pre-load both** (recommended) — two processes or one custom-built server. ~19 GB resident. No per-request swap cost. This is what you'd want for the LLM-classifier and cascade strategies which call qwen3:0.6b on every borderline routing decision.
2. **Unload + reload** — `ra_llm_destroy()` the big model, `ra_llm_create()` the small one, generate, repeat. ~5–10 s per swap. **Not viable** for a per-request classifier.
3. **Build a session pool inside `runanywhere-server`** — load N models on startup, round-robin between them on `model` field. Same as #1 but in one process; this is the patch sketched in §5b.

### 6e. Qwen3-Coder-30B-A3B (MoE) specifically

This is the model your overnight setup actually uses. Qwen3-Coder-30B-A3B is an MoE: 30B total params, ~3B active per token. The agent's mapping confirmed `engines/llamacpp/llamacpp_plugin.cpp` runs LFM2-8B-A1B (also MoE) successfully, and llama.cpp itself supports Qwen3 MoE GGUF as of late-2024 builds. There's no special handling needed in `runanywhere-server` — the GGUF metadata carries the architecture and llama.cpp picks the right kernels. **Validate this** with a smoke test on the converted GGUF before declaring success.

### 6f. Tool calling, streaming, the small stuff

- Tool calling: ✅ already shaped as OpenAI `tool_calls[]` (`openai_handler.cpp:285-289`). opencode's AI-SDK consumer will see the same shape it does from Ollama or OpenAI itself.
- Streaming: ✅ SSE format identical to what opencode passes through. The proxy emits its `[router] …` banner chunk first and then forwards SSE byte-for-byte.
- Cancellation: client closes the SSE connection → httplib's chunked-content-provider exits → the worker calls `ra_llm_cancel(session)` (`core/Public/ra_primitives.h:244`). KV cache is preserved by design (so the user can resume the conversation).
- Embeddings, STT, TTS: the SDK has all of these (`engines/onnx/`, `engines/sherpa/`, `engines/whisperkit/`) but `runanywhere-server` only exposes chat / completions. opencode doesn't currently use them; if it ever does, an extension is straightforward (the C ABI is in place; routes are not).

### 6g. What's *not* in runanywhere-server today

Honestly listed:

- **No `/v1/embeddings` route.** The proxy's `embedding-knn` strategy uses Ollama's `/api/embeddings` for `nomic-embed-text`. If you swap entirely to runanywhere-server, you either keep Ollama running just for embeddings, or extend the openai-server to expose `/v1/embeddings` (the engine is there in `engines/onnx/`, just not wired to a route).
- **No request batching across users.** See §5a.
- **No structured-output / JSON-mode `response_format`.** Tool calls work; arbitrary JSON-schema-constrained output does not.
- **No `temperature`, `top_p`, `top_k` overrides per request.** The handler appears to use a fixed sampler config — confirm in `openai_handler.cpp` if those flags matter to you.
- **No model unload/reload via HTTP.** Restart the process to swap models.

---

## 7. Phased migration plan (Ollama → runanywhere-server)

You don't have to flip the switch. opencode's local backend is one env var.

```
PHASE 0 — TODAY  (Ollama, working):
  Ollama on :11434 → opencode router on :8787 → opencode TUI

PHASE 1 — VALIDATE:
  Build runanywhere-server. Run on :11500 alongside Ollama.
  Curl-test /health, /v1/models, /v1/chat/completions on the new server.
  Note tok/s for Qwen3-Coder-30B; compare to Ollama.

PHASE 2 — A/B in opencode:
  Add a second hybrid-router provider in ~/.config/opencode/opencode.json that
  points at :11500 (runanywhere-server) instead of :11434 (Ollama). E.g.,
  hybrid-router-ra/router/heuristic.
  Run a real-world coding session on each for an afternoon.
  Watch the decisions log: same routing decisions? same latencies? errors?

PHASE 3 — SWITCH PRIMARY:
  Once parity is acceptable, change LOCAL_BASE in router/start.sh to :11500.
  Keep Ollama installed for /v1/embeddings until runanywhere-server grows that route.
  All 7 routing strategies + the architect mode work unchanged.

PHASE 4 — DECOMMISSION OLLAMA:
  Either (a) ship the /v1/embeddings route in runanywhere-server and stop Ollama,
  or (b) accept "Ollama for embeddings, runanywhere-server for chat" as a long-
  term split (it's a small process, 200 MB resident).

PHASE 5 — IN-PROCESS MULTI-MODEL:
  Patch server_main.cpp to accept multiple --model flags and register each as
  a session. Now one runanywhere-server hosts both qwen3-coder-30b and qwen3:0.6b
  on different `model` IDs — cleaner than two processes and saves a few hundred MB.
```

Each phase is ~1 evening of work. Phases 1–3 are the path of value; 4–5 are polish.

---

## 8. Comparison: Ollama vs runanywhere-server (today)

| capability | Ollama 0.x | runanywhere-server | implication for opencode |
|---|---|---|---|
| OpenAI-compatible `/v1/chat/completions` | ✅ | ✅ | drop-in |
| SSE streaming | ✅ | ✅ | proxy passes through unchanged |
| Tool calls (OpenAI shape) | ✅ (recent versions) | ✅ (`<tool_call>`) | both shapes work |
| Multi-model in one process | ✅ (`/api/pull`, hot-swap) | ❌ stock binary; ✅ with patch | matters for LLM-classifier strategy |
| Concurrent inference on one model | ✅ (`OLLAMA_NUM_PARALLEL`) | ❌ serialised | dev-laptop fine; multi-user not |
| `/v1/embeddings` | ✅ | ❌ today | embedding-kNN strategy needs Ollama or a route extension |
| Metal acceleration on M-series | ✅ default | ⚠ verify llama.cpp build flag | re-bench after first build |
| Model fetching / management | ✅ (`ollama pull`) | ❌ supply your own GGUF | manual today; could ship a pull script |
| Cold-start latency for 30B | ~5–15 s (mmap warm) | similar (same llama.cpp) | parity |
| Memory for 30B + 0.6B both loaded | ~19 GB | ~19 GB (same) | parity |
| Maturity | very high, used everywhere | newer, fewer eyes on the server target | watch for bugs at first |

**Bottom line:** at the chat-completion level, runanywhere-server is at parity with Ollama for opencode's needs *except* embeddings, parallel-on-one-model, and built-in model management. The first is one route to add; the second is unimportant for solo dev use; the third is a `wget` script away.

---

## 9. Open questions to resolve before going all-in

These are the things the agent's read-only mapping couldn't fully verify. Each is a 30-min experiment, not a project.

1. **Metal layers actually engaging on M4 Max.** Build the binary, run a 30-token generation, check `powermetrics --samplers gpu_power -i 1000 -n 1` and Activity Monitor's GPU column. If GPU is idle and we're CPU-only, file a flag in the llama.cpp submodule's CMake.
2. **Sampler controls.** Do `temperature` / `top_p` / `seed` actually flow from the HTTP body into `ra_llm_generate()`? If they're dropped silently, the routing strategies that rely on `temperature: 0` (the LLM-classifier in particular) won't be deterministic.
3. **Tool-call accuracy on Qwen3-Coder-30B.** ASSESSMENT.md only confirmed the parser works; confirm the model emits `<tool_call>{…}</tool_call>` reliably for the opencode tool definitions (Read, Edit, Bash, Grep, etc.). If not, opencode's AI SDK will need to do its own parsing pass anyway and the gain over Ollama is smaller.
4. **Streaming under contention.** Two opencode windows, two simultaneous SSE streams to the same model. Does the second stream see partial garbage from the first, or does httplib correctly serialise the chunked-content-provider per connection? (Should be the latter; verify.)
5. **MoE behaviour for Qwen3-Coder-30B-A3B specifically.** Convert the GGUF (or pull a community one), load it, run a 256-token completion, compare quality to Ollama's same model on the same prompt. If quality differs, the GGUF metadata or a llama.cpp version skew is biting.
6. **Cancellation propagation when opencode aborts an SSE stream mid-token.** Easy to test: `Ctrl+C` mid-response in opencode and confirm the server logs show `ra_llm_cancel` was called.

If 1, 2, 5 all pass, the migration is real. 3 and 4 are nice-to-haves; 6 is a polish bug at worst.

---

## 10. What this enables (the "why")

Three things the SDK gives you that Ollama doesn't:

1. **You own the binary.** Ollama is great until you want to add `/v1/embeddings` of your own embedding model, or expose the LFM2 tool-call format alongside the default, or change the SSE chunk shape, or add request-level metrics. With Ollama you wait. With your SDK you patch `openai_handler.cpp` and rebuild.
2. **Per-platform reuse.** The same C++ core that runs in `runanywhere-server` runs in your Swift, Kotlin, RN, Flutter, Web targets. If opencode ever ships a mobile companion, the local-inference layer is the same code. That's a strategic advantage no Ollama swap can give you.
3. **Custom engines.** The SDK's plugin model (`engines/<name>/<name>_plugin.cpp` lands at one C ABI) means you can ship a Qualcomm-NPU build for one platform, an MLX-native build for another, and a generic llama.cpp build for the rest, and `runanywhere-server` doesn't care — it just calls the same `ra_llm_*` API. opencode's router doesn't need to know either.

The C++ openai-server is the integration point that gives opencode access to all of that without any opencode rewrites.

---

## Appendix — file references

All paths are under `/Users/sanchitmonga/development/ODLM/MONOREPOOO/runanywhere-sdks3/runanywhere-sdks/`.

| topic | file:line |
|---|---|
| CLI args, defaults, model loading | `solutions/openai-server/server_main.cpp:1-162` |
| HTTP routes | `solutions/openai-server/openai_server.cpp:68-118` |
| Auth bearer-token check | `solutions/openai-server/openai_server.cpp:44-53` |
| Chat-completion lifecycle, SSE write | `solutions/openai-server/openai_handler.cpp:199-368` |
| Tool-call parse, OpenAI shape | `solutions/openai-server/openai_handler.cpp:267-289` |
| Tool-call parser/grammar | `core/Public/ra_tool.h:73-149` |
| Multi-session registry | `solutions/openai-server/server_session_registry.h:26-49` |
| llama.cpp engine, single-context | `engines/llamacpp/llamacpp_plugin.cpp:41-48` |
| `ra_llm_generate` blocking call | `core/Public/ra_primitives.h:236` |
| `ra_llm_cancel` semantics | `core/Public/ra_primitives.h:244` |
| Build target binary | `solutions/openai-server/CMakeLists.txt:76` |
| Available cmake presets | `CMakePresets.json` (`macos-debug`, `macos-release`, `linux-*`, `ios-*`, `android-release`, `wasm-release`) |
