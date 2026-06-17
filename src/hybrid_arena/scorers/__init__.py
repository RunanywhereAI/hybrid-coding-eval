"""Scorers that convert a model's raw output for a task into a ``Quality`` row.

Each scorer takes (task, model_output, ...) and returns a
``hybrid_arena.core.metrics.Quality``. Scorers are pure functions of
their inputs: they do not write results themselves — the agent runner is
responsible for assembling a ``ResultRow`` and persisting it.
"""
