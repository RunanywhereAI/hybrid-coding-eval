# Attribution: FastChat LLM Judge (MT-Bench)

Vendored read-only reference, not installed as a package.

- **Source**: https://github.com/lm-sys/FastChat/tree/587d5cfa1609a43d192cedb8441cac3c17db105d/fastchat/llm_judge
- **Upstream commit**: `587d5cfa1609a43d192cedb8441cac3c17db105d`
- **Fetched**: 2026-05-05
- **License**: Apache 2.0 (see `LICENSE`)
- **Purpose**: reference implementation for pairwise LLM-as-judge used by
  MT-Bench. Our own judge at `scorers/llm_judge.py` (T3.3) adapts these
  prompts + bias-correction methodology (position-swap, reference-guided
  grading); we do not import fastchat code directly.

## Why we chose FastChat over lm-evaluation-harness

The original task brief pointed at EleutherAI/lm-evaluation-harness, but the
canonical MT-Bench judge lives in `lm-sys/FastChat`'s `fastchat/llm_judge/`
directory and is the one cited and re-used by the community (including
lm-eval-harness itself for MT-Bench). We vendor the source of truth.

## What we adopt vs. leave behind

Adopt (re-implement in our own `scorers/llm_judge.py`):
- Prompt templates from `src/data/judge_prompts.jsonl`
  (pair-v2, pair-math-v1, single-v1, single-math-v1).
- Position-swap bias correction: run the judge twice with A/B swapped and
  only award a win if both agree; otherwise record a tie.
- Reference-guided grading for math/coding categories.
- Answer parsing regex (e.g. `\[\[A\]\]`, `\[\[B\]\]`, `\[\[C\]\]`).

Leave behind:
- `gen_model_answer.py`, `gen_api_answer.py` — we generate answers in our
  own `runners/` layer, not via fastchat.
- `qa_browser.py` — Gradio UI, out of scope.
- `download_mt_bench_pregenerated.py` — we're scoring our own outputs, not
  MT-Bench model outputs.
- OpenAI client wiring in `common.py` — we use the provider abstraction
  already built in `lib/`.

## Directory layout

```
lm-eval-harness-judge/
├── ATTRIBUTION.md   (this file)
├── LICENSE          (Apache 2.0, copied verbatim from FastChat)
└── src/             (unmodified copy of fastchat/llm_judge/)
    ├── README.md
    ├── common.py
    ├── gen_judgment.py
    ├── gen_model_answer.py
    ├── gen_api_answer.py
    ├── show_result.py
    ├── clean_judgment.py
    ├── compute_agreement.py
    ├── qa_browser.py
    ├── download_mt_bench_pregenerated.py
    └── data/
        ├── judge_prompts.jsonl
        ├── mt_bench/
        └── vicuna_bench/
```

## Re-fetch command

```bash
TMP=$(mktemp -d)
git clone --depth 1 https://github.com/lm-sys/FastChat.git "$TMP/fastchat"
rm -rf EXTERNAL/lm-eval-harness-judge/src
cp -r "$TMP/fastchat/fastchat/llm_judge/" EXTERNAL/lm-eval-harness-judge/src
cp "$TMP/fastchat/LICENSE" EXTERNAL/lm-eval-harness-judge/LICENSE
rm -rf "$TMP"
# Then update the commit SHA + Fetched date at the top of this file.
```
