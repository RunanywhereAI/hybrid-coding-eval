// Authoritative per-million-token pricing for the cloud models the proxy can
// route to. Tables live in ../configs/pricing/pricing_tables.json so the JS
// proxy and the Python eval harness (src/hybrid_arena/core/pricing.py)
// read the exact same numbers — cost-parity guaranteed by construction.
//
// Cost = (prompt_tokens - cached_tokens) * input
//      + cached_tokens                   * cache_read
//      + completion_tokens               * output
//
// completion_tokens already includes reasoning_tokens for reasoning models —
// OpenAI's usage object exposes both, but you should NOT add them; they're
// counted inside completion_tokens. We surface reasoning_tokens separately
// only for transparency in the report.
//
// Local backends are billed at $0 (we treat the laptop electricity / hardware
// amortisation as free at the margin — the comparison is "what extra would I
// have paid the cloud provider"). This is documented in the report.

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createHash } from "node:crypto";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Resolve the pricing table path:
//   1. Env override HYBRID_PRICING_TABLE wins.
//   2. Else walk up from this file until we find pyproject.toml (repo
//      root marker), then look for configs/pricing/pricing_tables.json.
//   3. Fall back to legacy lib/pricing_tables.json to avoid a hard
//      failure during the migration window.
function resolvePricingTablePath() {
  const envOverride = process.env.HYBRID_PRICING_TABLE;
  if (envOverride) return resolve(envOverride);

  let cur = __dirname;
  // Walk up until we find pyproject.toml — identifies repo root.
  while (true) {
    if (existsSync(resolve(cur, "pyproject.toml"))) {
      const newPath = resolve(cur, "configs", "pricing", "pricing_tables.json");
      if (existsSync(newPath)) return newPath;
      const legacy = resolve(cur, "lib", "pricing_tables.json");
      if (existsSync(legacy)) return legacy;
      return newPath; // report the expected path so error message is useful
    }
    const parent = dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  // Give up — try legacy colocated file.
  return resolve(__dirname, "..", "lib", "pricing_tables.json");
}

// Load the shared pricing tables at module import time.
const _tablesPath = resolvePricingTablePath();
const _tablesBytes = readFileSync(_tablesPath);
const _tables = JSON.parse(_tablesBytes.toString("utf8"));
const _tablesSha = createHash("sha256").update(_tablesBytes).digest("hex");

console.error(
  `[pricing] loaded ${_tablesPath} (sha256=${_tablesSha.slice(0, 12)}…)`,
);

export const RATES_PER_M = _tables.rates_per_m;
export const PRICING_META = {
  fetched_at: _tables._meta?.fetched_at ?? null,
  source: _tables._meta?.source ?? null,
  path: _tablesPath,
  sha256: _tablesSha,
};

const FETCHED_AT = _tables._meta?.fetched_at ?? null;
const SOURCE = _tables._meta?.source ?? null;

// Normalise a model id to a key in RATES_PER_M.
//   "gpt-5.5-2026-04-23"      → "gpt-5.5"
//   "gpt-5.5-pro-2026-04-23"  → "gpt-5.5-pro"
//   "qwen3-coder:30b"         → "__local__"
//   "qwen3.6:27b-coding-mxfp8"→ "__local__"
//   anything unrecognised     → null
export function normaliseModelId(modelId) {
  if (!modelId) return null
  const s = String(modelId).toLowerCase().trim()
  // Local Ollama-style identifiers always include a colon (model:tag).
  if (s.includes(":")) return "__local__"
  // Exact match.
  if (RATES_PER_M[s]) return s
  // Strip OpenAI-style date suffix (`-YYYY-MM-DD`).
  const dated = s.replace(/-\d{4}-\d{2}-\d{2}$/, "")
  if (RATES_PER_M[dated]) return dated
  // Try progressively shorter prefixes (handle "gpt-5.5-pro-XX" variants).
  const parts = dated.split("-")
  while (parts.length > 1) {
    parts.pop()
    const candidate = parts.join("-")
    if (RATES_PER_M[candidate]) return candidate
  }
  return null
}

// Compute cost in USD given an OpenAI-shape usage object.
//
//   usage = {
//     prompt_tokens, completion_tokens, total_tokens,
//     prompt_tokens_details: { cached_tokens, ... },
//     completion_tokens_details: { reasoning_tokens, ... },
//   }
//
// Returns { usd, breakdown: { input_uncached, input_cached, output }, key, missing, tokens }
// Throws nothing; if the model isn't in the table, returns usd=0 and missing=true.
export function costFor(modelId, usage) {
  const key = normaliseModelId(modelId)
  const rates = key ? RATES_PER_M[key] : null

  const promptTokens = usage?.prompt_tokens ?? 0
  const completionTokens = usage?.completion_tokens ?? 0
  const cachedTokens = usage?.prompt_tokens_details?.cached_tokens ?? 0
  const reasoningTokens = usage?.completion_tokens_details?.reasoning_tokens ?? 0

  const uncachedPrompt = Math.max(0, promptTokens - cachedTokens)

  if (!rates) {
    return {
      usd: 0,
      breakdown: { input_uncached: 0, input_cached: 0, output: 0 },
      key: key ?? null,
      missing: true,
      tokens: { promptTokens, completionTokens, cachedTokens, reasoningTokens },
    }
  }

  const inputUncached = (uncachedPrompt / 1_000_000) * rates.input
  const inputCached   = (cachedTokens   / 1_000_000) * rates.cache_read
  const output        = (completionTokens / 1_000_000) * rates.output
  const usd = inputUncached + inputCached + output

  return {
    usd,
    breakdown: { input_uncached: inputUncached, input_cached: inputCached, output },
    key,
    missing: false,
    tokens: { promptTokens, completionTokens, cachedTokens, reasoningTokens },
  }
}

// USD formatter — shows enough precision for sub-cent costs.
export function fmtUSD(n, opts = {}) {
  const { sign = false, pad = 0 } = opts
  if (!isFinite(n)) return "$?"
  const v = Math.abs(n)
  let s
  if (v === 0)         s = "$0.0000"
  else if (v < 0.0001) s = `$${n.toFixed(6)}`
  else if (v < 0.01)   s = `$${n.toFixed(5)}`
  else if (v < 1)      s = `$${n.toFixed(4)}`
  else                 s = `$${n.toFixed(3)}`
  if (sign && n > 0) s = "+" + s
  return pad ? s.padStart(pad) : s
}

// Token formatter — comma thousands, padded.
export function fmtTok(n, pad = 0) {
  const s = (n ?? 0).toLocaleString("en-US")
  return pad ? s.padStart(pad) : s
}
// PRICING_META is exported at the top of this file (so the early
// loader metadata — path, sha256 — is available alongside fetched_at).
