# Reproducing hybrid-coding-eval v1.4

**Copy-paste step-by-step instructions for reproducing the v1.4 canonical sweep on a fresh machine.** Every command below is verified against the current codebase. If one fails, consult [§13 Troubleshooting](#13-troubleshooting).

See [`METHODOLOGY.md`](./METHODOLOGY.md) for *why* we chose these tasks, agents, and scoring pipelines. This document is the *how*.

> **Status:** This document covers the **v1.4 canonical sweep**: 5 agentic routes (R6..R10) × 8 strategies × 3 local models × 18 tasks × 3 seeds. See [`release-notes/v1.4.0.md`](./release-notes/v1.4.0.md) for the published headline numbers and `gh release download v1.4.0 -p results-v1.4.0.tar.gz` for the dataset.

---

## 0. The four-command quickstart (TL;DR)

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval && cd hybrid-coding-eval
python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
cp .env.example .env && $EDITOR .env                   # OPEN_AI_API_KEY (+ ANTHROPIC_API_KEY)
./bench setup && ollama pull gemma4:31b
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
```

`bench sweep` auto-spawns the router proxy (reading `models.local` from the config), runs every `(strategy, seed)` pass, and tears down on completion. Add `--smoke` for a 1-task per category dry-run; add `--external-router` to manage the router proxy yourself.

The rest of this document is the long form: prerequisites, troubleshooting, post-sweep analysis, the cell→headline-number map.

---

## 1. What this reproduces

Running the steps below produces the **v1.4 canonical sweep**: pass-rate / cost / cloud-fraction / wall-ms for every `(category, route, strategy)` cell at 95% bootstrap confidence intervals, n=18 rows per cell (single seed) or n=54 per cell (3 seeds).

| | Count | What it measures |
| --- | --- | --- |
| **Unique tasks** | 18 | 10 Exercism Python (X) + 8 real-developer refactors (D) |
| **Routes tested** | 5 | R6 mini-swe-agent · R7 aider · R8 opencode · R9 claude-code · R10 cline |
| **Strategies** | 8 | always-cloud · always-local · rules · heuristic (agent-aware) · llm-classifier · embedding-knn · cascade · cascade-tuned |
| **Seeds** | 3 | 42, 7, 13 (for bootstrap CIs) |
| **Local models** | 3 | gemma4:31b (baseline) · qwen3-coder:30b · qwen2.5-coder:32b |
| **Time estimate** | 14–22 h | on M4 Max + gemma4:31b local + gpt-5.5 cloud (per-model, wall clock) |
| **Cost estimate** | ~$30–60 | OpenAI API per local model swept |

The v1.4 canonical baseline uses:

- **Local model**: `gemma4:31b` (≈19 GB) — dense generalist, the v1.3.0 winner
- **Cloud model**: `gpt-5.5`
- **Judge model**: `claude-opus-4-7` (for prose-scored rows where applicable)
- **Router classifier**: `qwen3:0.6b` (used by the `llm-classifier` and `cascade` strategies)
- **Infrastructure**: M4 Max (12 perf cores, 64 GB RAM), Docker, Ollama

---

## 2. Prerequisites

### Hardware

| | Minimum | Recommended |
| --- | --- | --- |
| **CPU** | Apple M1 or Linux x86_64 | Apple M4 Max (12 perf cores) |
| **RAM** | 32 GB | 64 GB |
| **Disk** | 80 GB free | 120 GB (Ollama models + Docker + venv) |
| **GPU** | none required | Metal (macOS) or CUDA (Linux) optional |

**Platform notes:**

- **macOS + Apple Silicon** (M1–M4): primary tested platform.
- **Linux x86_64**: fully supported. Docker images run natively.
- **Linux ARM64**: untested.
- **Windows**: not supported. WSL2 with Docker + Ollama may work but is untested.

### Software

- **macOS 14+** or **Linux x86_64** (Ubuntu 22.04 LTS recommended)
- **Python 3.11 or 3.12** — the orchestrator
- **Node 20+** — for the router proxy
- **Docker Desktop** (running) — required for the functional sandbox
- **Ollama 0.4+** — local model serving
- **Git** — for cloning

### API keys

- **OpenAI API key** (required): for cloud-routed turns and the `gpt-5.5` baseline
- **Anthropic API key** (optional): for the `claude-opus-4-7` judge on prose-scored rows

### Network access

- Downloads: Ollama models (~19 GB for gemma4:31b), Docker images (~5 GB)
- API calls: OpenAI (gpt-5.5) + optional Anthropic (claude-opus-4-7)

---

## 3. One-time setup

### 3.1 Clone the repo

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval.git
cd hybrid-coding-eval
git checkout v1.4.0          # the canonical tag for these numbers
```

### 3.2 Python environment

```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

`-e ".[dev]"` installs the package in editable mode plus the dev extras (ruff). All runtime dependencies (`pandas`, `httpx`, `pydantic`, `pyyaml`, `openai`, `anthropic`, …) are in `pyproject.toml` and mirrored in `requirements.txt`.

Verify the install:

```bash
.venv/bin/pytest tests/ -q -m 'not slow'
# Expected: all tests pass (Docker-slow tests are skipped here)
```

### 3.3 Install Ollama

**macOS**: download from <https://ollama.com/download>, launch `Ollama.app`.

**Linux**:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
```

Verify:

```bash
curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name'
```

### 3.4 One-shot setup

```bash
./bench setup
```

What it does, idempotently:

1. Builds the `hybrid-eval-python:latest` Docker sandbox image
2. Pulls auxiliary Ollama models: `qwen3:0.6b` (router `llm-classifier` / `cascade`), `nomic-embed-text` (router `embedding-knn`)
3. Installs `aider-chat` into `.venv/bin/aider` (R7 agent)
4. Optionally clones the opencode fork into `vendor/opencode/` if `BENCH_SETUP_OPENCODE=1`
5. Sanity-checks Python version, .env presence, Ollama/Docker on PATH

Re-run any time — already-completed steps are skipped.

### 3.5 Pull the canonical local model

```bash
ollama pull gemma4:31b           # ~19 GB; ~15 minutes on broadband
```

For multi-model sweeps:

```bash
ollama pull qwen3-coder:30b      # ~18 GB
ollama pull qwen2.5-coder:32b    # ~19 GB
```

### 3.6 Environment variables

Create `.env` at the repo root:

```bash
cat > .env <<'EOF'
OPEN_AI_API_KEY=sk-proj-your-openai-key-here

# Optional — required only for the claude-opus-4-7 judge on prose-scored rows
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
EOF
chmod 600 .env
```

The router auto-reads `.env` at startup (when spawned by `bench sweep`). Python readers use `os.environ`, so either export them or let your shell auto-load `.env`:

```bash
set -a && source .env && set +a
```

---

## 4. Smoke test (~5 minutes)

Before running the full sweep, validate the harness with a tiny smoke run:

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies heuristic --seeds 42 --smoke
```

Smoke = 1 task per category × 1 strategy. `bench sweep` will auto-spawn the router on :8787 with `LOCAL_MODEL=gemma4:31b`, run the pass, and tear the router down.

Verify success:

```bash
SWEEP=results/runs/v1.4-canonical/heuristic/seed-42
wc -l "$SWEEP/raw.jsonl"
# Expected: > 0 lines, one per (task, route) pair

jq -s '[.[] | select(.error != null)] | length' "$SWEEP/raw.jsonl"
# Expected: 0
```

If smoke fails, see [§13 Troubleshooting](#13-troubleshooting).

---

## 5. Full v1.4 canonical sweep

### 5.1 Single-model canonical (gemma4:31b)

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
```

- 4 strategies × 3 seeds = 12 passes
- Each pass writes to `results/runs/v1.4-canonical/<strategy>/seed-<seed>/raw.jsonl`
- Total: 18 tasks × 5 routes × 12 passes = 1,080 graded rows (subject to route applicability per category)
- Wall: ~14–22 h on M4 Max
- Cost: ~$30–60 OpenAI

Per-pass progress can be monitored:

```bash
watch -n 30 'find results/runs/v1.4-canonical -name raw.jsonl | xargs wc -l'
```

### 5.2 Multi-model sweep

Loop over local models by overriding `models.local`:

```bash
for MODEL in gemma4:31b qwen3-coder:30b qwen2.5-coder:32b; do
  ./bench sweep --config configs/v1.4-canonical.yaml \
    --set models.local="$MODEL" \
    --set out_dir="results/runs/v1.4-${MODEL//:/}" \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
done
```

### 5.3 Cascade-threshold sweep (optional)

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies cascade --cascade-thresholds 5,10,15,20,25 --seeds 42,7,13
```

Each threshold gets its own router spawn with `ROUTER_CASCADE_THRESHOLD=<N>`. Layout: `results/runs/v1.4-canonical/cascade-threshold-<N>/seed-<S>/`.

---

## 6. Resume a crashed sweep

Per-pass orchestration is crash-resumable. If a pass crashes partway, re-run the same `bench sweep` command — completed `(task_id, route)` pairs in `raw.jsonl` are skipped automatically by `core.experiment.pair_already_done`. Pairs with `error != null` are also skipped — manually delete the row first if you want to retry.

---

## 7. Subset sweeps (optional)

### 7.1 Single strategy

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies heuristic --seeds 42
```

### 7.2 Single category

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --set benchmark.categories='[D]' \
  --strategies heuristic --seeds 42
```

### 7.3 Single task

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --set 'benchmark.task_ids=[real-dev/d1-rate-limit]' \
  --strategies heuristic --seeds 42
```

### 7.4 Dry run (plan only)

```bash
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies heuristic --seeds 42 --dry-run
```

---

## 8. Post-sweep: re-scoring, analysis, reports

### 8.1 Re-judge prose-scored rows

```bash
./bench rejudge results/runs/v1.4-canonical/
```

### 8.2 Aggregate, bootstrap CIs, decision matrix, charts

```bash
./bench analyze results/runs/v1.4-canonical/
```

Produces, under each per-cell subdirectory and at the top level:

- `aggregate.json` — per-(category, route, strategy) means/medians/sums
- `bootstrap_cis.json` — **the headline statistics** — 95% percentile CIs for `pass_rate`, `cost_usd`, `cloud_fraction`, `wall_ms` per cell
- `decision_matrix.md` — category × route quality/cost grid
- `charts/pareto.png`, `heatmap_quality.png`, `heatmap_cost.png`

### 8.3 Token budget (6-scenario re-pricing)

```bash
./bench token-budget results/runs/v1.4-canonical/
```

Re-prices the sweep under all 6 pricing scenarios without re-running inference.

---

## 9. How to read the results — cell → headline number

Every published number in this repo's release notes traces back to a specific cell in `bootstrap_cis.json`. The cell key shape is:

```
"<category>::<route>::<strategy>"
```

For example, the headline preview number in the README (`gemma4:31b + heuristic = 96% pass-rate [88, 100]` on real-developer D-tasks) is the pass-rate point estimate and 95% CI of cell `refactors::aider::heuristic` (the v1.4 task-class names) in:

```bash
results/runs/v1.4-canonical/heuristic/seed-42/bootstrap_cis.json
```

To extract it:

```bash
# Point estimate
jq '.cells["refactors::aider::heuristic"]["pass_rate"]["point"]' \
  results/runs/v1.4-canonical/heuristic/seed-42/bootstrap_cis.json
# → 0.96

# Lower 95% bound
jq '.cells["refactors::aider::heuristic"]["pass_rate"]["lo"]' \
  results/runs/v1.4-canonical/heuristic/seed-42/bootstrap_cis.json
# → 0.88

# Upper 95% bound
jq '.cells["refactors::aider::heuristic"]["pass_rate"]["hi"]' \
  results/runs/v1.4-canonical/heuristic/seed-42/bootstrap_cis.json
# → 1.00
```

The same shape holds for the other metrics: `cost_usd`, `cloud_fraction`, `wall_ms`. Each one has `point`, `lo`, `hi`, and `n` keys.

### v1.4 cell-naming reference

v1.4 renamed the task classes for clarity:

| v1.4 name | Prior name (v1.0–v1.3) | What it is |
|---|---|---|
| `puzzles` | `X` (Exercism Python) | Small functional algorithmic tasks |
| `refactors` | `D` (real-developer D1+D5) | Practical refactoring patterns from real PRs |

Route names use the agent's CLI name (no `R6`/`R7`/etc. prefixes in cell keys): `mini-swe-agent`, `aider`, `opencode`, `claude-code`, `cline`.

### Pareto-frontier check

To check whether `heuristic` is on the Pareto frontier vs `always-cloud` on refactors:

```bash
JF=results/runs/v1.4-canonical/heuristic/seed-42/bootstrap_cis.json
JC=results/runs/v1.4-canonical/always-cloud/seed-42/bootstrap_cis.json

jq '.cells["refactors::aider::heuristic"]["pass_rate"]' "$JF"
jq '.cells["refactors::aider::always-cloud"]["pass_rate"]' "$JC"
# Compare lo/hi: if the heuristic CI overlaps the always-cloud CI AND
# heuristic's mean cost_usd is lower, hybrid is on the Pareto frontier.
```

For aggregated stats across seeds, run `./bench analyze results/runs/v1.4-canonical/` (without the strategy subdir) — it stratifies by seed automatically and combines into single per-cell CIs.

---

## 10. Reproducing the article numbers exactly

To match the numbers in [`release-notes/v1.4.0.md`](./release-notes/v1.4.0.md):

```bash
git checkout v1.4.0
./bench sweep --config configs/v1.4-canonical.yaml \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-canonical/
```

Same hardware + same models + same seeds + same pricing → identical token counts, identical costs, identical functional pass/fail. Judge scores are deterministic at `temperature=0.0`. Latencies vary with system load and network.

Cross-check your output against the published dataset:

```bash
gh release download v1.4.0 -p results-v1.4.0.tar.gz
tar xzf results-v1.4.0.tar.gz -C /tmp/v1.4-baseline/
diff <(jq -S '.cells' results/runs/v1.4-canonical/heuristic/seed-42/bootstrap_cis.json) \
     <(jq -S '.cells' /tmp/v1.4-baseline/.../bootstrap_cis.json)
```

---

## 11. Drop in a new local model

```bash
ollama pull <new-model>
./bench sweep --config configs/v1.4-canonical.yaml \
  --set models.local=<new-model> \
  --set out_dir=results/runs/v1.4-<new-model> \
  --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-<new-model>/
```

Full walkthrough: [`BENCHMARK_NEW_MODEL.md`](./BENCHMARK_NEW_MODEL.md).

---

## 12. Cost breakdown (v1.4 canonical, single local model)

> Numbers TBD after the v1.4.0 canonical sweep lands. v1.3.0's per-sweep cost for gemma4:31b on 18 tasks × 4 strategies × 3 seeds was ≈$9–10 in OpenAI API spend; v1.4 will be in the same range for the canonical strategies and modestly higher if all 8 strategies are run.

The token counts persist in `raw.jsonl`; re-price under any of the 6 scenarios via `./bench token-budget`. The cost ranking is invariant across all six scenarios (we expect): cheap-cloud (gpt-5-mini, haiku-4.5) < always-local < hybrid < always-cloud (opus-4.7).

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `curl http://127.0.0.1:8787/healthz` → `Connection refused` during a sweep | A previous sweep crashed without cleaning up; the auto-spawned router process is gone. | Just re-run `./bench sweep` — it spawns a fresh router. The `--external-router` flag lets you opt out of auto-spawn. |
| `router spawn failed: never healthy on :8787` | Port already in use by something else. | `lsof -ti :8787 \| xargs kill` then re-run. |
| `healthz` says `cloud.key_present=false` | `.env` missing or wrong var name. | Confirm `.env` has `OPEN_AI_API_KEY=sk-...` (not `OPENAI_API_KEY`). Re-run the sweep. |
| `docker: permission denied` (Linux) | User not in `docker` group. | `sudo usermod -aG docker $USER && newgrp docker` |
| `docker: ...permission denied` (macOS) | Docker Desktop not running. | Launch Docker Desktop. |
| Local model OOMs or is very slow | gemma4:31b doesn't fit in available RAM/VRAM. | Try a smaller model (e.g. `ollama pull gemma4:9b`) or reduce `num_ctx` in your Modelfile. |
| `ANTHROPIC_API_KEY not set` (warning only) | Opus judge is optional. | Expected if you skip the judge. Rows have `judge_win_rate=null`. |
| `"error": "..."` in `raw.jsonl` | Per-task infra failure (Docker, API rate-limit, timeout). | Read the row's `error` field. Re-run the sweep with the same command — completed pairs are skipped. |
| Pytest `test_r*` times out | Subprocess test needs the router proxy. | Start router; tests auto-skip cleanly if router is down. |
| Sweep hangs on a single task | Long task or upstream API hang. | `Ctrl-C`, then re-run with the same command. |

---

## 14. Verifying a clean run

After a full sweep:

```bash
SWEEP=results/runs/v1.4-canonical

# (a) Per-cell row counts
find "$SWEEP" -name raw.jsonl -exec wc -l {} +

# (b) No errors
find "$SWEEP" -name raw.jsonl -exec jq -s 'map(select(.error != null)) | length' {} \;
# Expected: 0 per file

# (c) always-local has zero cloud tokens (routing bug if non-zero)
find "$SWEEP/always-local" -name raw.jsonl -exec \
  jq 'select((.tokens.cloud_prompt + .tokens.cloud_completion) > 0)' {} \;
# Expected: empty

# (d) always-cloud has positive cloud tokens
find "$SWEEP/always-cloud" -name raw.jsonl -exec \
  jq 'select((.tokens.cloud_prompt + .tokens.cloud_completion) == 0)' {} \;
# Expected: empty

# (e) Repo tests pass
.venv/bin/pytest tests/ -q -m 'not slow'
```

---

## 15. Data redistribution and licensing

**Results** (raw.jsonl, charts, decision matrix, release notes) are licensed under **CC-BY-4.0**. You may republish and cite; please include attribution.

**Code** (harness, router, agents, scorers, analysis) is **MIT-licensed**.

Suggested citation:

> Monga, Sanchit and contributors. *hybrid-coding-eval: reproducible cost/latency/quality benchmark for local vs cloud vs hybrid LLM routing on coding tasks.* 2026. <https://github.com/RunanywhereAI/hybrid-coding-eval>. Tag `v1.4.0`.

---

## 16. See also

- [`./METHODOLOGY.md`](./METHODOLOGY.md) — scoring rubrics + biases acknowledged
- [`./BENCHMARK_NEW_MODEL.md`](./BENCHMARK_NEW_MODEL.md) — drop-in walkthrough for a new local model
- [`./ARCHITECTURE.md`](./ARCHITECTURE.md) — code layout + data flow
- [`./ROUTING_STRATEGIES.md`](./ROUTING_STRATEGIES.md) — deep dive on the 8 router strategies
- [`./AGENTIC_ROUTES.md`](./AGENTIC_ROUTES.md) — R6..R10 design + correlation-id attribution
- [`./release-notes/v1.4.0.md`](./release-notes/v1.4.0.md) — v1.4.0 canonical findings

Questions or reproducibility issues? File an issue: <https://github.com/RunanywhereAI/hybrid-coding-eval/issues>
