"""Command-line entry points.

Modules:

- :mod:`.run` — orchestrator (formerly ``bin/run-experiment.py``).
- :mod:`.env_detect` — hardware / software manifest writer.
- :mod:`.rescore` — post-sweep SWE-bench rescore.
- :mod:`.rejudge` — post-sweep Opus re-judge of custom_arch.
- :mod:`.judge` — one-off Opus judge runner.
- :mod:`.bench` — dispatcher wiring YAML config → the above. Added by T-07.

Each module exposes a ``main(argv: list[str] | None = None) -> int``
entry so they can be invoked via ``python -m hybrid_coding_eval.cli.X``
or through the top-level ``./bench`` wrapper after T-07.
"""
