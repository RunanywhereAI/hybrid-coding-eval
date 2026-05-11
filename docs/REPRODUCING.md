# Reproducing the hybrid-coding-eval experiment

Copy-paste instructions for running the benchmark on a fresh machine. Every
command below has been executed verbatim from a clean checkout — if one
fails, the fix is in [§9 Troubleshooting](#9-troubleshooting).

See [`METHODOLOGY.md`](./METHODOLOGY.md) for *why* we chose these tasks,
routes, and scoring pipelines. This document is the *how*.

> **Note (2026-05-11).** This document was written for the MVP (3 routes
> R1-R3, categories A/B/C, 90 rows). The v3 sweep introduced R4, R5, and
> category D — see [`configs/variants/07-v3-devstral-all-routes.yaml`](../configs/variants/07-v3-devstral-all-routes.yaml)
> for the canonical 5-route config and [`reports/FINAL_V3_REPORT.md`](../reports/FINAL_V3_REPORT.md)
> for the current methodology. The reproduction steps below remain valid
> for the MVP; the only commands that changed are the orchestrator
> invocations (`./bench run …` replaces the old `bin/run-experiment.py`).

---

## 1. What this covers + prerequisites

The experiment runs three routing strategies across three task categories
(30 tasks total, one row per task × route = **90 rows**):

| | Source | What it measures |
|---|---|---|
| **Category A** | HumanEval+ (10) | tiny single-function completion |
| **Category B** | SWE-bench Verified (10) | repo-level agentic patches |
| **Category C** | BigCodeBench-Hard (5) + custom-arch (5) | hard functional + architectural judgement |
| **R1** | cloud-only (`gpt-5.5`) | quality ceiling / cost ceiling |
| **R2** | local-only (`qwen3.6:27b-coding-mxfp8`) | zero-cost / latency floor |
| **R3** | hybrid architect | local planner + targeted cloud calls |

### Hardware

| | Minimum | Recommended |
|---|---|---|
| **CPU/GPU** | M-series Mac OR Linux + Docker | M3/M4 Max / Ultra, 12+ perf cores |
| **RAM** | 32 GB | 64 GB |
| **Disk** | ~50 GB free (SWE-bench Docker images) | 100 GB |
| **GPU** | not required | NVIDIA optional; Ollama will use Metal/CUDA |

### Software

- **macOS 14+** or **Linux x86_64** / **Linux ARM64**
- **Docker Desktop** (running) — required for the functional sandbox and SWE-bench harness
- **Node 20+** — for the router proxy
- **Python 3.11 or 3.12** — the orchestrator
- **Ollama 0.4+** — local model serving
- Network access: required for Ollama model downloads, cloud API calls, and SWE-bench Docker image pulls

### API keys

Put these in a `.env` at the repo root:

```dotenv
# Required for R1 (cloud) and R3 (hybrid) routes
OPEN_AI_API_KEY=sk-...
# or OPENAI_API_KEY=sk-...  (both names accepted)

# Required only for LLM-judge scoring of Category C custom-arch tasks.
# Optional — if unset, judge tests skip cleanly; functional scoring is unaffected.
ANTHROPIC_API_KEY=sk-ant-...
```

### Time + budget (full 90-row sweep)

| | wall time | API $ |
|---|---|---|
| **Compute** | 2–4 h on M4 Max, longer on M1/M2 | — |
| **OpenAI** (R1 + R3) | — | ~$30–80 |
| **Anthropic** (LLM-judge on 5 Category C rows × 3 routes) | — | ~$5 |

---

## 2. Quick start (60-second smoke test)

From a cleanly-cloned repo with Docker running and Ollama installed:

```bash
# 1. Python env (one-time)
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

# 2. Pull the local model (one-time, ~27 GB, 10–30 min)
ollama pull qwen3.6:27b-coding-mxfp8
ollama pull qwen3:0.6b

# 3. Build the Python sandbox image (one-time, ~1 min)
docker build -f scorers/Dockerfile.functional_python -t hybrid-eval-python:latest .

# 4. Put your API key in .env
echo 'OPEN_AI_API_KEY=sk-...' > .env

# 5. Start the router (foreground; leave in its own terminal)
(cd router && ./start.sh) &

# 6. Sanity check
curl -s http://127.0.0.1:8787/healthz | jq .

# 7. Run a 9-row smoke (1 task × 3 categories × 3 routes, ~30 min)
./bench run --config configs/variants/_template.yaml --smoke

# 8. Analyse
./bench analyze results/runs/<variant_tag>/
```

---

## 3. Full setup (step-by-step)

### 3.1 Clone

```bash
git clone <repo-url> hybrid-coding-eval
cd hybrid-coding-eval
```

### 3.2 Install Ollama

macOS: download from <https://ollama.com/download> and launch `Ollama.app`.
Linux:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama   # or `ollama serve &`
```

Verify:

```bash
curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name'
```

### 3.3 Pull the local model

```bash
ollama pull qwen3.6:27b-coding-mxfp8   # ~27 GB, 10–30 min on a 1 Gbit link
ollama pull qwen3:0.6b                 # ~520 MB, used by the router's LLM-classifier strategy
```

Optional (only if you want to exercise the embedding-kNN router strategy):

```bash
ollama pull nomic-embed-text
```

### 3.4 Python virtual environment

```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

Smoke-test that the package installed and tests import:

```bash
.venv/bin/pytest tests/test_pricing_parity.py -q
```

### 3.5 Build the functional-scorer Docker image

```bash
docker build -f scorers/Dockerfile.functional_python -t hybrid-eval-python:latest .
```

This is a lightweight `python:3.12-slim` image with `pytest`. All generated
Python code is executed inside it with `--network none`, memory caps, and a
wall-clock timeout — the host never sees model output directly.

### 3.6 API keys

```bash
cat > .env <<'EOF'
OPEN_AI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
EOF
chmod 600 .env
```

The router reads `../.env` automatically via `router/start.sh`. Python
readers use `os.environ`, so either export the variables in your shell or
have your shell auto-load `.env` (most recent shells do not by default).

```bash
set -a && source .env && set +a   # makes .env visible to python
```

### 3.7 Start the router proxy

In its own terminal:

```bash
cd router && ./start.sh
```

or detached:

```bash
cd router && nohup ./start.sh > /tmp/router.log 2>&1 &
```

The proxy exposes an OpenAI-compatible API on `http://127.0.0.1:8787`. It
reads the same `.env` the python orchestrator does.

### 3.8 Verify the proxy + record the environment

```bash
curl -s http://127.0.0.1:8787/healthz | jq .
# Expected: local.reachable=true, cloud.reachable=true, cloud.key_present=true

.venv/bin/python bin/env-detect.py --out env-manifest.json
jq '.cpu, .memory_gb, .python_version, .ollama.version' env-manifest.json
```

`env-manifest.json` is the provenance record every sweep row links to via
`hardware_profile_ref`.

---

## 4. Running the experiment

The orchestrator is `./bench run`. All flags:

```bash
./bench run --help
```

### 4.1 Smoke test (9 rows, ~30 min)

```bash
./bench run --config configs/variants/_template.yaml --smoke
```

One task per category × three routes. Output lands in
`results/runs/<variant_tag>/`.

### 4.2 Full sweep (90 rows, ~2–4 h)

```bash
./bench run --config configs/variants/_template.yaml
```

Each row is flushed to `raw.jsonl` as soon as it completes — you can tail
progress:

```bash
tail -f results/full-*/progress.log
wc -l results/full-*/raw.jsonl
```

### 4.3 Resume a crashed sweep

```bash
./bench run --config configs/variants/_template.yaml --resume
```

Already-completed `(task_id, route)` pairs are skipped.

### 4.4 Subset a sweep

```bash
# Override variant fields on the CLI rather than editing the YAML
./bench run --config configs/variants/_template.yaml --set routes='[R1,R2]' --set categories='[A,B]'

# Smoke mode caps each category to 1 task
./bench run --config configs/variants/_template.yaml --smoke

# See the plan without executing
./bench run --config configs/variants/_template.yaml --dry-run
```

---

## 5. Scoring

**Scoring runs inline by default.** Each row in `raw.jsonl` already has its
`quality` block populated when the orchestrator finishes.

If you ran with `--skip-scoring` (useful for separating long inference runs
from a flaky Docker daemon), re-score afterwards with a small wrapper:

```python
# scripts/rescore.py
import json, pathlib, sys
from scorers.functional_python import score as score_fn
from scorers.swebench import score as score_swe
from benchmark.humaneval_plus.adapter import load_tasks as hep
from benchmark.bigcodebench_hard.adapter import load_tasks as bch
from benchmark.swebench_verified.adapter import load_tasks as swe

tasks = {}
for t in hep(n=10): tasks[t.task_id] = ("humaneval_plus", t)
for t in bch(n=5):  tasks[t.task_id] = ("bigcodebench_hard", t)
for t in swe(n=10): tasks[t.task_id] = ("swebench_verified", t)

src = pathlib.Path(sys.argv[1]) / "raw.jsonl"
rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
for r in rows:
    src_name, task = tasks[r["task_id"]]
    out = (pathlib.Path(sys.argv[1]) / "outputs" / f"{r['task_id']}-{r['route']}.txt").read_text()
    q = score_swe(task, out) if src_name == "swebench_verified" else score_fn(task, out)
    r["quality"] = q.__dict__
src.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
```

Run it: `.venv/bin/python scripts/rescore.py results/full-20260505`.

---

## 6. Analysis

One command runs aggregate → ARQGC → decision matrix → charts:

```bash
.venv/bin/python -m analysis.all results/full-20260505/
```

Produces, inside that directory:

| File | Contents |
|---|---|
| `aggregate.json` | per-(category, route) means, medians, totals |
| `arqgc.json` | bounded area-under-quality-cost curve per route |
| `decision_matrix.md` | the human-readable table (see §7) |
| `charts/pareto.png` | cost vs quality scatter (Pareto frontier) |
| `charts/heatmap_quality.png` | category × route quality grid |
| `charts/heatmap_cost.png` | category × route cost grid |
| `charts/heatmap_arqgc.png` | category × route ARQGC grid |

Re-price under different scenarios without re-running inference:

```bash
.venv/bin/python -m analysis.all results/full-20260505/ \
  --scenarios openai-gpt5.5,openai-gpt5-mini,anthropic-claude-opus-4.7
```

---

## 7. Reading the results

### `decision_matrix.md`

A trimmed example (`results/full-sweep/decision_matrix.md` from a real run):

```
## Quality × cost × wall time

| Category | R1 quality      | R2 quality      | R3 quality      | R1 cost (Σ)         | R2 cost (Σ) | R3 cost (Σ)         |
|----------|-----------------|-----------------|-----------------|---------------------|-------------|---------------------|
| A        | 1.00 (μ 1.00)   | 1.00 (μ 1.00)   | 1.00 (μ 0.67)   | $0.0125 (Σ $0.0505) | $0.0000     | $0.0565 (Σ $0.1438) |

## Bounded-ARQGC — area under quality-cost curve

| Category | R1    | R2    | R3    | Recommended |
|----------|-------|-------|-------|-------------|
| A        | 0.699 | 0.000 | 0.691 | R1          |
```

- **Quality** is the composite score (`0`–`1`) produced by the row's scorer:
  `functional_pass` for HumanEval+ / BigCodeBench-Hard / SWE-bench,
  `judge_win_rate` for custom-arch judged-by-LLM.
- **Cost** is priced under the default `openai-gpt5.5` scenario
  (`analysis/cost_scenarios.py`). R2 is always **exactly $0** because it
  never calls the cloud — this is the cheapest sanity check in §8.
- **ARQGC** is the **bounded** area-under-quality-cost curve: how much
  quality you get per dollar *up to a fixed budget* (p90 of R1's cost). A
  route with perfect quality but double the budget scores the same as the
  $0 local route if quality ≥ the bound. See `analysis/arqgc.py`.

### `charts/pareto.png`

X-axis: cost ($, log scale). Y-axis: composite quality. Pareto-efficient
points form the lower-right frontier. Dominated routes sit above it.

---

## 8. Verification — is your run clean?

Run all of these after a full sweep:

```bash
SWEEP=results/full-20260505

# (a) Row count — should be 90 for a full sweep, 9 for smoke, N*3 for --tasks N
wc -l "$SWEEP/raw.jsonl"

# (b) No more than ~5% of rows should have errors set
jq 'select(.error != null)' "$SWEEP/raw.jsonl" | jq -s 'length'

# (c) R1 under default pricing should always have positive cost
jq 'select(.route=="R1") | .cost_cents_default // .tokens' "$SWEEP/raw.jsonl" | head
jq 'select(.route=="R1" and .cost_usd_default <= 0)' "$SWEEP/raw.jsonl"   # expect empty

# (d) R2 should always cost exactly $0 (no cloud tokens)
jq 'select(.route=="R2" and (.tokens.cloud_prompt + .tokens.cloud_completion) > 0)' \
   "$SWEEP/raw.jsonl"   # expect empty

# (e) Repo tests still pass
.venv/bin/pytest tests/ -v -m 'not slow'
```

Any non-empty output from (c) or (d) indicates a routing bug — report an
issue with the offending row.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `curl http://127.0.0.1:8787/healthz` fails | `ollama serve` not running → `ollama list`. Router not running → `cd router && ./start.sh`. |
| `healthz` returns `cloud.key_present=false` | `.env` missing `OPEN_AI_API_KEY`. Re-source it before starting the router: `set -a && source .env && set +a && (cd router && ./start.sh)`. |
| Docker `permission denied` | user not in `docker` group (Linux) or Docker Desktop not running (macOS). |
| SWE-bench harness fails with `exec format error` on Apple Silicon | enable Rosetta in Docker Desktop settings; each SWE-bench instance takes ~10 min. |
| SWE-bench Docker pulls fill the disk | ~50 GB required. Prune unused images: `docker image prune -a`. |
| Local model OOM / very slow | lower `LOCAL_MODEL` to a smaller quant: `LOCAL_MODEL=qwen3.6:7b ./start.sh`, or set `num_ctx` lower via `~/.ollama/...`. |
| `ANTHROPIC_API_KEY not set` warnings | expected if you skipped the Anthropic key — LLM-judge scoring returns `null` and Category C judge tests skip cleanly. Functional scoring (A, B, bigcodebench) is unaffected. |
| `datasets` / `evalplus` import errors | you only need them to *refresh* the pinned `tasks.jsonl` files. The pinned ones are committed — `pip install -r requirements.txt` is already enough. |
| Sweep hangs on one task | Ctrl-C; rerun with `--resume`. |

---

## 10. Expected costs + timing

All numbers on an M4 Max, 64 GB, Ollama + Docker warm, under
`openai-gpt5.5` default pricing.

| Scope | Rows | Wall time | API $ (OpenAI) | API $ (Anthropic) |
|---|---|---|---|---|
| `--smoke` (1 × 3 cat × 3 route) | 9 | ~30 min | ~$0.50 | ~$0.10 |
| `--tasks 3` (3 × 3 cat × 3 route) | 27 | ~1–1.5 h | ~$8–15 | ~$1 |
| Full sweep (10+10+10 × 3 route) | 90 | ~2–4 h | ~$30–80 | ~$5 |

Largest single cost driver: R3 on SWE-bench (multi-turn architect +
cloud-tail, 5k–30k cloud tokens per task). Largest single time sink:
SWE-bench Docker harness evaluation (~10 min per instance on Apple Silicon
under Rosetta).

---

## See also

- [`METHODOLOGY.md`](./METHODOLOGY.md) — task selection, scoring rubrics, ARQGC definition
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — code layout
- [`ROUTING_STRATEGIES.md`](./ROUTING_STRATEGIES.md) — the seven router strategies (R3 uses the architect one)
