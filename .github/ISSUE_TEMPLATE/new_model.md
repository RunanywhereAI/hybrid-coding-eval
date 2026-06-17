---
name: New model request
about: Propose adding a new local or cloud model to the canonical benchmark
title: "[model] add <model-name>"
labels: ["model-request"]
---

## Model

- Name + tag (e.g. `qwen3-coder:30b`, `gpt-5-mini`):
- Provider (Ollama / OpenAI / Anthropic / other):
- Parameter count + quantization (if local):
- Public link to model card / API docs:
- License:

## Why this model

<!-- What gap does it fill? Cheaper than current cloud baseline? Bigger context? Code-specialized? New architecture (MoE, etc.)? -->

## Hardware fit (local models only)

- Approximate VRAM / unified-memory requirement:
- Tested on (your hardware):
- Expected vs other local models in the suite:

## Smoke-test evidence

If you've already tried it, please attach:

- The exact command you ran (typically `./arena sweep --config configs/v1.4-canonical-gemma4.yaml --set models.local=<model> --set out_dir=results/runs/<your-model>` with overrides)
- `progress.log` from the run's output directory
- Any errors hit

If not yet tested, that's fine — flag the model and the maintainer or another contributor can run the smoke sweep.

## Pricing (cloud models only)

For cloud-API models, please paste the current input/output token pricing and link to the official pricing page. New entries go in `configs/pricing/pricing_tables.json`.
