# Run 10 — triple-judge robustness audit (T-14)

_Not a sweep — re-judges custom_arch pairings from
`results/runs/02-v2-qwen-fixed-synth/` under three judges × two A/B
orders. No inference re-run._

## Headline

**MVP REPORT's "R3 ties R1 on custom_arch" finding survives triple-judge
audit.** 30 verdicts = 5 pairings × 3 judges × 2 orders.

| result | count |
|---|---:|
| tie | 27 / 30 |
| B-wins (R3) | 3 / 30 |
| A-wins (R1) | 0 / 30 |
| error | 0 / 30 |

## Per-task agreement

| task | pair | unanimous? | majority | order-swap flips |
|---|---|:-:|---|---:|
| `custom-arch/auth-multitenant-design` | R1_vs_R3 | ✅ | **tie** (6/6) | 0/3 judges |
| `custom-arch/cache-invalidation-tradeoffs` | R1_vs_R3 | ✅ | **tie** (6/6) | 0/3 judges |
| `custom-arch/code-review-flaky-test` | R1_vs_R3 | ❌ | **tie** (5/6) | 1/3 judges |
| `custom-arch/migration-planning-zero-downtime` | R1_vs_R3 | ❌ | **tie** (5/6) | 1/3 judges |
| `custom-arch/production-debug-reasoning` | R1_vs_R3 | ❌ | **tie** (5/6) | 1/3 judges |

Three tasks had one judge flip under order reversal (tie → B). In
every case the majority stayed tie. No flips of the aggregate winner.

## Known defect (fixed)

Initial run had gpt-5.5 judge calls 401'ing because
``scorers/llm_judge.py::_call_judge`` passed the Anthropic API key to
OpenAI models. Fixed to re-resolve the key per-vendor. Re-ran T-14,
confirmed all 30 verdicts valid.

## Config

Judges: `claude-opus-4-7`, `claude-sonnet-4-6`, `gpt-5.5`.
Source run: `results/runs/02-v2-qwen-fixed-synth/`.
Script: `src/hybrid_coding_eval/analysis/judge_robustness.py`.

Re-run: `./bench env-detect` then
`./venv/bin/python -m hybrid_coding_eval.analysis.judge_robustness`.
