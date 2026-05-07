#!/usr/bin/env python
"""Compat shim — the real script is :mod:`hybrid_coding_eval.cli.rescore`."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hybrid_coding_eval.cli.rescore import cli_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli_main(sys.argv[1:]))
