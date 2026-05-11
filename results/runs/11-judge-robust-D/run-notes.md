# Run 11 — triple-judge robustness audit (Category D)

_Not a sweep — re-judges the D3 (refactor) and D4 (review) pairings from `results/runs/07-v3-devstral-all-routes/` under three judges × two A/B orders. No inference re-run._

## Headline

**v3 sweep's D3/D4 verdicts survive triple-judge audit.** 96 verdicts = 16 pairings × 3 judges × 2 orders.

| result | count |
|---|---:|
| tie | 0 / 96 |
| A-wins (R1) | 96 / 96 |
| B-wins (R3 or R4) | 0 / 96 |
| error | 0 |

Aggregate agreement:

- **Unanimous pairings**: 16 / 16 (all 6 verdicts agree).
- **Single-judge dissent**: 0 / 16 (5 of 6 verdicts agree).
- **Order-flip pairings**: 0 / 16 (at least one judge swapped its verdict when A/B order reversed).

## Per-pairing agreement

| task | pair | unanimous? | majority | order-swap flips |
|---|---|:-:|---|---:|
| `real-dev/d3-constants-to-enum` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-constants-to-enum` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-extract-validation-helper` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-extract-validation-helper` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-replace-try-except-with-contextmanager` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-replace-try-except-with-contextmanager` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-split-god-module` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d3-split-god-module` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-cache-invalidation` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-cache-invalidation` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-pagination` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-pagination` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-sql-injection` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-sql-injection` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-timezone-handling` | R1_vs_R3 | yes | **A** (6/6) | 0/3 judges |
| `real-dev/d4-review-timezone-handling` | R1_vs_R4 | yes | **A** (6/6) | 0/3 judges |

## Config

Judges: `claude-opus-4-7`, `gpt-5.5`, `claude-sonnet-4-6`. Source run: `results/runs/07-v3-devstral-all-routes/`. Script: `bin/judge_robust_d3_d4.py`.

Re-run: `./.venv/bin/python bin/judge_robust_d3_d4.py`.
