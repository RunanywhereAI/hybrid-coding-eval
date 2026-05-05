#!/usr/bin/env node
// Subprocess shim the Python R3 runner calls. Reads one JSON object from
// stdin describing the run, invokes runArchitect() from
// router/agentic/architect-core.mjs, and prints exactly one JSON object to
// stdout with the full trace the Python side needs. Progress events are
// emitted to stderr (one JSON per line, prefixed "EVENT ") so the parent can
// tail them for debugging without parsing stdout.
//
// Input JSON (stdin):
//   {
//     "task": "<task prompt>",        // required
//     "proxy": "http://127.0.0.1:8787", // optional
//     "maxSteps": 10,                  // optional
//     "planner": "router/always-cloud",    // optional
//     "executor": "router/heuristic",      // optional
//     "synthesizer": "router/heuristic"    // optional (cloud-by-default via always-cloud is also acceptable)
//   }
//
// Output JSON (stdout, single object):
//   {
//     "plan": [...],
//     "plannerResult": { content, elapsed, usage, cost, routerChoice, routerBackend, echoedModel },
//     "stepResults": [ { step, content, elapsed, usage, cost, routerChoice, routerBackend, echoedModel }, ... ],
//     "synth": { ... } | null,
//     "totals": { totalLocal, totalCloud, totalCalls, wallMs, hybridCostUsd,
//                 promptTokens, completionTokens, cachedTokens, reasoningTokens },
//     "finalOutput": "..."
//   }

import { runArchitect, answerFromRun, stripBanner } from "../router/agentic/architect-core.mjs";

async function readAllStdin() {
  return await new Promise((resolve, reject) => {
    let buf = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (buf += chunk));
    process.stdin.on("end", () => resolve(buf));
    process.stdin.on("error", reject);
  });
}

function emitEvent(ev) {
  try {
    process.stderr.write("EVENT " + JSON.stringify(ev) + "\n");
  } catch (_) {
    // ignore — progress events are advisory
  }
}

async function main() {
  const raw = await readAllStdin();
  let input;
  try {
    input = JSON.parse(raw || "{}");
  } catch (err) {
    process.stderr.write(`_architect_runner: bad stdin JSON: ${err.message}\n`);
    process.exit(2);
  }
  if (!input.task || typeof input.task !== "string") {
    process.stderr.write("_architect_runner: missing required field 'task'\n");
    process.exit(2);
  }

  const opts = {
    task: input.task,
    proxy: input.proxy || "http://127.0.0.1:8787",
    maxSteps: Number(input.maxSteps || 10),
    onProgress: emitEvent,
  };
  if (input.planner) opts.planner = input.planner;
  if (input.executor) opts.executor = input.executor;
  if (input.synthesizer) opts.synthesizer = input.synthesizer;

  let run;
  try {
    run = await runArchitect(opts);
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    process.stderr.write(`_architect_runner: runArchitect failed: ${msg}\n`);
    process.exit(1);
  }

  // Build the final output string — prefer synth.content, else stitch step
  // outputs. answerFromRun() is report-y; we just want the raw artifact the
  // Python side can hand to scorers.
  let finalOutput = "";
  if (run.synth && run.synth.content) {
    finalOutput = stripBanner(run.synth.content);
  } else if (run.stepResults.length === 1) {
    finalOutput = stripBanner(run.stepResults[0].content || "");
  } else {
    finalOutput = run.stepResults
      .map((r) => `### Step ${r.step.index}: ${r.step.title || ""}\n${stripBanner(r.content || "")}`)
      .join("\n\n");
  }

  // Drop bulky system-prompt text from the payload. The Python side only
  // needs the response content, usage, cost, and routing metadata.
  const slimPlanner = run.plannerResult
    ? {
        content: run.plannerResult.content,
        elapsed: run.plannerResult.elapsed,
        usage: run.plannerResult.usage,
        cost: run.plannerResult.cost,
        routerChoice: run.plannerResult.routerChoice,
        routerBackend: run.plannerResult.routerBackend,
        echoedModel: run.plannerResult.echoedModel,
      }
    : null;

  const slimSteps = (run.stepResults || []).map((r) => ({
    step: {
      index: r.step?.index,
      title: r.step?.title || "",
      kind: r.step?.kind || "?",
      router_hint: r.step?.router_hint || "auto",
    },
    content: r.content,
    elapsed: r.elapsed,
    usage: r.usage,
    cost: r.cost,
    routerChoice: r.routerChoice,
    routerBackend: r.routerBackend,
    echoedModel: r.echoedModel,
    error: r.error || null,
  }));

  const slimSynth = run.synth
    ? {
        content: run.synth.content,
        elapsed: run.synth.elapsed,
        usage: run.synth.usage,
        cost: run.synth.cost,
        routerChoice: run.synth.routerChoice,
        routerBackend: run.synth.routerBackend,
        echoedModel: run.synth.echoedModel,
      }
    : null;

  const out = {
    plan: run.plan,
    plannerResult: slimPlanner,
    stepResults: slimSteps,
    synth: slimSynth,
    totals: run.totals,
    finalOutput,
  };
  process.stdout.write(JSON.stringify(out));
}

main().catch((err) => {
  const msg = err && err.message ? err.message : String(err);
  process.stderr.write(`_architect_runner: unhandled: ${msg}\n`);
  process.exit(1);
});
