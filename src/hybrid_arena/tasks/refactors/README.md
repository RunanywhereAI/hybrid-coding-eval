# `refactors` — real-developer Python refactor tasks

A hand-written task class meant to look like the kind of small Python
work a developer actually does in a working session: implement a
feature, fix a bug from a stack trace, refactor a small module, review
a PR diff, or write a one-shot script. Six shapes total:

| Shape | What | Scored by |
| ----- | ---- | --------- |
| `D1` | Implement a small feature in an existing file (e.g. `auth.login()`) | Overlay + pytest |
| `D2` | Fix a real upstream bug given the stack trace; return a unified diff | LLM-judge against rubric (kept for reference, not in canonical sweep) |
| `D3` | Refactor (extract / split / move code; behaviour preserved) | LLM-judge against rubric |
| `D4` | Review a PR diff and produce a structured critique | LLM-judge against rubric |
| `D5` | One-shot script (Python or bash) for data-munging / CLI glue | Overlay + pytest |
| `D6` | **Hard implementation challenge** (v1.5): single-file algorithmic + state-machine problems calibrated to stress 30B local models | Overlay + pytest |

The v1.4 canonical sweep uses **D1 + D5** only (eight tasks). v1.5 adds
the four D6 tasks. D2/D3/D4 are retained as fixtures + scorers but not
part of the headline benchmark.

The `tasks.jsonl` file at this directory holds one JSON object per
task. Each row carries `id`, `shape`, `prompt`, `fixtures_dir` (relative
to this directory), `tests` (path to the pytest test file used for
overlay scoring), and per-row attribution (`source_url`, `source_license`).

## Layout

```text
refactors/
├── README.md            (you are here)
├── adapter.py           — loads tasks.jsonl into the harness
├── scorers.py           — dispatches per-shape scoring
├── tasks.jsonl          — task metadata
└── fixtures/
    ├── d1-rate-limit/
    │   ├── app.py
    │   ├── middleware.py
    │   ├── test_rate_limit.py
    │   └── _reference/  — reference solution (used for scoring only)
    ├── d6-lru-ttl-cache/
    └── ...
```

## Attribution

D1–D5 fixtures are original work, **CC-BY-4.0**. D2 reproducers
reference real upstream issues; the per-task `source_url` and
`base_commit` in `tasks.jsonl` point to the canonical issue and the
upstream repo (pytest, jsonschema, click, werkzeug). The fixture files
are minimised reproductions, not redistributions of those projects.
