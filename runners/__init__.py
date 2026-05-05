"""Per-route runners: R1 (cloud-only), R2 (local-only), R3 (hybrid architect).

Each runner exposes a ``run(task, ...) -> ResultRow`` function and a small
``__main__`` CLI for ad-hoc runs. The orchestrator in T4.1 ties them
together; for now they're self-contained so each can be built/tested in
isolation.
"""
