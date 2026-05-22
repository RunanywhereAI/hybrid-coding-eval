# Category D — Real-developer tasks

Real-developer tasks across 5 shapes:

- **D1** — feature (add a small endpoint / handler / utility)
- **D2** — bug-fix (reproducer + patch)
- **D3** — refactor (extract / move code; behaviour preserved)
- **D4** — review (given a PR diff, produce a critique)
- **D5** — script (one-shot data-munging / CLI glue)

Populated incrementally by **P1.1–P1.4**. See `adapter.py` module
docstring for the full `tasks.jsonl` schema, and refer to
`fixtures/<slug>/` for per-task fixture layout.

Scoring lives in `scorers.py` (stub until P2.1). D1/D2/D5 will be
scored functionally via the fixture's pytest/jest file; D3/D4 by the
LLM-judge against the 5-dimension rubric shipped on each row.

## Attribution

Per-task source URLs, upstream repos, SPDX licenses, and (for D2) base
commits are enumerated in the repo-root `NOTICE.md` under the section
"Category D — real-developer tasks". `LICENSE-DATA` at the repo root
additionally clarifies how the CC-BY-4.0 data license and the per-task
upstream licenses interact for fixtures under `fixtures/`.
