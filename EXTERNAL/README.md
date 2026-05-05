# EXTERNAL/

Read-only reference clones of third-party projects we study but do not vendor into our own source tree. Treat everything here as reference material for methodology/prior-art, not as a build-time dependency.

Nothing in this directory is imported at runtime. If something here needs to influence our code, the influence flows through *re-implementation* in `scorers/`, `runners/`, or `router/`, not through `import`.

## Contents

| Path | What | License | Tracked in git? | Size |
|---|---|---|---|---|
| `minions/` | Stanford Hazy Research reference clone (Minions protocol) | MIT | No (large, ~8.5 MB) | ~8.5 MB |
| `lm-eval-harness-judge/` | FastChat MT-Bench LLM-judge source | Apache 2.0 | Yes (small, <1 MB) | ~600 KB |

---

## minions/

- **Source**: https://github.com/HazyResearch/minions
- **Paper**: *Minions: Cost-efficient Collaboration Between On-device and Cloud Language Models* (arXiv 2502.15964)
- **License**: MIT
- **What it is**: Stanford Hazy Research's implementation of the Minions protocol — stateful Q&A between a local worker and cloud supervisor.
- **Why we reference it**: The `DevMinion` variant (`minions/minion_code.py`) has a 5-stage runbook → execute → review → edit → synthesize loop that informs our post-MVP R4/R5 routes. Worth reading as prior art; reusable Python classes.
- **First cloned**: ~2026-04 into `opencode/EXTERNAL/`, moved here during consolidation 2026-05-05.
- **Tracked in git**: No — gitignored in root `.gitignore` under `EXTERNAL/minions/`. The clone is ~8.5 MB and noisy.
- **How to refresh**:
  ```bash
  cd EXTERNAL && git clone https://github.com/HazyResearch/minions.git
  ```

---

## lm-eval-harness-judge/

- **Source**: https://github.com/lm-sys/FastChat/tree/587d5cfa1609a43d192cedb8441cac3c17db105d/fastchat/llm_judge
- **Upstream commit**: `587d5cfa1609a43d192cedb8441cac3c17db105d`
- **Fetched**: 2026-05-05
- **License**: Apache 2.0 (see `lm-eval-harness-judge/LICENSE`)
- **What it is**: The canonical MT-Bench LLM-as-judge code from `lm-sys/FastChat`. The directory name says "lm-eval-harness" because EleutherAI's `lm-evaluation-harness` re-uses this exact implementation for its MT-Bench task — the source of truth lives in FastChat.
- **Why we reference it**: `scorers/llm_judge.py` (task T3.3) adapts these prompts and the position-swap bias-correction methodology for our pairwise category-C judgments. We do not import FastChat as a Python dependency — it has many transitive deps (Gradio, vLLM, etc.) we do not need.
- **Tracked in git**: Yes — the entire `src/` is only ~600 KB, so checking it in makes the repo self-contained and pins the exact reference our write-up cites. No giant model weights, notebooks, or datasets are included.
- **See also**: `lm-eval-harness-judge/ATTRIBUTION.md` for the fetch command, adopted-vs-leave-behind notes, and re-fetch procedure.

### Key files

- `src/common.py` — prompt templates, judge API calls, response parsing regexes.
- `src/gen_judgment.py` — pairwise / single-answer judgment generation loop.
- `src/data/judge_prompts.jsonl` — the actual prompt templates (pair-v2, pair-math-v1, single-v1, single-math-v1).
- `src/data/mt_bench/question.jsonl` — the 80-question MT-Bench set (for reference; we do not run MT-Bench itself).
- `src/README.md` — upstream README with usage/recipe.
