"""Command-line entry points.

Modules:

- :mod:`.bench` — the ``./arena`` dispatcher. Wires every other CLI
  subcommand (``sweep``, ``run``, ``analyze``, ``token-budget``,
  ``setup``, ``schema``, ``show-config``, ``env-detect``, and the
  ``start`` / ``pause`` / ``resume`` / ``stop`` / ``status`` lifecycle
  commands).
- :mod:`.run` — single-pass sweep orchestrator (one
  ``(strategy, seed)`` pass). Invoked from ``arena sweep`` per pass.
- :mod:`.env_detect` — hardware / software manifest writer
  (``arena env-detect``).

Each module exposes a ``main(argv: list[str] | None = None) -> int``
entry so they can be invoked via ``python -m hybrid_arena.cli.X``
or through the top-level ``./arena`` wrapper.
"""
