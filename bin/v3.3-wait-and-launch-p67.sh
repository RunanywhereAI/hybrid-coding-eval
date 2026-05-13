#!/usr/bin/env bash
# Watcher: polls the master sweep PID; when it exits, kicks off Phase 6 + 7.
# Hands-free chaining — designed to be launched in background and forgotten.
#
# Usage:
#   nohup caffeinate -i ./bin/v3.3-wait-and-launch-p67.sh > /tmp/v3.3-watcher.log 2>&1 &

set -e
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$HERE"

MASTER_PID="${MASTER_PID:-27730}"

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "Watching master sweep PID=${MASTER_PID}…"

# Poll until the master sweep PID no longer exists.
while kill -0 "$MASTER_PID" 2>/dev/null; do
  sleep 300   # 5-min poll
done

log "Master sweep finished. Launching Phase 6 + 7…"
./bin/v3.3-phase-6-7.sh

log "Phase 6 + 7 done. Launching Phase 8 (recover missed strategy × new-model sub-sweeps)…"
exec ./bin/v3.3-phase-8-model-strategies.sh
