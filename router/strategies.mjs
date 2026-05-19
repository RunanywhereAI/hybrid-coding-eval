// Routing strategies. Pure logic. Each `decide(req, ctx)` returns
//   { choice: 'local' | 'cloud', reason: string, confidence: number, meta?: object }
//
// `req` = the parsed chat-completion body (messages, tools, temperature, …).
// `ctx` = { localBase, localModel, cloudBase, cloudModel, cloudKey, corpus, embedCache, log }.

import { readFile } from "node:fs/promises";

// ----- helpers ---------------------------------------------------------------

export function lastUserText(messages) {
  if (!Array.isArray(messages)) return "";
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m && m.role === "user") {
      if (typeof m.content === "string") return m.content;
      if (Array.isArray(m.content)) {
        return m.content
          .map((p) => (typeof p === "string" ? p : p && p.type === "text" ? p.text : ""))
          .filter(Boolean)
          .join("\n");
      }
    }
  }
  return "";
}

export function approxTokens(text) {
  // ~4 chars/token rule of thumb. Cheap, no tokenizer dep.
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}

export function totalPromptTokens(messages) {
  let n = 0;
  for (const m of messages || []) {
    if (typeof m.content === "string") n += approxTokens(m.content);
    else if (Array.isArray(m.content)) {
      for (const p of m.content)
        n += approxTokens(typeof p === "string" ? p : p?.text || "");
    }
  }
  return n;
}

export function countCodeBlocks(text) {
  const m = (text || "").match(/```/g);
  return m ? Math.floor(m.length / 2) : 0;
}

// ----- strategy 1: always-local ---------------------------------------------
export async function alwaysLocal() {
  return { choice: "local", reason: "control: always-local", confidence: 1 };
}

// ----- strategy 2: always-cloud ---------------------------------------------
export async function alwaysCloud() {
  return { choice: "cloud", reason: "control: always-cloud", confidence: 1 };
}

// ----- strategy 3: rules ----------------------------------------------------
const CLOUD_KEYWORDS = [
  "design","architect","architecture","explain why","compare",
  "long","comprehensive","plan","strategy","trade-off","tradeoff",
  "production","security","threat model","performance critical",
  "optimize","refactor entire","refactor all","migration plan",
  "step by step","prove","derive","analyze the","review the",
  "best way to","what would be the best",
];
const LOCAL_KEYWORDS = [
  "rename","typo","add a comment","format","prettier",
  "what is","fix the typo","change the variable",
  "convert","one-liner","quick","trivial",
];

export async function rules(req) {
  const text = lastUserText(req.messages).toLowerCase();
  const tokens = totalPromptTokens(req.messages);
  const codeBlocks = countCodeBlocks(text);

  const cloudHits = CLOUD_KEYWORDS.filter((k) => text.includes(k));
  const localHits = LOCAL_KEYWORDS.filter((k) => text.includes(k));

  const triggers = [];
  if (tokens > 4000) triggers.push(`tokens>${4000} (${tokens})`);
  if (codeBlocks >= 3) triggers.push(`code-blocks>=3 (${codeBlocks})`);
  if (cloudHits.length > 0) triggers.push(`kw[cloud]: ${cloudHits.slice(0, 3).join(",")}`);

  if (triggers.length > 0)
    return {
      choice: "cloud",
      reason: `rules: ${triggers.join(" | ")}`,
      confidence: Math.min(1, 0.5 + 0.15 * triggers.length),
    };

  if (localHits.length > 0)
    return {
      choice: "local",
      reason: `rules: kw[local]: ${localHits.slice(0, 3).join(",")}`,
      confidence: 0.85,
    };

  return {
    choice: "local",
    reason: `rules: default-local (tokens=${tokens}, codeBlocks=${codeBlocks})`,
    confidence: 0.6,
  };
}

// ----- legacyHeuristic (composite score, non-agent fall-through) -----------
// The v1.0.0 heuristic. Calibrated for human-typed prompts where the user
// message IS the work to do. Score is a weighted sum over (user tokens,
// code blocks, cloud/local keyword hits, tool count). Threshold 25 →
// cloud, below → local.
//
// In v1.1 this is no longer the canonical `heuristic` strategy — it's the
// private fall-through called by the new agent-aware heuristic (below)
// when isAgentCall(messages) returns false. This preserves byte-identical
// behavior for every v3.3 row in the canonical dataset (non-agent calls
// score identically; the model field has no /run-<id> for those rows).
async function legacyHeuristic(req) {
  const text = lastUserText(req.messages);
  const lower = text.toLowerCase();
  const userTokens = approxTokens(text);
  const codeBlocks = countCodeBlocks(text);

  // Weighted score. Higher → more "complex" → cloud.
  let score = 0;
  const parts = [];

  // User-message size: cap contribution so a single 4 K-token paste alone
  // doesn't auto-cloud everything.
  const tokenScore = Math.min(20, userTokens / 80);
  score += tokenScore;
  parts.push(`uTok=${userTokens}(+${tokenScore.toFixed(1)})`);

  // Code blocks: more = bigger context.
  const codeScore = codeBlocks * 6;
  score += codeScore;
  if (codeBlocks > 0) parts.push(`cb=${codeBlocks}(+${codeScore})`);

  // Cloud keyword count — strong signal.
  const cloudKw = CLOUD_KEYWORDS.filter((k) => lower.includes(k));
  const kwScore = cloudKw.length * 14;
  score += kwScore;
  if (cloudKw.length > 0) parts.push(`kw=${cloudKw.length}(+${kwScore})`);

  // Local keyword count: subtract.
  const localKw = LOCAL_KEYWORDS.filter((k) => lower.includes(k));
  const localPenalty = localKw.length * 18;
  score -= localPenalty;
  if (localKw.length > 0) parts.push(`-local-kw=${localKw.length}(-${localPenalty})`);

  // Heavy tools fan-out is a weak agentic-difficulty signal but unreliable
  // (opencode always sends 10+ tools regardless of task), so we only bump for
  // *very* heavy tool sets.
  const toolCount = (req.tools || []).length;
  if (toolCount >= 25) {
    score += 6;
    parts.push(`tools=${toolCount}(+6)`);
  }

  const THRESHOLD = 25;
  const choice = score >= THRESHOLD ? "cloud" : "local";
  const distance = Math.abs(score - THRESHOLD);
  const confidence = Math.min(1, 0.5 + distance / 50);

  return {
    choice,
    reason: `heuristic[score=${score.toFixed(1)} >=${THRESHOLD}? → ${choice}] ${parts.join(" ")}`,
    confidence,
    meta: { score, threshold: THRESHOLD, distance },
  };
}

// ----- strategy 3b — also re-score `rules` to use user-message tokens ------
// (rules() above already keys off lastUserText; the only token check is a hard
// > 4000 ceiling on totalPromptTokens which we keep for "user pasted a giant
// blob" safety. No change needed.)

// ----- strategy 5: LLM classifier (qwen3:0.6b) ------------------------------
const CLASSIFIER_SYSTEM = `You are a routing classifier. You will be given a coding task. Your job is to classify it as either SIMPLE or COMPLEX.

SIMPLE means: a junior developer can do it in under 5 minutes with no architectural thought. Examples: rename a variable, fix a typo, add a single function, convert a list comprehension.

COMPLEX means: requires planning, multiple files, architectural decisions, security/performance reasoning, or producing a long structured answer. Examples: design a system, refactor a whole module, explain why a bug occurs across components, write comprehensive tests for a feature, plan a migration.

Respond with EXACTLY one word: SIMPLE or COMPLEX. No reasoning, no other words.`;

export async function llmClassifier(req, ctx) {
  const text = lastUserText(req.messages).slice(0, 4000); // truncate
  const t0 = Date.now();
  let raw = "";
  try {
    // Use Ollama's native /api/chat to disable Qwen3 thinking mode (think:false).
    const ollamaBase = ctx.localBase.replace(/\/v1$/, "");
    const res = await fetch(`${ollamaBase}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: ctx.routerModel || "qwen3:0.6b",
        messages: [
          { role: "system", content: CLASSIFIER_SYSTEM },
          { role: "user", content: text },
        ],
        stream: false,
        think: false,
        options: { temperature: 0, num_predict: 4 },
      }),
    });
    if (!res.ok) throw new Error(`status=${res.status}`);
    const j = await res.json();
    raw = (j?.message?.content || "").trim().toUpperCase();
  } catch (err) {
    return {
      choice: "local",
      reason: `llm-classifier: error → fallback local (${err.message})`,
      confidence: 0.3,
    };
  }
  const elapsed = Date.now() - t0;
  const isComplex = raw.startsWith("COMPLEX");
  const isSimple = raw.startsWith("SIMPLE");
  if (!isComplex && !isSimple)
    return {
      choice: "local",
      reason: `llm-classifier: unclear "${raw.slice(0, 20)}" → fallback local (${elapsed}ms)`,
      confidence: 0.4,
    };

  return {
    choice: isComplex ? "cloud" : "local",
    reason: `llm-classifier(${ctx.routerModel || "qwen3:0.6b"}): "${raw}" (${elapsed}ms)`,
    confidence: 0.8,
    meta: { classifierLatencyMs: elapsed },
  };
}

// ----- strategy 6: embedding kNN -------------------------------------------
export async function embeddingKnn(req, ctx) {
  const text = lastUserText(req.messages).slice(0, 4000);
  const t0 = Date.now();

  // Lazy-load corpus & precompute embeddings.
  if (!ctx.corpus._loaded) {
    try {
      const raw = await readFile(ctx.corpus.path, "utf8");
      const examples = JSON.parse(raw); // [{text, label: "local"|"cloud"}]
      const embedded = [];
      for (const ex of examples) {
        const e = await ollamaEmbed(ctx.localBase.replace(/\/v1$/, ""), ex.text);
        if (e) embedded.push({ ...ex, emb: e });
      }
      ctx.corpus.examples = embedded;
      ctx.corpus._loaded = true;
      ctx.log("info", `embedding-knn: corpus ready (${embedded.length} examples)`);
    } catch (err) {
      ctx.corpus.examples = [];
      ctx.corpus._loaded = true;
      ctx.log("warn", `embedding-knn: corpus load failed: ${err.message}`);
    }
  }

  if (!ctx.corpus.examples || ctx.corpus.examples.length === 0)
    return {
      choice: "local",
      reason: "embedding-knn: empty corpus → fallback local",
      confidence: 0.3,
    };

  let qEmb = null;
  try {
    qEmb = await ollamaEmbed(ctx.localBase.replace(/\/v1$/, ""), text);
  } catch (err) {
    return {
      choice: "local",
      reason: `embedding-knn: embed failed → fallback local (${err.message})`,
      confidence: 0.3,
    };
  }
  if (!qEmb)
    return {
      choice: "local",
      reason: "embedding-knn: no query embedding → fallback local",
      confidence: 0.3,
    };

  const scored = ctx.corpus.examples
    .map((ex) => ({ label: ex.label, sim: cosine(qEmb, ex.emb), text: ex.text }))
    .sort((a, b) => b.sim - a.sim);

  const k = 5;
  const top = scored.slice(0, k);
  const cloudVotes = top.filter((t) => t.label === "cloud");
  const cloudWeight = cloudVotes.reduce((s, t) => s + t.sim, 0);
  const localWeight = top.filter((t) => t.label === "local").reduce((s, t) => s + t.sim, 0);
  const choice = cloudWeight > localWeight ? "cloud" : "local";
  const total = cloudWeight + localWeight || 1;
  const confidence = Math.max(cloudWeight, localWeight) / total;
  const elapsed = Date.now() - t0;

  return {
    choice,
    reason: `embedding-knn[k=${k}]: cloud=${cloudVotes.length}/${k} (w=${cloudWeight.toFixed(2)} vs ${localWeight.toFixed(2)}) (${elapsed}ms) — top: "${top[0].text.slice(0, 60)}"`,
    confidence,
    meta: { topSim: top[0].sim, neighborhoodMs: elapsed },
  };
}

// ----- strategy 4: heuristic (agent-aware) ----------------------------------
//
// The v1.1 canonical heuristic. The v1.0.0 heuristic (now `legacyHeuristic`
// above) routed 100% cloud on agent calls because every mini-swe-agent /
// aider / opencode message has a long system prompt + tool descriptions
// + code blocks that all add to the composite score. This version fixes
// it by:
//
//   1. Detecting agent-shaped requests via isAgentCall() — structural
//      signals (tool/function role, assistant.tool_calls) first, then
//      system-marker fallback for first-turn detection.
//   2. Scoring the DELTA (latest tool/user message) instead of the full
//      prompt — short tool-result echoes score low; planning prompts
//      score high.
//   3. Applying phase signals (post-tool-call → bias local; first call
//      of loop with no prior assistant → bias cloud).
//
// Non-agent calls fall through to `legacyHeuristic` so v3.3 numbers stay
// byte-identical.

// Default markers that identify an agent call by system-prompt content.
// Structural signals (`tool`/`function` role + assistant.tool_calls) are
// the PRIMARY detection path — they fire reliably for any modern agent
// after the first turn. Markers are a SECONDARY (first-turn) signal, used
// when there's no role/tool_calls evidence yet (the very first model call
// of the loop has only [system, user] messages).
//
// Extend at runtime via env: ROUTER_AGENT_SYSTEM_MARKERS=foo,bar.
export const DEFAULT_AGENT_SYSTEM_MARKERS = [
  // mini-swe-agent (R6)
  "You are a helpful assistant that can interact with a computer shell",
  "mini-swe-agent",
  "submit your solution",
  "You are a software engineer interacting continuously with a computer",
  "<pr_description>",
  // Aider (R7)
  "Aider",
  // opencode (R8)
  "opencode",
  // Generic agentic-tool markers — added for v1.2+ tool support.
  // Educated guesses; refine when we integrate each tool.
  "Claude Code",
  "Cursor",
  "Cline",
  "Warp",
  "Roo Code",
  "Continue",
];

/**
 * Return true if the request is from an agent loop.
 *
 * Primary signals (structural, very reliable from turn 2 onward):
 *   - any message with role === "tool" or "function"
 *   - any assistant message with non-empty tool_calls[]
 *
 * Secondary signal (first-turn-only, marker-based):
 *   - system prompt contains a known agent marker (DEFAULT + ctx.extraAgentMarkers)
 *
 * For non-agent calls (regular chat completions), agent-heuristic falls
 * back to legacyHeuristic, so a false-negative here is non-fatal —
 * routing still proceeds via the prompt-bulk heuristic.
 */
function isAgentCall(messages, ctx = {}) {
  if (!Array.isArray(messages) || messages.length === 0) return false;

  // Primary: structural signals.
  for (const m of messages) {
    if (!m) continue;
    if (m.role === "tool" || m.role === "function") return true;
    if (
      m.role === "assistant" &&
      Array.isArray(m.tool_calls) &&
      m.tool_calls.length > 0
    ) {
      return true;
    }
  }

  // Secondary: system marker (first-turn detection).
  const extra = Array.isArray(ctx?.extraAgentMarkers) ? ctx.extraAgentMarkers : [];
  const markers = [...DEFAULT_AGENT_SYSTEM_MARKERS, ...extra];
  for (const m of messages) {
    if (m && m.role === "system" && typeof m.content === "string") {
      if (markers.some((mk) => m.content.includes(mk))) return true;
    }
  }
  return false;
}

function extractContent(m) {
  if (!m) return "";
  if (typeof m.content === "string") return m.content;
  if (Array.isArray(m.content))
    return m.content
      .map((p) => (typeof p === "string" ? p : p?.text || ""))
      .filter(Boolean)
      .join("\n");
  return "";
}

function lastSignificantMessage(messages) {
  // The newest content this call needs to reason about. For agent loops the
  // tool result is usually most recent; for fresh user turns the user message.
  if (!Array.isArray(messages) || messages.length === 0)
    return { text: "", role: "unknown" };
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (!m) continue;
    if (m.role === "tool" || m.role === "function" || m.role === "user") {
      return { text: extractContent(m), role: m.role };
    }
  }
  return { text: "", role: "unknown" };
}

function previousAssistantHadToolCall(messages) {
  if (!Array.isArray(messages)) return false;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.role === "assistant") {
      return Array.isArray(m.tool_calls) && m.tool_calls.length > 0;
    }
  }
  return false;
}

export async function heuristic(req, ctx = {}) {
  const isAgent = isAgentCall(req.messages, ctx);

  // Non-agent: fall through to the v1.0.0 legacy heuristic — preserves
  // v3.3 / v1.0.0 numerical semantics for any caller that doesn't carry
  // an agent fingerprint.
  if (!isAgent) {
    const h = await legacyHeuristic(req);
    return {
      ...h,
      reason: `heuristic[not-agent → legacy]: ${h.reason}`,
    };
  }

  const { text: delta, role: deltaRole } = lastSignificantMessage(req.messages);
  const lower = delta.toLowerCase();
  const deltaTokens = approxTokens(delta);
  const codeBlocks = countCodeBlocks(delta);

  let score = 0;
  const parts = [];

  // Token contribution: cap so even a 4 K delta only scores 20.
  const tokenScore = Math.min(20, deltaTokens / 60);
  score += tokenScore;
  parts.push(`Δtok=${deltaTokens}(+${tokenScore.toFixed(1)})`);

  // Code blocks: each block is signal of new logic to reason about.
  const codeScore = codeBlocks * 4;
  score += codeScore;
  if (codeBlocks > 0) parts.push(`cb=${codeBlocks}(+${codeScore})`);

  // Cloud-keyword count on the delta (not the whole prompt).
  const cloudKw = CLOUD_KEYWORDS.filter((k) => lower.includes(k));
  const kwScore = cloudKw.length * 8;
  score += kwScore;
  if (cloudKw.length > 0) parts.push(`kw=${cloudKw.length}(+${kwScore})`);

  // Phase signal: tool-result echoes route local (small bash output etc.).
  if (deltaRole === "tool" || deltaRole === "function" || delta.includes("<returncode>")) {
    score -= 12;
    parts.push("toolResult(-12)");
  }

  // Phase signal: the previous assistant turn had a tool call → this is a
  // consume-tool-result call. Likely simple continuation.
  if (previousAssistantHadToolCall(req.messages)) {
    score -= 8;
    parts.push("postToolCall(-8)");
  }

  // First call of agent loop (no prior assistant) → planning step, bias cloud.
  const hasAssistant = req.messages.some((m) => m?.role === "assistant");
  if (!hasAssistant) {
    score += 15;
    parts.push("firstCall(+15)");
  }

  // Threshold is env-overridable via ROUTER_AGENT_HEURISTIC_THRESHOLD
  // (plumbed by server.mjs into ctx.agentHeuristicThreshold). Default 12.
  const THRESHOLD = ctx?.agentHeuristicThreshold ?? 12;
  const choice = score >= THRESHOLD ? "cloud" : "local";
  const distance = Math.abs(score - THRESHOLD);
  const confidence = Math.min(1, 0.5 + distance / 30);

  return {
    choice,
    reason: `heuristic[agent score=${score.toFixed(1)} >=${THRESHOLD}? → ${choice}] role=${deltaRole} ${parts.join(" ")}`,
    confidence,
    meta: { score, threshold: THRESHOLD, distance, deltaRole, deltaTokens },
  };
}

// ----- strategy 8: cascade --------------------------------------------------
// 1) Pre-filter with heuristic. 2) If clearly simple OR clearly complex → trust it.
// 3) If borderline (within `ctx.cascadeThreshold` of heuristic boundary, default 15) → run LLM-classifier as tie-breaker.
// 4) Final answer is whichever the tie-breaker (or heuristic) picked.
//
// The threshold is configurable via the ROUTER_CASCADE_THRESHOLD env var
// (read in router/server.mjs, threaded through `ctx.cascadeThreshold`).
// Lower threshold → trust heuristic more (less LLM cost, less accuracy
// on borderline). Higher threshold → more LLM tiebreaks fire.
export async function cascade(req, ctx) {
  const threshold = ctx.cascadeThreshold ?? 15;
  // Forward ctx so the inner heuristic can read agentHeuristicThreshold +
  // extraAgentMarkers. Cascade is now also agent-aware (free ride via the
  // heuristic upgrade).
  const h = await heuristic(req, ctx);
  const distance = h.meta?.distance ?? 999;
  if (distance > threshold)
    return {
      choice: h.choice,
      reason: `cascade[trust-heuristic dist=${distance.toFixed(1)} >${threshold}]: ${h.reason}`,
      confidence: h.confidence,
    };

  // Borderline → tie-break with LLM classifier.
  const c = await llmClassifier(req, ctx);
  if (c.choice === h.choice)
    return {
      choice: h.choice,
      reason: `cascade[agree dist=${distance.toFixed(1)} ≤${threshold}, llm=${c.choice}]: ${h.reason} | ${c.reason}`,
      confidence: Math.min(1, 0.5 + (h.confidence + c.confidence) / 4),
    };
  return {
    choice: c.choice,
    reason: `cascade[disagree dist=${distance.toFixed(1)} ≤${threshold} → trust-llm]: heur=${h.choice}, llm=${c.choice} | ${c.reason}`,
    confidence: Math.max(c.confidence - 0.1, 0.5),
  };
}

// ----- ollama embedding helper ---------------------------------------------
async function ollamaEmbed(ollamaBase, input, model = "nomic-embed-text") {
  const url = `${ollamaBase}/api/embeddings`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, prompt: input }),
  });
  if (!res.ok) throw new Error(`embeddings status=${res.status}`);
  const j = await res.json();
  return j.embedding || null;
}

function cosine(a, b) {
  if (!a || !b || a.length !== b.length) return 0;
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (!na || !nb) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

// ----- registry --------------------------------------------------------------
export const STRATEGIES = {
  "always-local":   { fn: alwaysLocal,   description: "Control: always route to the local model. Useful for measuring local-only quality." },
  "always-cloud":   { fn: alwaysCloud,   description: "Control: always route to the cloud model. Useful for measuring cloud-only cost." },
  "rules":          { fn: rules,         description: "Hard-coded keyword + token rules. Fast, deterministic, no model in the loop." },
  "heuristic":      { fn: heuristic,     description: "Agent-aware composite-score heuristic. Detects ReAct agent calls and scores the latest message delta with phase signals; falls through to legacy non-agent heuristic for human chat prompts." },
  "llm-classifier": { fn: llmClassifier, description: "Single qwen3:0.6b call returns SIMPLE or COMPLEX. ~50–150ms latency overhead." },
  "embedding-knn":  { fn: embeddingKnn,  description: "Embed query with nomic-embed-text and kNN-vote against a 50-example labelled corpus." },
  "cascade":        { fn: cascade,       description: "Heuristic first; if score is borderline, fall back to llm-classifier as tie-breaker." },
};
