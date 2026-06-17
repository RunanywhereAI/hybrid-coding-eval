# `real-prs` — SWE-bench Verified (easy tier, 10 tasks)

The third task class in hybrid-arena: **real agentic software
engineering on real GitHub issues**. Each task is one pull-request-sized
bug-fix from a well-known Python project (Django, Sphinx, Astropy,
xarray…), graded by running the project's own test suite in a per-task
Docker container.

This task class is **not in the v1.4 / v1.5 canonical sweep** — Apple
Silicon hosts run the per-task x86 Docker images under emulation, which
makes a full sweep impractical on the same M4 Max laptop the rest of
the benchmark runs on. The adapter + verify-harness are kept so the
sweep can be picked up on an x86 Linux host in a later release.

## What's here

| file | purpose |
|---|---|
| `adapter.py` | `Task` dataclass + `load_tasks()` — pure Python, no Docker. |
| `tasks.jsonl` | 10 pinned tasks (`seed=42`, `difficulty="easy"`). Checked in. |
| `verify_harness.py` | Manual end-to-end sanity check of the Docker scoring harness. |

The **adapter** is what the agent runners consume to build prompts. It never
touches Docker. Running `python -m pytest tests/test_swebench_verified.py -v`
passes without Docker installed.

The **harness** (grading) is not in this file set — the scorer lives in
`scorers/swebench.py` (T3.2). This directory only contains a *verification*
script to confirm the harness path is usable on the current host before the
scorer is wired in.

## Upstream source

- Dataset: [`princeton-nlp/SWE-bench_Verified`](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified), split `test`, 500 rows.
- Paper: [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770) — Jimenez et al., 2024.
- Verified subset: human-validated by OpenAI + Princeton to drop instances with
  broken / ambiguous test oracles.
- License: **MIT** for the dataset. Individual test patches inherit their
  source repos' licences (all the repos we sample from are permissively
  licensed, mostly BSD-3).

## Difficulty tier

SWE-bench Verified rows carry a `difficulty` field with four buckets:

| bucket | count | meaning |
|---|---:|---|
| `<15 min fix` | 194 | Smallest, fastest-to-grade — **our "easy" tier.** |
| `15 min - 1 hour` | 261 | |
| `1-4 hours` | 42 | |
| `>4 hours` | 3 | |

We pin `difficulty="easy"` → `"<15 min fix"`. This is the bucket where open
local models have the best chance of matching frontier cloud models, which is
what our hybrid-routing experiment is measuring. It also keeps the per-task
Docker image pull and test runtime tractable.

## The 10 pinned tasks

Generated with `load_tasks(n=10, seed=42, difficulty="easy")`:

1. `astropy__astropy-7166`
2. `django__django-11163`
3. `django__django-11179`
4. `django__django-13512`
5. `django__django-15315`
6. `django__django-15863`
7. `pydata__xarray-4356`
8. `sphinx-doc__sphinx-7889`
9. `sphinx-doc__sphinx-9698`
10. `sphinx-doc__sphinx-9711`

Regenerate via:

```bash
python -c "
from hybrid_arena.tasks.real_prs.adapter import load_tasks, write_tasks_jsonl
write_tasks_jsonl(load_tasks(n=10, seed=42, difficulty='easy'))
"
```

## Infrastructure requirements (for scoring, not loading)

Loading tasks: **nothing special** (just `datasets`, which is in
`requirements.txt`).

Scoring tasks:

- **Docker** (Docker Desktop on macOS, or Docker Engine on Linux).
- **Disk**: each instance pulls a per-task image at ~300–700 MB, with a
  ~2 GB shared base image. For 10 tasks, budget ~8 GB; for the full 500-row
  dataset, ~50 GB. Use `--cache_level env` (or `none`) to prune.
- **CPU architecture**: SWE-bench images are built for **x86_64**. On Apple
  Silicon (M1–M4) they run via Rosetta + QEMU emulation.
- **Network**: images are pulled from `docker.io/swebench/sweb.eval.x86_64.<instance_id>:latest`.

### Apple Silicon caveat

**On M-series Macs the harness works but is slow.** Each x86 Docker image
runs under emulation; a single easy-tier instance can take 10–30 minutes
(image pull + test run). Building a local cache helps on subsequent runs
but the underlying tests always run under Rosetta.

For the MVP we document this honestly: **scoring reliability is verified on
x86 Linux**. On Apple Silicon the harness is usable for spot-checks but not
for full sweeps. Run full sweeps on an x86 Linux host (e.g. a VM / cloud
runner). The `verify_harness.py` script will exit with a clear "environment
cannot run the harness" message if the emulation path fails or times out.

## Running the harness verification

```bash
# from repo root, with .venv active
python -m hybrid_arena.tasks.real_prs.verify_harness
```

Exit codes:

- `0` — empty patch FAILS and gold patch PASSES: harness works end-to-end.
- `1` — harness ran but graded incorrectly (bug — file an issue).
- `2` — Docker/environment could not run the harness. Not necessarily a
  bug in this code — try again on x86 Linux.

The script loads task #1 (`astropy__astropy-7166` after seeded shuffle), runs
the harness twice (empty patch + gold patch), and checks each row in the
harness's output report.

## Why this task class matters

SWE-bench Verified easy tier is the gold-standard tier — real agentic
coding on real GitHub issues. The harness runs each task in a Docker
container with the repo's own test suite, giving binary pass/fail.
Frontier scores at time of writing: Claude Opus 4.6 77.2 %, GPT-5 74.9 %,
Devstral-Small-2-24B 72.2 % — the gap between the best open and the best
cloud model is ~5pp here, so hybrid routing should be measurable.

This is on the v1.6+ roadmap once we have an x86 host available for full
sweeps; the adapter + verify-harness ship today so contributors can pick
it up.
