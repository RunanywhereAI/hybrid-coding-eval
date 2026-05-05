# Prior art — synthesised research findings (May 2026)

A condensed read of four parallel deep-research runs (Exa + Perplexity sonar-deep-research) saved under `research/`. Each section here pulls only the facts that change a decision in `PLAN.md`. Full reports live in `research/{01,02,03,04}/report.md`.

The single sentence: **the question of "should this run local, hybrid, or cloud?" has now been studied enough — by Stanford Hazy Research (Minions / DevMinion), Aider, Cursor, Copilot, Cline, plus ~10 academic papers — that the answer space is well-mapped, but no one has shipped an open benchmark suite that lets a developer measure it on their own hardware**. That gap is exactly what this project fills.

---

## 1. The benchmark landscape — what to reuse, what to skip

### 1a. Function-level (saturation tier — useful as floor, not ceiling)

| benchmark | size | shape | license | usable today? | contamination risk |
|---|---:|---|---|---|---|
| **HumanEval** | 164 problems | gen + run pytest | MIT | yes — trivial harness | **high** (released 2021, in everything) |
| **HumanEval+** (EvalPlus) | 164 problems, **80×** more tests | drop-in for HumanEval | MIT | yes | high — but tests are stricter so memorised "passes" become real failures |
| **MBPP** | 974 problems | gen + run pytest | Apache 2.0 | yes | high |
| **MBPP+** (EvalPlus) | 974 problems, 35× tests | drop-in | MIT | yes | high (same caveat as HumanEval+) |
| **HumanEval Pro / MBPP Pro** | same problems, self-invoking variants | gen + multi-step exec | MIT | yes | partial mitigation — base→pro gap reveals memorisation |

Frontier saturation: GPT-5.5, Claude Sonnet 4.5, Gemini 3 Pro all >90 % pass@1 on HumanEval/MBPP. **For us these benchmarks are useful only as a sanity floor — "did the model produce parseable code at all" — not for differentiating routes.**

### 1b. Repository-scale (the meaningful tier for routing)

| benchmark | size | shape | usable today? |
|---|---:|---|---|
| **SWE-bench Verified** | 500 human-validated GitHub issues | apply patch → run repo's own tests in Docker | yes — `mini-SWE-agent` provides a standard harness; **gold-standard for agentic coding routing** |
| **SWE-bench Lite** | 300 issues | same, smaller | yes |
| **SWE-bench Multilingual** | 9 languages | same | yes |
| **SWE-bench Pro** | harder subset | same | yes |
| **RepoBench 1.1** | cross-file completion | `pip install`, single-command eval | yes |
| **ClassEval** | 100 classes / 410 methods | class-level pytest | yes — slightly less standardised |
| **ComplexCodeEval** | 3,897 Java + 7,184 Python from high-star repos | timestamp-bounded (anti-contamination) | yes |
| **AppWorld** | 750 agentic tasks across 457 APIs | high-fidelity simulator | yes — heavyweight setup |

Frontier scores on **SWE-bench Verified** as of early 2026: Claude Opus 4.6 **77.2 %**, GPT-5 **74.9 %**, Gemini 2.5 Pro **71.8 %**, **Devstral-Small-2-24B 72.2 %** (specialised open model nearly matches frontier!).

This is the most important finding for our project: the gap between top open and top cloud on real software-engineering work is **5 percentage points** when the open model is task-specialised. For our hybrid routing experiments to be useful, **SWE-bench Verified is the primary measuring stick.** Functional scoring is built in; running the harness is a few hours of setup.

### 1c. Contamination-resistant (the credibility tier)

| benchmark | how it dodges contamination | usable today? |
|---|---|---|
| **LiveCodeBench** | continuously scrapes new LeetCode/AtCoder/Codeforces problems | yes — the canonical contamination-free reference; ~500 problems published May 2023+ |
| **BigCodeBench-Hard** | designed-from-scratch with rare APIs | yes |
| **Aider Polyglot** | 225 hard Exercism problems × 6 languages × 2-attempt format | yes — `aider --benchmark` flag |
| **StackUnseen** | most-recent Stack Overflow content | yes |

Frontier on **LiveCodeBench Hard**: GPT-5 **68.4 %**, Claude Opus 4 **66.8 %**, Gemini 2.5 Pro **61.3 %**, DeepSeek-V3 **57.4 %**, Qwen3-Coder-30B-A3B **55.9 %** — gap is **~13 percentage points** here, much wider than on saturated function benchmarks. This is where we should expect hybrid routing to genuinely matter.

### 1d. Routing-specific (rare and partial)

| | size | what it gives us |
|---|---:|---|
| **RouterBench** | 405,467 inferences × 11 models × 8 datasets | pre-recorded performance traces; lets us compute "what would router X have done?" without re-running models |
| **RouterEval** | 200 M records × 8 500 model variants | very wide; coding is one of many; not a code-specific subset |
| **IPRBench / Bounded-ARQGC** | 1.5 M prompts with quality-cost AUC metric | the closest existing metric to what we want — adopt as v1 metric |

**Decision**: we don't build our own router benchmark. We use **IPRBench's Bounded-ARQGC** metric (area-under quality-cost curve) as the headline aggregate, on top of per-task functional/judge scores from the benchmarks in 1b/1c.

### 1e. Source-of-truth links

- HumanEval+/MBPP+: https://evalplus.github.io/leaderboard.html
- BigCodeBench: https://huggingface.co/spaces/bigcode/bigcodebench
- SWE-bench Verified: https://www.swebench.com — `pip install swebench`, official mini-SWE-agent harness
- LiveCodeBench: https://livecodebench.github.io/leaderboard.html
- Aider Polyglot: https://aider.chat/docs/leaderboards/ — already automated

---

## 2. Local-model performance — what we can actually run on M-series

### 2a. The 20–40 B-parameter coding tier

| model | params | HumanEval+ | MBPP+ | BigCodeBench | SWE-bench Verified | LiveCodeBench | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| **Qwen3-Coder-30B-A3B-Instruct** | 30 B (3 B active, MoE) | **87.2 %** | **77.2 %** | 27.7 % (Hard) | n/a public | 55.9 % | best general open coder |
| **Qwen3.6-27B-Coding** | 27 B dense | n/a | n/a | n/a | n/a | n/a (new) | "flagship-level coding in 27 B"; tool-call reliable; what we're running |
| **Devstral-Small-2-24B** | 24 B | n/a | n/a | n/a | **72.2 %** ⭐ | n/a | **specialised for SWE-bench**; 5 pp from Claude Opus 4.6 |
| **DeepSeek-Coder-V3 / V3.2** | 33–671 B (37 B active MoE) | 92.1 % | n/a | 71.8 % | 49.2 % | 57.4 % | strongest at scale; 671 B variant needs 4×24 GB |
| **GLM-4.5-Coding** | 32 B | n/a | n/a | n/a | n/a | n/a | premium pricing; quality slightly above Qwen3-Coder |
| **StarCoder2-15B** | 15 B | n/a | n/a | n/a | n/a | n/a | first fully-transparent code model >70 % on HumanEval |
| **Codestral-Mamba-7B** | 7 B | n/a | 68.5 % | n/a | n/a | n/a | SSM/Mamba architecture, linear-time inference, 256 K context |

Frontier reference scores (cloud) for the same benchmarks:

- **GPT-5**: 96.9 / n/a / **79.3** / **74.9** / **68.4**
- **Claude Opus 4 / Sonnet 4.5**: 95.7–97.6 / 94.2 / 78.7 / **77.2** / 66.8
- **Gemini 2.5 Pro**: 94.2 / n/a / 75.4 / 71.8 / 61.3

### 2b. Where local matches cloud (and where it doesn't) — task-by-task

From a community comparison (kunalganglani.com 2026 blog) of **Qwen2.5-Coder-32B vs Claude Sonnet 4** on real coding tasks, scored 0–5:

| task type | local | cloud | gap |
|---|---:|---:|---:|
| **function generation from spec** | 4.1 | 4.4 | small (close) |
| **code explanation / documentation** | 4.2 | 4.1 | **local equal or better** |
| **single-file refactor** | 4.0 | 4.3 | small |
| **debugging unfamiliar codebase** | 3.8 | 4.6 | medium |
| **multi-file context / cross-cutting** | 2.8 | 4.5 | **wide (60 % gap)** |
| **test generation (catch edge cases)** | n/a | "Claude finds subtle bugs local misses" | wide |
| **API / architecture design** | n/a | "comprehensive schemas + edge cases" | wide |

The two-axis takeaway:

```
                 single-file ⇄ multi-file
                      │
   mechanical    ──── local ✅  ──── routing decision ──── cloud ✅ ──── reasoning-heavy
   (rename, fix)                      hybrid wins                       (architecture,
                                                                         debugging,
                                                                         tests)
```

### 2c. Quantization — what to run on a 64 GB Mac

From extensive 2026 community benchmarking:

| format | quality retention | notes |
|---|---:|---|
| **Q4_K_M** | ~95 % | the pragmatic default. Mature in llama.cpp, MLX, vLLM |
| **Q5_K_M** | ~98 % | slightly slower; **recommended for coding-quality-sensitive work** (debugging, tests) |
| **Q6_K** | very minimal loss | middle ground |
| **MLX bf16** | full | Apple Silicon-native; 15 % faster than llama.cpp on identical hardware; better long-context |
| **AWQ-INT4** | ~95 % | NVIDIA-only; 741 tok/s on A10G via Marlin kernels (vs GPTQ's 712); no LoRA |
| **NVFP4** (Blackwell) | **80–82 % on hard reasoning** ⚠ | speed advantage doesn't justify the AIME drop from 75.86 % FP16 → 62.07 %; **avoid for coding** |
| **mxfp8** | ~92 % | newer; what our `qwen3.6:27b-coding-mxfp8` uses |

**Recommendation for our eval**: Q5_K_M is the right default for the local-only and hybrid runs. Worth running a quantization-axis sweep eventually, but not for MVP.

### 2d. Apple Silicon tok/s — measured numbers

From heyuan110.com 2026-04 benchmarks on M3 Max 64 GB:
- Llama 3.1 8 B Q4_K_M: **58 tok/s**
- Qwen 2.5 14 B Q4_K_M: **33 tok/s**
- Llama 3.1 34 B Q4_K_M: **15 tok/s**
- Llama 3.3 70 B Q4_K_M: **7.5 tok/s**

Counter-intuitive finding: **M3 Max 64 GB beats M4 Pro 48 GB** on large-model inference because of memory bandwidth (400 vs 273 GB/s). For the hybrid eval, we should:
1. Record memory bandwidth in the result rows (it's the dominant predictor for local tok/s)
2. Recommend Q5_K_M on 64 GB+ Apple Silicon; Q4_K_M as fallback; **avoid M4 Pro 48 GB for large coder models**
3. Note the bandwidth-vs-cores quirk in the README so users buying hardware don't pick wrong

---

## 3. Hybrid architectures already in the wild — what's been learned

The research surfaced **~12 production hybrid systems** and **~8 academic routing papers**. Distilled patterns:

### 3a. The two architectural shapes that ship

1. **Task-type routing** — pick a model based on what *kind* of work it is, not what the prompt says. **Aider's architect/editor split is the canonical example.** Cursor's Tab-vs-Composer is the same idea on different axes.
2. **Cascade** — try cheap first, escalate on low confidence or failure. Windsurf's "Adaptive Cascade", FrugalGPT, R2-Router, our `cascade` strategy.

Complexity-classifier routing ("predict difficulty up front") is **less reliable in production than either of the above** according to multiple sources. Worth knowing — it's exactly what our `heuristic` and `llm-classifier` strategies are.

### 3b. Production cost reductions, with sources

| system | claimed savings | quality regression | source |
|---|---|---|---|
| **Aider architect/editor** | "matches GPT-4 quality at lower cost" | not quantified publicly | aider.chat docs |
| **Cursor (Tab local + Composer cloud)** | reduced cloud usage vs always-cloud | qualitative parity claimed | Cursor announcements |
| **Windsurf Adaptive (Cascade)** | not published | not published | proprietary |
| **CodePRM** (process reward model) | **20–40 % reduction in flagship-model usage**, similar quality | benchmark-controlled, not production | CodePRM paper |
| **FrugalGPT cascade** | **25–50 % cost savings**, depends on task distribution | varies by calibration | FrugalGPT paper |
| **General "intelligent routing"** | **30–60 % across multiple production systems** | "qualitatively similar" | aggregated from research/03 report |
| **Hybrid local+cloud (CodeProject / dev.to)** | **60–80 % cost reduction** for moderate-tier devs | acceptable | community blog posts |

The **30–60 % reduction is the credible production range** (cited from multiple sources). The 60–80 % comes from blog-post anecdotes — possible but noisy.

### 3c. Documented failure modes (each is a thing our eval should expose)

1. **Token-limit prediction failures** — local model picked, then context exceeds its window, fallback chain produces degraded output. Multiple postmortems.
2. **Calibration drift** — thresholds calibrated on benchmarks behave differently on production traffic. Routing flipped too aggressive → quality drop; too conservative → no savings. Our heuristic threshold tuning is exactly this risk.
3. **Session-state inconsistency** — Tab completion uses local pattern, Composer uses cloud pattern, code styles diverge mid-session.
4. **Synth-budget exhaustion on reasoning models** — gpt-5.5 burns the entire output budget on hidden reasoning, returns empty visible content. **We hit this in exp 3 of our existing eval.** Mentioned in our article. Confirmed by research as a general failure pattern.

### 3d. Stanford Minions / DevMinion specifics worth integrating

- **DevMinion** is the coding-specific variant in `EXTERNAL/minions/minions/minion_code.py`. Distinct from generic Minion — has dedicated prompts: `RUNBOOK_GENERATION_PROMPT` (planner), `SUBTASK_EXECUTION_PROMPT` (executor), `CODE_REVIEW_PROMPT` (review), `EDIT_REQUEST_PROMPT` (iterative fix), `FINAL_INTEGRATION_PROMPT` (synth). The review+fix loop is something we don't have.
- **Minion (singular)** uses a stateful Q&A pattern: cloud asks targeted questions, local reads context and answers, cloud never sees raw context. Reduces synth replay tax — relevant to our **R4 hybrid-minion** route.
- The `minion_arch.py` variant uses an **Arch Router** (the 1.5 B Katanemo router model) for client selection — same lineage as our `llm-classifier` strategy but with a real routing-trained model.

### 3e. Academic papers worth reading for routing technique

- **CodePRM, ThinkPRM-Code, FunPRM, DreamPRM-Code** — process reward models for code; the most concrete "20–40 % savings, controlled quality" measurements
- **R2-Router** — joint optimisation of routing + model fine-tuning
- **AdaptiveLLM, DAAO-Code, BaRP-Code** — code-specific contextual bandits
- **xRouter** — routing for tool-using agents
- **FrugalGPT, RouteLLM** — foundational cascade/routing literature

---

## 4. Hardware reality + cost — calibrating the article

### 4a. Cloud subscription pricing as of May 2026

| service | tier | cost / mo | what you get |
|---|---|---:|---|
| GitHub Copilot | Free | $0 | 2 K completions + 50 premium req |
| GitHub Copilot | Pro | $10 | 300 premium req + unlimited completions |
| GitHub Copilot | Pro+ | $39 | 1 500 premium req, all models |
| Cursor | Pro | $20 | $20 credit pool (usage-based) |
| Cursor | Pro+ | $60 | 3× credits |
| Cursor | Ultra | $200 | 20× credits |
| Anthropic Claude Code | Max | $200 | (Claude Code removed from $20 Pro tier April 2026) |
| OpenAI Codex CLI | Plus | $20 | lightweight |
| OpenAI Codex CLI | Pro | $100 | 5× / 20× rate limits |

Heavy users at orgs like Uber: **$5K–$100K+/month** on Claude Code via the API (documented).

### 4b. Token consumption tiers (developer surveys 2026)

| tier | tokens/day | tokens/mo | cloud $/mo |
|---|---:|---:|---:|
| **Light** (occasional completion) | 10–50 K | 200 K – 1 M | $10–30 |
| **Moderate** (daily integration) | 50–300 K | 1–6 M | $30–100 |
| **Heavy** (pair-programming) | 300 K–2 M | 6–40 M | $100–300+ |
| **Agentic** | 2–20 M / task (variable!) | unbounded | unpredictable |

### 4c. Hardware cost-of-ownership

| hardware | initial | monthly amortised | electricity | total monthly |
|---|---:|---:|---:|---:|
| Mac Mini M4 Pro 48 GB | $1 999 | $83 | $16 | **$99** |
| MacBook Pro M4 Max 64 GB | $3 499 | $146 | $20 | **$166** |
| Mac Studio M4 Ultra 128 GB | $3 999–11 999 | $167–500 | $30 | $197–530 |
| RTX 4090 24 GB used + host | ~$1 500 | $63 | $97 (450 W × 6 h × $0.12) | **$160** |
| Dual RTX 4090 + host | ~$2 800 | $117 | $194 | **$311** |
| RTX 5090 32 GB + host | ~$4 500 | $188 | ~$130 (600 W) | **$318** |
| AMD Ryzen AI Max+ 395 96 GB | ~$2 800 | $117 | $25 | **$142** |
| CPU-only (AVX-512, 64-core, DDR5) | ~$3 000 | $125 | $30 | **$155** |

### 4d. Break-even — when does hybrid actually pay off?

Single developer:

| usage tier | cloud $/mo | break-even on Mac M4 Pro 48 GB | break-even on RTX 4090 used |
|---|---:|---:|---:|
| Light | $20 | **~5 months** (then $16/mo electricity vs $20 forever) | ~9 months |
| Moderate | $75 | **~2 months** | ~3 months |
| Heavy | $200 | **<1 month** | <1 month |

Team: economics shift dramatically toward local with team size. 10-dev team at moderate tier would pay $750/mo cloud vs ~$300/mo for shared dual-RTX-4090 infrastructure → 60 % savings, breakeven in 4 months.

### 4e. Realistic local tok/s by hardware

For Qwen3-Coder-30B / Qwen3.6-27B-Coding at Q4_K_M-class quantization:

| hardware | tok/s | acceptable for interactive? |
|---|---:|---|
| Mac Mini M4 Pro 48 GB | n/a (model barely fits) | no |
| MacBook Pro M4 Max 64 GB | 12–18 | borderline |
| Mac Studio M4 Ultra 128 GB | 25–35 | yes |
| RTX 4090 24 GB | 24–28 (Q4_K_M) | yes |
| Dual RTX 4090 48 GB | 30–40 | yes |
| RTX 5090 32 GB | 35–50 (and 70-B viable) | yes |
| AMD Ryzen AI Max+ 395 96 GB | 15–20 | borderline |
| CPU-only (AVX-512) | 3–5 | no — batch only |

### 4f. The honest case for hybrid in numbers

Hybrid (60–80 % savings on the cloud half) only pays off on hardware where the local half is *good enough*. The break-even table above assumes that. **For the article, this means: the chart that matters most is "hardware tier × usage tier → break-even months" with hybrid as one of the cells.**

---

## 5. What this changes in our PLAN

Concrete updates to fold into PLAN.md (will do separately):

1. **Task selection (§3 of PLAN.md)** — replace placeholder with concrete picks:
   - 10 × **HumanEval+** (random sample) — sanity floor + functional scoring
   - 5 × **MBPP+** (random sample) — same
   - 10 × **BigCodeBench-Hard** (random sample) — library-intensive realism
   - **5 × SWE-bench Verified easy tier** (most important) — agentic coding gold-standard, functional scoring via mini-SWE-agent harness
   - **5 × LiveCodeBench (latest month)** — contamination-resistant reasoning
   - **5 × Aider Polyglot** (one per language) — code-editing-specific 2-attempt format
   - 3 × hand-curated architecture / explanation tasks → LLM-as-judge scoring
   - 2 × our existing examples (kept for continuity with the article)
   - **Total: 45 tasks** (up from 30 in placeholder)

2. **Scoring (§5 of PLAN.md)** — adopt **Bounded-ARQGC** (from IPRBench) as the headline aggregate metric on top of per-task scores. Standardised, peer-reviewed, exactly what we want.

3. **R4 hybrid-minion** route — implement the **Minion (singular) Q&A pattern** from `EXTERNAL/minions/minions/minion.py`, not the parallel-batch `Minions` variant. Cleaner protocol. Borrow `RUNBOOK_GENERATION` + `EDIT_REQUEST` from DevMinion as a 5th route.

4. **Add a 5th route: R5 local-with-cloud-review** — use Aider's architect/editor pattern: local writes code, cloud reviews and requests fixes. The single most-deployed real hybrid pattern. Ours doesn't currently test this.

5. **Hardware envelope** — add memory bandwidth to the host-detection step. It's the dominant predictor of local tok/s. Recommend Q5_K_M default on 64 GB+, Q4_K_M on 48 GB or below.

6. **Headline article visualisation** — the matrix that matters is **(hardware tier × usage tier × task category) → recommended route**, plus the cost-quality Pareto curve per task.

---

## 6. Open questions the research didn't answer

1. **Per-task cost-quality curves at production scale.** Most papers report controlled-experiment numbers; production reports are mostly anecdotal. Our project's contribution is to add reproducible per-task curves to the literature.
2. **How much of the gap closes when local model is task-fine-tuned?** Devstral-Small-2-24B at 72.2 % on SWE-bench Verified suggests the answer is "a lot" — but this hasn't been measured systematically across task types. Worth a V2 axis.
3. **Latency vs cost vs quality is genuinely 3-D**, not 2-D. Most analyses collapse latency into a "wall time" footnote. Our framework should keep it as a first-class axis.
4. **The role of prompt caching** is under-measured. Anthropic and OpenAI both auto-cache stable prefixes; in architect-mode pipelines this is non-trivial savings. Our experiments don't currently use it.

---

## 7. Bibliography (selected)

Full citation lists in `research/{01,02,03,04}/report.md`. Key sources:

- HumanEval / EvalPlus leaderboards (evalplus.github.io/leaderboard.html)
- SWE-bench Verified (swebench.com)
- LiveCodeBench (livecodebench.github.io/leaderboard.html)
- Aider Polyglot (aider.chat/docs/leaderboards)
- BigCodeBench (huggingface.co/spaces/bigcode/bigcodebench)
- RouterBench paper (arXiv 2403.12031)
- IPRBench / Bounded-ARQGC paper
- Stanford Minions (arXiv 2502.15964)
- Aider architect/editor docs
- CodePRM, ThinkPRM-Code, FunPRM papers
- Heyuan110 M3 Max benchmarks (heyuan110.com/posts/ai/2026-04-14-mac-apple-silicon-ai-workstation/)
- Sitepoint quantization comparison (sitepoint.com/quantization-explained-q4km-vs-awq-vs-fp16-for-local-llms)
- Kunal Ganglani local vs Claude benchmark (kunalganglani.com/blog/local-llm-vs-claude-coding-benchmark)
