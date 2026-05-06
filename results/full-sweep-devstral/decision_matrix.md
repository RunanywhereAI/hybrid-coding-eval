# Decision matrix — category × route

_Generated from `results/full-sweep-devstral/raw.jsonl` — 60 rows, default pricing: **openai-gpt5.5**._

## Quality × cost × wall time

| Category | R2 quality | R3 quality | R2 cost | R3 cost | R2 wall | R3 wall |
|---|---|---|---|---|---|---|
| A | 1.00 (μ 0.90) | 1.00 (μ 1.00) | $0.0000 (Σ $0.0000) | $0.0362 (Σ $0.3548) | 10,716 ms | 46,332 ms |
| B | 0.00 (μ 0.00) | 0.00 (μ 0.30) | $0.0000 (Σ $0.0000) | $0.1439 (Σ $1.693) | 14,424 ms | 194,002 ms |
| C | 0.80 (μ 0.59) | 0.83 (μ 0.83) | $0.0000 (Σ $0.0000) | $0.3049 (Σ $3.139) | 34,223 ms | 254,274 ms |

## Bounded-ARQGC — area under quality-cost curve

| Category | R2 | R3 | Recommended |
|---|---|---|---|
| A | 0.900 | 1.000 | R3 |
| B | 0.000 | 0.300 | R3 |
| C | 0.297 | 0.413 | R3 |
| **all** | 0.399 | 0.571 | — |

## Alternative pricing scenarios — median cost per task

| Category/Route | openai-gpt5.5 | openai-gpt5 | openai-gpt5-mini | anthropic-claude-opus-4.7 | anthropic-claude-sonnet-4.6 |
|---|---|---|---|---|---|
| A/R2 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| A/R3 | $0.0362 | $0.0114 | $0.00227 | $0.0946 | $0.0189 |
| B/R2 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| B/R3 | $0.1439 | $0.0465 | $0.00929 | $0.3688 | $0.0738 |
| C/R2 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| C/R3 | $0.3049 | $0.0984 | $0.0197 | $0.7816 | $0.1563 |

## Interpretation

- **R3** wins on categories A, B, C (highest ARQGC under the $0.0000 budget).

### Token totals per route (across all tasks)

| Route | Cloud prompt | Cloud completion | Local prompt | Local completion |
|---|---:|---:|---:|---:|
| R2 | 0 | 0 | 44,273 | 13,794 |
| R3 | 121,607 | 152,631 | 243,916 | 55,252 |
