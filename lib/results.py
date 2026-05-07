"""Compat shim — see :mod:`hybrid_coding_eval.core.results`."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hybrid_coding_eval.core.results import *  # noqa: E402,F401,F403
from hybrid_coding_eval.core.results import (  # noqa: E402,F401
    PRICING_SCENARIOS,
    aggregate_by,
    append_row,
    load_results,
)
