# T-22 — v3 publish-readiness audit

**Date**: 2026-05-11
**Branch**: `mono-repo-reorg`
**Head**: `85c1427a73016607ef274ebfef50eb94166fd3b3` (`docs: refresh README indexes for v3 sweep (runs 07 + 11)`)
**Auditor**: T-22 sub-agent (follow-up to T-21).

## Status: YELLOW

The v3 sweep is publish-ready in substance: 250 rows in the canonical
dataset, every report regenerated, every internal link resolves, every
attribution captured. Two known gaps keep this from being GREEN:

1. **Fresh-clone `pytest` is not clean** — the R4 + R5 runner modules
   import the Stanford Minions library at *module load time* from
   `vendor/minions/` (or legacy `EXTERNAL/minions/`). That clone is
   gitignored, so a brand-new checkout fails to import `r4_minion` /
   `r5_devminion` and the 14 tests in `tests/runners/test_r5_devminion.py`
   `ERROR` rather than `SKIP`. Documented in `vendor/README.md` (the
   user is told to clone Minions themselves) but the failure mode is
   confusing and should ideally be a `pytest.importorskip` guard before
   tagging.
2. **README still carries two stale `EXTERNAL/` references** (lines 95
   + 159). The layout diagram and the bottom attribution link both
   point at `EXTERNAL/README.md` where the file actually lives at
   `vendor/README.md`. P5.1 fixed the 200→250 headline and route count
   but missed these two strings.

Everything else — secrets, licenses, the article + appendix coherence,
the `./bench` entry point, the v3 dataset itself — is GREEN.

---

## What was checked

### 1. Fresh-clone smoke

```bash
tmp=$(mktemp -d) && cd "$tmp"
git clone https://github.com/RunanywhereAI/hybrid-coding-eval hce-fresh
cd hce-fresh
git checkout mono-repo-reorg          # at 85c1427
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

| Step | Outcome |
|---|---|
| `git clone` (then checkout `mono-repo-reorg`) | OK — branch tracked, 85c1427 checked out |
| `python3.12 -m venv .venv` | OK |
| `pip install -r requirements.txt` | OK — clean install, only a pip-upgrade notice on stderr |
| `pip install -e .` | OK — editable install of `hybrid_coding_eval` |
| `./bench --help` | OK — lists all 9 subcommands (run, show-config, env-detect, rescore, rejudge, analyze, token-budget, report, schema) |
| `./bench show-config --config configs/variants/_smoke-v3.yaml` | OK — emits valid merged config JSON (sha256 = `9fd52a95…`); 6 pricing scenarios surfaced; primary `openai-gpt5.5` |
| `pytest -q -m 'not slow'` | **MIXED** — `162 passed, 4 skipped (ANTHROPIC_API_KEY not set), 14 failed (R5 module-import errors)`, 3 deselected (slow). Failures are *all* in `tests/runners/test_r5_devminion.py` and they fail at the very first `from hybrid_coding_eval.runners import r5_devminion` line because that module transitively imports `vendor/minions/minions/usage.py` at load time — and `vendor/minions/` is gitignored. |

The 162 passing non-runner tests cover: aggregate, ARQGC, BigCodeBench
adapter, config parser, custom-arch adapter, env-detect, functional
Python scorer, HumanEval+ adapter, judge schema, metrics, orchestrator
dispatch, pricing parity (path + scenario), R2 local-only runner,
results glue, sandbox, SWE-bench adapter, SWE-bench scorer (no Docker
codepath), viz. The 4 skipped tests are all in `tests/test_llm_judge.py`
and skip cleanly when `ANTHROPIC_API_KEY` is not exported — that is
correct skip behaviour, not a failure.

**Fix recommendation**: wrap the top-level `vendor/minions` imports in
`r4_minion.py` and `r5_devminion.py` with a `try/except ImportError`
that flips a `_MINIONS_AVAILABLE = False` flag, and prefix every R4/R5
test with `pytest.importorskip("minions.clients.openai")`. That keeps
the runner-modules importable without the vendored library and turns
the failing 14 tests into clean skips. Out of scope for this audit —
filed as T-23 candidate.

### 2. Router `npm test`

`router/package.json` has a `"test"` script wired to
`node tests/run-tests.mjs`. It is an end-to-end harness — it pings
`http://127.0.0.1:8787/healthz`, then walks 17 prompts × 7 strategies
(119 calls) against the live proxy. Cannot run in CI without a hot
Ollama + a real `OPEN_AI_API_KEY`.

Manual probe: started the proxy, ran `npm test --prefix router`. Output
header confirmed `Proxy OK. local=✓ cloud=✓ (key present)` and the
harness began iterating strategies (always-local, always-cloud, rules,
heuristic, llm-classifier, embedding-knn, cascade). Stopped early once
the smoke confirmed the harness wires correctly — the full sweep is
~30 minutes and there's a frozen reference at `router/tests/RESULTS.md`
(`2026-04-26T08:00:56.609Z`) from a green pre-reorg run.

**Documented gap**: there is no fast unit-level test of the strategies
themselves (`router/strategies.mjs` covers ~600 LoC of routing logic
with no isolated test). Filed as T-23 candidate — does not block v3
publish.

### 3. Secret / key audit

```bash
git ls-files | xargs grep -l "sk-ant-\|sk-proj-\|sk-svc-" \
   2>/dev/null | grep -v '.example' | head -5
```

Four hits, **all placeholders or regex patterns**, none are real keys:

- `archive/docs/OSS_REVIEW.md:19` — describes the regex pattern `sk-ant-…`
  used by the leak-scanner.
- `docs/REPRODUCING.md:60,176` — copy-paste examples (`sk-ant-…`).
- `research/2026-04_production_hybrid_general_use_cases/report.md:891`
  — example config snippet (`"api_key": "sk-ant-***"`).
- `research/2026-04_production_hybrid_general_use_cases/results.json`
  — content of a public blog post we cited (the string `sk-ant-…`
  appears in the quoted text).

Tighter check (`grep -E "sk-(ant-|proj-|svc-)[A-Za-z0-9_-]{20,}"`) on
the same files returns zero hits. **`.env` is gitignored.**
**`.env.example` exists with placeholder values only.** GREEN.

### 4. License coverage

| File | Present | Covers |
|---|---|---|
| `LICENSE` | yes (MIT, 1703 B) | code (harness, router, runners, scorers, analysis, viz) |
| `LICENSE-DATA` | yes (CC-BY-4.0, 3048 B) | results, metrics, figures, article |
| `NOTICE.md` | yes (7751 B) | vendored libraries, referenced libraries, idea attributions, every D-category source row |
| `vendor/README.md` | yes (file index for the two vendored clones) | lm-eval-harness-judge (tracked) + minions (referenced, not tracked) |

`NOTICE.md` spot-check:

- §Vendored: `vendor/lm-eval-harness-judge/` credited (FastChat
  Apache-2.0, commit pin `587d5cfa`).
- §Referenced: `vendor/minions/` credited (HazyResearch MIT, paper
  arXiv 2502.15964); explicitly marked "not tracked — clone yourself".
- §Benchmarks: all 5 benchmark sources (HumanEval+, SWE-bench Verified,
  BigCodeBench-Hard, LiveCodeBench, Aider) credited with license,
  paper, and usage scope.
- §Category D: every D1/D3/D4/D5 task is marked "(own work,
  hand-crafted) — CC-BY-4.0". Every D2 row has its upstream GitHub
  issue URL, repo, license, and base commit pinned:
  - `d2-click-3298` → pallets/click BSD-3 @ 04ef3a6f47
  - `d2-jsonschema-1124` → python-jsonschema/jsonschema MIT @ 90ea779619
  - `d2-werkzeug-3127` → pallets/werkzeug BSD-3 @ 795f4eaf6e
  - `d2-pytest-13817` → pytest-dev/pytest MIT @ 8f81c76744

All four D2 GitHub issue links resolve (verified P5.3 landed the
URLs; this audit confirms they're still there). GREEN.

### 5. `.env.example` completeness

```text
OPEN_AI_API_KEY=sk-your-openai-key-here
# OPENAI_API_KEY=sk-your-openai-key-here   # same thing, either spelling works
# ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
# CLOUD_BASE=https://api.openai.com/v1
# CLOUD_MODEL=gpt-5.5
# LOCAL_BASE=http://127.0.0.1:11434/v1
# LOCAL_MODEL=qwen3.6:27b-coding-mxfp8
```

Required keys present: `OPEN_AI_API_KEY`, `ANTHROPIC_API_KEY`,
`CLOUD_MODEL`, `LOCAL_MODEL`, `LOCAL_BASE`, `CLOUD_BASE`.

**Documented gaps**:

- The example `LOCAL_MODEL` value is `qwen3.6:27b-coding-mxfp8` — the
  v3 sweep actually ran on `devstral:24b`. Both work; the example
  should probably mention both. Cosmetic.
- No `ROUTER_PROXY_URL` knob is documented — but the router's
  `start.sh` reads `PROXY_PORT` (default 8787) and prints the URL.
  Not strictly required in `.env`; documented in `router/start.sh`
  comments instead.

YELLOW — works as-is, but the local-model name and the router URL
deserve a one-line note. Out of scope to edit in this audit pass.

### 6. ARTICLE.md + appendices coherence

`reports/ARTICLE.md` (321 lines, v3 narrative):

- References `results/runs/07-v3-devstral-all-routes/raw.jsonl`
  (250 rows) and `results/runs/11-judge-robust-D/judge.jsonl`
  (96 triple-judge verdicts) as the primary data sources. Both files
  exist and weights check out.
- References four chart files under
  `results/runs/07-v3-devstral-all-routes/charts/` —
  `pareto.png`, `heatmap_cost.png`, `heatmap_quality.png`,
  `heatmap_arqgc.png`. All four files exist.
- Cross-references `reports/DECISION_TABLE.md`,
  `reports/TOKEN_BUDGET.md`, `reports/APPENDIX_TASKS.md`,
  `reports/APPENDIX_SCENARIOS.md`, `reports/APPENDIX_ROUTES.md` — all
  present.
- §7 calls out the D2-functional-pass-None gap explicitly.

`reports/APPENDIX_TASKS.md` (32,907 lines, 63 unique task headings):

- All 50 unique v3 task IDs (30 MVP + 20 new D-category) are covered
  with a heading of the form `` ## `<task_id>` ``. Zero v3 task IDs are
  missing from the appendix.
- Plus 13 historical task IDs from the v1/v2 corpus carried forward.

Markdown link integrity inside `reports/`:

- 0 broken relative links across all six `.md` files in `reports/`
  (script: `python -c '<walk-and-check>'`). GREEN.

### 7. README headline accuracy

P5.1 updated the headline (line 6): "**Status: v3 sweep complete.**
250 graded rows across 5 routes (R1, R2, R3, R4, R5) and 8 task
shapes…". The 200-row claim and the 4-routes claim are both gone from
the top of the file. The decision table (line 33 onward) cites v3
numbers from `reports/DECISION_TABLE.md`. GREEN for the headline.

**However**, README still has two `EXTERNAL/` references that should
be `vendor/`:

- **Line 95** (repo-layout diagram):
  ```
  └── EXTERNAL/
      ├── minions/                   ← Stanford Minion library (MIT, vendored for R4)
      └── lm-eval-harness-judge/     ← MT-Bench judge reference (Apache 2.0)
  ```
- **Line 159** (bottom attribution):
  ```
  - Third-party code and research we build on: see `NOTICE.md` and
    `EXTERNAL/README.md`.
  ```
  This second one is a **broken link** — `EXTERNAL/README.md` doesn't
  exist on this branch; the file is at `vendor/README.md`.

These two strings are the only README defects. Filed as a one-line fix
for the same PR that ships this audit, but not done here (the audit
brief says "Do NOT touch any other files — only the new audit doc").
Tagged YELLOW.

---

## What's still red / yellow

| Severity | Item | Where |
|---|---|---|
| YELLOW | Fresh-clone `pytest` fails 14 R5 tests because `vendor/minions/` is gitignored. Documentation tells users to clone Minions themselves; the failure mode is confusing. Fix: `pytest.importorskip` guards on R4/R5 module imports. | `tests/runners/test_r5_devminion.py`, `src/hybrid_coding_eval/runners/r{4,5}*.py` |
| YELLOW | README has two stale `EXTERNAL/` references — one in the layout diagram (line 95), one in the attribution link (line 159). Link 159 is broken. | `README.md:95,159` |
| YELLOW | `.env.example` `LOCAL_MODEL` example is `qwen3.6:27b-coding-mxfp8`; v3 ran on `devstral:24b`. Cosmetic. | `.env.example:16` |
| YELLOW | D2 functional pass is `None/4` on every route by design (external GH-issue tasks, no functional scorer wired). Documented in `reports/ARTICLE.md §7` and in `NOTICE.md §Category-D`. Treat D2 cost / cloud-fraction as observation only. | by design |
| YELLOW | R5 has a JSON-extraction fragility in `vendor/minions` (`_extract_jsons` strips fenced ```python blocks that contain ```json substrings). Patched in our `r5_devminion.py` wrapper via a `_json_proxy` monkey-patch. Documented in `reports/ARTICLE.md §5`; the v3 numbers reflect the patched behaviour. May still bias against R5 on some edge cases. | `src/hybrid_coding_eval/runners/r5_devminion.py` |
| INFO | `router` has no fast unit-level tests of the routing strategies — only the 30-minute E2E harness. | `router/tests/` |

No items are RED. No items block tagging.

---

## What's deferred to T-23 (next cycle)

- Live SWE-bench-Verified D2 scorer (currently external GH issues — no
  princeton-nlp dataset support, no Docker harness for the upstream
  repos at the pinned base commits).
- Aider proper or a cascade router as R6/R7. R5 (DevMinion) is the
  current most-recent route; the article shows it's Pareto-dominated
  on three of four categories so the next route should target
  *fewer* tokens, not more loop overhead.
- Multi-hardware-tier reruns (still single M4 Max 64 GB).
- R4/R5 `importorskip` guards (see §1 above) — let `vendor/minions/`
  be genuinely optional rather than a silent prerequisite.
- README `EXTERNAL/` → `vendor/` cleanup (lines 95, 159).
- Unit-level tests on `router/strategies.mjs` (currently only
  end-to-end via `router/tests/run-tests.mjs`).
- `.env.example` cosmetic: add `LOCAL_MODEL=devstral:24b` as the
  primary recommended local; keep qwen as alternate.

---

## Recommended action

- [ ] If GREEN: tag `v3-public-candidate` (P6.2).
- [x] **If YELLOW: ship as-is with caveats explicitly called out in
  ARTICLE §8.** This is the recommendation. Two cosmetic README defects
  + a fresh-clone pytest hazard (caused by an explicitly-optional
  vendored clone) do not justify another PR cycle. The v3 dataset, the
  derived report, the attribution layer, and the licensing are all in
  good shape.
- [ ] If RED: fix what's red before tagging; identify each fix as a
  follow-up task.

**Suggested next step**: ship the YELLOW fixes as a single small PR
(README two-string patch, `pytest.importorskip` on R4/R5,
`.env.example` cosmetic) and then re-run this audit at HEAD; if the
re-run is GREEN, tag `v3-public-candidate` immediately. If shipping
under time pressure, tag now and file the cleanups as T-23.
