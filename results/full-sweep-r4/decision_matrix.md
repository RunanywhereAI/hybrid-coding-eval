# Decision matrix — category × route

_Generated from `results/full-sweep-r4/raw.jsonl` — 10 rows, default pricing: **openai-gpt5.5**._

## Quality × cost × wall time

| Category | R4 quality | R4 cost | R4 wall |
|---|---|---|---|
| B | 0.00 (μ 0.40) | $0.2224 (Σ $2.026) | 147,196 ms |

## Bounded-ARQGC — area under quality-cost curve

| Category | R4 | Recommended |
|---|---|---|
| B | 0.400 | R4 |
| **all** | 0.400 | — |

## Alternative pricing scenarios — median cost per task

| Category/Route | openai-gpt5.5 | openai-gpt5 | openai-gpt5-mini | anthropic-claude-opus-4.7 | anthropic-claude-sonnet-4.6 |
|---|---|---|---|---|---|
| B/R4 | $0.2224 | $0.0701 | $0.0140 | $0.5801 | $0.1160 |

## Interpretation

- **R4** wins on categories B (highest ARQGC under the $0.0000 budget).

### Token totals per route (across all tasks)

| Route | Cloud prompt | Cloud completion | Local prompt | Local completion |
|---|---:|---:|---:|---:|
| R4 | 81,290 | 53,991 | 11,803 | 8,322 |
