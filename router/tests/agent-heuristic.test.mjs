#!/usr/bin/env node
/**
 * Unit tests for the `agentHeuristic` strategy in router/strategies.mjs.
 *
 * Uses Node's built-in test runner (node:test) — no extra deps. Tests
 * the strategy function directly (no HTTP / running proxy required).
 *
 * Run via:
 *     node --test router/tests/agent-heuristic.test.mjs
 *
 * Also chained from router/tests/run-tests.mjs so `npm test --prefix router`
 * picks it up.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

// In v1.1 the agent-aware logic IS the canonical `heuristic` strategy.
// Tests live in this file (and call `heuristic` directly) because they
// were written to validate the agent-aware behavior specifically.
import { heuristic as agentHeuristic } from "../strategies.mjs";

// -- fixtures ---------------------------------------------------------------

const SYS_MINI_SWE_AGENT = {
  role: "system",
  content:
    "You are a helpful assistant that can interact with a computer shell. " +
    "Your job is to fix a bug in this repository. " +
    "Use the provided tools to explore the codebase, then submit your solution.",
};

const SYS_AIDER = {
  role: "system",
  content: "You are Aider, an AI pair programmer in the user's repo.",
};

const SYS_OPENCODE = {
  role: "system",
  content: "You are opencode, a TypeScript+Bun coding agent with Read/Write/Edit/Bash/Grep/Glob tools.",
};

const SYS_CLAUDE_CODE = {
  role: "system",
  content:
    "You are Claude Code, Anthropic's official CLI for Claude. " +
    "You can read, edit, write, and execute code in the user's local environment.",
};

const SYS_HUMAN_CHAT = {
  role: "system",
  content: "You are a helpful AI assistant. Answer questions concisely.",
};

const USR_PLAN_DJANGO = {
  role: "user",
  content:
    "<pr_description>\nFix django__django-11163: model_to_dict returns empty dict for instance with no concrete fields.\n</pr_description>\n\nExplore the repo, locate the bug, and submit a unified diff that passes the failing test.",
};

const USR_SHORT_CHAT = {
  role: "user",
  content: "What does this regex do? /a(b|c)+/",
};

const ASST_TOOL_CALL = {
  role: "assistant",
  content: null,
  tool_calls: [
    {
      id: "call_1",
      type: "function",
      function: { name: "bash", arguments: '{"command": "grep -r model_to_dict ."}' },
    },
  ],
};

const TOOL_RESULT_SHORT = {
  role: "tool",
  tool_call_id: "call_1",
  content:
    "./django/forms/models.py:34:def model_to_dict(instance, ...\n<returncode>0</returncode>",
};

const TOOL_RESULT_LONG_CODE = {
  role: "tool",
  tool_call_id: "call_2",
  content:
    "```python\ndef model_to_dict(instance, fields=None, exclude=None):\n" +
    "    opts = instance._meta\n    data = {}\n" +
    "    for f in chain(opts.concrete_fields, opts.private_fields, opts.many_to_many):\n" +
    "        if not getattr(f, 'editable', False):\n            continue\n        ...\n```\n" +
    "<returncode>0</returncode>",
};

// -- structural detection ---------------------------------------------------

test("non-agent chat → falls through to legacyHeuristic, choice and reason wrap correctly", async () => {
  const req = { messages: [SYS_HUMAN_CHAT, USR_SHORT_CHAT] };
  const out = await agentHeuristic(req, {});
  assert.match(out.reason, /not-agent → legacy/);
  assert.ok(["local", "cloud"].includes(out.choice));
});

test("tool-role message → detected as agent regardless of system prompt", async () => {
  const req = {
    messages: [
      SYS_HUMAN_CHAT, // not an agent marker
      USR_SHORT_CHAT,
      ASST_TOOL_CALL,
      TOOL_RESULT_SHORT,
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
  assert.match(out.reason, /heuristic\[agent score=/);
});

test("assistant.tool_calls[] → detected as agent on second turn", async () => {
  const req = {
    messages: [
      SYS_HUMAN_CHAT,
      { role: "user", content: "list files" },
      ASST_TOOL_CALL, // tool_calls present
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
});

// -- system-marker first-turn detection -------------------------------------

test("mini-swe-agent system marker on first turn → agent", async () => {
  const req = { messages: [SYS_MINI_SWE_AGENT, USR_PLAN_DJANGO] };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
});

test("Aider system marker on first turn → agent", async () => {
  const req = {
    messages: [SYS_AIDER, { role: "user", content: "Implement grep.py to pass grep_test.py" }],
  };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
});

test("opencode system marker on first turn → agent", async () => {
  const req = { messages: [SYS_OPENCODE, USR_SHORT_CHAT] };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
});

test("Claude Code system marker on first turn → agent (future-proofing)", async () => {
  const req = { messages: [SYS_CLAUDE_CODE, USR_SHORT_CHAT] };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
});

test("extra markers via ctx.extraAgentMarkers → agent", async () => {
  const req = {
    messages: [
      { role: "system", content: "You are FancyNewAgent v3.0." },
      USR_SHORT_CHAT,
    ],
  };
  const out = await agentHeuristic(req, { extraAgentMarkers: ["FancyNewAgent"] });
  assert.doesNotMatch(out.reason, /not-agent/);
});

// -- phase signals: first call (no prior assistant) → cloud bias ------------

test("first call with planning prompt (no prior assistant) → cloud", async () => {
  const req = { messages: [SYS_MINI_SWE_AGENT, USR_PLAN_DJANGO] };
  const out = await agentHeuristic(req, {});
  assert.equal(out.choice, "cloud", `expected cloud (planning step), got ${out.choice}: ${out.reason}`);
  assert.match(out.reason, /firstCall/);
});

// -- phase signals: post-tool-call → local bias ------------------------------

test("short tool result post-tool-call → local", async () => {
  const req = {
    messages: [
      SYS_MINI_SWE_AGENT,
      USR_PLAN_DJANGO,
      ASST_TOOL_CALL,
      TOOL_RESULT_SHORT,
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.equal(out.choice, "local", `expected local (tool-result interp), got ${out.choice}: ${out.reason}`);
  assert.match(out.reason, /toolResult/);
  assert.match(out.reason, /postToolCall/);
});

test("delta role is reported in meta", async () => {
  const req = {
    messages: [
      SYS_MINI_SWE_AGENT,
      USR_PLAN_DJANGO,
      ASST_TOOL_CALL,
      TOOL_RESULT_SHORT,
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.equal(out.meta.deltaRole, "tool");
});

// -- phase signals: tool result with heavy code → still local (delta scored) -

test("tool result with code blocks does NOT escalate to cloud (delta-only scoring)", async () => {
  const req = {
    messages: [
      SYS_MINI_SWE_AGENT,
      USR_PLAN_DJANGO,
      ASST_TOOL_CALL,
      TOOL_RESULT_LONG_CODE,
    ],
  };
  const out = await agentHeuristic(req, {});
  // Even with a 13-line code block in the delta, the tool-role penalty (-12)
  // + postToolCall penalty (-8) should overcome the codeBlocks*4 boost.
  assert.equal(out.choice, "local", `expected local, got ${out.choice}: ${out.reason}`);
});

// -- threshold override via ctx ---------------------------------------------

test("threshold can be raised via ctx.agentHeuristicThreshold (defaults to 12)", async () => {
  const req = { messages: [SYS_MINI_SWE_AGENT, USR_PLAN_DJANGO] };
  // First-call planning normally scores high enough to route cloud at THRESHOLD=12.
  // Raising threshold to 999 should force local for this call.
  const out = await agentHeuristic(req, { agentHeuristicThreshold: 999 });
  assert.equal(out.meta.threshold, 999);
  assert.equal(out.choice, "local", `expected local with threshold=999, got ${out.choice}: ${out.reason}`);
});

test("default threshold is 12", async () => {
  const req = { messages: [SYS_MINI_SWE_AGENT, USR_PLAN_DJANGO] };
  const out = await agentHeuristic(req, {});
  assert.equal(out.meta.threshold, 12);
});

// -- non-agent: legacy heuristic preserves semantics ------------------------

test("non-agent simple question → legacy heuristic picks local", async () => {
  const req = { messages: [SYS_HUMAN_CHAT, { role: "user", content: "what is 2+2?" }] };
  const out = await agentHeuristic(req, {});
  assert.match(out.reason, /not-agent/);
  assert.equal(out.choice, "local");
});

test("non-agent design question → legacy heuristic picks cloud", async () => {
  const req = {
    messages: [
      SYS_HUMAN_CHAT,
      {
        role: "user",
        content:
          "Design a system architecture for a distributed cache that handles 1M QPS. " +
          "Compare Redis vs Memcached vs DynamoDB tradeoffs and recommend the best option.",
      },
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.match(out.reason, /not-agent/);
  assert.equal(out.choice, "cloud");
});

// -- edge cases -------------------------------------------------------------

test("empty messages → not detected as agent (no crash)", async () => {
  const req = { messages: [] };
  const out = await agentHeuristic(req, {});
  assert.match(out.reason, /not-agent/);
});

test("only system message, no user → handled gracefully", async () => {
  const req = { messages: [SYS_OPENCODE] };
  const out = await agentHeuristic(req, {});
  // Detected as agent via system marker; delta = "" (no user msg).
  assert.doesNotMatch(out.reason, /not-agent/);
});

test("non-agent with array-content user message → still scored", async () => {
  // OpenAI multimodal-style content: array of {type, text}
  const req = {
    messages: [
      SYS_HUMAN_CHAT,
      { role: "user", content: [{ type: "text", text: "Hello world" }] },
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.ok(["local", "cloud"].includes(out.choice));
});

test("function role (legacy OpenAI schema) also triggers detection", async () => {
  const req = {
    messages: [
      SYS_HUMAN_CHAT,
      { role: "user", content: "what's the weather" },
      { role: "function", name: "get_weather", content: '{"temp": 72}' },
    ],
  };
  const out = await agentHeuristic(req, {});
  assert.doesNotMatch(out.reason, /not-agent/);
});
