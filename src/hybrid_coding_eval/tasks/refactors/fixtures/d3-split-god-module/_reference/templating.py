"""String templating helpers: ``render`` and ``slugify``."""

from __future__ import annotations

import re
from typing import Any

_TEMPLATE_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)\}")


def render(template: str, **values: Any) -> str:
    """Render ``{name}`` placeholders with ``values``. Missing keys raise KeyError."""
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(key)
        return str(values[key])

    return _TEMPLATE_RE.sub(repl, template)


def slugify(text: str) -> str:
    text = text.strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")
