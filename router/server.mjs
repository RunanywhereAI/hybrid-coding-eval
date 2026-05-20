#!/usr/bin/env node
// Hybrid local/cloud LLM router — OpenAI-compatible proxy.
//
// Listens on PORT (default 8787) and exposes:
//   POST /v1/chat/completions   — routed to local (Ollama) or cloud (OpenAI)
//   GET  /v1/models             — lists one model per routing strategy
//   GET  /healthz               — liveness + backend status
//
// The strategy is chosen by the `model` field of the request:
//   model: "router/<strategy>"   →   look up STRATEGIES[strategy], call its decide()
//   model: "router/<strategy>!local" or "!cloud"   →   force a backend (debug)
//
// Decisions are logged to logs/decisions.jsonl and (optionally) prefixed as a
// banner into the first content delta of the streamed response.

import http from "node:http";
import { mkdirSync, appendFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { STRATEGIES, lastUserText, totalPromptTokens } from "./strategies.mjs";
import { runArchitect, answerFromRun, userTaskFromMessages } from "./pipelines/architect/core.mjs";
import { costFor, fmtUSD } from "./pricing.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ----- env -----------------------------------------------------------------
const PORT = Number(process.env.PORT || 8787);

const LOCAL_BASE = process.env.LOCAL_BASE || "http://127.0.0.1:11434/v1";
const LOCAL_MODEL = process.env.LOCAL_MODEL || "qwen3-coder:30b";
const ROUTER_MODEL = process.env.ROUTER_MODEL || "qwen3:0.6b";
const CASCADE_THRESHOLD = parseInt(process.env.ROUTER_CASCADE_THRESHOLD || "15", 10);
const AGENT_HEURISTIC_THRESHOLD = parseInt(
  process.env.ROUTER_AGENT_HEURISTIC_THRESHOLD || "12",
  10,
);
// Optional comma-separated list of extra system-prompt markers that
// identify an agent call (in addition to the built-in mini-swe-agent /
// aider / opencode patterns). Per-tool integration may extend this at
// runtime — see docs/AGENTIC_ROUTES.md.
const EXTRA_AGENT_MARKERS = (process.env.ROUTER_AGENT_SYSTEM_MARKERS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// v1.2: nudge for local models in agent tool-use loops. qwen3-coder:30b
// (and similar mid-size locals) tend to reply with prose on tool-result
// interpretation turns instead of emitting the follow-up tool_call the
// agent loop needs. This nudge is appended to the system prompt AND a
// per-turn reminder is appended after tool messages before forwarding
// to the local backend WHEN the request includes a `tools` array.
//
// Override with ROUTER_LOCAL_TOOL_USE_NUDGE=<system-suffix> or
// ROUTER_LOCAL_POST_TOOL_REMINDER=<user-reminder>. Either can be set to
// "disable" to skip that part of the injection.
const DEFAULT_LOCAL_TOOL_USE_NUDGE = `\n\nIMPORTANT — Tool-Use Policy:\n` +
  `When you need to make progress on the task, you MUST use a tool. Do not respond with prose ` +
  `explanations, summaries, or questions about what to do next — call the appropriate tool ` +
  `(read, write, edit, bash, glob, grep, etc.) to advance the task. Only emit plain content ` +
  `when reporting a final result that requires no further action.`;
const DEFAULT_LOCAL_POST_TOOL_REMINDER =
  `Continue. The previous tool result is above. Your next response MUST be a tool_call ` +
  `(read / write / edit / bash / glob / grep / etc.) to advance the task. Do not summarize ` +
  `or ask what to do — call the next tool.`;
const _rawNudge = process.env.ROUTER_LOCAL_TOOL_USE_NUDGE;
const LOCAL_TOOL_USE_NUDGE =
  _rawNudge === "disable" ? "" : (_rawNudge && _rawNudge.length > 0 ? _rawNudge : DEFAULT_LOCAL_TOOL_USE_NUDGE);
const _rawReminder = process.env.ROUTER_LOCAL_POST_TOOL_REMINDER;
const LOCAL_POST_TOOL_REMINDER =
  _rawReminder === "disable" ? "" : (_rawReminder && _rawReminder.length > 0 ? _rawReminder : DEFAULT_LOCAL_POST_TOOL_REMINDER);

const CLOUD_BASE = process.env.CLOUD_BASE || "https://api.openai.com/v1";
const CLOUD_MODEL = process.env.CLOUD_MODEL || "gpt-5.5";
const CLOUD_FALLBACK_MODEL = process.env.CLOUD_FALLBACK_MODEL || "gpt-5";
const CLOUD_API_KEY =
  process.env.CLOUD_API_KEY || process.env.OPENAI_API_KEY || process.env.OPEN_AI_API_KEY;

const BANNER_ENABLED = process.env.ROUTER_BANNER !== "0";
const LOG_DIR = process.env.ROUTER_LOG_DIR || join(__dirname, "logs");
const LOG_FILE = join(LOG_DIR, "decisions.jsonl");

mkdirSync(LOG_DIR, { recursive: true });

if (!CLOUD_API_KEY)
  console.warn("[router] WARNING: no CLOUD_API_KEY / OPENAI_API_KEY / OPEN_AI_API_KEY set; cloud calls will fail.");

// ----- shared context ------------------------------------------------------
const ctx = {
  localBase: LOCAL_BASE,
  localModel: LOCAL_MODEL,
  routerModel: ROUTER_MODEL,
  cascadeThreshold: CASCADE_THRESHOLD,
  agentHeuristicThreshold: AGENT_HEURISTIC_THRESHOLD,
  extraAgentMarkers: EXTRA_AGENT_MARKERS,
  localToolUseNudge: LOCAL_TOOL_USE_NUDGE,
  localPostToolReminder: LOCAL_POST_TOOL_REMINDER,
  cloudBase: CLOUD_BASE,
  cloudModel: CLOUD_MODEL,
  cloudKey: CLOUD_API_KEY,
  corpus: {
    // T-05 moved router/corpus/examples.json → configs/router/corpus.json.
    path: join(__dirname, "..", "configs", "router", "corpus.json"),
    examples: [],
    _loaded: false,
  },
  log: (level, msg, extra) => {
    const ts = new Date().toISOString();
    console.log(`[${ts}] [${level}] ${msg}`, extra || "");
  },
};

// ----- utility -------------------------------------------------------------
function reqId() {
  return Math.random().toString(36).slice(2, 10);
}

async function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function appendDecision(record) {
  try {
    appendFileSync(LOG_FILE, JSON.stringify(record) + "\n");
  } catch (err) {
    console.error("[router] failed to write decision log:", err.message);
  }
}

// ----- local backend adapter: OpenAI-shape ↔ Ollama native --------------
//
// Ollama exposes its OWN /v1/chat/completions but it's a thin wrapper that
// silently ignores model-specific options like `think: false` (Qwen3 family
// thinking-mode toggle). When we route a Qwen3.x reasoning model locally,
// the OpenAI-compat path burns the entire output budget on hidden reasoning
// and returns empty content. To fix this for everything Ollama serves we
// route to Ollama's native /api/chat, set think:false, and translate both
// directions back to OpenAI shape so the rest of the proxy is unchanged.
//
// localBase is `http://127.0.0.1:11434/v1` (we strip the trailing `/v1`).
async function fetchLocalOllamaAsOpenAI(localBase, openaiBody) {
  const ollamaBase = localBase.replace(/\/v1$/, "");
  const ollamaBody = {
    model: openaiBody.model,
    messages: openaiBody.messages,
    stream: !!openaiBody.stream,
    think: false,
    options: {
      temperature: openaiBody.temperature ?? undefined,
      top_p: openaiBody.top_p ?? undefined,
      num_predict: openaiBody.max_tokens ?? openaiBody.max_completion_tokens ?? undefined,
    },
  };
  if (openaiBody.tools) ollamaBody.tools = openaiBody.tools;
  if (openaiBody.tool_choice) ollamaBody.tool_choice = openaiBody.tool_choice;

  const res = await fetch(`${ollamaBase}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ollamaBody),
  });

  if (!res.ok) return res; // pass error through unchanged

  if (!openaiBody.stream) {
    const oj = await res.json();
    const fakeBody = JSON.stringify(ollamaToOpenAI(oj));
    return new Response(fakeBody, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Streaming: NDJSON → SSE.
  const transformed = res.body.pipeThrough(ollamaNdjsonToOpenAISSE());
  return new Response(transformed, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function ollamaToOpenAI(oj) {
  return {
    id: `chatcmpl-ollama-${Date.now().toString(36)}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: oj.model,
    choices: [
      {
        index: 0,
        message: {
          role: oj.message?.role || "assistant",
          content: oj.message?.content || "",
          ...(oj.message?.tool_calls ? { tool_calls: oj.message.tool_calls } : {}),
        },
        finish_reason: oj.done_reason === "length" ? "length" : "stop",
      },
    ],
    usage: {
      prompt_tokens: oj.prompt_eval_count || 0,
      completion_tokens: oj.eval_count || 0,
      total_tokens: (oj.prompt_eval_count || 0) + (oj.eval_count || 0),
    },
  };
}

function ollamaNdjsonToOpenAISSE() {
  let textBuf = "";
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const sseHead = `chatcmpl-ollama-${Date.now().toString(36)}`;
  return new TransformStream({
    transform(chunk, controller) {
      textBuf += decoder.decode(chunk, { stream: true });
      let nl;
      while ((nl = textBuf.indexOf("\n")) >= 0) {
        const line = textBuf.slice(0, nl).trim();
        textBuf = textBuf.slice(nl + 1);
        if (!line) continue;
        let obj;
        try { obj = JSON.parse(line); } catch { continue; }
        const sse = {
          id: sseHead,
          object: "chat.completion.chunk",
          created: Math.floor(Date.now() / 1000),
          model: obj.model,
          choices: [
            {
              index: 0,
              delta: {
                ...(obj.message?.role && { role: obj.message.role }),
                content: obj.message?.content ?? "",
                ...(obj.message?.tool_calls ? { tool_calls: obj.message.tool_calls } : {}),
              },
              finish_reason: obj.done ? (obj.done_reason === "length" ? "length" : "stop") : null,
            },
          ],
        };
        if (obj.done) {
          sse.usage = {
            prompt_tokens: obj.prompt_eval_count || 0,
            completion_tokens: obj.eval_count || 0,
            total_tokens: (obj.prompt_eval_count || 0) + (obj.eval_count || 0),
          };
        }
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(sse)}\n\n`));
        if (obj.done) controller.enqueue(encoder.encode(`data: [DONE]\n\n`));
      }
    },
    flush(controller) {
      // any remaining buffer is dropped (incomplete line)
    },
  });
}

// Reasoning-API quirks: newer OpenAI models (gpt-5*, o1*, o3*, o4*) reject
// `max_tokens` in favor of `max_completion_tokens`, and reject custom
// `temperature` / `top_p`. Translate so callers can stay OpenAI-classic.
function isReasoningModel(model) {
  return /^(gpt-5|o1|o3|o4)/i.test(model || "");
}
function translateForCloud(body) {
  const out = { ...body };
  const model = out.model || "";
  if (isReasoningModel(model)) {
    if ("max_tokens" in out && !("max_completion_tokens" in out)) {
      out.max_completion_tokens = out.max_completion_tokens || out.max_tokens;
    }
    delete out.max_tokens;
    // Reasoning models only accept default temperature (1) — drop overrides.
    if ("temperature" in out && out.temperature !== 1) delete out.temperature;
    if ("top_p" in out && out.top_p !== 1) delete out.top_p;
  }
  return out;
}

/**
 * Translate the OpenAI-shape request body into something Ollama's
 * qwen3-coder template accepts.
 *
 * The OpenAI spec requires ``tool_calls[].function.arguments`` to be a
 * JSON-encoded STRING (per
 * https://platform.openai.com/docs/api-reference/chat/object). Strict
 * clients like opencode obey this. But Ollama's qwen3-coder renderer
 * (RENDERER qwen3-coder + PARSER qwen3-coder, baked into Ollama 0.24.x)
 * crashes on stringified arguments with::
 *
 *     "Value looks like object, but can't find closing '}' symbol"
 *
 * It expects ``arguments`` as a JSON OBJECT in incoming messages.
 * Bisected via the test in router/tests/ollama-tool-message.test.mjs.
 *
 * Symmetric inverse of normalizeToolCallsInChunk(): the response
 * normalizer stringifies for outgoing replies; this de-stringifies for
 * incoming requests.
 *
 * Returns a NEW body — does not mutate the caller's copy.
 */
function translateForLocal(body) {
  if (!body || !Array.isArray(body.messages)) return body;
  const out = { ...body, messages: [] };
  // (3) Tool-use nudge: if this is an agent call (request has tools[])
  // append the nudge to the FIRST system message (or prepend a new
  // system message if none exists). Helps qwen3-coder + similar locals
  // emit tool_calls instead of prose on interpretation turns.
  let nudge = ctx.localToolUseNudge;
  const isAgentCall = Array.isArray(body.tools) && body.tools.length > 0;
  if (!isAgentCall) nudge = "";
  let nudgeApplied = false;
  for (const raw of body.messages) {
    if (!raw) {
      out.messages.push(raw);
      continue;
    }
    let m = raw;
    // (1) Tool / function / assistant messages with array content: Ollama's
    // qwen3-coder template requires string content. OpenAI 1.x allows
    // content: [{type:"text", text:"..."}, ...] for multipart messages.
    // Flatten to plain string.
    if (Array.isArray(m.content)) {
      const flat = m.content
        .map((p) => (typeof p === "string" ? p : (p && typeof p === "object" && typeof p.text === "string" ? p.text : "")))
        .filter(Boolean)
        .join("\n");
      m = { ...m, content: flat };
    }
    // (3a) Append the tool-use nudge to the first system message we see.
    if (nudge && !nudgeApplied && m.role === "system" && typeof m.content === "string") {
      m = { ...m, content: m.content + nudge };
      nudgeApplied = true;
    }
    // (2) assistant.tool_calls[].function.arguments: OpenAI spec requires
    // JSON-encoded STRING; Ollama qwen3-coder rejects strings with "Value
    // looks like object, but can't find closing '}' symbol". Parse back to
    // OBJECT for the qwen3-coder renderer.
    if (Array.isArray(m.tool_calls) && m.tool_calls.length > 0) {
      const newToolCalls = m.tool_calls.map((tc) => {
        if (!tc?.function || tc.function.arguments == null) return tc;
        if (typeof tc.function.arguments !== "string") return tc;
        let parsed;
        try {
          parsed = JSON.parse(tc.function.arguments);
        } catch {
          return tc;
        }
        return { ...tc, function: { ...tc.function, arguments: parsed } };
      });
      m = { ...m, tool_calls: newToolCalls };
    }
    out.messages.push(m);
  }
  // (3b) No system message in the conversation → prepend one with the nudge.
  if (nudge && !nudgeApplied) {
    out.messages.unshift({ role: "system", content: nudge.trimStart() });
  }
  // (4) Post-tool reminder — if the LAST message is a tool result and the
  // call is agentic, append a user message that explicitly demands the
  // next tool_call. This is the strongest-position prompt-engineering
  // intervention; system messages are far away from the generation point
  // for long agent contexts, but a user message at the tail is right
  // before generation. Helps weaker locals (qwen3-coder:30b) emit
  // tool_calls instead of prose summaries.
  const reminder = isAgentCall ? ctx.localPostToolReminder : "";
  if (reminder && out.messages.length > 0) {
    const last = out.messages[out.messages.length - 1];
    if (last && (last.role === "tool" || last.role === "function")) {
      out.messages.push({ role: "user", content: reminder });
    }
  }
  return out;
}

function bannerString(d, ctx, backendModel) {
  return (
    `[router] strategy=${d.strategy} → ${d.choice.toUpperCase()} ` +
    `(${backendModel}) | conf=${d.confidence?.toFixed(2) ?? "?"} | ${d.reason}\n\n`
  );
}

// ----- /v1/chat/completions ------------------------------------------------
async function handleChatCompletion(req, res) {
  const id = reqId();
  const t0 = Date.now();
  let body;
  try {
    const raw = await readBody(req);
    body = JSON.parse(raw);
  } catch (err) {
    return sendJson(res, 400, { error: { message: "invalid JSON body", type: "invalid_request_error" } });
  }

  const requestedModel = String(body.model || "");

  // Special pseudo-strategy: router/architect runs the multi-step
  // plan→execute→synthesise pipeline (Pattern A from ROUTING_STRATEGIES.md).
  if (requestedModel === "router/architect" || requestedModel === "router/architect-mode") {
    return handleArchitect(req, res, body, id, t0);
  }

  const force = requestedModel.includes("!local")
    ? "local"
    : requestedModel.includes("!cloud")
    ? "cloud"
    : null;
  const stripped = requestedModel.replace(/!local|!cloud/g, "");
  // Parse "router/<strategy>" or "router/<strategy>/run-<bench_run_id>".
  // v1.1+: agentic runners (R6/R7/R8) embed a 12-hex correlation id in the
  // model field so attribution can join back into decisions.jsonl without
  // timestamp races. Legacy callers (no suffix) keep working unchanged.
  const afterPrefix = stripped.startsWith("router/") ? stripped.slice("router/".length) : stripped;
  const runIdMatch = afterPrefix.match(/^(.+?)\/run-([a-zA-Z0-9_-]+)$/);
  const strategyName = runIdMatch ? runIdMatch[1] : afterPrefix;
  const benchRunId = runIdMatch ? runIdMatch[2] : null;

  let strategy = STRATEGIES[strategyName];
  if (!strategy) {
    strategy = STRATEGIES["heuristic"]; // sensible default
    ctx.log("warn", `[${id}] unknown strategy "${strategyName}" → falling back to heuristic`);
  }

  // Make routing decision.
  const tDecideStart = Date.now();
  let decision;
  try {
    decision = await strategy.fn(body, ctx);
  } catch (err) {
    decision = {
      choice: "local",
      reason: `strategy[${strategyName}] threw: ${err.message} → fallback local`,
      confidence: 0.2,
    };
  }
  const decideMs = Date.now() - tDecideStart;
  if (force) {
    decision.reason = `[FORCED ${force}] ${decision.reason}`;
    decision.choice = force;
  }

  const promptText = lastUserText(body.messages);
  const promptTokens = totalPromptTokens(body.messages);

  // Pick backend.
  const backend =
    decision.choice === "cloud"
      ? { base: ctx.cloudBase, model: ctx.cloudModel, key: ctx.cloudKey, label: "cloud" }
      : { base: ctx.localBase, model: ctx.localModel, key: null, label: "local" };

  // Build upstream request body — replace model name, keep everything else.
  let upstreamBody = { ...body, model: backend.model };
  if (backend.label === "cloud") upstreamBody = translateForCloud(upstreamBody);
  else if (backend.label === "local") upstreamBody = translateForLocal(upstreamBody);

  // Always ask for `usage` back, even when streaming. Some backends (OpenAI)
  // require an explicit opt-in via `stream_options.include_usage`, otherwise
  // streamed responses omit the usage block entirely and we can't price the
  // call. Harmless for backends that don't honour the option.
  if (upstreamBody.stream === true) {
    upstreamBody.stream_options = { ...(upstreamBody.stream_options || {}), include_usage: true };
  }

  ctx.log(
    "info",
    `[${id}] strategy=${strategyName} → ${decision.choice} (${backend.model}) decideMs=${decideMs} promptTok=${promptTokens} | ${decision.reason}`,
  );

  // Forward the request.
  const upstreamHeaders = { "Content-Type": "application/json" };
  if (backend.key) upstreamHeaders["Authorization"] = `Bearer ${backend.key}`;

  let upstream;
  try {
    upstream =
      backend.label === "local"
        ? await fetchLocalOllamaAsOpenAI(backend.base, upstreamBody)
        : await fetch(`${backend.base}/chat/completions`, {
            method: "POST",
            headers: upstreamHeaders,
            body: JSON.stringify(upstreamBody),
          });
  } catch (err) {
    return sendJson(res, 502, {
      error: {
        message: `upstream ${backend.label} fetch failed: ${err.message}`,
        type: "upstream_error",
      },
    });
  }

  // Cloud-model fallback: if e.g. gpt-5 returns 404/400, retry with fallback model.
  if (
    !upstream.ok &&
    backend.label === "cloud" &&
    backend.model !== CLOUD_FALLBACK_MODEL &&
    (upstream.status === 404 || upstream.status === 400)
  ) {
    const errText = await upstream.text().catch(() => "");
    ctx.log(
      "warn",
      `[${id}] cloud model "${backend.model}" returned ${upstream.status}: ${errText.slice(0, 200)} — retrying with "${CLOUD_FALLBACK_MODEL}"`,
    );
    upstreamBody.model = CLOUD_FALLBACK_MODEL;
    backend.model = CLOUD_FALLBACK_MODEL;
    decision.reason += ` | fallback-model=${CLOUD_FALLBACK_MODEL}`;
    upstream = await fetch(`${backend.base}/chat/completions`, {
      method: "POST",
      headers: upstreamHeaders,
      body: JSON.stringify(upstreamBody),
    });
  }

  if (!upstream.ok) {
    const errText = await upstream.text().catch(() => "");
    appendDecision({
      ts: new Date().toISOString(),
      id,
      strategy: strategyName,
      bench_run_id: benchRunId,
      choice: decision.choice,
      reason: decision.reason,
      backend_model: backend.model,
      backend_status: upstream.status,
      backend_error: errText.slice(0, 500),
      decide_ms: decideMs,
      prompt_tokens_est: promptTokens,
      stream: !!body.stream,
      success: false,
    });
    return sendJson(res, upstream.status, {
      error: {
        message: `upstream ${backend.label} returned ${upstream.status}: ${errText.slice(0, 500)}`,
        type: "upstream_error",
      },
    });
  }

  const decisionRecord = {
    ts: new Date().toISOString(),
    id,
    strategy: strategyName,
    bench_run_id: benchRunId,
    choice: decision.choice,
    forced: force || null,
    reason: decision.reason,
    confidence: decision.confidence ?? null,
    backend_model: backend.model,
    decide_ms: decideMs,
    prompt_tokens_est: promptTokens,
    prompt_preview: promptText.slice(0, 200),
    stream: !!body.stream,
    success: true,
  };

  if (body.stream) {
    await streamThrough(res, upstream, decisionRecord, decision, strategyName, backend.model, t0);
  } else {
    await jsonThrough(res, upstream, decisionRecord, decision, strategyName, backend.model, t0);
  }
}

async function jsonThrough(res, upstream, record, decision, strategyName, backendModel, t0) {
  const text = await upstream.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    res.writeHead(upstream.status, { "Content-Type": upstream.headers.get("content-type") || "application/json" });
    res.end(text);
    record.total_ms = Date.now() - t0;
    appendDecision(record);
    return;
  }
  // Cost calc — uses the actual model id the backend echoed back (handles
  // OpenAI's dated variants like "gpt-5.5-2026-04-23"), falling back to the
  // backend model we asked for, falling back to the local-pricing key if the
  // call went local.
  const usage = parsed?.usage || null;
  const echoedModel = parsed?.model || backendModel;
  const costKey = decision.choice === "local" ? "__local__" : echoedModel;
  const cost = costFor(costKey, usage);
  // v1.2: normalize tool_calls schema in non-streaming response too
  // (streaming had it via streamThrough; this closes the gap for opencode
  // sessions that use stream:false for some calls).
  normalizeToolCallsInChunk(parsed);
  if (BANNER_ENABLED && parsed?.choices?.[0]?.message?.content !== undefined) {
    parsed.choices[0].message.content =
      bannerString({ ...decision, strategy: strategyName }, ctx, backendModel) +
      (parsed.choices[0].message.content || "");
  }
  const headers = {
    "Content-Type": "application/json",
    "X-Router-Strategy": strategyName,
    "X-Router-Choice": decision.choice,
    "X-Router-Backend": backendModel,
    "X-Router-Backend-Model-Echo": echoedModel,
    "X-Cost-USD": cost.usd.toFixed(6),
    "X-Tokens-Prompt": String(cost.tokens.promptTokens),
    "X-Tokens-Completion": String(cost.tokens.completionTokens),
    "X-Tokens-Cached": String(cost.tokens.cachedTokens),
    "X-Tokens-Reasoning": String(cost.tokens.reasoningTokens),
    "X-Cost-Pricing-Key": cost.key || "(unknown)",
  };
  res.writeHead(200, headers);
  res.end(JSON.stringify(parsed));
  record.total_ms = Date.now() - t0;
  record.echoed_model = echoedModel;
  record.usage = usage;
  record.cost_usd = cost.usd;
  record.cost_breakdown = cost.breakdown;
  record.cost_key = cost.key;
  record.cost_missing = cost.missing;
  appendDecision(record);
}

/**
 * Rewrite a streamed OpenAI-shape chat-completion chunk so tool_calls are
 * OpenAI-compliant. Ollama-served models (qwen3-coder etc.) sometimes
 * emit:
 *   - ``function.arguments`` as a JSON OBJECT instead of a JSON-encoded
 *     STRING (the OpenAI spec requires string).
 *   - ``function.index`` instead of the sibling ``tool_calls[i].index``.
 * Strict clients (opencode 1.1.x) reject both with TypeValidationError.
 * Mutates ``obj`` in place; returns nothing.
 */
function normalizeToolCallsInChunk(obj) {
  if (!obj || !Array.isArray(obj.choices)) return;
  for (const choice of obj.choices) {
    const tc = choice?.delta?.tool_calls || choice?.message?.tool_calls;
    if (!Array.isArray(tc)) continue;
    for (let i = 0; i < tc.length; i++) {
      const t = tc[i];
      if (!t) continue;
      if (t.function && typeof t.function.index === "number" && t.index === undefined) {
        t.index = t.function.index;
        delete t.function.index;
      }
      if (t.index === undefined) t.index = i;
      if (t.function && t.function.arguments != null && typeof t.function.arguments !== "string") {
        try {
          t.function.arguments = JSON.stringify(t.function.arguments);
        } catch {
          t.function.arguments = String(t.function.arguments);
        }
      }
      if (t.function && !t.type) t.type = "function";
    }
  }
}


async function streamThrough(res, upstream, record, decision, strategyName, backendModel, t0) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Router-Strategy": strategyName,
    "X-Router-Choice": decision.choice,
    "X-Router-Backend": backendModel,
  });

  // Emit a synthetic banner chunk first.
  if (BANNER_ENABLED) {
    const fakeChunk = {
      id: "router-banner",
      object: "chat.completion.chunk",
      created: Math.floor(Date.now() / 1000),
      model: backendModel,
      choices: [{ index: 0, delta: { content: bannerString({ ...decision, strategy: strategyName }, ctx, backendModel) } }],
    };
    res.write(`data: ${JSON.stringify(fakeChunk)}\n\n`);
  }

  // Pipe upstream SSE through.
  if (!upstream.body) {
    res.end();
    appendDecision({ ...record, total_ms: Date.now() - t0, error: "no upstream body" });
    return;
  }

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let totalChunks = 0;
  let totalBytes = 0;
  let usage = null;
  let echoedModel = null;
  let buf = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalChunks++;
      totalBytes += value.length;
      // Parse, normalize tool_calls schema (v1.1: qwen3-coder + other Ollama
      // models emit non-OpenAI-compliant tool_calls — arguments as JSON
      // objects instead of JSON-encoded strings; function.index instead of
      // tool_call.index). Re-serialize before forwarding so opencode + other
      // strict clients accept the response.
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const event = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let rewritten = event;
        const lines = event.split("\n");
        const out = [];
        for (const line of lines) {
          if (!line.startsWith("data: ")) {
            out.push(line);
            continue;
          }
          const json = line.slice(6).trim();
          if (!json || json === "[DONE]") {
            out.push(line);
            continue;
          }
          try {
            const obj = JSON.parse(json);
            if (obj?.model) echoedModel = obj.model;
            if (obj?.usage) usage = obj.usage;
            normalizeToolCallsInChunk(obj);
            out.push(`data: ${JSON.stringify(obj)}`);
          } catch {
            out.push(line);
          }
        }
        rewritten = out.join("\n") + "\n\n";
        res.write(rewritten);
      }
    }
    // Any tail buffered after the loop (no trailing \n\n) — forward as-is.
    if (buf.length > 0) {
      res.write(buf);
      buf = "";
    }
  } catch (err) {
    ctx.log("warn", `streaming aborted: ${err.message}`);
  }
  res.end();

  const costKey = record.choice === "local" ? "__local__" : (echoedModel || record.backend_model);
  const cost = costFor(costKey, usage);

  record.total_ms = Date.now() - t0;
  record.stream_chunks = totalChunks;
  record.stream_bytes = totalBytes;
  record.echoed_model = echoedModel;
  record.usage = usage;
  record.cost_usd = cost.usd;
  record.cost_breakdown = cost.breakdown;
  record.cost_key = cost.key;
  record.cost_missing = cost.missing;
  appendDecision(record);
}

// ----- router/architect handler --------------------------------------------
async function handleArchitect(_req, res, body, id, t0) {
  const task = userTaskFromMessages(body.messages);
  if (!task) {
    return sendJson(res, 400, {
      error: { message: "router/architect requires a user message", type: "invalid_request_error" },
    });
  }
  ctx.log("info", `[${id}] router/architect → starting pipeline (task: ${task.slice(0, 80)})`);
  const proxyBase = `http://127.0.0.1:${PORT}`;

  // SSE events to opencode so the user sees progress live.
  const stream = !!body.stream;
  if (stream) {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Router-Strategy": "architect",
      "X-Router-Choice": "architect",
      "X-Router-Backend": "(plan/execute/synth)",
    });
    const emit = (text) => {
      const chunk = {
        id: "router-architect",
        object: "chat.completion.chunk",
        created: Math.floor(Date.now() / 1000),
        model: "router/architect",
        choices: [{ index: 0, delta: { content: text } }],
      };
      res.write(`data: ${JSON.stringify(chunk)}\n\n`);
    };

    emit(`[architect] task: ${task.slice(0, 200)}\n\n`);
    emit(`[architect] Phase 1 — planning…\n`);

    let run;
    try {
      run = await runArchitect({
        proxy: proxyBase,
        task,
        onProgress: (ev) => {
          if (ev.type === "plan-done")
            emit(
              `[architect] plan: ${ev.plan.length} steps\n` +
                ev.plan
                  .map(
                    (s) =>
                      `  ${s.index}. (${s.kind || "?"}, hint=${s.router_hint || "auto"}) ${s.title || ""}`,
                  )
                  .join("\n") +
                `\n\n[architect] Phase 2 — executing…\n`,
            );
          else if (ev.type === "step-start")
            emit(
              `  step ${ev.step.index} (${ev.step.kind || "?"}, hint=${ev.step.router_hint || "auto"}) → ${ev.model} …\n`,
            );
          else if (ev.type === "step-done")
            emit(
              `    ↳ ${ev.result.routerChoice} (${ev.result.routerBackend}) ${(ev.result.elapsed / 1000).toFixed(1)}s\n`,
            );
          else if (ev.type === "synth-start") emit(`\n[architect] Phase 3 — synthesising…\n`);
          else if (ev.type === "synth-done")
            emit(
              `  synth → ${ev.synth.routerChoice} (${ev.synth.routerBackend}) ${(ev.synth.elapsed / 1000).toFixed(1)}s\n\n---\n\n`,
            );
        },
      });
    } catch (err) {
      emit(`\n[architect] FATAL: ${err.message}\n`);
      res.write(`data: [DONE]\n\n`);
      res.end();
      appendDecision({
        ts: new Date().toISOString(),
        id,
        strategy: "architect",
        choice: "error",
        reason: `architect: ${err.message}`,
        success: false,
      });
      return;
    }

    emit(answerFromRun(run));
    res.write(`data: [DONE]\n\n`);
    res.end();
    appendDecision({
      ts: new Date().toISOString(),
      id,
      strategy: "architect",
      choice: "architect",
      reason: `architect: plan=${run.plan.length} local=${run.totals.totalLocal} cloud=${run.totals.totalCloud}`,
      backend_model: "(architect-pipeline)",
      total_ms: Date.now() - t0,
      stream: true,
      success: true,
      architect_plan_steps: run.plan.length,
      architect_local_steps: run.totals.totalLocal,
      architect_cloud_steps: run.totals.totalCloud,
    });
    return;
  }

  // Non-streaming: run pipeline, return single chat completion JSON.
  let run;
  try {
    run = await runArchitect({ proxy: proxyBase, task });
  } catch (err) {
    return sendJson(res, 500, {
      error: { message: `architect failed: ${err.message}`, type: "architect_error" },
    });
  }
  const answer = answerFromRun(run);
  const completion = {
    id: `chatcmpl-architect-${id}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: "router/architect",
    choices: [{ index: 0, message: { role: "assistant", content: answer }, finish_reason: "stop" }],
    usage: {
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
    },
  };
  res.writeHead(200, {
    "Content-Type": "application/json",
    "X-Router-Strategy": "architect",
    "X-Router-Choice": "architect",
    "X-Router-Backend": "(plan/execute/synth)",
    "X-Architect-Steps": String(run.plan.length),
    "X-Architect-Local": String(run.totals.totalLocal),
    "X-Architect-Cloud": String(run.totals.totalCloud),
  });
  res.end(JSON.stringify(completion));
  appendDecision({
    ts: new Date().toISOString(),
    id,
    strategy: "architect",
    choice: "architect",
    reason: `architect: plan=${run.plan.length} local=${run.totals.totalLocal} cloud=${run.totals.totalCloud}`,
    backend_model: "(architect-pipeline)",
    total_ms: Date.now() - t0,
    stream: false,
    success: true,
    architect_plan_steps: run.plan.length,
    architect_local_steps: run.totals.totalLocal,
    architect_cloud_steps: run.totals.totalCloud,
  });
}

// ----- /v1/models ----------------------------------------------------------
function handleModels(_req, res) {
  const created = Math.floor(Date.now() / 1000);
  const data = Object.keys(STRATEGIES).map((name) => ({
    id: `router/${name}`,
    object: "model",
    created,
    owned_by: "opencode-hybrid-router",
    description: STRATEGIES[name].description,
  }));
  data.push({
    id: "router/architect",
    object: "model",
    created,
    owned_by: "opencode-hybrid-router",
    description:
      "Architect/Editor pipeline: cloud planner emits a JSON plan, each step is routed individually via router/heuristic (with router_hint overrides), final answer is synthesised. Per-subtask granularity.",
  });
  sendJson(res, 200, { object: "list", data });
}

// ----- /healthz ------------------------------------------------------------
async function handleHealth(_req, res) {
  const health = {
    ok: true,
    strategies: Object.keys(STRATEGIES),
    local: { base: LOCAL_BASE, model: LOCAL_MODEL, reachable: false },
    cloud: { base: CLOUD_BASE, model: CLOUD_MODEL, key_present: !!CLOUD_API_KEY, reachable: false },
    router_model: ROUTER_MODEL,
    log_file: LOG_FILE,
    banner_enabled: BANNER_ENABLED,
  };
  try {
    const r = await fetch(`${LOCAL_BASE}/models`, { signal: AbortSignal.timeout(2000) });
    health.local.reachable = r.ok;
  } catch {}
  if (CLOUD_API_KEY) {
    try {
      const r = await fetch(`${CLOUD_BASE}/models`, {
        signal: AbortSignal.timeout(4000),
        headers: { Authorization: `Bearer ${CLOUD_API_KEY}` },
      });
      health.cloud.reachable = r.ok;
      if (r.ok) {
        const j = await r.json();
        const ids = (j.data || []).map((m) => m.id);
        health.cloud.has_configured_model = ids.includes(CLOUD_MODEL);
        health.cloud.has_fallback_model = ids.includes(CLOUD_FALLBACK_MODEL);
        health.cloud.sample_models = ids.slice(0, 8);
      }
    } catch (err) {
      health.cloud.error = err.message;
    }
  }
  sendJson(res, 200, health);
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

// ----- server --------------------------------------------------------------
const server = http.createServer(async (req, res) => {
  const url = req.url || "/";
  if (req.method === "POST" && url === "/v1/chat/completions") return handleChatCompletion(req, res);
  if (req.method === "GET" && url === "/v1/models") return handleModels(req, res);
  if (req.method === "GET" && (url === "/healthz" || url === "/health")) return handleHealth(req, res);
  // Stub for Ollama's /api/tags (cline 3.0.9 issues this before the first
  // /v1/chat/completions call). Our router is OpenAI-compat, not Ollama-
  // native, so a 404 here is non-fatal but noisy in logs. Returning an
  // empty models list lets the caller proceed silently.
  if (req.method === "GET" && url === "/api/tags") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ models: [] }));
    return;
  }
  if (req.method === "GET" && url === "/") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end(
      `opencode hybrid router\n\n` +
        `endpoints:\n` +
        `  POST /v1/chat/completions   (OpenAI-compatible)\n` +
        `  GET  /v1/models             (lists routing strategies as model IDs)\n` +
        `  GET  /healthz               (status of local + cloud backends)\n` +
        `  GET  /api/tags              (Ollama-compat stub: returns empty list)\n\n` +
        `strategies (${Object.keys(STRATEGIES).length}): ${Object.keys(STRATEGIES).join(", ")}\n\n` +
        `local : ${LOCAL_BASE} model=${LOCAL_MODEL}\n` +
        `cloud : ${CLOUD_BASE} model=${CLOUD_MODEL} key=${CLOUD_API_KEY ? "present" : "MISSING"}\n` +
        `router-model (small): ${ROUTER_MODEL}\n` +
        `log file: ${LOG_FILE}\n`,
    );
    return;
  }
  sendJson(res, 404, { error: { message: `not found: ${req.method} ${url}`, type: "not_found" } });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`opencode hybrid router listening on http://127.0.0.1:${PORT}`);
  console.log(`  strategies: ${Object.keys(STRATEGIES).join(", ")}`);
  console.log(`  local : ${LOCAL_BASE} model=${LOCAL_MODEL}`);
  console.log(`  cloud : ${CLOUD_BASE} model=${CLOUD_MODEL} key=${CLOUD_API_KEY ? "present" : "MISSING"}`);
  console.log(`  log file: ${LOG_FILE}`);
});

process.on("SIGINT", () => { server.close(() => process.exit(0)); });
process.on("SIGTERM", () => { server.close(() => process.exit(0)); });
