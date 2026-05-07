# Drop in a new model — 5-step walkthrough

_You have a new cloud or local model you want to benchmark against
the four routes (R1 / R2 / R3 / R4) in this repo. Here's how to do
it without editing any Python._

## Prerequisites

1. Repo cloned and `pip install -e .` done (see `docs/REPRODUCING.md`).
2. Router running: `./router/start.sh` in its own terminal.
3. `.env` has `OPEN_AI_API_KEY` (or `OPENAI_API_KEY`); optionally
   `ANTHROPIC_API_KEY` for Opus judge.
4. If you're plugging in a local model: it's pulled into Ollama
   (``ollama pull <your-tag>``).

## Step 1 — copy the template

```bash
cp configs/variants/_template.yaml configs/variants/my-model.yaml
```

## Step 2 — edit two required lines

```yaml
variant_tag: my-cool-experiment          # goes into every ResultRow.variant
out_dir: results/runs/99-my-cool-experiment

models:
  cloud: gpt-5                           # ← your new cloud model, or keep gpt-5.5
  local: llama-3.2:8b                    # ← your new local model (Ollama tag)
```

All other fields have MVP-matching defaults. Override anything else
you like — see `configs/variants/_template.yaml` for the full set of
knobs (router strategy, seeds, pricing scenarios, smoke mode, …).

## Step 3 — sanity-check the config

```bash
./bench show-config --config configs/variants/my-model.yaml
```

This prints the merged config as JSON plus a `sha256` hash. The hash
is stable — same YAML always produces the same hash — and will be
written into every ResultRow's `config_sha` field.

## Step 4 — dry-run the plan

```bash
./bench run --config configs/variants/my-model.yaml --dry-run
```

Prints the 10 × 3 × 4 = 120 (task, route) pairs that would be
executed, but doesn't actually call any API.

## Step 5 — run and analyse

```bash
# full sweep (~4–5 h on M4 Max, ~$15 API on gpt-5.5)
./bench run --config configs/variants/my-model.yaml

# or smoke test first (1 task per category × all routes, ~30 min, ~$0.50)
./bench run --config configs/variants/my-model.yaml --smoke

# analysis
./bench analyze results/runs/99-my-cool-experiment/
./bench rescore  results/runs/99-my-cool-experiment/    # SWE-bench rescore
./bench rejudge  results/runs/99-my-cool-experiment/    # Opus judge for custom_arch

# add your variant to the multi-scenario matrix
.venv/bin/python -m hybrid_coding_eval.analysis.decision_matrix_v2
.venv/bin/python -m hybrid_coding_eval.analysis.reprice
.venv/bin/python -m hybrid_coding_eval.analysis.token_share
./bench report appendix-tasks    # regenerates reports/APPENDIX_TASKS.md with your rows
```

## What about pricing?

If your new cloud model isn't already in
`configs/pricing/pricing_tables.json`, add it:

```json
{
  "rates_per_m": {
    "my-new-model": { "input": 2.0, "output": 8.0, "cache_read": 0.2 }
  }
}
```

Then register it as a scenario in
`src/hybrid_coding_eval/core/results.py::PRICING_SCENARIOS` (a one-line
dict entry: `"my-scenario": "my-new-model"`). Re-run
`.venv/bin/python -m hybrid_coding_eval.analysis.reprice` and the new
column appears in `results/reprice/cost_by_scenario.csv`.

## Override from the CLI instead of editing YAML

```bash
./bench run \
  --config configs/variants/_template.yaml \
  --set variant_tag=my-quick-test \
  --set out_dir=results/runs/98-my-quick-test \
  --set models.cloud=gpt-5 \
  --set models.local=llama-3.2:8b \
  --smoke
```

## Common issues

- **Router 502 / Ollama 404**: your local model tag isn't pulled.
  `ollama list` to check; `ollama pull <tag>` if missing.
- **401 on Anthropic**: `ANTHROPIC_API_KEY` not set, only the Opus
  judge path uses it. Set it only if you're running C-category with
  custom_arch judging.
- **Docker sandbox not available**: set `scoring.skip: true` in the
  YAML to skip inline scoring; you can run `./bench rescore ...`
  later when Docker is up.
- **Schema validation error**: `./bench schema --out /dev/null` then
  diff against `configs/schema.json` to see what the Pydantic model
  expects.

## Reading the results

After your sweep completes:

- `results/runs/99-.../raw.jsonl` — one row per `(task, route)` cell.
- `results/runs/99-.../outputs/` — verbatim model outputs.
- `results/runs/99-.../run-notes.md` — human-readable summary (write
  this yourself).
- `results/runs/99-.../bench-config.json` — the resolved config that
  produced this run (SHA-stamped).

For the article-shaped view, look at:

- `reports/APPENDIX_TASKS.md` — includes every `(task_id, route, variant)`
  tuple in the committed dataset.
- `results/reprice/decision_matrix.md` — your new variant appears in
  the per-scenario grid.
