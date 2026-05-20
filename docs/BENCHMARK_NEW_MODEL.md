# Benchmark a new local model (v1.4)

The production use case for **hybrid-coding-eval** is straightforward: a new local coding model drops on Ollama (or anywhere with an OpenAI-compatible endpoint) and you want to know, with statistical confidence, **whether it's good enough to run inside a real coding agent loop hybridized with the cloud**.

This guide takes you from "model exists" → "publishable cost/quality numbers vs the v1.4 canonical baseline" in 5 minutes of work + a few hours of wall time.

---

## 1. Pull the new model

```bash
ollama pull deepseek-coder-v3:33b              # or wherever your model lives
```

`bench sweep` reads `models.local` from the variant config and auto-spawns the router proxy with `LOCAL_MODEL=<model>`. You do **not** need to restart anything manually; just point a sweep at the new model below.

Cloud baseline stays `gpt-5.5` unless you override `models.cloud`. The v1.4 canonical numbers are against gpt-5.5; keep that constant to make the comparison meaningful.

## 2. Point a sweep at the new model

Either edit `configs/v1.4-canonical.yaml`:

```yaml
models:
  cloud: gpt-5.5
  local: deepseek-coder-v3:33b                # ← your new model
```

Or override on the CLI without touching the YAML:

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --set models.local=deepseek-coder-v3:33b \
  --set out_dir=results/runs/v1.4-deepseek-coder-v3 \
  --strategies heuristic --seeds 42 --smoke
```

Leave everything else at canonical defaults. The v1.4 canonical config covers the full benchmark mix: 5 agentic routes × 8 strategies × 18 tasks.

## 3. Smoke first (~5 min)

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --set models.local=deepseek-coder-v3:33b \
  --set out_dir=results/runs/v1.4-deepseek-coder-v3 \
  --strategies heuristic --seeds 42 --smoke
```

Smoke = 1 task per category × 1 strategy. Verifies your model handles the agent loops end-to-end (returns valid tool calls; doesn't 400 on the function-call format).

If smoke fails, the most common causes are:

- **400 on tool-call format**: your model's tokenizer can't handle the agent's tool schema. Try a different agent (R7 aider's architect/editor protocol is more forgiving than R8 opencode's free-form tool-use).
- **Timeout**: bump the per-task timeout or use a faster model.
- **No diff produced**: model's understanding of the harness is weak. Either tune temperature or move on.

## 4. Full canonical sweep (~14–22 h wall, ~$30–60 spend)

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --set models.local=deepseek-coder-v3:33b \
  --set out_dir=results/runs/v1.4-deepseek-coder-v3 \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
```

18 tasks × 5 routes × 4 strategies × 3 seeds = up to 1,080 graded rows. Per-cell subdirectories under `results/runs/v1.4-deepseek-coder-v3/`.

`bench sweep` will:

1. Auto-spawn `node router/server.mjs` with `LOCAL_MODEL=deepseek-coder-v3:33b` on :8787
2. Loop every `(strategy, seed)` pass, writing to `<out_dir>/<strategy>/seed-<seed>/raw.jsonl`
3. Tear the router down on completion

Pass `--external-router` if you want to manage the router proxy yourself.

## 5. Analyze

```bash
./bench analyze results/runs/v1.4-deepseek-coder-v3/
```

Produces:

- `aggregate.json` — per-cell sums, means, medians (categories × routes × strategies)
- `bootstrap_cis.json` — 95% percentile CIs for `pass_rate`, `cost_usd`, `cloud_fraction`, `wall_ms` per cell
- `decision_matrix.md` — human-readable summary
- `charts/pareto.png` + 3 heatmaps

## 6. Compare to the v1.4 canonical baseline

```bash
gh release download v1.4.0 -p 'results-v1.4.0.tar.gz'
tar xzf results-v1.4.0.tar.gz -C /tmp/v1.4-baseline/
diff <(jq -S '.cells' results/runs/v1.4-deepseek-coder-v3/bootstrap_cis.json) \
     <(jq -S '.cells' /tmp/v1.4-baseline/.../bootstrap_cis.json)
```

The two `bootstrap_cis.json` files use the same cell-key shape (`<category>::<route>::<strategy>`), so you can compare CIs directly. Cells where your new model's CI is strictly better than the baseline's CI are real wins; cells where they overlap are statistically tied.

To extract a single headline number from a specific cell, see [`REPRODUCING.md` §9 "How to read the results"](./REPRODUCING.md#9-how-to-read-the-results--cell--headline-number).

## 7. (Optional) Publish

Open a PR adding `configs/v1.4-<model-tag>.yaml` (a copy of `configs/v1.4-canonical.yaml` with your model in `models.local`) to the repo. Maintainer reviews + merges. Your variant becomes a permanent benchmark recipe. If you also include `results/runs/v1.4-<model-tag>/bootstrap_cis.json` + run-notes, the maintainer can include your dataset in the next minor release's tarball.

---

## What the canonical sweep covers (v1.4)

The default `configs/v1.4-canonical.yaml` runs against this benchmark mix:

| Benchmark | Category (v1.4 cell name) | Tasks | Why |
| --- | --- | --- | --- |
| Exercism Python | `puzzles` (was `X`) | 10 | Small algorithmic tasks — local models tend to struggle here |
| real-developer D1+D5 | `refactors` (was `D`) | 8 | Practical refactoring patterns from real PRs — the v1.3.0 hybrid-win regime |
| **Total** | | **18 tasks** | |

The five agentic routes (R6..R10) all use the same task set; the routing strategy decides which turns hit local vs cloud. v1.4 deletes the legacy non-agentic R1/R2/R3 routes and the Stanford-Minion R4/R5 wrappers — `bench sweep` runs the agentic surface only.

## Comparable canonical baselines

| Tag | Local model | Wall | Cost (gpt-5.5 cloud) | Notes |
|---|---|---|---|---|
| v1.4.0 (latest) | gemma4:31b | ~14–22 h | ~$30–60 | Multi-agent, 8 strategies — `gh release v1.4.0` |
| v1.3.0 | gemma4:31b + qwen3-coder:30b | ~6 h | ~$33 | Aider-only (R7), 3 sweeps, 507 rows — `gh release v1.3.0` |
| v1.2.0 | qwen3-coder:30b | ~5 h | ~$5 | Aider-only (R7), 60 rows — `gh release v1.2.0` |
| v1.0.0 | devstral:24b | ~12 h | ~$40 | Non-agentic R1–R5 only — `gh release v1.0.0` |

## When NOT to benchmark a new model with this harness

- **Non-coding domain.** This harness is calibrated for coding tasks; a creative-writing or math model will produce uninterpretable scores.
- **No OpenAI-compatible chat API.** Every agent (R6..R10) talks via OpenAI-compatible chat completions. Models without that wire format won't work end-to-end.
- **You only care about throughput.** This harness measures quality and cost; raw tokens/sec belongs in lm-eval-harness or vLLM's own benchmarks.

---

## See also

- [`./REPRODUCING.md`](./REPRODUCING.md) — copy-paste v1.4 reproducer + how-to-read-results
- [`./AGENTIC_ROUTES.md`](./AGENTIC_ROUTES.md) — R6..R10 design + correlation-id attribution
- [`./ROUTING_STRATEGIES.md`](./ROUTING_STRATEGIES.md) — full strategy taxonomy
- [`./METHODOLOGY.md`](./METHODOLOGY.md) — scoring rubrics + biases acknowledged
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — how to propose new tasks / strategies / benchmarks
