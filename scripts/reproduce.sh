#!/usr/bin/env bash
# scripts/reproduce.sh — one-command reproducer for hybrid-coding-eval.
#
# Checks prereqs (Python 3.11+, Docker, Ollama, Node, .env), provisions
# the sandbox image + aux models on first run, then runs a sweep through
# ./bench. Designed to be the FIRST thing a stranger runs after `git clone`.
#
# USAGE
#   scripts/reproduce.sh --smoke
#       Run the 1-task smoke sweep (configs/v1.4-smoke.yaml). ~30 seconds,
#       ~$0.01 cloud spend. If this completes cleanly, the harness is wired.
#
#   scripts/reproduce.sh --config configs/v1.4-canonical-gemma4.yaml \
#       --strategies always-cloud,always-local,heuristic,cascade \
#       --seeds 42,7,13
#       Run a full canonical sweep. ~10–15 hours on M4 Max 64 GB,
#       ~$30–50 cloud spend at gpt-5.5 list price.
#
#   scripts/reproduce.sh --config configs/v1.4-canonical-gemma4.yaml \
#       --set models.local=<new-model> \
#       --set out_dir=results/runs/v1.4-<new-model> \
#       --strategies always-cloud,always-local,heuristic,cascade --seeds 42,7,13
#       Benchmark a NEW local model against the canonical matrix.
#
# Anything after `scripts/reproduce.sh` is forwarded verbatim to `./bench sweep`
# (after we inject defaults). `--smoke` is a shortcut for the smoke recipe.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

#─── helpers ────────────────────────────────────────────────────────────────
log()  { printf '\033[1;36m[reproduce]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[reproduce]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[reproduce]\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "missing prerequisite: '$1'. ${2:-}"
}

#─── parse args ─────────────────────────────────────────────────────────────
SMOKE=0
FORWARD=()
for arg in "$@"; do
    case "$arg" in
        --smoke) SMOKE=1 ;;
        -h|--help)
            sed -n '2,32p' "$0"
            exit 0
            ;;
        *) FORWARD+=("$arg") ;;
    esac
done

#─── prereq checks (fail fast) ──────────────────────────────────────────────
log "checking prerequisites…"
require_cmd python3   "install Python 3.11 or 3.12 from https://python.org"
require_cmd docker    "install Docker Desktop from https://docker.com/products/docker-desktop"
require_cmd node      "install Node 20+ from https://nodejs.org"
require_cmd ollama    "install Ollama from https://ollama.com (only needed for local-routed sweeps)"
require_cmd jq        "install jq (brew install jq / apt-get install jq)"

if ! docker info >/dev/null 2>&1; then
    die "docker daemon not running. Start Docker Desktop, then re-run."
fi

PY_MINOR="$(python3 -c 'import sys; print(sys.version_info.minor)')"
if [[ "$PY_MINOR" -lt 11 ]]; then
    die "Python 3.11+ required (got 3.$PY_MINOR)."
fi

#─── .env presence ──────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    warn ".env not found — copying from .env.example."
    cp .env.example .env
    warn "Edit .env and add your OPEN_AI_API_KEY before running again."
    exit 1
fi
set +u; source .env; set -u
if [[ -z "${OPEN_AI_API_KEY:-}${OPENAI_API_KEY:-}" ]]; then
    die "neither OPEN_AI_API_KEY nor OPENAI_API_KEY set in .env"
fi

#─── venv ───────────────────────────────────────────────────────────────────
if [[ ! -x .venv/bin/python ]]; then
    log "creating .venv (Python 3.$PY_MINOR)…"
    python3 -m venv .venv
fi
log "installing package (editable)…"
# Hide the routine "pip dependency resolver" warnings — the harness pins
# a known-good openai SDK; aider-chat declares a stricter range, but the
# fallback works in practice (verified by the test suite). Real errors
# still surface because we keep stderr.
.venv/bin/pip install --quiet --upgrade pip 2>&1 | grep -v "dependency resolver" || true
.venv/bin/pip install --quiet -e ".[dev]" 2>&1 | grep -vE "dependency resolver|but you have|requires openai" || true

#─── first-run setup (idempotent) ───────────────────────────────────────────
log "running ./bench setup (idempotent: Docker image + aux models + agents)…"
./bench setup

#─── pick the recipe ────────────────────────────────────────────────────────
if [[ "$SMOKE" -eq 1 ]]; then
    log "running SMOKE sweep (configs/v1.4-smoke.yaml)…"
    set -x
    ./bench sweep \
        --config configs/v1.4-smoke.yaml \
        --strategies always-cloud \
        --seeds 42 \
        --smoke
    { set +x; } 2>/dev/null
    log "analyzing smoke results…"
    ./bench analyze results/runs/v1.4-smoke
    log "smoke sweep complete. Inspect results/runs/v1.4-smoke/."
    exit 0
fi

if [[ "${#FORWARD[@]}" -eq 0 ]]; then
    die "no sweep config given. Try: scripts/reproduce.sh --smoke (or pass --config <yaml>)."
fi

log "running ./bench sweep ${FORWARD[*]}"
set -x
./bench sweep "${FORWARD[@]}"
{ set +x; } 2>/dev/null

# Best-effort analyse: if the user passed --set out_dir=… or relies on the
# config's out_dir, derive it from `./bench show-config` and call analyze.
OUT_DIR="$(./bench show-config "${FORWARD[@]}" 2>/dev/null | jq -r '.out_dir // empty' || true)"
if [[ -n "$OUT_DIR" && -d "$OUT_DIR" ]]; then
    log "analyzing $OUT_DIR…"
    ./bench analyze "$OUT_DIR"
fi

log "done."
