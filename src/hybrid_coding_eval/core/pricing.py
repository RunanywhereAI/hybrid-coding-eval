"""Python mirror of ``router/pricing.mjs``.

Loads ``configs/pricing/pricing_tables.json`` at import time — the
same file the JS proxy reads — so the Python eval harness and the JS
router compute identical costs by construction. See
``tests/test_pricing_parity.py`` and ``tests/test_pricing_path_parity.py``
for proof.

Cost formula::

    usd = (prompt_tokens - cached_tokens) * input     / 1_000_000
        + cached_tokens                   * cache_read / 1_000_000
        + completion_tokens               * output     / 1_000_000

``completion_tokens`` already includes ``reasoning_tokens`` — do NOT add
reasoning separately; it's surfaced only for transparency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from .paths import pricing_tables_path

__all__ = [
    "RATES_PER_M",
    "PRICING_META",
    "normalise_model_id",
    "compute_cost",
    "fmt_usd",
    "fmt_tok",
]

logger = logging.getLogger(__name__)

# Shared source of truth — same JSON file loaded by ``router/pricing.mjs``.
_TABLES_PATH = pricing_tables_path()
with _TABLES_PATH.open("rb") as _fh_bytes:
    _RAW_BYTES = _fh_bytes.read()
_TABLES = json.loads(_RAW_BYTES.decode("utf-8"))
_TABLES_SHA256 = hashlib.sha256(_RAW_BYTES).hexdigest()

logger.info(
    "pricing tables loaded from %s (sha256=%s…)",
    _TABLES_PATH,
    _TABLES_SHA256[:12],
)

RATES_PER_M: dict[str, dict[str, float]] = _TABLES["rates_per_m"]
PRICING_META: dict[str, Any] = {
    "fetched_at": _TABLES.get("_meta", {}).get("fetched_at"),
    "source": _TABLES.get("_meta", {}).get("source"),
    "path": str(_TABLES_PATH),
    "sha256": _TABLES_SHA256,
}

# Matches OpenAI-style date suffix (e.g. ``-2026-04-23``) at end of string.
_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def normalise_model_id(model_id: str | None) -> str | None:
    """Map a backend-echoed model id to a pricing-table key.

    Mirrors ``normaliseModelId`` in ``router/pricing.mjs`` exactly:
      - Falsy input → ``None``.
      - Colon-convention (``qwen3-coder:30b``) → ``"__local__"``.
      - Exact match in the table wins.
      - Strip date suffix (``-YYYY-MM-DD``) and re-check.
      - Progressively shorter prefixes (split on ``-``) until something matches.
      - Otherwise ``None``.
    """
    if not model_id:
        return None
    s = str(model_id).lower().strip()
    if ":" in s:
        return "__local__"
    if s in RATES_PER_M:
        return s
    dated = _DATE_SUFFIX_RE.sub("", s)
    if dated in RATES_PER_M:
        return dated
    parts = dated.split("-")
    while len(parts) > 1:
        parts.pop()
        candidate = "-".join(parts)
        if candidate in RATES_PER_M:
            return candidate
    return None


def compute_cost(model_id: str | None, usage: dict[str, Any] | None) -> dict[str, Any]:
    """Return cost information for an OpenAI-shape ``usage`` dict.

    Returns a dict with the same shape as the JS ``costFor`` return value::

        {
            "usd": float,
            "breakdown": {"input_uncached": ..., "input_cached": ..., "output": ...},
            "key": str | None,
            "missing": bool,
            "tokens": {
                "promptTokens": int,
                "completionTokens": int,
                "cachedTokens": int,
                "reasoningTokens": int,
            },
        }

    When the model is unknown, returns ``usd=0`` and ``missing=True`` (never
    raises).
    """
    key = normalise_model_id(model_id)
    rates = RATES_PER_M.get(key) if key else None

    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0
    cached_tokens = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    reasoning_tokens = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0

    uncached_prompt = max(0, prompt_tokens - cached_tokens)

    tokens = {
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "cachedTokens": cached_tokens,
        "reasoningTokens": reasoning_tokens,
    }

    if not rates:
        return {
            "usd": 0.0,
            "breakdown": {"input_uncached": 0.0, "input_cached": 0.0, "output": 0.0},
            "key": key,
            "missing": True,
            "tokens": tokens,
        }

    input_uncached = (uncached_prompt / 1_000_000) * rates["input"]
    input_cached = (cached_tokens / 1_000_000) * rates["cache_read"]
    output = (completion_tokens / 1_000_000) * rates["output"]
    usd = input_uncached + input_cached + output

    return {
        "usd": usd,
        "breakdown": {
            "input_uncached": input_uncached,
            "input_cached": input_cached,
            "output": output,
        },
        "key": key,
        "missing": False,
        "tokens": tokens,
    }


def fmt_usd(n: float, sign: bool = False, pad: int = 0) -> str:
    """Same ``$`` formatter as ``fmtUSD`` in ``router/pricing.mjs``."""
    if not math.isfinite(n):
        return "$?"
    v = abs(n)
    if v == 0:
        s = "$0.0000"
    elif v < 0.0001:
        s = f"${n:.6f}"
    elif v < 0.01:
        s = f"${n:.5f}"
    elif v < 1:
        s = f"${n:.4f}"
    else:
        s = f"${n:.3f}"
    if sign and n > 0:
        s = "+" + s
    return s.rjust(pad) if pad else s


def fmt_tok(n: int | None, pad: int = 0) -> str:
    """Same as ``fmtTok`` in ``router/pricing.mjs`` — comma thousands, padded."""
    s = f"{(n or 0):,}"
    return s.rjust(pad) if pad else s
