#!/usr/bin/env node
/**
 * Unit test for the GET /api/tags Ollama-compat stub in router/server.mjs.
 *
 * Background: cline 3.0.9 issues a GET /api/tags call to its Ollama
 * provider BEFORE the first /v1/chat/completions call (it's Ollama's
 * model-listing endpoint). Our router proxy is OpenAI-compat, so before
 * this stub the call 404'd. The 404 was non-fatal but polluted logs.
 * This test pins the contract: 200 OK + JSON body {"models":[]}.
 *
 * Spawns server.mjs in a child process on a free port (PORT=0 is not
 * supported because the server hard-codes PORT=8787 default and binds
 * to it; instead we pick a high random port and pass via env), then
 * curls /api/tags via fetch and asserts the shape.
 *
 * Run via:
 *     node --test router/tests/api-tags-stub.test.mjs
 *
 * Picked up automatically by `npm test --prefix router` (which runs
 * `node --test tests/*.test.mjs`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SERVER_PATH = join(__dirname, "..", "server.mjs");

// Pick a likely-free high port to avoid colliding with a running router
// on the dev box. The default is :8787; we use :18787 to stay clear.
const TEST_PORT = Number(process.env.API_TAGS_TEST_PORT || 18787);

function startServer() {
  const env = {
    ...process.env,
    PORT: String(TEST_PORT),
    // Don't actually need cloud creds — /api/tags doesn't touch backends.
    CLOUD_API_KEY: process.env.CLOUD_API_KEY || "test-key-not-used",
    // Quieter logs in CI.
    ROUTER_BANNER: "0",
  };
  const child = spawn("node", [SERVER_PATH], {
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  return child;
}

async function waitForListen(child, timeoutMs = 4000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(`http://127.0.0.1:${TEST_PORT}/`, {
        signal: AbortSignal.timeout(500),
      });
      if (r.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`server did not listen on :${TEST_PORT} within ${timeoutMs}ms`);
}

test("/api/tags returns 200 with empty models list", async (t) => {
  const child = startServer();
  t.after(() => {
    try { child.kill("SIGTERM"); } catch {}
  });

  await waitForListen(child);

  const res = await fetch(`http://127.0.0.1:${TEST_PORT}/api/tags`);
  assert.equal(res.status, 200, "expected 200 OK");
  assert.equal(
    res.headers.get("content-type"),
    "application/json",
    "expected application/json content-type",
  );

  const body = await res.json();
  assert.ok(body && typeof body === "object", "body must be an object");
  assert.ok(Array.isArray(body.models), "body.models must be an array");
  assert.equal(body.models.length, 0, "body.models must be empty");
});

test("/api/tags only accepts GET (POST 404s like other endpoints)", async (t) => {
  const child = startServer();
  t.after(() => {
    try { child.kill("SIGTERM"); } catch {}
  });

  await waitForListen(child);

  const res = await fetch(`http://127.0.0.1:${TEST_PORT}/api/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  assert.equal(res.status, 404, "POST /api/tags should 404 (only GET is stubbed)");
});
