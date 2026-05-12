#!/usr/bin/env bash
# v3.3 smoke test: one D1 task per route × per local model.
# Catches OOM, quantization parse failures, response shape issues before
# committing to the multi-hour sweep. ~15 min per model.
#
# Usage:
#   ./bin/v3.3-smoke.sh                 # all 4 new models
#   ./bin/v3.3-smoke.sh 17 19           # variants 17 + 19 only

set -e
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$HERE"

VARIANTS=("17-qwen3coder-all-routes" "18-qwen2.5coder-all-routes" "19-glm47flash-all-routes" "20-gemma4-26b-all-routes")
if [ $# -gt 0 ]; then
  SELECTED=()
  for arg in "$@"; do
    for v in "${VARIANTS[@]}"; do
      if [[ "$v" == "${arg}-"* ]]; then SELECTED+=("$v"); break; fi
    done
  done
  VARIANTS=("${SELECTED[@]}")
fi

# Verify router is up
if ! curl -s --max-time 2 http://127.0.0.1:8787/healthz | grep -q '"ok": *true'; then
  echo "ERROR: router not running at :8787. Start it: (cd router && ./start.sh)"
  exit 1
fi

mkdir -p /tmp/v3.3-smoke
LOG="/tmp/v3.3-smoke/$(date +%Y%m%d_%H%M%S).log"
echo "Logging to $LOG"

for V in "${VARIANTS[@]}"; do
  echo "=== [$(date +%H:%M:%S)] Smoke test: $V ==="
  echo "=== [$(date +%H:%M:%S)] Smoke test: $V ===" >> "$LOG"

  # 1 task per category × R2 + R3 (heuristic) = 8 rows. ~10 min wall.
  # Uses --smoke flag to cap at 1 task per category.
  ./bench run --config "configs/variants/${V}.yaml" \
    --set out_dir="results/runs/smoke-${V}" \
    --set benchmark.routes=R2,R3 \
    --smoke \
    >> "$LOG" 2>&1 || { echo "FAILED: $V — see $LOG"; continue; }

  # Verify
  raw="results/runs/smoke-${V}/raw.jsonl"
  if [ ! -f "$raw" ]; then
    echo "FAIL: no raw.jsonl for $V"; continue
  fi
  rows=$(wc -l < "$raw" | tr -d ' ')
  errors=$(jq -s 'map(select(.error != null)) | length' "$raw" 2>/dev/null || echo "?")
  echo "  $V: $rows rows, $errors error rows"
done

echo "=== Smoke run complete. Full log: $LOG ==="
