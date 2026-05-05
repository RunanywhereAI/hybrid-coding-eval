# Open-source review — hybrid-coding-eval

Single-pass audit performed **2026-05-05** in preparation for flipping
the repository public (currently private at
`https://github.com/RunanywhereAI/hybrid-coding-eval`). This file is the
checklist of what was verified, what was changed, and what remains.

Scope: T6.3 of `PLAN.md`. Audit only — no feature work, no history
rewrites, no changes under `router/`, `runners/`, `scorers/`,
`analysis/`, `viz/`, `bin/`, `benchmark/`, `lib/`.

---

## 1. Secret sweep

**Method.** Full-tree grep (excluding `.venv/`, `node_modules/`, `.git/`,
`EXTERNAL/minions/`) for:

- `sk-[A-Za-z0-9_-]{30,}`, `sk-ant-…`, `sk-proj-…`
- `AKIA…` (AWS), `AIza…` (Google), JWT triplets
- `https://user:pass@…` credential URLs
- Any tracked `.env` / `.env.*`
- `git log --all --full-history -- .env`

**Findings.**

- **Zero real secrets in tracked content.** The only `sk-…`-shaped
  strings that appear are `sk-your-proxy-master-key` /
  `sk-your-openai-key-here` placeholders quoted verbatim from a
  third-party blog post cached under
  `research/2026-04_production_hybrid_general_use_cases/results.json`.
  These are documentation examples, not credentials.
- **Zero AWS/Google/JWT matches.**
- **Zero credential URLs.**
- **`.env` is not and has never been tracked** (confirmed with
  `git log --all --full-history -- .env` — empty output). The live
  `.env` on disk is correctly listed in `.gitignore`.
- **`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPEN_AI_API_KEY`
  references in code** (18 files) are all `process.env.*` or
  `os.environ[...]` lookups or docstring mentions — none contain
  values.

**Fix.** None needed. Added `.env.example` so users have a template.

## 2. License files

**Findings.** `LICENSE`, `LICENSE-DATA`, and `NOTICE.md` were missing at
repo root.

**Fix.**

- `LICENSE` — MIT, covers harness code.
- `LICENSE-DATA` — CC-BY-4.0, covers results, metrics, docs, article,
  figures, and the prior-art synthesis.
- `NOTICE.md` — enumerates every vendored / referenced upstream:
  - `EXTERNAL/lm-eval-harness-judge/` (FastChat, Apache 2.0, vendored
    tracked).
  - `EXTERNAL/minions/` (HazyResearch, MIT, referenced only — not
    tracked, gitignored).
  - Benchmarks: HumanEval+ / MBPP+ (MIT), BigCodeBench-Hard (Apache
    2.0), SWE-bench Verified (CC-BY-4.0), plus papers cited in
    `docs/PRIOR_ART.md`.

The pre-existing `EXTERNAL/lm-eval-harness-judge/LICENSE` (Apache 2.0
full text) and `EXTERNAL/lm-eval-harness-judge/ATTRIBUTION.md` were
already correct.

## 3. Laptop-specific paths

**Findings.** 31 grep hits for `/Users/sanchitmonga/`:

- `research/_run_research_2026-0{4,5}.py` — external-dependency loader
  pointing at a sibling `research_agent` checkout. These are run-once
  research-invocation scripts, not part of the harness; the
  hard-coded path is quoted as a comment/docstring at the top.
  Acceptable: `research/` is archival.
- `docs/history/HOW_TO_TEST.md`, `docs/history/OVERNIGHT_SUMMARY.md`,
  `docs/RUNANYWHERE_INTEGRATION.md` — archival / design notes that
  describe the original opencode sibling path for context.
  Acceptable: these are not reproduction instructions (those are in
  `docs/REPRODUCING.md`, which uses relative paths exclusively).
- `router/test/RESULTS.json` — `log_file` field from one recorded
  test run, pre-move from the opencode monorepo. Out of scope for
  this task (T6.3 must not touch `router/`). Cosmetic issue only,
  no leakage.
- `PLAN.md §12` — status note referencing the project path. **Fixed**
  to `(this repo root)`.
- `results/**/raw.jsonl` — generated run artefacts, all untracked
  (confirmed via `git ls-files | grep results/` returning zero).

**Fix.** PLAN.md updated. `.gitignore` tightened so `results/` is
ignored entirely by default, with explicit positive matches for
shippable artefacts (`REPORT.md`, `DECISION_MATRIX.md`, `*.png`,
`*.svg`). This prevents future accidental check-in of raw JSONL with
absolute paths.

`/tmp/` matches (2 in tracked code) are standard Unix tempfile usage
and cross-platform-fine on macOS and Linux. No action needed.

## 4. README

**Findings.** Missing quick-start, missing license section, missing
document index.

**Fix.** Added three sections to `README.md`: quick-start with pointer
to `docs/REPRODUCING.md`, a "Where to read next" index linking
`PLAN.md`, `METHODOLOGY.md`, `REPRODUCING.md`, `PRIOR_ART.md`,
`ROUTING_STRATEGIES.md`, `ARCHITECTURE.md`, and a license +
attribution section with suggested citation.

## 5. `.gitignore` audit

**Findings.** `.env` and `.venv/` were already ignored.
`EXTERNAL/minions/` was already ignored. `results/20*/` and
`results/latest` were ignored but named runs like `results/smoke/`
were **not** — risky because those contain absolute paths.

**Fix.** `.gitignore` rewritten to ignore `results/` entirely with
explicit `!results/**/REPORT.md` / `!results/**/*.png` allowlist for
the shippable subset. `.env.*` glob added (covers `.env.local`,
`.env.production`, etc.) with `!.env.example`.

## 6. Dependency hygiene

**Findings.**

- `requirements.txt` — all versions pinned to `>=X,<Y` ranges. OK.
- `pyproject.toml` — has `name`, `version`, `description`, `readme`,
  `requires-python`, `license = { text = "MIT" }`, `authors`. Missing
  `urls` (homepage / repository). Minor; cosmetic.
- `router/package.json` — declared `"zero deps"`; verified: no
  `dependencies` or `devDependencies` keys. Ships a single
  `node server.mjs` entry point.

**Fix.** None in this pass. Missing `[project.urls]` in
`pyproject.toml` is a nice-to-have; not a blocker for going public.

## 7. Prior-art attribution

**Findings.** `docs/PRIOR_ART.md` already cites arXiv IDs, paper
authors, and benchmark licenses inline. `NOTICE.md` now mirrors the
key citations for legal clarity.

## Recommendation

**SAFE TO FLIP PUBLIC.**

Every blocker class (secrets, missing license, unattributed vendored
code, `.env` in history, tracked absolute paths) is resolved. The
remaining items (`pyproject.toml` urls, `router/test/RESULTS.json`
cosmetic path) are non-blocking polish items and explicitly out of
scope for this task.
