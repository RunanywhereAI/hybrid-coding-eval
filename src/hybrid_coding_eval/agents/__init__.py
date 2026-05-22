"""Per-agent runners for the v1.4 agent-only sweep.

The kept runners wrap external coding-agent processes and let them
drive multi-turn tool use; this repo only owns the routing of each LLM
call (per-strategy):

* :mod:`r6_mini_swe_agent` — mini-swe-agent on SWE-bench-style patches.
* :mod:`r7_aider` — Aider on small refactors / scripts.
* :mod:`r8_opencode` — opencode (TUI agent) on free-form tasks.

Agents B and C add :mod:`r9_claude_code` (Claude Code) and
:mod:`r10_cline` (Cline) in parallel during the v1.4 cleanup.

Each runner exposes a ``run(task, ...) -> ResultRow`` function and a
small ``__main__`` CLI for ad-hoc runs. The orchestrator in
:mod:`hybrid_coding_eval.core.experiment` ties them together.
"""
