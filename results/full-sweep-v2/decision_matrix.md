# Decision matrix — category × route

_Generated from `results/full-sweep-v2/raw.jsonl` — 30 rows, default pricing: **openai-gpt5.5**._

_Bounded-ARQGC cost cap: **$2.936** (p90 of R1's per-task cost × task count)._

## Quality × cost × wall time

| Category | R1 quality | R2 quality | R3 quality | R1 cost | R2 cost | R3 cost | R1 wall | R2 wall | R3 wall |
|---|---|---|---|---|---|---|---|---|---|
| C | 0.99 (μ 0.92) | 0.74 (μ 0.72) | 0.98 (μ 0.87) | $0.1109 (Σ $1.546) | $0.0000 (Σ $0.0000) | $0.3007 (Σ $2.981) | 66,448 ms | 133,165 ms | 453,154 ms |

## Bounded-ARQGC — area under quality-cost curve

| Category | R1 | R2 | R3 | Recommended |
|---|---|---|---|---|
| C | 0.510 | 0.000 | 0.934 | R3 |
| **all** | 0.510 | 0.000 | 0.934 | — |

## Alternative pricing scenarios — median cost per task

| Category/Route | openai-gpt5.5 | openai-gpt5 | openai-gpt5-mini | anthropic-claude-opus-4.7 | anthropic-claude-sonnet-4.6 |
|---|---|---|---|---|---|
| C/R1 | $0.1109 | $0.0369 | $0.00737 | $0.2777 | $0.0555 |
| C/R2 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| C/R3 | $0.3007 | $0.0965 | $0.0193 | $0.7742 | $0.1548 |

## Interpretation

- **R3** wins on categories C (highest ARQGC under the $2.936 budget).

### Token totals per route (across all tasks)

| Route | Cloud prompt | Cloud completion | Local prompt | Local completion |
|---|---:|---:|---:|---:|
| R1 | 2,936 | 51,054 | 0 | 0 |
| R2 | 0 | 0 | 3,103 | 16,761 |
| R3 | 88,912 | 84,550 | 79,967 | 44,413 |
