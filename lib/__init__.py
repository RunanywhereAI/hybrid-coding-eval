"""Compat shim — real code lives at :mod:`hybrid_coding_eval.core`.

Kept only to let pre-reorg code paths (older tests, documentation
snippets, external scripts) keep importing ``from lib.X import Y``
during the mono-repo migration. Removed at T-06 once every call site
points at ``hybrid_coding_eval.core``.
"""
