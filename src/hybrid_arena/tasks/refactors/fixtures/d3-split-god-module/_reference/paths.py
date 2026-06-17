"""File-path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def ensure_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_relpath(base: str | os.PathLike, target: str | os.PathLike) -> Path:
    """Return ``target`` relative to ``base`` or raise if target escapes base."""
    b = Path(base).resolve()
    t = Path(target).resolve()
    rel = t.relative_to(b)  # raises ValueError if outside
    return rel


def iter_files(root: str | os.PathLike, *, suffix: str | None = None):
    for p in Path(root).rglob("*"):
        if not p.is_file():
            continue
        if suffix is not None and p.suffix != suffix:
            continue
        yield p
