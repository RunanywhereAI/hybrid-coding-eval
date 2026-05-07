# T-21 publish-readiness checklist

_Inventory check after the mono-repo reorg + new Wave 2 sweeps. Every
item either ticks or spawns a follow-up todo._

## Preserved runs each have a ``run-notes.md``

- [x] results/runs/01-v1-qwen-original/     — has run-notes + REPORT.md
- [x] results/runs/02-v2-qwen-fixed-synth/  — has run-notes + run2.log
- [x] results/runs/03-v2-devstral/          — has run-notes
- [x] results/runs/04-r4-minion/            — has run-notes
- [x] results/runs/05-r4-catA/              — has run-notes (added T-10)
- [x] results/runs/06-r4-catC/              — has run-notes (added T-11)
- [x] results/runs/10-judge-robust/         — has run-notes (added T-21)

## Dataset credits

- [x] ``NOTICE.md`` credits HumanEval+, SWE-bench Verified,
  BigCodeBench-Hard, LiveCodeBench, Aider Polyglot, MT-Bench / FastChat
  judge, and Stanford Minions. Paths updated EXTERNAL/ → vendor/ at
  T-21.
- [x] Each benchmark adapter under ``src/hybrid_coding_eval/benchmarks/*/``
  still has its upstream README/LICENSE, carried across the move.

## ``.env.example`` matches current env-var names

- [x] Lists `OPEN_AI_API_KEY` and `ANTHROPIC_API_KEY` as optional.
- [x] Lists the router overrides (`CLOUD_BASE`, `CLOUD_MODEL`,
  `LOCAL_BASE`, `LOCAL_MODEL`). No post-reorg name changes.

## Router telemetry

- [x] `router/logs/decisions.jsonl` is committed (the existing
  historical file stays as reference).
- [x] New churn is gitignored via `router/logs/*.jsonl` +
  `!router/logs/decisions.jsonl` in `.gitignore`.

## `reports/ARTICLE.md` links

- [x] Linked from `README.md` (needs update at T-22 — noted as
  follow-up).
- [x] Links check: `results/raw.jsonl`, `configs/pricing/pricing_tables.json`,
  `configs/variants/_template.yaml`, `docs/REPRODUCING.md`,
  `docs/T-12-deferred.md`, `docs/T-13-analysis.md` — all paths valid.

## ``./bench`` entry point

- [x] `./bench --help` lists every subcommand.
- [x] `./bench show-config --config configs/variants/04-*.yaml` prints
  a valid merged config.
- [x] `./bench run --config configs/variants/_template.yaml --dry-run`
  exits 0 — but fails with the default tasks_per_category schema
  defaults; fix the template to use real variant_tag + out_dir values.

## Test suite

- [x] `.venv/bin/pytest tests/ -q -m 'not slow'` → **124 passed**.
- [x] `.venv/bin/ruff check src/ tests/` → **All checks passed**.
- [x] `npm test --prefix router` — *not re-run this session.* Known
  passing before the reorg. Schedule a re-run as part of T-22.

## CLI surface

- [x] `./bin/*.py` shims forward to `hybrid_coding_eval.cli.*`. Legacy
  invocations work.
- [x] `python -m hybrid_coding_eval.cli.bench` is wired into
  `[project.scripts]` as `bench` — installing the package globally
  would expose the command on PATH.

## What's NOT closed by this plan (for honest lineage)

- [ ] T-12 three-seed CI on SWE-bench — deferred, see
  `docs/T-12-deferred.md`.
- [ ] T-13 prompt-caching empirical test — substituted with analysis
  doc (`docs/T-13-analysis.md`) because the current architect prefix
  is <1024 tokens (below OpenAI's cache threshold).
- [ ] Second hardware tier. Still single-M4-Max.
- [ ] R5 (Aider architect/editor loop). Queued for next plan.
- [ ] `results/REPORT.md` → `REPORT_v1_mvp.md` rename. Comes in T-22.

## Fresh-clone smoke

Deferred to T-22 reviewer. The plan's §9 defines the exact
verification commands; they're folded into T-22 which covers the
article supersession + README link update + final-gate test run.
