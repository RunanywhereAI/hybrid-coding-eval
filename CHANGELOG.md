# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) starting with v1.0.0.

## [Unreleased]

## [1.4.0] — 2026-05-22

**Cleanup + production-pipeline release.** v1.4 deletes the legacy non-agentic R1–R5 routes and the experimental Stanford-Minion / Devminion wrappers — the harness is now **agent-only** (aider · opencode · mini-swe-agent · claude-code · cline). Drops the `Rn` prefix; renames `runners/` → `agents/` and `benchmarks/` → `tasks/`. Adds 5 production lifecycle commands (`./bench start|pause|resume|stop|status`). `bench sweep` auto-spawns the router proxy from `models.local`, so the canonical reproducer is now four copy-paste commands.

### Headline canonical (708 rows, ~20h wall, $90.48 cloud spend on M4 Max 64GB)

> Sweeps complete: 468 v1.4-canonical-gemma4 + 48 v1.4-opencode-fairness + 192 v1.4-strategy-sweep. qwen3-coder + qwen3.6 canonical sweeps queued for v1.4.1.

- **Marquee Pareto win: aider + heuristic on refactors** → **23/24 = 96% [88, 100]** at **48% cloud-fraction** (~52% token spend reduction vs always-cloud 24/24 = 100%). Replicates v1.3.0's headline with refreshed code.
- **NEW: cline + always-local on puzzles** → **15/15 = 100%** with **zero cloud** — first 30B local-only result that nails Exercism Python puzzles (vs aider always-local 3/15, opencode 0/15).
- **NEW: opencode RESURRECTED with gemma4** → **17/24 = 71%** heuristic on refactors (vs v1.1.x's 0/15 with qwen3-coder). The fork-audit's "model + NUDGE" hypothesis verified. Puzzles still 0/15 — runLoop hard-exit ceiling.
- **NEW: cascade is dead in agentic regime** — heuristic ≥ cascade in every (agent, task-class) cell. Strategy-tuning is not the lever; agent + task-class selection is.

### Added

- **`configs/v1.4-canonical.yaml`** — the single canonical v1.4 sweep config covering 5 agentic routes × 8 strategies × 18 tasks × 3 local models. Drop-in surface for new local models.
- **`bench sweep` auto-spawns the router proxy** — reads `models.local` from the config, spawns `node router/server.mjs` with `LOCAL_MODEL=<model>`, waits for `/healthz`, runs the sweep, tears the router down on completion. Eliminates the manual `(cd router && ./start.sh) &` step from the reproducer.
- **`--external-router` flag** on `bench sweep` — opt-out for users who want to manage the router proxy themselves.
- **`docs/release-notes/v1.4.0.md`** — tracked-in-git release notes for v1.4.0 (replaces the GH-release-only `findings.md` from v1.0–v1.3).
- **"How to read the results" section** in `docs/REPRODUCING.md` — maps each headline number to its exact `bootstrap_cis.json` cell key with `jq` examples.
- **`pydantic` and `pyyaml`** in `requirements.txt` (were pyproject-only — broke fresh `pip install -r requirements.txt` installs).

### Changed

- **README rewritten for v1.4** — v1.4 hero, 4-command quickstart, 5 agentic routes, 8 strategies, 3 local models, CI badge, v1.3.0 carry-over preview headline.
- **`docs/REPRODUCING.md`** — v1.4 reproducer, expanded troubleshooting, cell→headline-number map.
- **`docs/BENCHMARK_NEW_MODEL.md`** — v1.4 add-a-model guide (18 tasks, 5 agents, 8 strategies, gemma4 baseline).
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
- **`bench sweep` required a manually-started router** — the reproducer recipe was incomplete (audit finding #4). Auto-spawn-router fixes the "I followed the GH release recipe and got Connection refused" class of bug.

### Pre-v1.4 history

The v1.0.0 → v1.3.0 release lineage is preserved on the [GitHub releases page](https://github.com/RunanywhereAI/hybrid-coding-eval/releases). Highlights below; see each release's notes for full per-version detail.

- **v1.3.0 (2026-05-20)** — Multi-model + threshold sweep release. 507 rows across 3 sweeps. First hybrid-equals-cloud result with statistical significance: **gemma4:31b + heuristic = 96% [88, 100]** on real_dev D-tasks. (See GH release `v1.3.0` for full notes.)
- **v1.2.0 (2026-05-19)** — Single-agent v1.2 release. Locked in **R7 aider** as the canonical agentic route. 60-row canonical sweep with qwen3-coder:30b. (See GH release `v1.2.0`.)
- **v1.1.3 / v1.1.2 / v1.1.1 / v1.1.0 (2026-05-19)** — Agentic-routes release lineage. Added R8 opencode, the Exercism Python benchmark (category X), the agent-aware `heuristic` strategy, `./bench sweep`, bootstrap CIs, correlation-id token attribution. (See GH release tags `v1.1.x`.)
- **v1.0.0 (2026-05-18)** — First public OSS release. R1–R5 non-agentic surface, 250-row v3 publication sweep, `./bench setup`. (See GH release `v1.0.0`.)
- **Pre-1.0 (v0.x → v3.x)** — Internal research iterations. The v3.3 sweep (3,581 rows, 33 variants, 6 local models) is the canonical pre-1.0 corpus under `results/runs/`. The 250-row v3 sweep at `results/runs/07-v3-devstral-all-routes/` is preserved bit-identically.

[Unreleased]: https://github.com/RunanywhereAI/hybrid-coding-eval/compare/v1.3.0...HEAD
[1.4.0]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.4.0
[1.3.0]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.3.0
[1.2.0]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.2.0
[1.1.3]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.1.3
[1.1.2]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.1.2
[1.1.1]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.1.1
[1.1.0]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.1.0
[1.0.0]: https://github.com/RunanywhereAI/hybrid-coding-eval/releases/tag/v1.0.0
