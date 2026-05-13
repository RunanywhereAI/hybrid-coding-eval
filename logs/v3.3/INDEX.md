# v3.3 sweep — log + artefact index

Everything produced by the v3.3 sweep, indexed in one place. Persistent — survives `/tmp` wipes, reboots, terminal disconnects.

## How to use this directory

- **Reports & analysis**: read `master-sweep.log` end-to-end for the full trail of phase transitions, errors, warnings.
- **Per-phase debugging**: each phase has its own log section (search for `=== Phase N` markers in master-sweep.log).
- **Reproducibility**: combined with `results/runs/*/bench-config.json` and `results/runs/*/env-manifest.json`, this index gives a complete picture of what ran when and on what hardware.

## File-by-file inventory

### Top-level logs (text)

| file | source | purpose |
| --- | --- | --- |
| `master-sweep.log` | `/tmp/v3.3-sweep.log` (mirrored every 5 min) | Full stdout/stderr of `bin/v3.3-full-sweep.sh` — all phases 1-5, every variant, every model response, every error. Largest file. The single most important text log. |
| `watcher.log` | `/tmp/v3.3-watcher.log` | Stdout of `bin/v3.3-wait-and-launch-p67.sh` — the auto-chain process that fires Phase 6 → 7 → 8 when the master sweep finishes. |
| `initial-model-pulls.log` | `/tmp/v3.3-pull.log` | Initial pulls of the 4 new local models (qwen3-coder, qwen2.5-coder, glm-4.7-flash, gemma4:26b) on May 12 night. |
| `gemma4-31b-pull.log` | `/tmp/gemma4-31b-pull.log` | Pull of `gemma4:31b` after the swap from 26b. |
| `phase6-classifier-pulls.log` | `/tmp/phase6-classifier-pulls.log` | Pulls of small classifier candidates (qwen3:1.7b, qwen3:4b, qwen2.5-coder:1.5b). |
| `phase6-qwen35-pulls.log` | `/tmp/phase6-qwen35-pulls.log` | Pulls of Qwen3.5 small variants (0.8b, 2b, 4b) for the classifier sub-sweep. |
| `phase-6-7.log` (future) | `/tmp/v3.3-p67.log` | Stdout of Phase 6 + 7 launcher when it runs (after master sweep finishes). |
| `router-classifier-*.log` (future) | `/tmp/router-classifier-*.log` | One file per classifier-variant router restart in Phase 6. |
| `router-cascade-t*.log` (future) | `/tmp/router-cascade-t*.log` | One file per cascade-threshold router restart in Phase 7. |

### Subdirectories

| dir | purpose |
| --- | --- |
| `smoke-tests/` | Pre-sweep smoke runs for all 4 new local models (8 rows each, ~15 min per model). |

## Persistent artefacts elsewhere in the repo

Not in this dir — these are tracked separately:

| path | what |
| --- | --- |
| `results/runs/<variant>/raw.jsonl` | **The actual data** — one JSON line per (task, route, strategy) sweep row. Append-only; survives all log loss. |
| `results/runs/<variant>/outputs/*.txt` | Raw model-generated text per (task, route). |
| `results/runs/<variant>/progress.log` | Per-row orchestrator progress (wall ms, pass/fail). |
| `results/runs/<variant>/bench-config.json` | The merged BenchConfig that produced this run, with SHA256 for canonicalization. |
| `results/runs/<variant>/env-manifest.json` | Hardware snapshot (chip, RAM, git SHA, Ollama version) at run time. |
| `router/logs/decisions.jsonl` | Per-call routing decisions: every cloud-or-local choice the router made, with reason + confidence. |

## Manifest of expected run directories (v3.3 sweep)

Each row is one variant the sweep should produce. Status as of last update — check `wc -l raw.jsonl` for live counts.

| variant directory | what | rows expected | status |
| --- | --- | ---: | --- |
| `results/runs/07-v3-devstral-all-routes/` | v3 baseline (run before v3.3) | 250 | ✅ existing |
| `results/runs/11-judge-robust-D/` | v3 triple-judge audit | 96 verdicts | ✅ existing |
| `results/runs/12-r3-strategy-heuristic/` | Phase 1: devstral × heuristic | 50 | ✅ done |
| `results/runs/13-r3-strategy-rules/` | Phase 1: devstral × rules | 50 | ✅ done |
| `results/runs/14-r3-strategy-llm-classifier/` | Phase 1: devstral × llm-classifier | 50 | ✅ done |
| `results/runs/15-r3-strategy-embedding-knn/` | Phase 1: devstral × embedding-knn | 50 | ✅ done |
| `results/runs/16-r3-strategy-cascade/` | Phase 1: devstral × cascade | 50 | ✅ done (1 error) |
| `results/runs/17-qwen3coder-all-routes/` | Phase 2: qwen3-coder × heuristic baseline | 200 | ✅ done |
| `results/runs/18-qwen2.5coder-all-routes/` | Phase 3: qwen2.5-coder × heuristic baseline | 200 | 🔄 in progress |
| `results/runs/19-glm47flash-all-routes/` | Phase 4: glm-4.7-flash × heuristic baseline | 200 | ⏸ pending |
| `results/runs/20-gemma4-31b-all-routes/` | Phase 5: gemma4:31b × heuristic baseline | 200 | ⏸ pending |
| `results/runs/p6-classifier-*/` (4 dirs) | Phase 6: classifier sub-sweep | 50 each | ⏸ pending |
| `results/runs/p7-cascade-threshold-*/` (5 dirs) | Phase 7: cascade threshold sub-sweep | 50 each | ⏸ pending |
| `results/runs/{17,18,19,20}-*-cascade/` (4 dirs) | Phase 8: cascade × new model | 50 each | ⏸ pending |
| `results/runs/{17,18,19,20}-*-llm-classifier/` (4 dirs) | Phase 8: llm-classifier × new model | 50 each | ⏸ pending |

**Total rows when complete:** ~2,950 rows + 96 audit verdicts.

## How to analyze everything when done

```bash
# Per-strategy R3 comparison (Phase 1 variants 12-16)
python3 bin/v3.3-aggregate-strategy.py

# Cross-model decision matrix (variants 17-20 heuristic baselines)
python3 bin/v3.3-aggregate-models.py

# Refresh ARTICLE.md AUTO-GENERATED sections + commit
./bin/v3.3-refresh-article.sh --commit

# Inspect any specific (task, route) cell
jq 'select(.task_id=="real-dev/d3-extract-validation-helper" and .route=="R3")' \
   results/runs/*/raw.jsonl

# Cost across all sweeps under any pricing scenario
./bench token-budget results/runs/12-*
```

## Recovery procedures

If `/tmp` gets wiped or the master sweep crashes:
- Log files are mirrored every 5 min by `bin/v3.3-mirror-logs.sh` (if running)
- The master sweep is `--resume` safe: re-running `bin/v3.3-full-sweep.sh` skips completed (task, route) pairs via `raw.jsonl` dedup
- Phase 6+7+8 sub-launchers all use `--resume` too

If a single variant has errors:
- Check `results/runs/<variant>/raw.jsonl` for rows with `error != null`
- Manually re-run with `./bench run --config <config> --resume`
- Or just leave it — the analysis tools handle null `error` rows gracefully

## Updated by

- 2026-05-13 15:11 PDT — initial snapshot + index after the strategy-sub-sweep bug discovery
