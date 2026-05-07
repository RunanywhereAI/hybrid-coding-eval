"""Repo-root resolution.

Both Python and Node code in this repo share data files under
``configs/``. To keep the layers decoupled the loaders should resolve
paths against the repository root rather than hard-coding relative
traversals.

``repo_root()`` walks up from *this* file looking for the first
directory that contains ``pyproject.toml``. That marker is stable
(it's how ``pip install -e .`` finds the project) and lives at the
same depth forever, which means the walker is O(1) after the first
call.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

__all__ = ["repo_root", "pricing_tables_path"]


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the absolute path to the repository root.

    Raises :class:`RuntimeError` if no ancestor of this file contains
    ``pyproject.toml`` — which would only happen if the package has
    been copied out of its source tree.
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(
        f"repo_root() could not find pyproject.toml walking up from {here!s}"
    )


def pricing_tables_path() -> Path:
    """Absolute path to the shared pricing-tables JSON.

    Single source of truth for both the Python pricing helper
    (``hybrid_coding_eval.core.pricing``) and the Node router
    (``router/pricing.mjs``). Override with ``HYBRID_PRICING_TABLE``
    when you want to test a what-if scenario without editing the
    checked-in file.
    """
    import os

    override = os.environ.get("HYBRID_PRICING_TABLE")
    if override:
        return Path(override).resolve()
    return repo_root() / "configs" / "pricing" / "pricing_tables.json"
