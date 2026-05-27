"""Per-agent runners for the v1.4 agent-loop sweep.

Each module wraps one external coding agent and lets it drive its own
multi-turn tool use. This repo only owns the routing of each LLM call
(per-strategy) — the agent decides what to ask for, the router decides
where to ask.

* :mod:`hybrid_coding_eval.agents.mini_swe` — mini-swe-agent (Princeton),
  SWE-bench-style patches.
* :mod:`hybrid_coding_eval.agents.aider` — Aider, architect/editor protocol
  on small refactors and scripts.
* :mod:`hybrid_coding_eval.agents.opencode` — opencode TUI agent, free-form
  tool use.
* :mod:`hybrid_coding_eval.agents.cline` — Cline VSCode agent (headless).

Each runner exposes a ``run(task, ...) -> ResultRow`` function and a small
``__main__`` CLI for ad-hoc calls. The orchestrator in
:mod:`hybrid_coding_eval.core.experiment` ties them together.
"""
