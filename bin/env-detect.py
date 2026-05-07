#!/usr/bin/env python
"""Compat shim — the real script is :mod:`hybrid_coding_eval.cli.env_detect`.

Re-exports every public attribute so callers that ``importlib``-load
this file (e.g. tests) keep seeing the same surface they did before
the reorg.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hybrid_coding_eval.cli import env_detect as _impl  # noqa: E402

# Re-export all public attributes onto this module's namespace.
for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)


if __name__ == "__main__":
    raise SystemExit(_impl.main(sys.argv[1:]))
