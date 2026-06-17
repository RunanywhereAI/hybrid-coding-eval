#!/usr/bin/env bash
# Extract ERROR-level lines from the given dated log file and print them
# sorted by timestamp (lexicographic sort works for YYYY-MM-DD HH:MM:SS).
set -euo pipefail
grep -E ' ERROR ' "$1" | sort
