#!/usr/bin/env bash
# v3.3 Phase 8 — recover missed strategy sub-sweeps for new models.
#
# The master sweep (bin/v3.3-full-sweep.sh) had a bug in its strategy loop:
# `--set benchmark.routes=R3` (single value) failed Pydantic validation
# (expects a list). The fix is `R3,` (trailing comma forces list parsing
# in core/config/resolve.py:_coerce). All 16 strategy sub-sweeps for the
# 4 new models silently exited with validation errors.
#
# This script recovers the missed strategy × model matrix. Scoped to the
# 2 most-informative strategies from Phase 1 (cascade + llm-classifier)
# × 4 new local models = 8 variants × 50 R3 tasks = 400 rows.
#
# Why these 2 strategies (not all 4):
#   - cascade   — best-Pareto strategy in Phase 1 (15% cheaper, +1 on D5)
#   - llm-classifier — biggest cost-saver in Phase 1 (57% cheaper) but tanks SWE-bench
# The other two (rules, embedding-knn) were both *worse than heuristic*
# in Phase 1; testing them across new models adds dataset volume but
# little new insight.
#
# Skip-safe: re-runs check raw.jsonl row counts and skip variants ≥ 50 rows.

set -e
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$HERE"

log() { echo "=== [$(date +%Y-%m-%d_%H:%M:%S)] $* ==="; }

# Verify router is up (Phase 8 doesn't restart it — uses ambient state from 6+7's last restore)
if ! curl -s --max-time 2 http://127.0.0.1:8787/healthz | grep -q '"ok": *true'; then
  log "ERROR: router not running at :8787"; exit 1
fi

VARIANTS=(
  "17-qwen3coder-all-routes"
  "18-qwen2.5coder-all-routes"
  "19-glm47flash-all-routes"
  "20-gemma4-31b-all-routes"
)

STRATEGIES=(cascade llm-classifier)

for V in "${VARIANTS[@]}"; do
  for S in "${STRATEGIES[@]}"; do
    OUTDIR="results/runs/${V}-${S}"
    log "Phase 8 — ${V} × strategy=${S}"

    if [ -f "$OUTDIR/raw.jsonl" ] && [ "$(wc -l < "$OUTDIR/raw.jsonl" | tr -d ' ')" -ge 50 ]; then
      log "  SKIP — already has 50+ rows"
      continue
    fi

    ./bench run --config "configs/variants/${V}.yaml" \
      --set benchmark.routes=R3, \
      --set router.strategy="$S" \
      --set out_dir="$OUTDIR" \
      --resume || log "  WARN: ${V} × ${S} failed; continuing"
  done

  # Re-judge prose-scored rows for both strategy variants of this model
  for S in "${STRATEGIES[@]}"; do
    ./bench rejudge "results/runs/${V}-${S}" || true
    ./bench analyze "results/runs/${V}-${S}" || true
  done
done

log "Phase 8 complete."
./bin/v3.3-refresh-article.sh --commit || true
git push origin main 2>&1 | tail -3 || true

log "Launching Phase 9 — Qwen 3.6 27B-mxfp8 + 35B-A3B sweeps…"
exec ./bin/v3.3-phase-9-qwen36.sh
