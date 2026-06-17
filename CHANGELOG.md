# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) starting with v1.0.0.

## [Unreleased]

## [1.5.1] — 2026-05-27

**Open-source polish release** — addresses every audit finding from the
pre-publish review (security, licensing, UX, hygiene). No code-behaviour
changes; safe to take.

### Removed

- `NOTICE.md`, `LICENSE-DATA`, `LICENSE.md` — consolidated to a single
  MIT `LICENSE` that covers code, data, and docs.
- `scripts/reproduce.sh` — `./arena setup` already does prereq checks
  and the smoke sweep is a one-liner (`./arena sweep --config
  configs/v1.4-smoke.yaml`).
- `logs/v3.3/` — historical sweep logs moved to maintainer-private
  storage. `logs/` is now gitignored.
- `pytest` runtime dependency promoted to `[dev]` only (was shipped in
  both before).
- `pytest -m slow` filter removed from CI and docs — no test is
  currently marked `slow`, so the filter was a no-op.

### Changed

- **`README.md` rewritten end-to-end** — six-cell headline table, real
  quickstart with accurate prereq + timing estimates, "picking a config
  for real work" section distilled from the v1.5 leaderboard, full
  `arena` CLI table, MIT-only license + citation block.
- **`AGENTS.md` refreshed for v1.5.0** — D6 task shape documented,
  v1.5 configs added to the tree, latest-results pointer updated,
  conventions section reflects single-letter codes are retired.
- **`CODE_OF_CONDUCT.md` simplified** to a short, direct version.
- **`src/hybrid_arena/__init__.py`** — `__version__` is now
  `"1.5.0"` (was stuck at `"0.1.0"`).
- **Source-tree docstrings + READMEs** — `lib.*` stale references
  rewritten to `core.*` / `hybrid_arena.*`; "Category D/B/X"
  rewritten to `refactors` / `real-prs` / `puzzles` end-to-end.
- **Tracked `raw.jsonl` datasets** — sanitized **263 home-directory
  path leaks** to repo-relative form. JSON integrity preserved
  (`json.loads()` re-validated on every row).

### Fixed

- `.github/ISSUE_TEMPLATE/new_model.md` — broken
  `configs/variants/_template.yaml` reference replaced with a real
  command.
- `docs/HYBRID_ROUTING_DESIGN.md` — `jq` cell-key examples updated
  from legacy `D::cline::heuristic` form to current
  `refactors::cline::heuristic`. D6 row added to the task-class table.
- `docs/release-notes/v1.4.0.md` and `v1.4.1.md` — same cell-key fix
  in the reproduction snippets.
- Test aliases `r10_cline` and `r6_mini_swe_agent` renamed to
  `cline_runner` / `mini_swe_runner` to remove the last legacy
  R-numbers from the testsuite.

## [1.5.0] — 2026-05-27

**Hard-task stress test release.** Adds a new D6 task shape with 4
deliberately harder problems (LRU+TTL cache, multi-key token bucket,
deterministic toposort + cycle detection, mini templating engine)
that stress 30B local models beyond the D1/D5 calibration. Stress
sweeps the v1.4.1 top-3 configs (aider+gemma4+heuristic,
cline+qwen3.6+cascade, cline+qwen3.6+always-local) against the new
hard tasks with 3 seeds each. Full notes at
[`docs/release-notes/v1.5.0.md`](./docs/release-notes/v1.5.0.md).

### Added

- **New D6 task shape** under `refactors`: `d6-lru-ttl-cache`
  (23 acceptance tests), `d6-token-bucket` (14 tests),
  `d6-toposort` (16 tests), `d6-mini-template` (27 tests) =
  80 acceptance assertions total. Each task is a single-file
  implementation challenge with comprehensive pytest coverage,
  scored via the existing D1/D5 overlay-and-run pipeline.
- **New configs**: `configs/v1.5-hard-gemma4.yaml` and
  `configs/v1.5-hard-qwen3.6.yaml` for the stress-test sweeps.
- **New article**: `personal/reports/publish-v1.5/article.html`
  with the §4.5 real-world walkthrough section, the §8.5
  permutation matrix, and a new §12 hard-task stress test
  section.
- **New dataset**: `results/runs/v1.5-hard-gemma4/` and
  `results/runs/v1.5-hard-qwen3.6/`.

### Changed

- `tasks/refactors/adapter.py` accepts `D6` as a valid task shape.
- `tasks/refactors/scorers.py` dispatches `D6` through the
  existing D1 overlay+pytest path.

### Fixed

- **aider pytest-summary parser bug.** `_parse_pytest_summary`
  in `src/hybrid_arena/agents/aider.py` previously read
  the summary line positionally and missed the "failed" count
  when it preceded "passed" (e.g. `2 failed, 21 passed` was
  scored 0/2 instead of 21/23). New implementation uses
  independent regexes per token and is order-agnostic. Covered
  by `tests/agents/test_aider_parser.py` (18 parametrized cases).

### Findings (post-sweep)

- **cline + qwen3.6:35b + always-local on D6 hits 67% with $0 cloud spend** —
  the new headline. 30B local-only solves token-bucket and toposort 3/3,
  partial-passes lru-ttl-cache and mini-template.
- **aider + gemma4 + heuristic on D6 falls to 58%** vs always-cloud 100%.
  The v1.3 marquee profile breaks on harder calibration.
- **cline + qwen3.6 + cascade on D6 drops from v1.4.1's 100%/8% to 75%/13%** —
  the router under-escalates on `d6-mini-template` (recursive parser).

## [1.4.4] — 2026-05-27

**Fresh-user reproducibility patch.** Targets the last two paper cuts a
brand-new clone hits on the way from `git clone` to a green
`arena analyze` chart. Full notes at
[`docs/release-notes/v1.4.4.md`](./docs/release-notes/v1.4.4.md).

### Changed

- **`scripts/reproduce.sh`** explicitly prefers `python3.12` /
  `python3.11` over generic `python3` and recreates `.venv` if it
  was pinned to a different (e.g. 3.13/3.14) interpreter. Python
  3.13+ breaks several agent installers (notably `aider-chat`)
  because they depend on a `setuptools` bootstrap that 3.13/3.14
  dropped from the stdlib.

### Fixed

- **`arena analyze` works on a clean `pip install -e ".[dev]"`.**
  `matplotlib` + `numpy` are now declared in
  `pyproject.toml::[project.dependencies]` (they were previously only
  in `requirements.txt`, so the canonical install path left them
  missing and `arena analyze` died with
  `ModuleNotFoundError: No module named 'matplotlib'`).
- **Per-agent scratch directories no longer carry the legacy R-prefix.**
  aider writes to `outputs/aider_<task>_<strategy>/`, cline to
  `outputs/cline_<task>_<strategy>/`, opencode to
  `outputs/opencode_<task>_<strategy>/`, mini-swe-agent to
  `outputs/mini-swe-agent_<task>_<strategy>/`. Default `output_dir`
  per agent is now `results/<agent-name>/` instead of
  `results/r6/`…`results/r10/`. The v1.4.3 commit cleaned every other
  R-number surface but missed these inline path templates.
- **Task adapter dataclass defaults align with the v1.4.3 rename.**
  `refactors.Task.category` defaults to `"refactors"` (was `"D"`) and
  `real_prs.Task.category` defaults to `"real-prs"` (was `"B"`). The
  parsers already overrode these defaults in v1.4.3, but the
  dataclass field defaults still leaked the legacy letters if a row
  was constructed without going through `_parse_task`.

### Verified

End-to-end fresh-user replay: `rm -rf .venv && ./scripts/reproduce.sh
--smoke` → 1m 26s wall, 1/1 PASS, all charts emitted, no missing
modules, no R-prefix leaks in `output_ref`.

## [1.4.3] — 2026-05-26

**Back-compat-free cleanup.** Drops every v1.0–v1.3 legacy surface from
the v1.4 harness. No new benchmark data; the v1.4.1 leaderboard
(1,644 rows) stands. Full release notes at
[`docs/release-notes/v1.4.3.md`](./docs/release-notes/v1.4.3.md).

### Changed

- **Task-class names are consistent end-to-end.** `ResultRow.category`,
  `aggregate.json` cell keys, `bootstrap_cis.json` cell keys, and
  `decision_matrix.md` rows all use `puzzles` / `refactors` / `real-prs`
  instead of the legacy single letters (`A` / `D` / `B`). Affects
  scripts that grep cell keys; the rename is mechanical.
- **`README.md`** — added explicit Prerequisites section with per-platform
  install commands (macOS Homebrew + Debian/Ubuntu apt) for Python,
  Docker, Node, Ollama, jq.
- **`scripts/reproduce.sh`** — platform-aware install hints. When a
  prereq is missing it prints the exact `brew install …` or
  `sudo apt install …` command for the host OS, plus a hint to start
  the Ollama daemon when port 11434 isn't reachable.
- **`pyproject.toml`** — `matplotlib` and `numpy` are now first-class
  runtime dependencies. `arena analyze` needs them for chart
  generation, but they were previously only in `requirements.txt`,
  so `pip install -e ".[dev]"` left them missing. Fresh installs now
  work end-to-end with zero extra steps.
- **Per-agent scratch directories** drop the R-prefix. aider writes
  to `outputs/aider_<task>_<strategy>/`, opencode to
  `outputs/opencode_<task>_<strategy>/`, cline to
  `outputs/cline_<task>_<strategy>/`, mini-swe-agent to
  `outputs/mini-swe-agent_<task>_<strategy>/`. Default
  `output_dir` per agent is `results/<agent-name>/`.
- **`core/experiment.pair_already_done`** is strict now — requires an
  exact `(task, route, strategy)` match instead of treating
  `router_strategy=None` as a wildcard. Stops a foot-gun where a
  resume could silently skip a stale legacy row.

### Removed

- **`router/pipelines/architect/`** + **`router/agentic/`** — the v3
  multi-step "plan → execute → synthesise" pipeline. Not referenced by
  any v1.4 agent; the `model: "router/architect"` pseudo-strategy
  dispatcher in `server.mjs` was unreachable. ~200 lines of dead code
  plus 9 vendored example outputs.
- **Single-letter category codes** (`A`/`B`/`C`/`D`/`X`) from adapter
  defaults, agent fallbacks, viz colour/marker fall-backs, and the
  refactor task JSONLs.
- **`R6` / `R7` / `R8` / `R10` references** from every docstring,
  comment, and test name. Agent modules read as standalone documents now.
- **`results/raw.jsonl` historical round-trip test** —
  `tests/test_metrics_new_fields.py::test_historical_dataset_still_loads`
  was pure v1.0 back-compat coverage; dropped.

### Fixed

- **`agents/aider.py` + `agents/cline.py`** dispatcher tests no longer
  rely on `mini-swe-agent` to dispatch a `puzzles` task. (Previously
  worked only because the back-compat wildcard in `pair_already_done`
  short-circuited the runner.)

## [1.4.2] — 2026-05-26

**OSS readiness cleanup.** Code, docs, and reproducibility cleanup pass — no new benchmark data. The full release notes live at [`docs/release-notes/v1.4.2.md`](./docs/release-notes/v1.4.2.md).

### Added

- **`scripts/reproduce.sh`** — one-command reproducer that checks every prerequisite, sets up the venv, runs `./arena setup`, and either runs the smoke sweep (`--smoke`) or forwards arbitrary `./arena sweep` arguments. ~30 s end-to-end for the smoke pass.
- **`docs/HYBRID_ROUTING_DESIGN.md`** — single canonical design doc consolidating the eight previously-separate `docs/*.md` files (routing strategies, agents, methodology, schema, add-a-model recipe).
- **`SECURITY.md`** — vulnerability-disclosure channel (private email).
- **`arena analyze` walks subdirectories.** Point it at a sweep root and it analyses every `<strategy>/seed-<seed>/raw.jsonl` it finds.
- **`arena setup` fails fast** (10 s timeout) when the Docker daemon is down, instead of hanging on the `docker image inspect` call.

### Changed

- **`README.md`, `AGENTS.md`, `CONTRIBUTING.md`** rewritten for v1.4.2 reality — TL;DR results table, repo layout, contribution recipes that point at the four-agent surface.
- **`LICENSE`, `LICENSE-DATA`, `LICENSE.md`, `NOTICE.md`** rewritten — every referenced path now actually exists (no more dangling `runners/`, `EXTERNAL/`, `vendor/minions/`, `vendor/lm-eval-harness-judge/`, `bin/`, `benchmark/`, `lib/`).
- **`pyproject.toml`** — version bumped to `1.4.2`; `ruff.extend-exclude` repointed to the v1.4 fixture roots under `tasks/`.
- **`requirements.txt`** synced with `pyproject.toml [project.dependencies]`, grouped Core / Viz / Optional.
- **`.env.example`** — dropped deleted-in-v1.4 `llm_judge` reference; added v1.4.1 `ROUTER_LOCAL_*` guards.
- **`CODE_OF_CONDUCT.md`** — private email reporting channel.

### Fixed

- **`analysis/bootstrap.py` cost CI** now reads from `configs/pricing/pricing_tables.json` instead of an empty per-row `cost_usd` field. (Pre-v1.4.2 analyses showed silently-zero cost CIs for some cells.)
- **`analysis/bootstrap.py` `cloud_fraction`** is token-based, not call-count-based — the canonical definition now applies everywhere (router, analysis, release notes).
- **`analysis/bootstrap.py` `stratify_by`** parameter now respected (was silently ignored).
- **`core/experiment.score_row`** accepts both `refactors` and the legacy `real_dev` source name — silent skip bug.
- **`core/experiment.run_pair`** stamps `seed` onto the `ResultRow` via the new `--seed` flag.
- **`cli/bench._cmd_sweep`** forwards `CLOUD_MODEL` from the config to the spawned router proxy.
- **`agents/aider.py` `_run_tests_local`** parses `pytest`'s summary line via regex — `tests_passed` / `tests_total` are now correct (was always 0/1 or 1/1).
- **`cli/env_detect.py`** uses `core.paths.repo_root` for path resolution (single source of truth).
- **`docs/release-notes/v1.4.1.md`** — corrected `cline + qwen3.6 + heuristic + refactors` headline from `22/24 = 92%` to `23/24 = 96%` (the prior figure was a transcription error from the raw data).
- **`CHANGELOG.md`** — restored missing `[1.4.1]` reference link; `[Unreleased]` compares against `v1.4.1` instead of `v1.3.0`.

### Removed

- **`analysis/arqgc.py` + `analysis/decision_matrix_v2.py`** — unused. The v1.4 decision matrix ranks cells by pass-rate then median cost; no ARQGC anywhere in the pipeline.
- **`agents/claude_code.py`** — deferred to v1.5. v1.4.2 surfaces four agents: `aider`, `opencode`, `mini-swe-agent`, `cline`.
- **`docs/REPRODUCING.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`, `docs/ROUTING_STRATEGIES.md`, `docs/AGENTIC_ROUTES.md`, `docs/HYBRID_ROUTER_DESIGN.md`, `docs/PRIOR_ART.md`, `docs/BENCHMARK_NEW_MODEL.md`** — consolidated into `docs/HYBRID_ROUTING_DESIGN.md`.
- **`docs/audits/`** — moved to gitignored `personal/audits/` (internal review artefacts, not OSS surface).
- **`examples/`** — stale; instructions live in `README.md` + `docs/HYBRID_ROUTING_DESIGN.md` now.
- **Stale `EXTERNAL/minions/` / `vendor/minions/` entries** removed from `.gitignore`.
- **Two `personal/raw-runs/v4*.yaml`** files untracked (were committed despite the `personal/` gitignore).

## [1.4.1] — 2026-05-25

**3-model agentic leaderboard.** v1.4.1 adds 936 rows across two new canonical sweeps (qwen3-coder:30b + qwen3.6:35b) — completing the 3-model leaderboard envisioned in the original v1.4 plan. Combined v1.4 + v1.4.1: **1,644 rows** of agentic-only data across 3 local models × 3 agents × 4-8 strategies × 13 tasks × 3 seeds.

### Headline (v1.4.1 new — the marquee cells)

| Cell | Pass-rate | Cloud-fraction |
|---|---|---|
| **cline + qwen3.6 + cascade + refactors** | **24/24 = 100%** [100, 100] | low (~5-10%) |
| cline + qwen3.6 + heuristic + refactors | 22/24 = 92% | ~7% |
| cline + qwen3-coder + heuristic + refactors | 22/24 = 92% | ~7% |
| cline + qwen3.6 + always-local + puzzles | 15/15 = 100% [100, 100] | 0% |

**cline + qwen3.6 is the new winner for refactors** — matches aider's marquee 96% / equals it under cascade, at a fraction of the cloud spend. **Two qwen variants (3-coder, 3.6) both deliver cline+heuristic+refactors at 92%.**

### Three new findings

1. **qwen3.6:35b is the unsung champion.** cline + qwen3.6 nails everything — 100% on puzzles always-local, 100% on refactors cascade, 92% heuristic. The model that wasn't in v1.4.0 turns out to be the strongest local for cline's protocol.

2. **opencode is gemma4-specific.** opencode + gemma4 + heuristic + refactors = 71% (v1.4.0 resurrection). opencode + qwen3-coder = 21%. opencode + qwen3.6 = 33%. The v1.4.0 fix doesn't transfer to qwen models — opencode's runLoop requires the model to produce clean tool_calls, which gemma4 does and qwen models don't reliably.

3. **Aider is model-sensitive too.** aider + heuristic + refactors = 96% on gemma4, 50% on qwen3.6, 33% on qwen3-coder. Aider's architect/editor protocol works best with gemma4's dense-generalist training.

### Added

- **`router/server.mjs` local-guard fix** (commit `c7392db`) — `ROUTER_LOCAL_NUM_PREDICT_CAP=4096`, `ROUTER_LOCAL_REQUEST_TIMEOUT_MS=180000`, `ROUTER_LOCAL_REPEAT_PENALTY=1.1`. Three model-agnostic env-overridable guards in `fetchLocalOllamaAsOpenAI()`. Discovered + fixed during v1.4.1 sweep 4 when qwen3-coder's weak `repeat_penalty=1.05` + unbounded `num_predict` (cline/opencode don't set `max_tokens`) caused a runaway repetition loop that crashed Ollama. Full RCA at `personal/iterations/v1.4.1/qwen3-coder-timeout-rca.md`.
- **`configs/v1.4-canonical-qwen3-coder.yaml`** and **`configs/v1.4-canonical-qwen3.6.yaml`** — the two new canonical configs (came in v1.4-rc1 but actually exercised in v1.4.1).
- **2 new release artifacts**: `results-v1.4.1.tar.gz` (15 MB, both qwen sweep dirs), v1.4.1 article HTML with code-generated visualizations.

### Verified

- The v1.4.0 marquee aider+heuristic+gemma4+refactors = 96% replicates exactly in the v1.4.1 data — refreshed code, same headline.
- The v1.4.0 cline+gemma4+always-local+puzzles = 100% also confirmed in v1.4.1's gemma4 columns (no change).

### Cost

v1.4.1 sweeps spent ~$50 incremental cloud (gpt-5.5 list pricing). Total v1.4 line (v1.4.0 + v1.4.1): **~$140 list / ~$80 cache-adjusted across 1,644 rows.**

## [1.4.0] — 2026-05-22

**Cleanup + production-pipeline release.** v1.4 deletes the legacy non-agentic R1–R5 routes and the experimental Stanford-Minion / Devminion wrappers — the harness is now **agent-only** (aider · opencode · mini-swe-agent · claude-code · cline). Drops the `Rn` prefix; renames `runners/` → `agents/` and `benchmarks/` → `tasks/`. Adds 5 production lifecycle commands (`./arena start|pause|resume|stop|status`). `arena sweep` auto-spawns the router proxy from `models.local`, so the canonical reproducer is now four copy-paste commands.

### Headline canonical (708 rows, ~20h wall, $90.48 cloud spend on M4 Max 64GB)

> Sweeps complete: 468 v1.4-canonical-gemma4 + 48 v1.4-opencode-fairness + 192 v1.4-strategy-sweep. qwen3-coder + qwen3.6 canonical sweeps queued for v1.4.1.

- **Marquee Pareto win: aider + heuristic on refactors** → **23/24 = 96% [88, 100]** at **48% cloud-fraction** (~52% token spend reduction vs always-cloud 24/24 = 100%). Replicates v1.3.0's headline with refreshed code.
- **NEW: cline + always-local on puzzles** → **15/15 = 100%** with **zero cloud** — first 30B local-only result that nails Exercism Python puzzles (vs aider always-local 3/15, opencode 0/15).
- **NEW: opencode RESURRECTED with gemma4** → **17/24 = 71%** heuristic on refactors (vs v1.1.x's 0/15 with qwen3-coder). The fork-audit's "model + NUDGE" hypothesis verified. Puzzles still 0/15 — runLoop hard-exit ceiling.
- **NEW: cascade is dead in agentic regime** — heuristic ≥ cascade in every (agent, task-class) cell. Strategy-tuning is not the lever; agent + task-class selection is.

### Added

- **`configs/v1.4-canonical.yaml`** — the single canonical v1.4 sweep config covering 5 agentic routes × 8 strategies × 18 tasks × 3 local models. Drop-in surface for new local models.
- **`arena sweep` auto-spawns the router proxy** — reads `models.local` from the config, spawns `node router/server.mjs` with `LOCAL_MODEL=<model>`, waits for `/healthz`, runs the sweep, tears the router down on completion. Eliminates the manual `(cd router && ./start.sh) &` step from the reproducer.
- **`--external-router` flag** on `arena sweep` — opt-out for users who want to manage the router proxy themselves.
- **`docs/release-notes/v1.4.0.md`** — tracked-in-git release notes for v1.4.0 (replaces the GH-release-only `findings.md` from v1.0–v1.3).
- **"How to read the results" cell→headline map** — maps each headline number to its exact `bootstrap_cis.json` cell key with `jq` examples.
- **`pydantic` and `pyyaml`** in `requirements.txt` (were pyproject-only — broke fresh `pip install -r requirements.txt` installs).

### Changed

- **README rewritten for v1.4** — v1.4 hero, 4-command quickstart, 5 agentic routes, 8 strategies, 3 local models, CI badge, v1.3.0 carry-over preview headline.
- **`AGENTS.md`** — reflects post-cleanup `agents/` directory + auto-spawn-router workflow.
- **`pyproject.toml`** — version bumped to 1.4.0.
- **Task class names**: `X` → `puzzles` (Exercism Python) and `D` → `refactors` (real-developer D-tasks). The v1.4 task classes are surfaced in `bootstrap_cis.json` cell keys and headline tables.

### Removed

- **R1 cloud-only, R2 local-only, R3 hybrid-architect runners** — legacy non-agentic routes deleted. The canonical v3 dataset (`results/runs/07-v3-devstral-all-routes/`) stays tracked for historical reproducibility.
- **R4 Stanford-Minion, R5 Stanford-DevMinion runners** — experimental wrappers around `vendor/minions/` deleted. The `mcp` / `rank_bm25` / `requests` transitive deps are no longer needed.
- **CI `Clone vendored Minions` + `Install Minions transitive deps` steps** — eliminated from `.github/workflows/ci.yml` now that R4/R5 are gone. Fresh `pip install -e ".[dev]"` is enough.
- **Legacy `runners/` directory** renamed to **`agents/`** to reflect what it actually contains post-cleanup.

### Fixed

- **`requirements.txt` was missing `pydantic` and `pyyaml`** — they were declared only in `pyproject.toml`'s `[project.dependencies]`. Fresh-install users hitting `pip install -r requirements.txt` got `ModuleNotFoundError: pydantic` from the config loader. Now mirrored in both files with the same pins.
- **`arena sweep` required a manually-started router** — the reproducer recipe was incomplete (audit finding #4). Auto-spawn-router fixes the "I followed the GH release recipe and got Connection refused" class of bug.

### Pre-v1.4 history

The v1.0.0 → v1.3.0 release lineage is preserved on the [GitHub releases page](https://github.com/RunanywhereAI/hybrid-arena/releases). Highlights below; see each release's notes for full per-version detail.

- **v1.3.0 (2026-05-20)** — Multi-model + threshold sweep release. 507 rows across 3 sweeps. First hybrid-equals-cloud result with statistical significance: **gemma4:31b + heuristic = 96% [88, 100]** on real_dev D-tasks. (See GH release `v1.3.0` for full notes.)
- **v1.2.0 (2026-05-19)** — Single-agent v1.2 release. Locked in **R7 aider** as the canonical agentic route. 60-row canonical sweep with qwen3-coder:30b. (See GH release `v1.2.0`.)
- **v1.1.3 / v1.1.2 / v1.1.1 / v1.1.0 (2026-05-19)** — Agentic-routes release lineage. Added R8 opencode, the Exercism Python benchmark (category X), the agent-aware `heuristic` strategy, `./arena sweep`, bootstrap CIs, correlation-id token attribution. (See GH release tags `v1.1.x`.)
- **v1.0.0 (2026-05-18)** — First public OSS release. R1–R5 non-agentic surface, 250-row v3 publication sweep, `./arena setup`. (See GH release `v1.0.0`.)
- **Pre-1.0 (v0.x → v3.x)** — Internal research iterations. The v3.3 sweep (3,581 rows, 33 variants, 6 local models) is the canonical pre-1.0 corpus under `results/runs/`. The 250-row v3 sweep at `results/runs/07-v3-devstral-all-routes/` is preserved bit-identically.

[Unreleased]: https://github.com/RunanywhereAI/hybrid-arena/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.4.3
[1.4.2]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.4.2
[1.4.1]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.4.1
[1.4.0]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.4.0
[1.3.0]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.3.0
[1.2.0]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.2.0
[1.1.3]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.1.3
[1.1.2]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.1.2
[1.1.1]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.1.1
[1.1.0]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.1.0
[1.0.0]: https://github.com/RunanywhereAI/hybrid-arena/releases/tag/v1.0.0
