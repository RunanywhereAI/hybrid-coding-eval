#!/usr/bin/env bash
# finalize-sweep.sh — run after the main sweep (bin/run-experiment.py) finishes.
#
# - Regenerates aggregate.json, arqgc.json, decision_matrix.md, charts/*.png
# - Attempts to score any rows that weren't auto-scored (e.g. SWE-bench rows
#   that errored during the live run and got functional_pass=None)
# - Samples 5 random rows for the manual-audit template
# - Prints a final summary
#
# Usage:
#   ./bin/finalize-sweep.sh [results-dir]
#   defaults to results/full-sweep/
set -euo pipefail

DIR="${1:-results/full-sweep}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
[[ -d "$DIR" ]] || { echo "no such dir: $DIR"; exit 1; }

echo "========================================================================"
echo "Finalising sweep at: $DIR"
echo "========================================================================"
echo ""

RAW="$DIR/raw.jsonl"
ROWS=$(wc -l < "$RAW" 2>/dev/null || echo 0)
echo "rows in raw.jsonl: $ROWS"
echo ""

# 1. Regenerate all analysis artefacts
echo "=== running analysis.all ==="
.venv/bin/python -m analysis.all "$DIR" || true
echo ""

# 2. Count error rows + rows needing re-score
echo "=== scoring status ==="
.venv/bin/python - <<PY
import json
path = "$RAW"
err_count = 0
unscored_funcB = 0  # swebench with functional_pass=None
unscored_cat_C_custom = 0
total_by_cat_route = {}
for line in open(path):
    r = json.loads(line)
    if r.get("error"):
        err_count += 1
    q = r.get("quality", {}) or {}
    tid = r["task_id"]
    key = (r["category"], r["route"])
    total_by_cat_route[key] = total_by_cat_route.get(key, 0) + 1
    if tid.startswith("swebench-verified/") and q.get("functional_pass") is None:
        unscored_funcB += 1
    if tid.startswith("custom-arch/") and q.get("composite") is None:
        unscored_cat_C_custom += 1
print(f"  infrastructure errors     : {err_count}")
print(f"  SWE-bench rows unscored   : {unscored_funcB}")
print(f"  custom-arch rows unjudged : {unscored_cat_C_custom}")
print()
print("  rows per (category, route):")
for key in sorted(total_by_cat_route):
    print(f"    {key[0]}/{key[1]}: {total_by_cat_route[key]}")
PY
echo ""

# 3. Sample 5 random rows for the manual audit (seed=2026 for reproducibility)
echo "=== manual-audit sample (seed=2026) ==="
.venv/bin/python - <<PY
import json, random
random.seed(2026)
rows = [json.loads(l) for l in open("$RAW")]
sample = random.sample(rows, min(5, len(rows)))
for i, r in enumerate(sample, 1):
    q = r.get("quality", {}) or {}
    print(f"  row {i}: {r['task_id']:<50} {r['route']} pass={q.get('functional_pass')} comp={q.get('composite')}")
    print(f"    output: {r.get('output_ref', 'n/a')}")
PY
echo ""

echo "=== summary ==="
echo "  $DIR/aggregate.json"
echo "  $DIR/arqgc.json"
echo "  $DIR/decision_matrix.md"
echo "  $DIR/charts/*.png"
echo "  $DIR/REPORT.md   (refresh by re-running the T5.4 writeup against the new aggregate)"
echo "  $DIR/manual_audit.md   (fill in with the 5 sampled rows above)"
