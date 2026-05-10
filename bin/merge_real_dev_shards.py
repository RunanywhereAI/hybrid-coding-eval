#!/usr/bin/env python
"""Merge the four per-shape ``tasks-d*.jsonl`` shards into ``tasks.jsonl``.

Phase-1 of P2.1 laid down twenty real-developer tasks across four shard
files (D1, D2, D3+D4, D5) so each phase-agent could edit a disjoint file.
The orchestrator's ``real_dev`` adapter reads exactly one ``tasks.jsonl``,
so we concatenate the shards here.

Interleaving order
------------------

We *round-robin* the shards by shape so the first five rows of the merged
file hit all five shapes in order D1 → D2 → D3 → D4 → D5. This makes the
``--tasks 5`` / smoke filter produce one task per shape without needing
new config plumbing. After the first pass, the remaining rows follow the
same round-robin until every shard is exhausted.

Layout produced
---------------

``tasks.jsonl`` (in ``benchmarks/real_dev/``) — 20 rows, one JSON object
per line. Each row's ``shape`` is one of D1/D2/D3/D4/D5. IDs are unique
across the file.

Shards are left in place for auditability: a reviewer can diff any given
shape's shard against the merged file.

Invariants enforced (raises ``SystemExit(2)`` on failure)
---------------------------------------------------------

- every shard row parses as JSON with an ``id`` and a ``shape``;
- shape matches the shard it came from (D1 rows can't sneak into the D5
  shard, etc.);
- IDs are globally unique;
- total row count equals 20 (four phase agents shipped 4+4+8+4).

Run
---

``python bin/merge_real_dev_shards.py`` from the repo root. Exits 0 on
success and prints a short summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_DEV_DIR = (
    _REPO_ROOT / "src" / "hybrid_coding_eval" / "benchmarks" / "real_dev"
)

# Shards, in the order their shapes should first appear in the merged file.
# Each entry: (shard filename, the shapes we expect to find in that shard).
# We preserve in-file order within each shape; the round-robin happens
# across shapes.
SHARDS: list[tuple[str, tuple[str, ...]]] = [
    ("tasks-d1.jsonl", ("D1",)),
    ("tasks-d2.jsonl", ("D2",)),
    ("tasks-d3-d4.jsonl", ("D3", "D4")),
    ("tasks-d5.jsonl", ("D5",)),
]

EXPECTED_TOTAL = 20


def _read_shard(path: Path, allowed_shapes: Iterable[str]) -> list[dict]:
    allowed = set(allowed_shapes)
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON ({exc})")
            if "id" not in row:
                raise SystemExit(f"{path}:{lineno}: missing 'id'")
            if "shape" not in row:
                raise SystemExit(f"{path}:{lineno}: missing 'shape'")
            if row["shape"] not in allowed:
                raise SystemExit(
                    f"{path}:{lineno}: shape {row['shape']!r} not in allowed "
                    f"{sorted(allowed)} for this shard"
                )
            rows.append(row)
    return rows


def _round_robin_by_shape(
    rows_by_shape: dict[str, list[dict]],
    shape_order: list[str],
) -> list[dict]:
    """Interleave rows so the first N rows cover every shape once (for N=5).

    Within each shape, preserves the shard's file order.
    """
    queues = {shape: list(rows_by_shape[shape]) for shape in shape_order}
    out: list[dict] = []
    while any(queues[s] for s in shape_order):
        for shape in shape_order:
            if queues[shape]:
                out.append(queues[shape].pop(0))
    return out


def main() -> int:
    rows_by_shape: dict[str, list[dict]] = {}
    for shard_name, shapes in SHARDS:
        shard_path = _REAL_DEV_DIR / shard_name
        if not shard_path.is_file():
            raise SystemExit(f"missing shard: {shard_path}")
        shard_rows = _read_shard(shard_path, shapes)
        for row in shard_rows:
            rows_by_shape.setdefault(row["shape"], []).append(row)

    shape_order = ["D1", "D2", "D3", "D4", "D5"]
    # Every shape must be represented.
    for shape in shape_order:
        if not rows_by_shape.get(shape):
            raise SystemExit(f"no rows found for shape {shape!r}")

    merged = _round_robin_by_shape(rows_by_shape, shape_order)

    # Invariants.
    if len(merged) != EXPECTED_TOTAL:
        raise SystemExit(
            f"expected {EXPECTED_TOTAL} rows, got {len(merged)}"
        )
    ids = [row["id"] for row in merged]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise SystemExit(f"duplicate ids: {dupes}")

    out_path = _REAL_DEV_DIR / "tasks.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in merged:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Summary.
    shape_counts: dict[str, int] = {}
    for row in merged:
        shape_counts[row["shape"]] = shape_counts.get(row["shape"], 0) + 1
    print(f"wrote {out_path} ({len(merged)} rows)")
    for shape in shape_order:
        print(f"  {shape}: {shape_counts.get(shape, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
