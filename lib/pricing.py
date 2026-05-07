"""Compat shim — see :mod:`hybrid_coding_eval.core.pricing`."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hybrid_coding_eval.core.pricing import *  # noqa: E402,F401,F403
from hybrid_coding_eval.core.pricing import (  # noqa: E402,F401
    PRICING_META,
    RATES_PER_M,
    compute_cost,
    fmt_tok,
    fmt_usd,
    normalise_model_id,
)
