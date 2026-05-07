# Run 05 — R4 Minion on HumanEval+ (Category A)

_Branch `mono-repo-reorg`; commit after T-10; bench-config-sha see
`bench-config.json`._

## Headline

R4 Minion on Category A: **9/10 pass** on HumanEval+ (seed=42).

Reference points from the preserved MVP dataset:

| route | pass rate | median wall |
|---|:-:|:-:|
| R1 cloud-only (gpt-5.5) | 10/10 | ~3s |
| R2 local-only (devstral:24b) | 9/10 | ~25s |
| R3 hybrid architect (devstral) | 10/10 | ~40s |
| **R4 Minion (this run, devstral)** | **9/10** | **41s** |

R4 ties R2 and is one task shy of R1/R3. On small function-completion
tasks the Minion supervisor/worker protocol pays an extra question-ask
round-trip without material accuracy gain — the local model already
solves these problems end-to-end. That's the expected shape: Minion's
win was on SWE-bench (Cat B) where context distribution matters.

## What failed

- `humaneval-plus/HumanEval_103` — tests failed. Same failure mode
  devstral showed on R2 (reference dataset). No runner error; the
  model's output was syntactically valid but semantically wrong.

## Token economics

- cloud tokens total: **47,034** (supervisor + initial context)
- local tokens total: **5,390** (worker answers)
- ratio: **~8.7× more cloud than local** on Cat A — Minion trades
  cloud prompt for local worker calls, but on small self-contained
  function-completion tasks the local side hardly gets any work. The
  supervisor still has to read the docstring and spec to ask a
  meaningful question.

For comparison on Cat B (preserved run 04-r4-minion): median cloud
tokens per SWE task ≈ 12,000; median local ≈ 20,000. Minion's token
balance flips toward local as context size grows.

## Wall clock

- median per task: 40.7s
- total: 393s ≈ 6.5 min
- R1 reference: 3s/task; R3 reference: ~40s. R4 is R3-class latency.

## Config

- variant: `r4-catA`
- cloud: gpt-5.5 (router `always-cloud`)
- local: devstral:24b
- router strategy: heuristic (unused — R4 pins always-cloud + always-local)

## Next

- T-11 runs R4 on Category C. This is the first honest test of R4 on
  non-SWE prose — expect some rows to come back as `error=protocol-mismatch`
  per the plan's guardrail on silent redesigns.
- T-12 runs two extra seeds on Cat B to give CIs on the 4/10 vs 3/10
  headline from run 04-r4-minion.
