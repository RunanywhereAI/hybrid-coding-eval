"""Command-line entry points.

Modules:

- :mod:`.run` — orchestrator (formerly ``bin/run-experiment.py``).
- :mod:`.env_detect` — hardware / software manifest writer.
- :mod:`.bench` — dispatcher wiring YAML config → the above. Added by T-07.

The v1.4 agentic cleanup removed the ``rescore`` / ``rejudge`` / ``judge``
/ ``report`` modules (post-sweep SWE-bench rescore + custom_arch judge
re-runs + appendix/article generator) along with the underlying R1–R5
non-agentic pipeline; the v1.4 publication surface is the GH release
tarball + article.

Each module exposes a ``main(argv: list[str] | None = None) -> int``
entry so they can be invoked via ``python -m hybrid_coding_eval.cli.X``
or through the top-level ``./bench`` wrapper after T-07.
"""
