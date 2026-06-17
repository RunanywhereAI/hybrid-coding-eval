"""Merge CLI overrides onto a loaded :class:`BenchConfig`.

CLI overrides take precedence over YAML values. Overrides are passed
as dotted keys, e.g. ``models.cloud=gpt-5`` or ``benchmark.smoke=true``.
"""

from __future__ import annotations

from typing import Any

from .schema import BenchConfig

__all__ = ["apply_overrides"]


def _coerce(value: str) -> Any:
    """Best-effort scalar coercion from CLI string.

    - ``true``/``false`` → bool
    - digit-only → int
    - float-shaped → float
    - comma-separated → list of strings
    - else: leave as-is.
    """
    low = value.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    if low == "null" or low == "none":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if "," in value:
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def apply_overrides(config: BenchConfig, overrides: list[str]) -> BenchConfig:
    """Return a new config with dotted-key overrides applied.

    ``overrides`` is a list of ``key=value`` strings. Unknown keys or
    type-incompatible values raise :class:`ValueError`.
    """
    if not overrides:
        return config

    data = config.model_dump(mode="python")
    for raw in overrides:
        if "=" not in raw:
            raise ValueError(f"override must be KEY=VALUE, got {raw!r}")
        key, value = raw.split("=", 1)
        value = _coerce(value)

        cur = data
        parts = key.split(".")
        for p in parts[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                raise ValueError(f"override path {key!r} not valid on BenchConfig")
            cur = cur[p]
        leaf = parts[-1]
        if leaf not in cur and not _is_top_level_field(key):
            raise ValueError(f"override path {key!r} not valid on BenchConfig")
        cur[leaf] = value

    return BenchConfig.model_validate(data)


def _is_top_level_field(key: str) -> bool:
    """Allow overriding top-level fields that may not exist in the dumped dict."""
    return "." not in key
