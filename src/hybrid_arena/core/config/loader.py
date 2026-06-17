"""YAML loader for :class:`BenchConfig`.

Reads a YAML file, substitutes ``${ENV:VAR}`` placeholders from the
process environment, then validates against
:class:`hybrid_arena.core.config.schema.BenchConfig`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .schema import BenchConfig

__all__ = ["load_config", "dump_schema_json"]


_ENV_RE = re.compile(r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute_env(obj: Any) -> Any:
    """Recursively substitute ``${ENV:FOO}`` placeholders.

    Missing env vars raise :class:`KeyError` so a typo is never silently
    evaluated to an empty string.
    """
    if isinstance(obj, str):
        def repl(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise KeyError(f"${{ENV:{name}}} referenced in config but not set")
            return os.environ[name]

        return _ENV_RE.sub(repl, obj)
    if isinstance(obj, list):
        return [_substitute_env(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _substitute_env(v) for k, v in obj.items()}
    return obj


def load_config(path: Path | str) -> BenchConfig:
    """Load ``path`` as YAML, do env substitution, validate.

    Raises :class:`pydantic.ValidationError` on malformed YAML /
    missing-required-fields / unknown-fields (``extra='forbid'``).
    """
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p}: top-level YAML must be a mapping, got {type(raw).__name__}")
    substituted = _substitute_env(raw)
    try:
        return BenchConfig.model_validate(substituted)
    except ValidationError as exc:
        raise ValueError(f"{p}: invalid config\n{exc}") from exc


def dump_schema_json() -> dict[str, Any]:
    """Return the JSON Schema document generated from :class:`BenchConfig`.

    Used at build time to regenerate ``configs/schema.json`` — that file
    is checked in for editor integrations (VS Code YAML extension, etc.)
    but is never hand-edited.
    """
    return BenchConfig.model_json_schema()
