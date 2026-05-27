# Contributing to hybrid-coding-eval

Thanks for your interest. This project is a **research artifact**, not a
product, but contributions — especially new local models, new agents, and
new routing strategies — are welcome.

By contributing you agree your changes are released under the same terms
as the rest of the repo: **MIT** for code, **CC-BY-4.0** for documentation,
data, and results.

---

## Environment setup

```bash
git clone https://github.com/RunanywhereAI/hybrid-coding-eval
cd hybrid-coding-eval

python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

cp .env.example .env                # add OPEN_AI_API_KEY
./bench setup                       # builds Docker image, pulls aux models, installs aider + cline
```

`./bench setup` is idempotent — safe to re-run. The one-command reproducer
at `scripts/reproduce.sh --smoke` runs setup + a 1-task smoke sweep end-to-end.

## Running tests

```bash
# fast tests (no Docker / Ollama / network)
.venv/bin/pytest tests/ -q -m 'not slow'

# one file
.venv/bin/pytest tests/test_orchestrator.py -q

# lint
.venv/bin/ruff check src/ tests/
```

All PRs must pass `pytest -m 'not slow'` and `ruff check src/ tests/`. CI
runs both on every push (see `.github/workflows/ci.yml`).

---

## Adding a new local model

The most common contribution; ~90 seconds for an Ollama model.

```bash
ollama pull <new-model>
./scripts/reproduce.sh \
    --config configs/v1.4-canonical-gemma4.yaml \
    --set models.local=<new-model> \
    --set out_dir=results/runs/v1.4-<new-model> \
    --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
./bench analyze results/runs/v1.4-<new-model>
```

The PR description should include:

- Model name, parameter count, quantization
- The smoke `progress.log`
- The `aggregate.json` and `bootstrap_cis.json` from the analyse step
- A one-line take vs the gemma4/qwen3-coder/qwen3.6 baselines

Datasets are accepted as a separate review pass — the YAML config alone
is enough for a first PR.

## Adding a new agent

1. Write `src/hybrid_coding_eval/agents/<name>.py` exposing
   `run(task, *, proxy_url, ...) -> ResultRow`. Keep it ≤ 250 LOC; copy
   the style of an existing agent (e.g. `agents/mini_swe.py`).
2. Add `<name>` to the `Agent` `Literal` in
   `src/hybrid_coding_eval/core/config/schema.py`.
3. Register it in `core/experiment.py:_runner_for(agent)` and in the
   `ROUTES` tuple.
4. Add `tests/agents/test_<name>.py` covering: import, dispatch, and an
   error-row when the underlying subprocess fails.
5. Regenerate the JSON schema: `./bench schema --out configs/schema.json`.
6. Update the agent table in `docs/HYBRID_ROUTING_DESIGN.md §3`.

## Adding a new routing strategy

1. Add the strategy function in `router/strategies.mjs` and register it
   in `STRATEGY_REGISTRY` at the bottom of that file.
2. Add the name to the `RouteStrategy` `Literal` in
   `src/hybrid_coding_eval/core/config/schema.py`.
3. Regenerate the JSON schema: `./bench schema --out configs/schema.json`.
4. Add a row to the strategy table in `docs/HYBRID_ROUTING_DESIGN.md §4`.
5. Add a test under `tests/test_router_strategies.py` (or
   `router/tests/`).

## Adding a new task class

1. Create `src/hybrid_coding_eval/tasks/<class>/` with an `adapter.py`
   (loads tasks) and a `scorers.py` (scores a `ResultRow`).
2. Register the class in `core/experiment.py:CATEGORY_SOURCES` and in
   the `TaskClass` `Literal` in `core/config/schema.py`.
3. Add a row to the task-class table in
   `docs/HYBRID_ROUTING_DESIGN.md §5`.
4. Document upstream attribution + license in `NOTICE.md`.
5. Add at least one unit test loading the first task.

---

## Pull request style

- **One logical change per PR.**
- **Title format:** `<area>(<scope>): <imperative summary>` —
  e.g. `feat(cli): bench setup subcommand`, `fix(scorer): handle empty stdout`.
- **Body:** what changed, why, and any reproducibility implications. Use
  the PR template (`.github/PULL_REQUEST_TEMPLATE.md`).

## Code style

- **Python:** ruff with the repo's default config. Public functions in
  `src/hybrid_coding_eval/core/` should have brief docstrings. Type hints
  encouraged.
- **JavaScript (router):** plain Node, no transpilation; match existing style.
- **No comments that just narrate code.** Comments should explain
  non-obvious intent, trade-offs, or constraints.

## Project principles

- **Reproducibility beats convenience.** Every published number traces
  back to `(task_id, route, router_strategy, seed, config_sha,
  hardware_profile_ref)` in `raw.jsonl`.
- **Cost honesty.** Costs are derived from `tokens × pinned pricing` at
  analyse-time. Pricing edits go in `configs/pricing/pricing_tables.json`
  and ripple through `./bench analyze` without re-running inference.
- **No silent dependencies.** New runtime deps go in `pyproject.toml`
  with a pinned range and a one-line justification in the PR.
- **Tests are sandboxed.** Functional scoring runs in Docker with
  `--network none`, memory caps, and 60-second wall-clock timeouts.

---

## Reporting bugs

Use the templates in `.github/ISSUE_TEMPLATE/`:

- `bug_report.md` — crashes, hangs, wrong numbers
- `new_model.md` — propose adding a model to the canonical benchmark
- `reproducibility_issue.md` — "I can't reproduce the published numbers"

For security vulnerabilities, follow [`SECURITY.md`](./SECURITY.md)
(private email — please don't open public issues).

Conduct: this project follows [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).
