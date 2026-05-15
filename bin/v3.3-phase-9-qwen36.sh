#!/usr/bin/env bash
# v3.3 Phase 9 — Qwen 3.6 family sweep.
#
# Two new local models added at owner's request after Phase 5 (gemma):
#   variant 21 — qwen3.6:27b-coding-mxfp8 ("Precision King", 8-bit, 31 GB)
#   variant 22 — qwen3.6:35b ("MoE Efficiency", Q4 MoE A3B, 22 GB)
#
# Same sweep shape as variants 17-20:
#   - Heuristic baseline: R2 + R3 + R4 + R5 × 50 tasks = 200 rows per model
#   - R3 × 4 alternative strategies (rules, llm-classifier, embedding-knn,
#     cascade) × 50 tasks = 200 rows per model
#   - Total: 400 rows per model × 2 models = 800 rows
#
# Expected: ~10h per model wall = ~20h total, ~$30 OpenAI gpt-5.5 + ~$2 judge.
#
# Resume-safe: every ./bench run uses --resume so re-running this script
# picks up where it left off via raw.jsonl dedup.

set -e
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$HERE"

log() { echo "=== [$(date +%Y-%m-%d_%H:%M:%S)] $* ==="; }

if ! curl -s --max-time 2 http://127.0.0.1:8787/healthz | grep -q '"ok": *true'; then
  log "ERROR: router not running at :8787"; exit 1
fi

STRATEGIES=(rules llm-classifier embedding-knn cascade)
VARIANTS=(
  "21-qwen3.6-27b-mxfp8-all-routes"
  "22-qwen3.6-35b-a3b-all-routes"
)

for VARIANT in "${VARIANTS[@]}"; do

  # Skip if Ollama doesn't have this model pulled — useful in case 35b pull
  # hasn't finished by the time Phase 9 fires. Owner can manually re-run later.
  MODEL=$(grep "^  local:" "configs/variants/${VARIANT}.yaml" | awk '{print $2}')
  if ! ollama list | awk '{print $1}' | grep -qx "$MODEL"; then
    log "Phase 9 — SKIP ${VARIANT}: model ${MODEL} not pulled. Re-run after 'ollama pull ${MODEL}'."
    continue
  fi

  log "Phase 9 — ${VARIANT} — heuristic baseline (R2+R3+R4+R5)"
  ./bench run --config "configs/variants/${VARIANT}.yaml" \
    --set benchmark.routes=R2,R3,R4,R5 \
    --resume || log "  WARN: ${VARIANT} heuristic baseline failed; continuing"

  for S in "${STRATEGIES[@]}"; do
    OUTDIR="results/runs/${VARIANT}-${S}"
    log "Phase 9 — ${VARIANT} × strategy=${S} — R3 only"
    ./bench run --config "configs/variants/${VARIANT}.yaml" \
      --set benchmark.routes=R3, \
      --set router.strategy="$S" \
      --set out_dir="$OUTDIR" \
      --resume || log "  WARN: ${VARIANT} × ${S} failed; continuing"
  done

  log "Phase 9 — ${VARIANT} — re-judge prose-scored rows (C-arch, D3, D4)"
  ./bench rejudge "results/runs/${VARIANT}" || true
  for S in "${STRATEGIES[@]}"; do
    ./bench rejudge "results/runs/${VARIANT}-${S}" || true
  done

  log "Phase 9 — ${VARIANT} — analyze"
  ./bench analyze "results/runs/${VARIANT}" || true
  for S in "${STRATEGIES[@]}"; do
    ./bench analyze "results/runs/${VARIANT}-${S}" || true
  done
done

log "Phase 9 complete."
./bin/v3.3-refresh-article.sh --commit || true
git push origin main 2>&1 | tail -3 || true
