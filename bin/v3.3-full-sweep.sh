#!/usr/bin/env bash
# v3.3 master sweep — runs everything sequentially. ~96h total wall time.
# Use `nohup ./bin/v3.3-full-sweep.sh > /tmp/v3.3-sweep.log 2>&1 &` so it
# survives terminal/SSH disconnect.
#
# Sequence:
#   1. v3.2 devstral strategy sweep (5 strategies × 50 tasks R3 only)  ~12.5h
#   2-5. Per new-model sweep × 4 models
#        Each: heuristic baseline (R2+R3+R4+R5, 200 rows) + R3 × 4 other strategies (200 rows)
#        Per model: ~21h
#   Total: ~12.5 + 4×21 = ~96.5h
#
# Resume-safe: each sub-sweep uses ./bench run which honors --resume on (task_id, route)
# dedup via raw.jsonl. If interrupted, re-running this script picks up where it left off
# (just re-add the --resume flag to whichever variant was partial).

set -e
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$HERE"

# Verify prerequisites
if ! curl -s --max-time 2 http://127.0.0.1:8787/healthz | grep -q '"ok": *true'; then
  echo "ERROR: router not running. Start it: (cd router && ./start.sh)" >&2
  exit 1
fi

if ! ollama list | grep -q "devstral:24b"; then
  echo "ERROR: devstral:24b not pulled. Run: ollama pull devstral:24b" >&2
  exit 1
fi

REQUIRED_MODELS=("devstral:24b" "qwen3-coder:30b" "qwen2.5-coder:32b" "glm-4.7-flash" "gemma4:26b" "qwen3:0.6b" "nomic-embed-text")
for m in "${REQUIRED_MODELS[@]}"; do
  if ! ollama list | grep -q "^${m%:*}"; then
    echo "WARN: $m not pulled. The variants that need it will fail." >&2
  fi
done

STRATEGIES=(rules llm-classifier embedding-knn cascade)

log() { echo "=== [$(date +%Y-%m-%d_%H:%M:%S)] $* ==="; }

# ----- Phase 1: v3.2 devstral strategy sweep -----

log "Phase 1 — v3.2 devstral strategy sweep (5 variants × 50 tasks R3)"

for V in 12-r3-strategy-heuristic 13-r3-strategy-rules 14-r3-strategy-llm-classifier 15-r3-strategy-embedding-knn 16-r3-strategy-cascade; do
  log "Phase 1 — running $V"
  ./bench run --config "configs/variants/${V}.yaml" --resume || {
    echo "WARN: $V failed; continuing with next variant"
  }
done

# ----- Phase 2-5: Per new-model sweeps -----

for VARIANT in 17-qwen3coder-all-routes 18-qwen2.5coder-all-routes 19-glm47flash-all-routes 20-gemma4-26b-all-routes; do

  log "Model sweep — $VARIANT — heuristic baseline (R2+R3+R4+R5)"
  ./bench run --config "configs/variants/${VARIANT}.yaml" \
    --set benchmark.routes=R2,R3,R4,R5 \
    --resume || {
    echo "WARN: $VARIANT heuristic baseline failed; continuing"
  }

  for S in "${STRATEGIES[@]}"; do
    OUTDIR="results/runs/${VARIANT}-${S}"
    log "Model sweep — $VARIANT — strategy=$S — R3 only"
    ./bench run --config "configs/variants/${VARIANT}.yaml" \
      --set benchmark.routes=R3 \
      --set router.strategy="$S" \
      --set out_dir="$OUTDIR" \
      --resume || {
      echo "WARN: $VARIANT × $S failed; continuing"
    }
  done

  log "Model sweep — $VARIANT — re-judge (C-arch, D3, D4)"
  ./bench rejudge "results/runs/${VARIANT}" || true
  for S in "${STRATEGIES[@]}"; do
    ./bench rejudge "results/runs/${VARIANT}-${S}" || true
  done

  log "Model sweep — $VARIANT — analyze"
  ./bench analyze "results/runs/${VARIANT}" || true
  for S in "${STRATEGIES[@]}"; do
    ./bench analyze "results/runs/${VARIANT}-${S}" || true
  done
done

# ----- Final aggregation -----

log "Final — analyze v3.2 devstral strategy sweep dirs"
for V in 12-r3-strategy-heuristic 13-r3-strategy-rules 14-r3-strategy-llm-classifier 15-r3-strategy-embedding-knn 16-r3-strategy-cascade; do
  ./bench analyze "results/runs/${V}" || true
done

log "v3.3 sweep complete. Results in results/runs/{12..20}*/"
log "Next: run analysis + write reports/ARTICLE.md §3.5 + §4.4"
