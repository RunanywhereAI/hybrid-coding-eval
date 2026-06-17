# Reproducing the results

Every published number in this repo traces back to one row in a
`results/runs/<sweep>/.../raw.jsonl`, and cost is derived from token counts ×
a pinned price table. This guide takes you from a clean clone to your own
green charts, then to comparing them against the canonical dataset.

> **Time + cost budget.** Smoke run: ~30 s, ~$0.01. Full canonical sweep on an
> M4 Max 64 GB: ~10–15 h wall, ~$30–50 cloud at frontier pricing, plus an ~18 GB
> local-model download. Always do the smoke run first — it's a green checkpoint
> before you commit to the long sweep.

---

## 1. Prerequisites

| Tool | Why | macOS | Linux |
| --- | --- | --- | --- |
| **Python 3.11 or 3.12** | Harness + agent runners | `brew install python@3.12` | `sudo apt install python3.12 python3.12-venv` |
| **git** | Clone | built-in | `sudo apt install git` |
| **Docker** | Sandbox for the functional Python scorer | [Docker Desktop](https://www.docker.com/products/docker-desktop) | `sudo apt install docker.io` (+ add user to `docker` group) |
| **Node ≥ 18** | Router proxy (`router/server.mjs`) | `brew install node` | `sudo apt install nodejs npm` |
| **Ollama** | Serves the local model on `:11434` | [ollama.com/download](https://ollama.com/download) | `curl -fsSL https://ollama.com/install.sh \| sh` |
| **An OpenAI API key** | The cloud half of every hybrid call | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | same |

The smoke run only needs Python + Docker + an API key. Node, Ollama, and a
pulled local model are needed once you run a real hybrid sweep.

---

## 2. Clone, install, configure

```bash
git clone https://github.com/RunanywhereAI/hybrid-arena
cd hybrid-arena

python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev,agents]"

cp .env.example .env
# edit .env and paste your OPEN_AI_API_KEY (either OPENAI_API_KEY or
# OPEN_AI_API_KEY spelling is accepted)
```

To pin to a specific release for an exact replication:

```bash
git checkout v1.5.1     # or v1.5.0 / v1.4.1 — matches that release's dataset
```

---

## 3. One-time setup

```bash
./arena setup
```

Idempotent — safe to re-run. It builds the functional-scoring Docker image
(`hybrid-eval-python:latest`), installs the `cline` / `opencode` CLIs via npm
if missing, clones the `opencode` fork into `vendor/` (opt-in via
`BENCH_SETUP_OPENCODE=1`), and runs a health check.

---

## 4. Smoke test (cloud-only, ~30 s)

No local model required — this proves the harness is wired up correctly.

```bash
./arena sweep --config configs/v1.4-smoke.yaml --strategies always-cloud --seeds 42
./arena analyze results/runs/v1.4-smoke
```

If `arena analyze` writes a `bootstrap_cis.json` and a chart, you're good.

---

## 5. A real hybrid sweep

Pull a local model, then run the canonical 4-strategy matrix:

```bash
ollama pull gemma4:31b                                # ~18 GB
./arena sweep \
    --config configs/v1.4-canonical-gemma4.yaml \
    --strategies always-cloud,always-local,heuristic,cascade \
    --seeds 42,7,13
./arena analyze results/runs/v1.4-canonical-gemma4
```

Other canonical configs (same matrix, different local model):

| Config | Local model |
| --- | --- |
| `configs/v1.4-canonical-gemma4.yaml` | gemma4:31b (dense generalist) |
| `configs/v1.4-canonical-qwen3-coder.yaml` | qwen3-coder:30b (MoE specialist) |
| `configs/v1.4-canonical-qwen3.6.yaml` | qwen3.6:35b (dense — the champion) |
| `configs/v1.5-hard-qwen3.6.yaml` | qwen3.6 on the D6 *hard* task class |
| `configs/v1.5-hard-gemma4.yaml` | gemma4 on the D6 *hard* task class |

---

## 6. Long / overnight sweeps (pause + resume)

The orchestrator is crash-resumable — `raw.jsonl` is append-only, so a crash
loses at most one row.

```bash
./arena start  --config configs/v1.4-canonical-qwen3.6.yaml \
               --strategies always-cloud,always-local,heuristic,cascade \
               --seeds 42,7,13          # detaches, returns immediately
./arena status                           # PID + row count + RUNNING/PAUSED
./arena pause                            # frees the laptop, keeps Ollama warm
./arena resume                           # picks up at the next un-written row
./arena stop                             # also kills Ollama (~19 GB freed)
```

State lives at `/tmp/hcev-sweep.json` and survives reboots until `--clear-state`.

---

## 7. Check your numbers against the canonical dataset

```bash
# Your headline cell:
jq '.cells["refactors::cline::cascade"].pass_rate' \
   results/runs/<your-sweep>/bootstrap_cis.json

# The published dataset to compare against:
gh release download v1.5.1 -p results-v1.5.1.tar.gz   # identical bytes to v1.5.0
tar xzf results-v1.5.1.tar.gz
```

Reference points on the `refactors::*::heuristic` cell from the canonical sweeps:
**96%** (qwen3.6), **92%** (qwen3-coder), **96%** (gemma4, error-adjusted).

---

## 8. Benchmark a brand-new local model (three commands)

```bash
ollama pull <new-model>
./arena sweep --config configs/v1.4-canonical-gemma4.yaml \
    --set models.local=<new-model> \
    --set out_dir=results/runs/v1.4-<new-model> \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./arena analyze results/runs/v1.4-<new-model>
```

`--set key.path=value` overrides any config field for a one-shot run without
editing the YAML.

---

## 9. Re-pricing without re-running

Cost is never stored — it's derived. To see the whole dataset under a different
model's pricing, just re-analyze:

```bash
./arena token-budget results/runs/<your-sweep>   # token-first matrix, all scenarios
```

Pricing lives in `configs/pricing/pricing_tables.json` (SHA256-pinned, shared by
the Python harness and the Node router; `tests/test_pricing_parity.py` asserts
they compute identical costs).

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `arena analyze` import errors on a fresh clone | Ensure you installed with `.[dev]` (matplotlib/numpy are runtime deps). |
| Router won't start | Check `.env` has a valid key; the router binds `127.0.0.1:8787` only. Health: `curl -s 127.0.0.1:8787/healthz`. |
| Local calls hang or stream forever | The v1.4.1 guards cap local calls at 4096 `num_predict` / 180 s. Override via `ROUTER_LOCAL_*` env vars if benchmarking an unusual model. |
| Docker scorer skipped | Functional tests `skip` cleanly if Docker is unavailable; install/start Docker to score puzzles + refactors. |

Found a number that doesn't reproduce? That's a bug worth filing — open an issue
with your `env-manifest.json` (`./arena env-detect`) attached.
