"""Parity tests between ``router/pricing.mjs`` (JS) and ``lib/pricing.py``.

The JS proxy and the Python harness load the same ``lib/pricing_tables.json``
— these tests prove their ``costFor`` / ``compute_cost`` implementations are
semantically identical across the full input space.

Six targeted cases:

  1. Simple flat — 1000 prompt + 500 completion on ``openai-gpt5.5`` → $0.020.
  2. With cached tokens.
  3. With reasoning tokens (must NOT be double-counted inside completion).
  4. Unknown model → ``missing=True``, ``usd=0``.
  5. Local model via colon-convention → ``key='__local__'``, ``usd=0``.
  6. Date-suffixed model id normalises correctly.

Then a **100-sample parity test** — random usage records fed through both the
Python implementation and the JS implementation (via ``node -e``), asserting
both agree to 1e-6 USD.
"""

from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Make ``lib`` importable regardless of how pytest is invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hybrid_arena.core.pricing import (  # noqa: E402
    RATES_PER_M,
    compute_cost,
    normalise_model_id,
)

# --------------------------------------------------------------------------- #
# Targeted unit tests
# --------------------------------------------------------------------------- #


def test_simple_gpt_5_5_cost_is_exactly_two_cents():
    """1000 prompt + 500 completion on gpt-5.5 = $0.005 + $0.015 = $0.020."""
    r = compute_cost("gpt-5.5", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert r["missing"] is False
    assert r["key"] == "gpt-5.5"
    assert math.isclose(r["usd"], 0.020, abs_tol=1e-12)
    assert math.isclose(r["breakdown"]["input_uncached"], 0.005, abs_tol=1e-12)
    assert math.isclose(r["breakdown"]["output"], 0.015, abs_tol=1e-12)
    assert math.isclose(r["breakdown"]["input_cached"], 0.0, abs_tol=1e-12)


def test_with_cached_tokens_discounts_correctly():
    """5000 prompt (1000 cached) + 2000 completion on gpt-5.5.

    uncached = (5000-1000) * 5.0 / 1e6 = 0.020
    cached   = 1000 * 0.5 / 1e6       = 0.0005
    output   = 2000 * 30.0 / 1e6      = 0.060
    total    = 0.0805
    """
    usage = {
        "prompt_tokens": 5000,
        "completion_tokens": 2000,
        "prompt_tokens_details": {"cached_tokens": 1000},
    }
    r = compute_cost("gpt-5.5", usage)
    assert r["key"] == "gpt-5.5"
    assert math.isclose(r["breakdown"]["input_uncached"], 0.020, abs_tol=1e-12)
    assert math.isclose(r["breakdown"]["input_cached"], 0.0005, abs_tol=1e-12)
    assert math.isclose(r["breakdown"]["output"], 0.060, abs_tol=1e-12)
    assert math.isclose(r["usd"], 0.0805, abs_tol=1e-12)
    assert r["tokens"]["cachedTokens"] == 1000


def test_reasoning_tokens_are_not_double_counted():
    """Reasoning tokens ride INSIDE completion_tokens — don't re-charge them.

    completion_tokens includes reasoning per OpenAI's usage shape; the cost
    function surfaces reasoning only for transparency.
    """
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 800,  # includes the 300 reasoning below
        "completion_tokens_details": {"reasoning_tokens": 300},
    }
    r = compute_cost("gpt-5.5", usage)
    # If the implementation wrongly added reasoning it would be based on 1100
    # completion tokens → 0.033 output. Correct answer uses 800 → 0.024.
    assert math.isclose(r["breakdown"]["output"], 0.024, abs_tol=1e-12)
    assert math.isclose(r["usd"], 0.005 + 0.024, abs_tol=1e-12)
    assert r["tokens"]["reasoningTokens"] == 300
    assert r["tokens"]["completionTokens"] == 800


def test_unknown_model_returns_missing_true_and_zero_usd():
    r = compute_cost("some-model-that-does-not-exist", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert r["missing"] is True
    assert r["usd"] == 0.0
    assert r["key"] is None


def test_local_colon_id_normalises_and_costs_zero():
    r = compute_cost("qwen3-coder:30b", {"prompt_tokens": 1234, "completion_tokens": 5678})
    assert r["missing"] is False
    assert r["key"] == "__local__"
    assert r["usd"] == 0.0
    # And another with a more elaborate local id.
    assert normalise_model_id("qwen3.6:27b-coding-mxfp8") == "__local__"


def test_date_suffixed_id_normalises_to_base_family():
    assert normalise_model_id("gpt-5.5-2026-04-23") == "gpt-5.5"
    r = compute_cost("gpt-5.5-2026-04-23", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert r["key"] == "gpt-5.5"
    assert math.isclose(r["usd"], 0.020, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# 100-sample JS ↔ Python parity
# --------------------------------------------------------------------------- #


# Inline JS shim: reads JSONL records from stdin, writes one JSON cost object
# per line to stdout. Kept tiny so no npm deps are needed.
_JS_SHIM = r"""
import { costFor } from './router/pricing.mjs'
import { createInterface } from 'node:readline'
const rl = createInterface({ input: process.stdin })
const out = []
rl.on('line', (line) => {
  if (!line.trim()) return
  const { model, usage } = JSON.parse(line)
  const r = costFor(model, usage)
  out.push({ usd: r.usd, key: r.key, missing: r.missing })
})
rl.on('close', () => { process.stdout.write(out.map(o => JSON.stringify(o)).join('\n') + '\n') })
"""


def _gen_sample(rng: random.Random) -> dict:
    model_keys = [k for k in RATES_PER_M.keys()]
    # Also sometimes inject ids that exercise the normaliser path.
    choice = rng.random()
    if choice < 0.1:
        model = "qwen3-coder:30b"
    elif choice < 0.2:
        model = "gpt-5.5-2026-04-23"
    elif choice < 0.25:
        model = "some-nonexistent-model-xyz"
    else:
        model = rng.choice(model_keys)

    prompt = rng.randint(0, 10_000)
    completion = rng.randint(0, 10_000)
    cached = rng.randint(0, prompt) if prompt > 0 else 0
    reasoning = rng.randint(0, completion) if completion > 0 else 0

    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "prompt_tokens_details": {"cached_tokens": cached},
        "completion_tokens_details": {"reasoning_tokens": reasoning},
    }
    return {"model": model, "usage": usage}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_parity_100_random_records():
    rng = random.Random(20260505)
    samples = [_gen_sample(rng) for _ in range(100)]

    # --- Python side.
    py_results = [compute_cost(s["model"], s["usage"]) for s in samples]

    # --- JS side. Spawn node once; feed JSONL; collect JSONL.
    stdin_blob = "\n".join(json.dumps(s) for s in samples) + "\n"
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", _JS_SHIM],
        input=stdin_blob,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, f"node failed: stderr={proc.stderr}"
    js_lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(js_lines) == len(samples), (
        f"JS returned {len(js_lines)} lines, expected {len(samples)}"
    )
    js_results = [json.loads(ln) for ln in js_lines]

    # --- Compare.
    mismatches = []
    for i, (py, js, s) in enumerate(zip(py_results, js_results, samples)):
        if abs(py["usd"] - js["usd"]) > 1e-6:
            mismatches.append(
                f"[{i}] model={s['model']!r} py={py['usd']:.9f} js={js['usd']:.9f} "
                f"diff={py['usd'] - js['usd']:.2e}"
            )
        # And the normalised key must agree too.
        if py["key"] != js["key"]:
            mismatches.append(
                f"[{i}] model={s['model']!r} py.key={py['key']!r} js.key={js['key']!r}"
            )
        if py["missing"] != js["missing"]:
            mismatches.append(
                f"[{i}] model={s['model']!r} py.missing={py['missing']} js.missing={js['missing']}"
            )

    assert not mismatches, "JS↔Python parity failures:\n  " + "\n  ".join(mismatches[:20])
