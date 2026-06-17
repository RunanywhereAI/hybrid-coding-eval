---
name: Reproducibility issue
about: "I can't reproduce the published numbers" — divergence from the canonical dataset
title: "[repro] "
labels: ["reproducibility"]
---

## Which result are you trying to reproduce?

<!-- Link the specific row or aggregate. Examples:
  - `results/runs/07-v3-devstral-all-routes/raw.jsonl` row `(task_id=..., route=R3)`
  - `reports/...` decision-table cell
  - article headline (e.g. "R5 0/4 on D3")
-->

## Your environment

- OS + version:
- Hardware (chip, RAM):
- Python version:
- Node version:
- Ollama version + local model tag:
- Docker version + functional-scoring image SHA (`docker image inspect hybrid-eval-python:latest --format '{{.Id}}'`):
- Repo commit + tag:

Attach your `env-manifest.json` — produced by `./arena env-detect` or auto-written into your sweep's output directory. It captures all of the above in one file.

## What you observed

```text
<paste the row(s) from your raw.jsonl that disagree with the canonical dataset>
```

## What the canonical dataset says

```text
<paste the corresponding row(s) from results/runs/.../raw.jsonl>
```

## Diff that matters

- Which field disagrees? (`tokens.cloud_prompt`, `quality.functional_pass`, `quality.composite`, `cost_usd`, `latency.wall_ms`, …)
- How much does it differ?

For wall-clock latency, drift is expected and not a reproducibility bug. For token counts and `quality.functional_pass`, bit-identical reproduction is the goal — any difference is worth investigating.

## What you've already checked

- [ ] Same git commit (`git rev-parse HEAD` matches the canonical run's `git_sha`)
- [ ] Same router strategy (`router.strategy` in the variant config)
- [ ] Same seed (`benchmark.seeds`)
- [ ] Pricing table unchanged since the canonical run
- [ ] Ollama model SHA matches (tags can shift; check `ollama show <tag>`)
