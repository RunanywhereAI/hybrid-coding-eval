#!/usr/bin/env python3
"""Cross-model aggregator for v3.3 — reads each new-model run dir and
produces a model × route × shape decision-table-friendly markdown.

Run dirs consumed (each is one new local model under v3.3):
- results/runs/17-qwen3coder-all-routes/         (heuristic baseline R2+R3+R4+R5)
- results/runs/18-qwen2.5coder-all-routes/       (substitute for Llama 4 Scout)
- results/runs/19-glm47flash-all-routes/         (substitute for GLM-4.5-Air)
- results/runs/20-gemma4-26b-all-routes/

Each dir's raw.jsonl is consumed. Variants that haven't started yet
show _pending_.

For comparison, run 07's R1 baseline is reused (R1 doesn't depend on
local model — it's cloud-only) and shown as the reference row.

Usage:
    python3 bin/v3.3-aggregate-models.py                    # print to stdout
    python3 bin/v3.3-aggregate-models.py > /tmp/cross.md    # save
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict
from statistics import median

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "results" / "runs"
PRICE = json.loads((REPO / "configs/pricing/pricing_tables.json").read_text())["rates_per_m"]["gpt-5.5"]

MODELS = [
    ("17-qwen3coder-all-routes", "qwen3-coder:30b"),
    ("18-qwen2.5coder-all-routes", "qwen2.5-coder:32b"),
    ("19-glm47flash-all-routes", "glm-4.7-flash"),
    ("20-gemma4-31b-all-routes", "gemma4:31b"),
    ("21-qwen3.6-27b-mxfp8-all-routes", "qwen3.6:27b-coding-mxfp8"),
    ("22-qwen3.6-35b-a3b-all-routes", "qwen3.6:35b"),
]
SHAPES = ["A", "B", "C-bcb", "C-arch", "D1", "D2", "D3", "D4", "D5"]
ROUTES = ["R2", "R3", "R4", "R5"]


def cost(row):
    t = row["tokens"]
    cached = t.get("cache_read", 0)
    input_ = t.get("cloud_prompt", 0) - cached
    output = t.get("cloud_completion", 0)
    return (
        input_ * PRICE["input"] / 1_000_000
        + cached * PRICE.get("cache_read", PRICE["input"]) / 1_000_000
        + output * PRICE["output"] / 1_000_000
    )


def cloud_fraction(row):
    t = row["tokens"]
    cloud = t.get("cloud_prompt", 0) + t.get("cloud_completion", 0)
    local = t.get("local_prompt", 0) + t.get("local_completion", 0)
    total = cloud + local
    return cloud / total if total else 0.0


def passing(row):
    q = row.get("quality") or {}
    if q.get("functional_pass") is not None:
        return 1 if q["functional_pass"] else 0
    if q.get("composite") is not None:
        return 1 if q["composite"] >= 0.5 else 0
    return None


def shape_of(row):
    cat = row.get("category") or ""
    task = (row.get("task_id") or "").lower()
    if cat == "A":
        return "A"
    if cat == "B":
        return "B"
    if cat == "C":
        return "C-arch" if "custom" in task or "arch" in task else "C-bcb"
    if cat == "D":
        for s in ("d1", "d2", "d3", "d4", "d5"):
            if f"/{s}-" in task:
                return s.upper()
        return "D?"
    return "?"


def load_rows(dir_):
    p = dir_ / "raw.jsonl"
    if not p.exists():
        return None
    rows = []
    for line in p.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def passes_cell(rows, route, shape):
    """Return e.g. '3/4' or 'None/4' or '—'."""
    matching = [r for r in rows if r.get("route") == route and shape_of(r) == shape]
    if not matching:
        return "—"
    passes = [passing(r) for r in matching]
    n = len(matching)
    if all(p is None for p in passes):
        return f"None/{n}"
    n_pass = sum(p for p in passes if p is not None)
    return f"{n_pass}/{n}"


def main():
    print("# v3.3 cross-model decision matrix (live)")
    print()
    print("Per (model, route, shape) — passes / N. R2/R3/R4/R5 across all 4 new")
    print("local models. R1 baseline reused from run 07 (cloud-only, doesn't")
    print("depend on local model).")
    print()

    for variant_dir, model_name in MODELS:
        d = RUNS / variant_dir
        rows = load_rows(d)
        if rows is None:
            print(f"## {model_name} — _pending_ (no raw.jsonl yet)")
            print()
            continue

        n = len(rows)
        n_err = sum(1 for r in rows if r.get("error"))
        total_cost = sum(cost(r) for r in rows)
        med_cloud = median([cloud_fraction(r) for r in rows]) if rows else 0

        print(f"## {model_name} ({n} rows, {n_err} errors, ${total_cost:.2f} total, {med_cloud:.0%} median cloud_frac)")
        print()
        print("| route |  A  |  B  | C-bcb | C-arch | D1 | D2 | D3 | D4 | D5 |")
        print("| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |")
        for route in ROUTES:
            cells = [passes_cell(rows, route, sh) for sh in SHAPES]
            print(f"| {route} | " + " | ".join(cells) + " |")
        print()


if __name__ == "__main__":
    main()
