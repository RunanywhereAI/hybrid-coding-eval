# NOTICE — third-party code and attributions

This project vendors, references, and re-implements ideas from a number
of upstream projects and research papers. This file enumerates every
case where attribution is legally or ethically required.

If you redistribute this repository, keep this file intact.

---

## Vendored source

### `vendor/opencode/`

- **Upstream**: opencode (the agent we wrap in `src/hybrid_coding_eval/agents/opencode.py`).
- **License**: MIT.
- **Status in this repo**: optional. Only cloned when
  `BENCH_SETUP_OPENCODE=1 ./bench setup` is run. See `vendor/README.md`
  for the fetch command + pin commit.
- **What we use**: the `opencode` CLI binary, invoked as a subprocess by
  our agent wrapper. We do not import any of its source as a library.
- **Modifications**: none inside `vendor/opencode/` — it is vendored
  read-only.

---

## Upstream agents (invoked as subprocesses, NOT vendored)

| Agent             | Upstream                                                                                | License            |
| ----------------- | --------------------------------------------------------------------------------------- | ------------------ |
| `aider`           | [Aider-AI/aider](https://github.com/Aider-AI/aider) (Paul Gauthier)                     | Apache 2.0         |
| `mini-swe-agent`  | [princeton-nlp/mini-swe-agent](https://github.com/princeton-nlp/mini-swe-agent)         | MIT                |
| `cline`           | [cline/cline](https://github.com/cline/cline) (driven through `vendor/cline-headless`)  | Apache 2.0         |
| `opencode`        | see above                                                                               | MIT                |

We invoke each as a CLI subprocess; no library code is copied or
modified. Our wrappers under `src/hybrid_coding_eval/agents/` only set
up environment, build the prompt, and parse the agent's output.

---

## Upstream benchmarks (referenced by task adapters)

| Benchmark         | Source                                                                                                   | License            | How we use it                                                  |
| ----------------- | -------------------------------------------------------------------------------------------------------- | ------------------ | -------------------------------------------------------------- |
| Aider polyglot    | [Aider-AI/aider](https://github.com/Aider-AI/aider) (Exercism Python subset)                             | Apache 2.0 / MIT   | `tasks/puzzles/` adapter pins 10 tasks                          |
| SWE-bench Verified| [princeton-nlp/SWE-bench](https://github.com/princeton-nlp/SWE-bench) (Jimenez et al., ICLR 2024)        | CC-BY-4.0          | `tasks/real_prs/` adapter pins a 5-task subset; scoring via upstream Docker harness |

Each adapter directory under `src/hybrid_coding_eval/tasks/<name>/`
carries a local README with the upstream attribution and pin commit.

---

## Ideas and methodology we build on (no code copied)

Attribution below follows academic custom — these are ideas /
measurement methods, not copyrightable code.

- **Architect / editor split** — originated by Aider. Our `phase-aware`
  routing strategy uses an architect-vs-editor heuristic; no code is
  copied.
- **Cascade routing (small-then-large)** — explored by FrugalGPT (Chen
  et al., arXiv 2305.05176) and RouteLLM (Ong et al., arXiv 2406.18665).
  Method influence only.
- **Bootstrap confidence intervals** — Efron, "Bootstrap Methods:
  Another Look at the Jackknife", Ann. Stat. 7(1) 1979. Implemented
  from scratch in `analysis/bootstrap.py`.
- **SWE-bench scoring harness** — referenced via subprocess in
  `scorers/swebench.py`; we do not reimplement scoring.

---

## `tasks/refactors/` (D-task fixtures)

A mix of hand-crafted scenarios (CC-BY-4.0) and derivations from real
public GitHub issues in permissively-licensed projects. No GPL, AGPL,
or proprietary sources are used. Task rows live in `tasks-d1.jsonl`,
`tasks-d3-d4.jsonl`, and `tasks-d5.jsonl`.

### D1 — small-feature-end-to-end (4)

Hand-crafted fixtures; prompts, tests, and reference solutions are the
authors' own work. No upstream code copied.

| Task ID                       | Source                  | Upstream repo | License    |
| ----------------------------- | ----------------------- | ------------- | ---------- |
| `real-dev/d1-rate-limit`      | (own work, hand-crafted)| —             | CC-BY-4.0  |
| `real-dev/d1-retry-decorator` | (own work, hand-crafted)| —             | CC-BY-4.0  |
| `real-dev/d1-json-schema`     | (own work, hand-crafted)| —             | CC-BY-4.0  |
| `real-dev/d1-auth-login`      | (own work, hand-crafted)| —             | CC-BY-4.0  |

### D2 — bug-fix-from-stacktrace (4, retired pre-v1.4)

D2 fixtures derive from real public GitHub issues on permissively-licensed
upstream projects. They are not part of the v1.4 sweep but remain
documented for the historical v3 dataset.

| Task ID                          | GitHub issue                                            | Upstream repo                  | License       | Base commit |
| -------------------------------- | ------------------------------------------------------- | ------------------------------ | ------------- | ----------- |
| `real-dev/d2-click-3298`         | https://github.com/pallets/click/issues/3298            | `pallets/click`                | BSD-3-Clause  | `04ef3a6f47`|
| `real-dev/d2-jsonschema-1124`    | https://github.com/python-jsonschema/jsonschema/issues/1124 | `python-jsonschema/jsonschema` | MIT          | `90ea779619`|
| `real-dev/d2-werkzeug-3127`      | https://github.com/pallets/werkzeug/issues/3127         | `pallets/werkzeug`             | BSD-3-Clause  | `795f4eaf6e`|
| `real-dev/d2-pytest-13817`       | https://github.com/pytest-dev/pytest/issues/13817       | `pytest-dev/pytest`            | MIT           | `8f81c76744`|

### D3 — refactor-across-files (4)

Hand-crafted fixtures; refactor targets, rubrics, and reference diffs
are the authors' own work.

| Task ID                                                | Source                  | License    |
| ------------------------------------------------------ | ----------------------- | ---------- |
| `real-dev/d3-extract-validation-helper`                | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d3-split-god-module`                         | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d3-replace-try-except-with-contextmanager`   | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d3-constants-to-enum`                        | (own work, hand-crafted)| CC-BY-4.0  |

### D4 — code-review (4)

Hand-crafted diffs and rubrics; the buggy/problematic PRs and their
critiques are the authors' own work.

| Task ID                                | Source                  | License    |
| -------------------------------------- | ----------------------- | ---------- |
| `real-dev/d4-review-pagination`        | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d4-review-cache-invalidation`| (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d4-review-sql-injection`     | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d4-review-timezone-handling` | (own work, hand-crafted)| CC-BY-4.0  |

### D5 — script-or-one-off (4)

Hand-crafted fixtures; input data and expected outputs are synthetic
and authored from scratch.

| Task ID                          | Source                  | License    |
| -------------------------------- | ----------------------- | ---------- |
| `real-dev/d5-todo-counter`       | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d5-csv-dedupe`         | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d5-log-errors-today`   | (own work, hand-crafted)| CC-BY-4.0  |
| `real-dev/d5-env-var-redactor`   | (own work, hand-crafted)| CC-BY-4.0  |

---

## This project's own license

- **Code**: MIT. See [`LICENSE`](./LICENSE).
- **Data / results / docs prose**: CC-BY-4.0. See
  [`LICENSE-DATA`](./LICENSE-DATA).

Nothing in this `NOTICE.md` supersedes or narrows those licenses; it
records the obligations we inherit from upstream work.
