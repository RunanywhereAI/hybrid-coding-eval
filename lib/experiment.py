"""Compat shim — see :mod:`hybrid_coding_eval.core.experiment`."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hybrid_coding_eval.core.experiment import *  # noqa: E402,F401,F403
from hybrid_coding_eval.core.experiment import (  # noqa: E402,F401
    CATEGORY_SOURCES,
    ROUTES,
    TaskPlan,
    build_task_plan,
    load_category_tasks,
    pair_already_done,
    run_pair,
    score_row,
    timestamp_dirname,
)
