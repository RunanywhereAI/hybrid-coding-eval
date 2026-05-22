"""utils.py — a 'god module' that mixes five unrelated concerns.

Refactor target: split this file into one cohesive module per concern
and update ``main.py`` to import from the new layout. Preserve behaviour.

Current concerns (in order of appearance):
    1. logging configuration
    2. HTTP retry wrapper
    3. file-path helpers
    4. JSON (de)serialisation helpers
    5. string templating
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# 1. logging configuration
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s :: %(message)s"


def configure_logging(level: str = "INFO", *, stream=None) -> logging.Logger:
    """Install a stdout handler once and return the root logger."""
    root = logging.getLogger()
    if getattr(root, "_app_configured", False):
        return root
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(level.upper())
    root._app_configured = True  # type: ignore[attr-defined]
    return root


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# 2. HTTP retry wrapper
# ---------------------------------------------------------------------------

_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF = 0.25


def retry_call(
    fn: Callable[[], Any],
    *,
    retries: int = _DEFAULT_RETRIES,
    backoff: float = _DEFAULT_BACKOFF,
    exc: type[BaseException] = Exception,
) -> Any:
    """Call ``fn()`` with exponential back-off on ``exc``."""
    attempt = 0
    while True:
        try:
            return fn()
        except exc:
            attempt += 1
            if attempt > retries:
                raise
            time.sleep(backoff * (2 ** (attempt - 1)))


def http_get_with_retry(url: str, *, retries: int = _DEFAULT_RETRIES) -> str:
    import urllib.request

    def _do() -> str:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            return resp.read().decode("utf-8")

    return retry_call(_do, retries=retries)


# ---------------------------------------------------------------------------
# 3. file-path helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 4. JSON (de)serialisation helpers
# ---------------------------------------------------------------------------


def dumps_pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


def load_jsonl(path: str | os.PathLike) -> list[Any]:
    out: list[Any] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def dump_jsonl(path: str | os.PathLike, rows: list[Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str))
            fh.write("\n")


# ---------------------------------------------------------------------------
# 5. string templating
# ---------------------------------------------------------------------------

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
