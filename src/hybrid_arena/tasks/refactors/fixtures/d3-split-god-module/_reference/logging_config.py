"""Logging configuration — one-shot install + named logger factory."""

from __future__ import annotations

import logging
import sys

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
