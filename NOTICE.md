# NOTICE — third-party code and attributions

This project vendors, references, and re-implements ideas from a number of
upstream projects and research papers. This file enumerates every case where
attribution is legally or ethically required.

If you redistribute this repository, keep this file intact.

---

## Vendored source (tracked in this repo)

### `vendor/lm-eval-harness-judge/`

- **Upstream**: [lm-sys/FastChat](https://github.com/lm-sys/FastChat) —
  `fastchat/llm_judge/` directory, commit
  `587d5cfa1609a43d192cedb8441cac3c17db105d`.
- **License**: Apache License 2.0. Full text at
  `vendor/lm-eval-harness-judge/LICENSE`.
- **What we use**: prompt templates (`src/data/judge_prompts.jsonl`),
  position-swap bias-correction methodology, answer-parsing regex.
  Adapted into `scorers/llm_judge.py` — we do not import FastChat as a
  Python dependency.
- **Modifications**: none inside `vendor/lm-eval-harness-judge/`. It is
  vendored read-only. Our own re-implementation lives in `scorers/`.
- See `vendor/lm-eval-harness-judge/ATTRIBUTION.md` for fetch command,
  re-fetch procedure, and adopt-vs-leave-behind notes.

---

## Referenced (cloned locally, NOT tracked)

### `vendor/minions/`

- **Upstream**: [HazyResearch/minions](https://github.com/HazyResearch/minions).
- **Paper**: Narayan, A. et al. *Minions: Cost-efficient Collaboration
  Between On-device and Cloud Language Models.* arXiv 2502.15964 (2025).
- **License**: MIT.
- **Status in this repo**: **not tracked** — listed in `.gitignore`. Users
  who want to read the reference implementation must clone it themselves
  (instructions in `vendor/README.md`).
- **What we use**: the `DevMinion` runbook→execute→review→edit→synthesize
  loop informed R4/R5 routing strategies. We reimplement the ideas in
  `runners/` — no code is copied.

---

## Ideas and methodology we build on (no code copied)

Attribution below follows academic custom (citation, not license — these
are ideas/measurement methods, not copyrightable code). Full citations
are in `docs/PRIOR_ART.md`.

### Benchmarks the harness targets

| Benchmark | Source | License | How we use it |
|---|---|---|---|
| HumanEval+ / MBPP+ | [EvalPlus](https://github.com/evalplus/evalplus) (Liu et al., NeurIPS 2023; arXiv 2305.01210) | MIT | adapter pins 10 HumanEval+ tasks (T1.1) |
| SWE-bench Verified | [princeton-nlp/SWE-bench](https://github.com/princeton-nlp/SWE-bench) (Jimenez et al., ICLR 2024; arXiv 2310.06770) | CC-BY-4.0 | adapter pins 10 tasks; scoring via upstream Docker harness (T1.2, T3.2) |
| BigCodeBench-Hard | [bigcode-project/bigcodebench](https://github.com/bigcode-project/bigcodebench) (Zhuo et al., arXiv 2406.15877) | Apache 2.0 | adapter pins 5 tasks (T1.3) |
| LiveCodeBench | [LiveCodeBench/LiveCodeBench](https://github.com/LiveCodeBench/LiveCodeBench) (Jain et al., arXiv 2403.07974) | MIT | referenced in prior-art synthesis; not in MVP sweep |
| Aider Polyglot | [Aider-AI/aider](https://github.com/Aider-AI/aider) | Apache 2.0 | referenced in prior-art synthesis; not in MVP sweep |

Each adapter directory under `benchmark/<name>/README.md` carries a local
copy of the upstream attribution and pin commit.

### Routing strategies we compare

- **Architect / editor split** — originated by Aider
  ([Aider-AI/aider](https://github.com/Aider-AI/aider), Paul Gauthier). R5
  mirrors this pattern; no code copied.
- **Minions protocol** — Stanford Hazy Research (see above). R4 borrows
  the stateful-Q&A shape; reimplemented from the paper.
- **FrugalGPT / RouteLLM / CodePRM** — referenced in `docs/PRIOR_ART.md`.
  Method influence, no code.

### LLM-as-judge methodology

- Based on MT-Bench (Zheng et al., NeurIPS 2023; arXiv 2306.05685),
  via FastChat. See `vendor/lm-eval-harness-judge/` above.

---

## This project's own license

- **Code**: MIT. See `LICENSE`.
- **Data/results/docs/article**: CC-BY-4.0. See `LICENSE-DATA`.

Nothing in this `NOTICE.md` supersedes or narrows those licenses; it
records the obligations we inherit from upstream work.
