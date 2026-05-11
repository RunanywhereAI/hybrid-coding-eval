# Token budget — where the tokens went

Generated from `results/runs/07-v3-devstral-all-routes/raw.jsonl` at `2026-05-11T16:16:36Z`; cost is derived from tokens at read time using `configs/pricing/pricing_tables.json`.

Every row below is one `(task_id, route, variant)` run from the committed dataset. `cloud_fraction` is the share of prompt+completion tokens that left the laptop; local tokens cost $0 by construction. `cost_<scenario>_usd` is re-derived from the stored tokens against the pinned pricing table, so the same dataset can be re-priced under any scenario without re-running inference.

**Scenarios surfaced:** `openai-gpt5.5`, `openai-gpt5`, `openai-gpt5-mini`, `anthropic-claude-opus-4.7`, `anthropic-claude-sonnet-4.6`, `anthropic-claude-haiku-4.5`

## 1. Top-10 most-local-efficient passing tasks

Rows where `functional_pass = True`, sorted by `cloud_fraction` ascending (ties broken by fewer total tokens). These are the tasks the laptop actually solved mostly on its own — the routing wins.

| task_id | route | variant | cat | cloud_frac | tokens | $openai-gpt5.5 | $openai-gpt5 | $openai-gpt5-mini | $anthropic-claude-opus-4.7 | $anthropic-claude-sonnet-4.6 | $anthropic-claude-haiku-4.5 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| humaneval-plus/HumanEval_15 | R2 |  | A | 0% | 1,387 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_13 | R2 |  | A | 0% | 1,406 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_99 | R2 |  | A | 0% | 1,470 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_154 | R2 |  | A | 0% | 1,472 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_121 | R2 |  | A | 0% | 1,478 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_118 | R2 |  | A | 0% | 1,482 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_161 | R2 |  | A | 0% | 1,534 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_103 | R2 |  | A | 0% | 1,580 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| humaneval-plus/HumanEval_123 | R2 |  | A | 0% | 1,826 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| bigcodebench-hard/BigCodeBench/530 | R2 |  | C | 0% | 2,107 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |

## 2. Per-(category, route) median table

One row per `(category, route)` cell. `median_cloud_frac` is the median across the runs in that cell; `pass_rate` ignores rows where `functional_pass` is null; each `med_$<scenario>` column is the median per-run cost under that scenario.

| cat | route | n_rows | median_cloud_frac | pass_rate | med_$openai-gpt5.5 | med_$openai-gpt5 | med_$openai-gpt5-mini | med_$anthropic-claude-opus-4.7 | med_$anthropic-claude-sonnet-4.6 | med_$anthropic-claude-haiku-4.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | R1 | 10 | 100% | 100% | $0.0119 | $0.0039 | $0.0008 | $0.0301 | $0.0060 | $0.0020 |
| A | R2 | 10 | 0% | 90% | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| A | R3 | 10 | 37% | 100% | $0.0380 | $0.0119 | $0.0024 | $0.0996 | $0.0199 | $0.0066 |
| A | R4 | 10 | 90% | 100% | $0.0659 | $0.0207 | $0.0041 | $0.1723 | $0.0345 | $0.0115 |
| A | R5 | 10 | 50% | 40% | $0.2488 | $0.0811 | $0.0162 | $0.6334 | $0.1267 | $0.0422 |
| B | R1 | 10 | 100% | 30% | $0.1058 | $0.0352 | $0.0070 | $0.2649 | $0.0530 | $0.0177 |
| B | R2 | 10 | 0% | 0% | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| B | R3 | 10 | 34% | 30% | $0.1369 | $0.0442 | $0.0088 | $0.3509 | $0.0702 | $0.0234 |
| B | R4 | 10 | 86% | 30% | $0.2025 | $0.0634 | $0.0127 | $0.5309 | $0.1062 | $0.0354 |
| B | R5 | 10 | 53% | 0% | $0.3902 | $0.1278 | $0.0256 | $0.9890 | $0.1978 | $0.0659 |
| C | R1 | 10 | 100% | 20% | $0.1400 | $0.0466 | $0.0093 | $0.3506 | $0.0701 | $0.0234 |
| C | R2 | 10 | 0% | 20% | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| C | R3 | 10 | 57% | 0% | $0.3010 | $0.0975 | $0.0195 | $0.7696 | $0.1539 | $0.0513 |
| C | R4 | 10 | 89% | 0% | $0.1201 | $0.0377 | $0.0075 | $0.3139 | $0.0628 | $0.0209 |
| C | R5 | 10 | 52% | 0% | $0.4934 | $0.1605 | $0.0321 | $1.2561 | $0.2512 | $0.0837 |
| D | R1 | 20 | 100% | 62% | $0.0354 | $0.0111 | $0.0022 | $0.0931 | $0.0186 | $0.0062 |
| D | R2 | 20 | 0% | 0% | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |
| D | R3 | 20 | 35% | 62% | $0.1234 | $0.0394 | $0.0079 | $0.3170 | $0.0634 | $0.0211 |
| D | R4 | 20 | 86% | 50% | $0.1611 | $0.0487 | $0.0097 | $0.4328 | $0.0866 | $0.0289 |
| D | R5 | 20 | 49% | 50% | $0.4043 | $0.1329 | $0.0266 | $1.0210 | $0.2042 | $0.0681 |

## 3. Decision matrix — cloud_fraction bands (costed under `openai-gpt5.5`)

Bucket every run by its `cloud_fraction` into 4 equal-width bands, then report how many tasks land in each band, their pass rate, and the mean USD cost under the primary pricing scenario.

| cloud_fraction band | n_tasks | pass_rate | mean $openai-gpt5.5/task |
|---|---:|---:|---:|
| 0-25% | 51 | 32% | $0.0005 |
| 25-50% | 64 | 50% | $0.2251 |
| 50-75% | 30 | 0% | $0.3738 |
| 75-100% | 105 | 55% | $0.1304 |

---

_n_rows=250 | scenarios=6 | derivation: tokens × pinned pricing_tables.json (sha256 pinned in `hybrid_coding_eval.core.pricing.PRICING_META`)._
