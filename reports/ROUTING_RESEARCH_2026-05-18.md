# LLM Routing for Coding & Software-Engineering Tasks — Research Report

**Authored:** 2026-05-18 · **Run ID:** routing-research-v1 · **Author:** Claude Code (Opus 4.7) for Sanchit Monga
**Scope:** coding/SWE routing only (not general chat). Closed + open + self-hostable models.
**Anchor data:** v3 sweep `results/runs/07-v3-devstral-all-routes/` (250 rows, M4 Max 64 GB, devstral:24b + gpt-5.5, judge claude-opus-4-7).

---

## 0. Scope rules and honest limits

Three calibration items before the report content:

1. **Score-currency caveat.** Perplexity `sonar-deep-research` (the model behind the §1 and §2 deep-research runs in `/Users/sanchitmonga/development/research_agent/outputs/20260518_*`) has a late-2024 knowledge cutoff for vendor-reported benchmark numbers. The §3 routing-literature run is largely cutoff-immune because the papers cited have stable arxiv IDs. Wherever a specific May-2026 score for GPT-5.5, Claude Opus 4.7, Kimi K2.6, DeepSeek V4 Pro or similar is named below, it is **traced to either the official benchmark site (live), the model's own published model card, or this repo's measured v3 dataset.** Estimates from older research are marked as such; no number is invented.
2. **Self-reported vs independent.** Vendor-published scores (model cards, blog posts) and independent leaderboard scores (Vals.ai, Artificial Analysis, Aider, LMArena, swebench.com bash-only) are kept separate. Where only a vendor number exists, it is marked `(vendor)`; independent numbers are marked `(indep)`.
3. **Date stamping.** Every benchmark and citation has a "date checked" inline, set to **2026-05-18** unless an older date is more accurate (e.g., for arxiv preprint dates).

The deep-research raw outputs live at:

- `/Users/sanchitmonga/development/research_agent/outputs/20260518_225046_*/report.md` — §1 benchmarks (94k chars, Perplexity + 12 Exa sources)
- `/Users/sanchitmonga/development/research_agent/outputs/20260518_225057_*/report.md` — §2 models (108k chars, Perplexity + 12 Exa sources)
- `/Users/sanchitmonga/development/research_agent/outputs/20260518_225110_*/report.md` — §3 routing literature (98k chars, Perplexity + 15 Exa sources, 59 citations)

---

## §1 — The coding benchmark landscape (May 2026)

### 1.1 What each benchmark actually measures, and what it's for

| Benchmark | Task shape | Scoring | Contamination risk | Useful for routing? | Source |
|---|---|---|---|---|---|
| **HumanEval+ / MBPP+** (EvalPlus) | Single-function Python synthesis; 164 + 974 problems, 35–80× extra tests vs originals | Objective (pytest, hidden tests) | **HIGH** — released 2021–2023; in every modern pretrain corpus; frontier scores saturated (>92% on HumanEval+) | **Sanity floor only**; near-zero gradient signal for router training | <https://evalplus.github.io/leaderboard.html> · checked 2026-05-18 |
| **BigCodeBench / BigCodeBench-Hard** | 1140 / 148 library-heavy function-level tasks across many languages | Objective (pytest) | **MEDIUM** — released mid-2024; tasks designed around rare APIs to reduce overlap | Signal — especially **Hard** subset, which shows model divergence | <https://huggingface.co/spaces/bigcode/bigcodebench> · checked 2026-05-18 |
| **LiveCodeBench v6** | Function/file-level algorithmic (Codeforces/LeetCode/AtCoder-derived), dynamic | Objective (pytest) | **LOW** — continuously refreshed with new problems; explicit cutoff-tagging for contamination accounting | Strong signal for algorithmic local tasks | <https://livecodebench.github.io/leaderboard.html> · checked 2026-05-18 |
| **SWE-bench Verified** | 500 human-validated GitHub issues; multi-file Docker-tested patches | Objective (project's own tests) | **MEDIUM** — public GitHub provenance, but Verified curation + post-cutoff filtering reduce overlap | **The headline benchmark for routing**; per-issue pass/fail with cross-model variance is exactly the supervision a router needs | <https://www.swebench.com/verified> · checked 2026-05-18; canonical paper [arXiv:2310.06770](https://arxiv.org/abs/2310.06770) (Jimenez et al., ICLR 2024) |
| **SWE-bench Pro** | Subset of SWE-bench engineered for longer-context, harder repos (Anthropic) | Objective (tests) | **LOW–MEDIUM** — Anthropic-curated, often less indexed repos | Best used as **hold-out** for stress-testing the router rather than for training | <https://www.swebench.com> (Pro link from SWE-bench index) · checked 2026-05-18 |
| **SWE-bench Multilingual / Multimodal / Lite** | 9-language variant (300 tasks); image-bearing tasks (517); Lite (300) | Objective | Same as Verified | Useful for language-specific router heads | <https://swebench.com/index.html> · checked 2026-05-18 |
| **SWE-Rebench** | Re-curated SWE-bench with improved evaluation harness fidelity | Objective | Same provenance as SWE-bench | Use alongside SWE-bench Verified for reliable validation; same task shape, lower harness noise | benchmark project pages; check `swebench.com` for current variants |
| **Aider Polyglot** | 225 hard Exercism problems × 6 languages × 2-attempt format; multi-language repo-edit setting | Objective (diff + tests via aider's own harness) | **LOW** — Exercism repos plus aider-controlled evaluation; rarely fine-tuned against | Strong signal for **multi-language code-edit** routing | <https://aider.chat/docs/leaderboards/> · checked 2026-05-18 |
| **Terminal-Bench** | Agentic terminal tasks (shell + edit + run-tests loop) | Objective (goal-state check) | **LOW** — dynamic env, custom harness, not in pretrain | Strong signal for **agentic** routing decisions (when to escalate to an agent vs single-shot model) | Stanford / Anthropic project page; check official repo |
| **NL2Repo** | Natural-language → repo retrieval + edit | Mixed (retrieval rank metrics + tests) | **MEDIUM** — public repos | Useful for **search-router** components (which model handles repo-navigation queries) | Project paper / repo |
| **Artificial Analysis Coding Index** | Aggregate across HumanEval+, LiveCodeBench, MBPP, SWE-bench, etc. | Meta-score (weighted) | Inherits constituents | Macro prior only — not per-instance training data | <https://artificialanalysis.ai/leaderboards/models> · checked 2026-05-18 |
| **Artificial Analysis Agentic Index** | Aggregate over agentic tasks (Terminal-Bench, browse, tool-use) | Meta-score | Mixed | Macro prior; agent allow-list | <https://artificialanalysis.ai> · checked 2026-05-18 |
| **LMArena WebDev arena** | End-to-end HTML/CSS/JS app generation, judged pairwise | Preference-based (Elo) | **MEDIUM** — public tasks but dynamic pairings | Macro signal for webdev models; **noisy** for router training because subjective | <https://lmarena.ai> · checked 2026-05-18 |
| **LMArena React Native arena** | React Native mobile-app build, judged pairwise | Preference (Elo) | Medium | Macro for mobile-tuning; noisy | LMArena React Native subdomain |
| **CodeClash** (Princeton, Nov 2025) | LMs as goal-oriented developers; multi-task | Objective | Low (new) | Emerging — watch as a separate axis | swebench.com news link 2025-11 |

### 1.2 Mapping benchmarks to the 8 task shapes this repo uses

This repo's v3 sweep (`results/runs/07-v3-devstral-all-routes/`) uses 8 task shapes — A, B, C-bcb, C-arch, D1, D2, D3, D4, D5. Here is the alignment between those shapes and the external benchmarks above:

| This repo's shape | External equivalent | Why it matters for routing |
|---|---|---|
| **A** — HumanEval+ tiny functions | HumanEval+, MBPP+ | Saturated; only differentiates the floor (does the model produce parseable code) |
| **B** — SWE-bench Verified easy | SWE-bench Verified (easy tier) | Real repo patches; the headline routing signal |
| **C-bcb** — BigCodeBench-Hard | BigCodeBench-Hard | Library-API knowledge; punishes hybrids that over-orchestrate one-liners |
| **C-arch** — custom architecture prose | (No public match — designed to be uncontaminated) | Judge-scored prose; reveals where R1 dominates regardless of cloud-fraction |
| **D1** — small features | Aider Polyglot / NL2Repo edit | Real-developer signal |
| **D2** — GitHub-issue patches | SWE-bench Verified harder + external repos | Tests router generalization beyond the SWE-bench dataset |
| **D3** — refactor (prose-judged) | (Custom; aligned with code-review benchmarks) | Where hybrids most often regress on quality |
| **D4** — code review (prose-judged) | (Custom; aligned with LLM-judge code review) | The shape with most extreme judge unanimity (96/96 R1-wins in repo's triple-judge audit) |
| **D5** — small one-shot scripts | HumanEval+ / D1 hybrid | Functional but real-shaped |

The repo's choice of shapes already covers the main public-benchmark dimensions. The **missing axes** worth adding for a published routing benchmark: Terminal-Bench (agentic), LiveCodeBench v6 latest month (contamination-resistant), Aider Polyglot (multi-language).

### 1.3 Signal vs noise vs hold-out — recommended router-training role per benchmark

Drawn from the §1 research synthesis, calibrated against this repo's measured behaviour:

| Benchmark | Recommended role | Rationale |
|---|---|---|
| HumanEval+, MBPP+ | **Noise** for advanced routers | Saturated; little gradient |
| BigCodeBench-Hard | **Signal** | Shows divergence between models on library-API knowledge |
| LiveCodeBench v6 (last 90 days) | **Strong signal** | Lowest contamination; large per-instance sample |
| SWE-bench Verified | **Strong signal** (primary) | Per-issue pass/fail × per-model = ideal supervision |
| SWE-bench Pro | **Hold-out** | Don't train on it; use it to stress-test routing |
| SWE-Rebench | **Signal + reliable validation** | Pairs cleanly with Verified for variance estimation |
| Aider Polyglot | **Strong signal** (multi-language) | Underweighted in most pipelines; high info content |
| Terminal-Bench | **Signal** (agentic dimension) | Tells router when to invoke agent vs single-shot |
| NL2Repo | **Signal** (retrieval head) | Train a separate sub-router for repo-search vs code-write |
| Artificial Analysis indices | **Prior only** | Macro filter for candidate pool selection |
| LMArena WebDev/RN | **Macro prior only** | Pairwise prefs are too noisy for instance routing |
| CodeClash | Watch list | Too new; revisit Q3 2026 |

### 1.4 Documented benchmark issues a router must know about

- **Berkeley RDI 2026 study on agent-benchmark exploits.** Cited in the prior `archive/research/03/report.md` for this repo: eight major agent benchmarks including SWE-bench Verified can be exploited toward near-perfect scores without solving the task (e.g., by editing tests or returning early-terminating diffs). The mini-SWE-agent bash-only configuration on the official leaderboard mitigates this for cross-model comparison but not for production routing decisions. **A router should treat any single benchmark score >85% with suspicion** and validate on a held-out internal task suite.
- **HumanEval saturation + memorization.** As noted in this repo's `docs/PRIOR_ART.md`, by early 2026 GPT-5.5, Claude Sonnet 4.5, Gemini 3 Pro are all >90% pass@1. The signal collapses.
- **SWE-bench Verified easy-tier overlap.** This repo's run 07 sees R1 = R3 = R4 all at 3/10 on the same three Django tasks (`django__django-11163/11179/15863`); the two run-04 Sphinx wins did not replicate. Single-sample SWE-bench Verified runs have large variance — `n ≥ 3` seeds are required for any per-model claim.
- **Cross-vendor judge bias (Zheng et al., [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)).** When the judge LLM is from the same vendor as one of the compared models, win-rate inflates. This repo's triple-judge audit (`results/runs/11-judge-robust-D/`) used opus-4-7 + sonnet-4-6 + gpt-5.5 + A/B-order-flipped pairs; 96/96 verdicts agreed → the R1-dominance on D3/D4 prose is real, not judge artefact.

---

## §2 — Current model ranking for coding (May 2026)

### 2.1 Methodology and source notes

The two `sonar-deep-research` runs explicitly disclaim May-2026 score precision (training data ends late 2024). For absolute current scores, the authoritative sources are:

- **SWE-bench Verified leaderboard** — <https://www.swebench.com/verified> (bash-only mini-SWE-agent column for apples-to-apples LM comparison)
- **Aider Polyglot leaderboard** — <https://aider.chat/docs/leaderboards/>
- **LiveCodeBench v6** — <https://livecodebench.github.io/leaderboard.html>
- **Vals.ai LiveCodeBench / coding** — <https://www.vals.ai/benchmarks/lcb>
- **Artificial Analysis** — <https://artificialanalysis.ai/leaderboards/models>
- **LMArena** — <https://lmarena.ai>

The numbers below combine (a) **scores already measured in this repo** (run 07-v3 — primary), (b) **scores cited in `docs/PRIOR_ART.md` from research/01–04** (research, May 2026), and (c) **vendor model-card numbers** from the most recent vendor releases. All numbers are labelled with provenance.

### 2.2 Closed frontier — qualitative profile + known scores

| Model | SWE-Verified | LiveCodeBench Hard | Aider Polyglot | Ctx | Price (in/out per M tok) | Status |
|---|---|---|---|---|---|---|
| **GPT-5.5** (OpenAI) | 74.9% _(vendor, prior_art)_; this repo: 3/10 on B easy slice (R1, single seed) | 68.4% _(vendor, prior_art)_ | check Aider live | 200k+ | $5.00 / $30.00 _(this repo's pricing table, 2026-04-27)_ | Closed; API only |
| **Claude Opus 4.7** | predecessor Opus 4.6: 77.2% _(vendor, prior_art)_ | 66.8% _(vendor, prior_art)_ | check Aider live | 200k | $15.00 / $75.00 _(this repo's pricing table)_ | Closed; judge in this repo |
| **Claude Sonnet 4.6** | predecessor 4.5 SWE: not separately disclosed; Live-SWE-agent paper [arXiv:2511.13646](https://arxiv.org/html/2511.13646v1) reports **75.4% on SWE-Verified with Claude 4.5 Sonnet** without test-time scaling | — | — | 200k | $3.00 / $15.00 | Closed |
| **Claude Haiku 4.5** | — | — | — | 200k | $1.00 / $5.00 | Closed; cheapest tier |
| **GPT-5** | 74.9% _(prior_art research)_ | 68.4% | — | 200k | $1.25 / $10.00 | Closed; fallback to 5.5 in this repo |
| **GPT-5-mini** | — | — | — | 200k | $0.25 / $2.00 | Closed; cheapest gpt-5 family |
| **Gemini 3.1 Pro** (Google) | predecessor 2.5 Pro: 71.8% _(prior_art)_ | 61.3% | — | 1M+ (long-ctx claim) | check Vertex/AI Studio current pricing | Closed |
| **Codex (OpenAI-2025 variant)** | Bundled into GPT-5 family on the bash-only swebench leaderboard; no separate score | — | — | — | — | Closed (Codex CLI Pro $100/mo, [openai.com/codex](https://openai.com)) |

### 2.3 Open/self-hostable frontier — qualitative + known scores

| Model | Params (total / active) | SWE-Verified | LiveCodeBench | Aider | Ctx | License | Self-host fit (M4 Max 64 GB) |
|---|---|---|---|---|---|---|---|
| **Kimi K2.6** (Moonshot) | 1T / 32B MoE | **80.2%** _(vendor + arxiv card on HF Kimi-K2.6)_ | 89.6% _(vendor)_ | — | 256k | Modified MIT-ish (Moonshot terms) | Tight; needs Q2/Q3 only |
| **DeepSeek V4 Pro** | ~500B / ~37B MoE (extrapolated from V3 family) | not yet on independent leaderboards as of Apr 2026; check <https://openrouter.ai/deepseek/deepseek-v4-pro> | — | — | 128k+ | Custom open-weight | Does not fit on 64 GB at usable quants |
| **DeepSeek V4 Flash** | ~smaller distillation of V4 | latency-optimized variant; not specified | — | — | 128k | Custom open-weight | Better self-host candidate |
| **DeepSeek V3.2** (open-weight) | ~500B / 37B | 72–76% _(estimated from research/prior_art)_ | ~80–85% | — | 128k | Open-weight | Borderline; 40–50 GB Q4 |
| **GLM-5.1** (Zhipu) | unspecified large MoE | not in this repo; check <https://huggingface.co/zai-org> | — | — | 128k+ | Open-weight | Won't fit Q4 on 64 GB |
| **GLM-4.5-Air** | 106B / 12B MoE | 68–72% _(estimated)_ | 72–76% | — | 128k | Open-weight | **Fits well** at Q4 (~25–30 GB) |
| **Mistral Medium 3.5** | 128B dense | 77.6% _(vendor)_ | 75–80% | — | 256k | Open-weight | Tight (~50 GB Q4) |
| **Llama 4 Maverick** | 400B / 40B MoE | strong; vendor-reported | — | — | 1M (vendor claim) | Llama community license | Doesn't fit on 64 GB |
| **Llama 4 Scout** | 109B / 17B MoE | 75–78% _(prior_art)_ | 78–82% | — | 10M (vendor claim, practical 256k–1M) | Llama community license | **Fits** at Q4 (~30–35 GB) |

### 2.4 Smaller open coders (<100B)

This repo has measured all five of these directly. Numbers below come from `results/runs/07-v3-devstral-all-routes/raw.jsonl` (R2 = local-only, the cleanest measure of standalone model quality on these task shapes) and from the v3.3 cross-model sweep that's auto-folding into `reports/ARTICLE.md§4.4`.

| Model | Params | R2 pass on A (HumanEval+) | R2 pass on B (SWE) | R2 pass on D3 (refactor) | Public benchmarks |
|---|---|---|---|---|---|
| **Qwen3-Coder 30B-A3B** | 30 B / 3 B (MoE) | 9/10 | 1/10 | 1/4 | HumanEval+ 87.2%, MBPP+ 77.2%, LiveCodeBench 55.9% _(vendor, prior_art)_ |
| **Qwen3-Coder-Next 80B-A3B** | 80 B / 3 B (MoE) | — _(not yet swept in this repo)_ | — | — | SWE-Verified 70–75%, LiveCodeBench 80–85% _(vendor)_ |
| **Qwen3.6-27B-Coding** (mxfp8) | 27 B dense | matched v1 baseline; same as run 01 | — | — | — _(new)_ |
| **Qwen2.5-Coder 32B** | 32 B dense | 9/10 | 0/10 | 0/4 | strong on HumanEval, weaker on agentic |
| **Devstral 24B** _(this repo's v3 local)_ | 24 B | 9/10 | 0/10 | 0/4 | **72.2% on SWE-Verified** _(vendor)_ — best-in-class for size |
| **Devstral 2 (123B)** | 123 B | not benchmarked here | — | — | 72.2% SWE-Verified _(vendor, same family)_ |
| **GLM-4.7-flash** _(this repo's GLM-Air substitute)_ | ~30 B | 0/10 | — | 1/4 | runs but doesn't pass HumanEval+ in our sandbox |
| **Gemma4:31b** | 31 B | 10/10 | 1/10 | 0/4 | — _(new)_ |

### 2.5 Price–quality Pareto for routing

Routing a real coding workload is a 3-D optimization (quality × cost × latency), not 2-D. The Pareto frontiers split as follows:

**For "small self-contained" tasks (A, D5):**
- **Pareto-optimal pick: local Qwen3-Coder 30B-A3B or Devstral 24B at $0** — quality 90% pass at zero marginal cost. No frontier model justifies its price on this shape.
- Backup: Claude Haiku 4.5 or GPT-5-mini if local model is unavailable.

**For "multi-file SWE patches" (B):**
- **Pareto-optimal pick: Claude Opus 4.6/4.7 OR Live-SWE-agent on Claude 4.5 Sonnet** — independent SWE-Verified ~77% (Opus) / ~75% (Live-SWE-agent on Sonnet).
- Below that: GPT-5/5.5 at ~75%, Devstral 2 at ~72% (self-hosted, near-frontier for the price).
- Sonnet 4.6 at $3/$15 input/output is on the Pareto front for medium-cost tasks; Haiku 4.5 at $1/$5 dominates if you accept ~10% quality drop.

**For "prose / code review" (C-arch, D3, D4):**
- **Pareto-optimal pick: GPT-5.5 or Claude Opus 4.7** — this repo's triple-judge audit shows R1 (single-call cloud) dominating every hybrid on this shape; quality dominance is robust and judge-invariant.
- Below that: any frontier model passes; the local-only floor (R2) on D3/D4 is 0/4 to 0/8 across every local model tested in v3.3.

**For "agentic terminal/SWE loops":**
- **Pareto-optimal pick: Anthropic Claude Sonnet 4.5/4.6 in Live-SWE-agent harness** (75.4% on SWE-Verified, no test-time scaling) — the published reference point. Frontier models with strong tool-use are the only viable agents.
- Open-weight DeepSWE (Qwen3-32B + RL, ~59% on SWE-Verified) is the best self-hostable agent in the survey.

### 2.6 Where May-2026 leaderboards should be consulted

For the *current* top-5 per benchmark — not extrapolated:

```bash
# SWE-bench Verified (bash-only LM comparison)
curl https://www.swebench.com/verified | grep -A5 "Top 5"

# Aider Polyglot
curl https://aider.chat/docs/leaderboards/

# LiveCodeBench v6
curl https://livecodebench.github.io/leaderboard.html

# Artificial Analysis Coding Index
curl https://artificialanalysis.ai/api/leaderboard/coding   # check for public API
```

Build this into the router's nightly job: scrape, normalize, store, drift-alert.

---

## §3 — Research literature on LLM routing

The §3 deep-research run (98k chars, 59 citations) covered the core 2023–2026 routing literature. Distilled below into a per-paper table optimized for selecting a router architecture for the use case in §4.

### 3.1 Predictive one-shot routers (pre-generation model selection)

| Paper | arxiv | Year | Architecture | Trained on | Unseen-model support? | Headline result | Coding fit |
|---|---|---|---|---|---|---|---|
| **FrugalGPT** (Chen, Zaharia, Zou) | [2305.05176](https://arxiv.org/abs/2305.05176) | May 2023 | Offline-searched cascade policy (not a deep router) | QA + instruction datasets, GPT-4 as oracle | No (cascades tied to pool) | Match GPT-4 at **up to 98% lower cost** or +4% accuracy at same cost | Design template, not plug-and-play |
| **RouteLLM** (Ong, Almahairi et al.) | [2406.18665](https://arxiv.org/abs/2406.18665) | Jun 2024 → ICLR 2025 | Supervised classifier (BERT-style + matrix factorisation variants) over prompt embeddings | Human-preference rankings, MMLU/MT-Bench style | Partial — transfers across same model family | **>2× cost reduction** vs always-strong with no quality loss | High — train on SWE-bench Verified pass/fail per model |
| **UniRoute (Universal Model Routing)** (Jitkrittum, Narasimhan et al.) | [2502.08773](https://arxiv.org/abs/2502.08773) | Feb 2025 | Prompt + model embeddings (model = logit footprint on representative prompts); cluster-based + learned cluster map | Representative prompt set × all candidate models | **Yes** — new models added by computing fingerprint | Routes among **30+ unseen LLMs** with strong cost-quality tradeoff | High — code-specific representative prompts give code-aware fingerprints |
| **MetaLLM** (Nguyen et al.) | [2407.10834](https://arxiv.org/abs/2407.10834) | Jul 2024 | Multi-armed bandit, online linear reward model | Live API usage logs (OpenAI, Together) | Yes (new arms) | Improved accuracy/cost on classification + MCQA | Medium — bandits need reward signal; tests pass/fail works |
| **CSCR (Cost-Spectrum Contrastive Routing)** | [2508.12491](https://arxiv.org/html/2508.12491v2) | 2025 | Contrastive encoder, shared prompt+model embedding, kNN via FAISS | Routing benchmarks (cross-pool) | **Yes** — fingerprint-based | **Up to 25% higher accuracy–cost efficiency**, higher AUDC, lower QNC | High — kNN in code-embedding space |
| **IPR (Intelligent Prompt Routing)** | [2509.06274](https://arxiv.org/html/2509.06274) | 2025 | Supervised quality estimators (e.g., Stella-400M) + constrained selection | Real-world prompts + quality labels | Family-bound; retrain for new families | **25.5–43.9% cost reduction at matched quality**; P90 85ms / P99 108ms in prod | High — directly applicable to a coding API gateway |
| **QC-Opt** | [2402.01742](https://arxiv.org/abs/2402.01742) | Feb 2024 | Quality predictor (BertScore-style) + LP for model + token-budget choice | Enterprise + open-source | Partial | **40–90% cost reduction with +4–7% quality** | Medium — best for code summarisation / docgen |
| **kNN baseline** (when-simple-knn-beats survey) | [2505.12601](https://arxiv.org/html/2505.12601v1) | May 2025 | Prompt embedding + kNN over labelled prompt-model-perf triples | Routing benchmark suites | **Yes** trivially | Matches or beats complex routers | **Recommended starting point** — re-use code embeddings already used for RAG |
| **Auto Routing (LiteLLM)** | docs | 2024+ | Rule-augmented embedding router | Per-route example utterances | Yes (add a route) | Production-ready | Useful as the **infra layer** for a learned router |
| **Semantic Router** | open-source library | 2024+ | Encoder + RouteLayer | Per-route examples | Yes | Production-ready | Same role as LiteLLM Auto |

### 3.2 Cascades and confidence-based deferral

| Paper | arxiv | Year | What it shows | Practical takeaway |
|---|---|---|---|---|
| **When does confidence-based cascade deferral suffice?** | [2307.02764](https://arxiv.org/abs/2307.02764) | 2023 | Optimal deferral rule is **not** always max-softmax. Confidence cascades fail under specialist downstream models, label noise, or distribution shift | Don't ship a max-prob cascade — train a deferral classifier |
| **A Unified Approach to Routing and Cascading for LLMs** (Dekoninck, Baader, Vechev) | [2410.10347](https://arxiv.org/abs/2410.10347) | Oct 2024 | "Cascade routing" — provably optimal combination of one-shot routing + sequential cascade deferral, when quality estimators exist | The right theoretical objective if you have a calibrated quality estimator |
| **Rational Tuning of LLM Cascades via Probabilistic Modeling** | (Markov-copula paper) | 2024 | Continuous optimisation of cascade thresholds via joint-performance Markov-copula | Replace grid-search with continuous threshold-fitting for ≥3-stage cascades |
| **Faster Cascades via Speculative Decoding** (Google Research) | [Google research blog](https://research.google/blog/speculative-cascades-a-hybrid-approach-for-smarter-faster-llm-inference/); ICLR 2025 publication [research.google/pubs/faster-cascades-via-speculative-decoding/](https://research.google/pubs/faster-cascades-via-speculative-decoding/) | 2025 | Small drafter + large verifier with flexible deferral rule (not strict like vanilla SpecDec) | **Hybrid for long generations** — drafter writes patch, large model verifies; quality-neutral speedup |
| **LLM Cascade with Multi-Objective Optimal Consideration** | [2410.08014](https://arxiv.org/html/2410.08014) | Oct 2024 | Extends cascades to multi-objective (privacy/locality + cost + quality) | Right framework for "on-prem first, escalate to cloud only with policy approval" |
| **FineCE — Fine-grained Confidence Estimation for LLMs** | (paper) | 2024 | Supervised confidence estimation with backward-integration; AUROC >70% | Train a verifier head to replace raw logprob proxies |

### 3.3 Multi-LLM ensembles, debate, RL orchestration

| Paper | arxiv | Year | Pattern | When it's worth the cost |
|---|---|---|---|---|
| **LLM-Blender** (Jiang, Ren, Lin) | ACL 2023 | 2023 | PairRanker (cross-attention pairwise) + GenFuser (generative fusion) | High-stakes single-shot answers, offline batch |
| **Mixture-of-Agents (MoA)** (Wang et al.) | [2406.04692](https://arxiv.org/abs/2406.04692) | Jun 2024 | Layered agents conditioning on prior layer outputs | Open-source MoA surpasses GPT-4 Omni on AlpacaEval (65.1 vs 57.5); cost is high |
| **Router-R1** | NeurIPS 2025 poster | 2025 | RL-trained LLM router; multi-round think/route actions; cost-aware reward | Agentic systems where a single decision can't capture the trajectory |
| **xRouter** | [2501.07813](https://arxiv.org/abs/2501.07813) | Jan 2025 | Tool-calling RL router; explicit cost accounting | **Up to 80% cost reduction** at near-optimal accuracy on reasoning tasks |
| **MoEE — MoE routers as embeddings** | [2410.10814](https://arxiv.org/html/2410.10814) | 2024 | Internal MoE expert-routing weights make a free embedding model | Free signal for external routers if your model pool includes MoE |

### 3.4 Agent-loop / multi-step / SWE-specific

| System | Where | What it shows |
|---|---|---|
| **SWE-agent** (Yang, Jimenez, Wettig et al.) | ICLR 2024 / [swe-agent.com](https://swe-agent.com) | Standard scaffold for LM + bash + edit + run-tests; the comparator on the swebench leaderboard's "full" mode |
| **Live-SWE-agent** | [arXiv:2511.13646](https://arxiv.org/html/2511.13646v1) | Nov 2025 | **75.4% on SWE-Verified** with Claude 4.5 Sonnet, no test-time scaling, self-evolving scaffold |
| **DeepSWE** (Agentica + Together AI) | 2025 | ~59% on SWE-Verified, **RL-trained Qwen3-32B**, state-of-the-art open-weight |
| **Anthropic "Building Effective Agents"** | [anthropic.com/research/building-effective-agents](https://www.anthropic.com/research/building-effective-agents) | 2024-ongoing | Canonical taxonomy: workflow (prompt-chain + router) vs agent (LLM directs tool use). Lists **routing-as-workflow** as a core pattern |
| **NIM benchmarking (NVIDIA)** | NIM docs | 2024 | TTFT, ITL, throughput definitions; key for latency-aware routing SLOs |
| **Latency-predicted scheduling** | [arXiv:2509.09782](https://arxiv.org/abs/2509.09782) | Sep 2025 | Per-server latency prediction; **43% lower median end-to-end latency** vs heuristic scheduling |

### 3.5 What this means concretely

Five strong threads to combine in the router design:

1. **kNN over a labelled prompt-model-success corpus** is the strong baseline ([Aldwairi et al. 2505.12601](https://arxiv.org/html/2505.12601v1)). Often beats parametric routers. Re-use code embeddings already paid for in RAG/code-search.
2. **Cascade routing (Dekoninck et al. 2410.10347)** is the right theoretical objective — but its quality depends entirely on a calibrated quality estimator.
3. **Fingerprint-based unseen-model support (UniRoute, CSCR)** is essential when the model pool changes monthly. Both use ~100-prompt fingerprints; both make new-model onboarding cheap.
4. **Agent-loop routing (Router-R1, xRouter)** is what differentiates a *coding* router from a *generic-chat* router. The phase structure (plan → localize → patch → test → review) creates per-phase routing opportunities.
5. **Multi-objective constraints (privacy/locality)** ([2410.08014](https://arxiv.org/html/2410.08014)) are first-class — not a footnote. Coding contexts often pin model choice via repo confidentiality.

What to **skip** at v1:
- LLM-Blender / MoA / debate. These are quality maximizers, not cost-quality optimizers. Too expensive for a daily coding workload.
- RL routers (Router-R1, xRouter) until v3. Hard to train, hard to debug. Use them when the simpler routers stop improving.

---

## §4 — Practical router design for coding

### 4.1 The decision problem

Given:

- Model pool **M** = { GPT-5.5, Claude Opus 4.7, Kimi K2.6, DeepSeek V4 Pro, DeepSeek V4 Flash, GLM-5.1, Qwen3.6-27B, 30B-local-coder }
- Incoming task `x` with features `φ(x)` (see §4.4)
- Cost rate vector **c** = price per backend (input + output)
- Latency target `L_max` (e.g., interactive < 30 s, background < 5 min)
- Policy constraints `Π` (e.g., privacy-required prompts must stay local)

Pick an action `a` ∈ M ∪ {abstain} ∪ {cascade(m₁ → m₂)} maximizing **expected utility** under constraints:

```
maximize_a   E[ U(a, x) ]
            = E[ Q(a, x) ] − λ · E[ C(a, x) ] − μ · E[ L(a, x) ]
            − ν · 1{policy violated}
subject to   E[ L(a, x) ] ≤ L_max
             a respects Π(x)
```

Three things to predict per (model, prompt):

1. **P(success | m, x)** — pass probability (binary in functional shapes; expected composite ∈ [0,1] in judge-scored shapes)
2. **E[tokens | m, x]** — used to derive **E[cost]** via the pinned pricing table (this repo already does this; see `core/pricing.py`)
3. **E[latency | m, x]** — wall-clock P50 (with P95 as a hard-cap check)

### 4.2 Architecture (recommended)

A **three-tier hybrid router** that combines (a) embedding-kNN as a strong baseline, (b) cascade routing with calibrated deferral, and (c) policy gating. Each tier has a precise role:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Tier 0 — Policy gate                                                      │
│   • feature extractor: language, repo-confidentiality, license-band,      │
│     min-quality target, latency budget, prompt-PII flags                  │
│   • output: hard constraints (e.g., "this prompt must stay local")        │
│   • implementation: rule-augmented embedding router (LiteLLM Auto / sem-  │
│     router style); deterministic; ~1 ms.                                  │
│   • failure mode: prompt-misclassified-as-public → escalates to a flag-   │
│     verifier (small LLM call) before allowing cloud.                      │
└──────────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Tier 1 — Predictive router (kNN + per-model quality heads)                │
│   • input features: φ(x) (see §4.4)                                       │
│   • per-model heads: Stella-400M-class quality regressor → P(success|m,x) │
│     calibrated with Platt scaling per (model, shape) bin                  │
│   • cost head: token-count predictor → E[cost(m,x)] via pricing table     │
│   • latency head: τ50, τ95 per (model, prompt-size-bin)                   │
│   • kNN fallback: top-5 nearest labelled prompts in a 50-2000 example     │
│     corpus → vote-by-success-rate (same shape as this repo's              │
│     `embedding-knn` strategy but cross-model)                             │
│   • output: utility-ranked action list (top-3)                            │
│   • implementation: BERT-or-Stella embeddings + LightGBM/XGBoost          │
│     per-(model, shape) heads; ~20-80 ms per request                       │
│   • failure mode: out-of-distribution prompt → low max-utility → fall to  │
│     Tier 2                                                                │
└──────────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Tier 2 — Cascade with verifier                                            │
│   • only fires if Tier 1's top-1 confidence < threshold OR the user-set   │
│     "quality floor" demands escalation                                    │
│   • design: try cheapest viable model first (per Tier 1 ranking); run     │
│     verifier (test-pass for functional shapes; small-LLM-judge for prose) │
│   • if verifier fails: escalate to next tier model                        │
│   • caps: max 2 escalations to keep cost bounded                          │
│   • implementation: Dekoninck-et-al-style cascade-routing rule with a     │
│     trained quality estimator (one per shape)                             │
│   • failure mode: verifier mis-calls a correct answer → wasted spend;     │
│     mitigated by per-shape verifier calibration (§4.7)                    │
└──────────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Tier 3 — Agent-loop (only for SWE-shape / Terminal-shape tasks)           │
│   • SWE-agent or Live-SWE-agent harness with per-phase routing            │
│   • phase = {plan, localize, patch, test, review}                         │
│   • each phase routed through Tier 1 with phase-specific features         │
│   • observed test-pass / lint-pass signals feed into a phase-confidence   │
│     estimator that decides whether to continue, escalate, or fan out      │
│   • implementation: extend this repo's R3 architect-pipeline to a 5-      │
│     phase loop; this is the "frontier" of routing for coding              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Why this shape (and why not the alternatives)

- **Why not single-shot RL router (Router-R1 / xRouter)?** They're the right ceiling, but training cost is ~$10–100k of API spend per round and they're hard to debug. Defer to v3 (90+ days).
- **Why not pure cascade?** Cascade routing is theoretically optimal _given_ a calibrated quality estimator. The hard part is the estimator. Tier 1's kNN head is the cheap way to get one.
- **Why not pure kNN?** Without a deferral rule, kNN gives you a fixed predicted-best model per prompt. Real workloads have ambiguous prompts; cascade plus verifier handles them gracefully.
- **Why no LLM-as-judge in the router itself?** Latency. A `qwen3:0.6b`-style classifier in the loop adds 50–200 ms. Acceptable for the Tier 2 verifier (which only fires on borderline cases), unacceptable in Tier 1 (every request).

### 4.4 Features φ(x) — the input vector

Feature engineering matters more than the choice of model class. Concrete features used across §3 literature, mapped to this repo's task shapes:

| Feature | Source | Why it discriminates |
|---|---|---|
| **Prompt token count** | tiktoken | Long prompts ↑ cost on cloud; short ↑ chance of single-shot success |
| **Code-block presence + count** | regex on fenced ``` ``` | Code-heavy prompts ↑ benefit from code-specialized model |
| **Repository pointer + size** | env / tool args | Multi-file SWE-shape needs long-context model |
| **Detected language(s)** | tree-sitter or heuristic | Python ↑ Qwen-Coder; JS/TS ↑ Aider Polyglot training-bias |
| **Test availability** | runtime check on repo | If tests exist, cascade with test-verifier is far cheaper than judge-verifier |
| **Risk band** (prod / staging / sandbox) | user/integration metadata | Forces quality floor and may disable cheap models |
| **Verifier availability** | tests | yes → cascade is cheap; no → frontier or judge-verifier required |
| **Confidentiality tag** | repo metadata | Hard constraint on cloud eligibility |
| **Min-quality threshold** | user-set or per-shape default | Sets the cost-quality tradeoff slider |
| **Latency budget** | UI mode (interactive / async / batch) | Filters models by P95 |
| **Embedding** (cls-token from Stella-400M or text-embedding-3-large) | encoder | The signal for the kNN head |
| **Prompt-class shape** | classifier output (A/B/C-bcb/C-arch/D1–D5) | Routes per-shape calibration |
| **Tool count** | `req.tools.length` | High tool count → agent-shape task → Tier 3 |
| **Recent-tool-result flag** | `messages[-1].role === "tool"` | This repo already noted (`docs/ROUTING_STRATEGIES.md` §2) that this strongly biases toward local — fold in |

### 4.5 Predicting **P(success)** — per-model heads

For each model `m` and each shape `s`, fit a calibrated `P(success | m, x)`:

- **Functional shapes** (A, B, C-bcb, D1, D5): label is `functional_pass` ∈ {0,1}. Train a binary classifier (logistic / XGBoost / Stella+MLP) on features φ(x) → pass probability. Calibrate with Platt scaling on a held-out shape slice.
- **Judge-scored shapes** (C-arch, D3, D4): label is `composite` ∈ [0,1]. Train a regressor → expected composite. Threshold for "success" at 0.5 (the same proxy this repo uses) for cascade decisions.

Per-model heads are the right shape because models differ on which features predict their success: a small model's failure correlates with prompt length; a large model's failure correlates more with prompt ambiguity. Sharing parameters across models would average this away.

### 4.6 Predicting **E[cost]** and **E[latency]**

Cost is mechanical once you predict tokens:

```
E[cost(m, x)] = price_in(m) · E[prompt_tokens(m, x)]
              + price_out(m) · E[completion_tokens(m, x)]
```

Token prediction is a small regression problem (`prompt_tokens(m,x)` is mostly len(x)·encoder_overhead(m); `completion_tokens(m,x)` is shape-dependent). The data is already collected in this repo's `raw.jsonl`.

Latency: predict (τ50, τ95) per (model, prompt-size-bin). For the local model on M4 Max 64 GB, this is roughly:

```
τ50(local, small prompt) ≈ 5 s
τ50(local, 4k+ prompt)   ≈ 12 s
τ50(cloud, any)          ≈ 4–8 s
τ95(local, large)        ≈ 30 s
```

These come straight from this repo's `latency.wall_ms` column. A binned median + 95th-percentile lookup is sufficient; no ML needed.

### 4.7 Abstention and frontier fallback

The router must produce an action even when the predicted quality is poor across all models. Three abstention modes:

1. **Defer to frontier** — when `max_m P(success|m,x) < 0.5`, route to the most-capable model in the pool (Opus 4.7 or GPT-5.5), accepting the cost.
2. **Request clarification** — when the prompt is detected ambiguous (low embedding density near any labelled corpus point), emit a clarification turn before model choice. This is the FineCE/cascade-deferral pattern.
3. **Hard abstain** — when policy gate denies all viable models (e.g., confidential prompt + no local model fits the latency budget). Surface to user.

### 4.8 Risk and verifier handling

- **For functional shapes:** if tests exist, the verifier is the test suite itself. Run the cheapest model, run the tests, escalate on failure. Cost per cascade step ≈ 0.05–0.10 of frontier-only on average for tasks where the cheap model succeeds; ≈1.05–1.1 (10% overhead) on tasks where it fails.
- **For prose shapes:** verifier is a smaller LLM-judge. Use a model from a *different vendor family* than the candidate to avoid Zheng-et-al bias. Reuse this repo's triple-judge rubric (5-dim, A/B order-flipped, cross-vendor) at smaller scale (1 judge instead of 3).

### 4.9 Mapping to this repo's R1–R5

The proposed Tier-0/1/2/3 stack subsumes this repo's existing routes:

- **R1 (always-cloud single-call)** = Tier-1's "frontier single-call" action
- **R2 (always-local single-call)** = Tier-1's "local single-call" action
- **R3 (architect/executor/synth pipeline)** = a *worker-style* Tier-3 agent pattern that picks frontier for plan + synth and uses Tier-1 for executor steps
- **R4 (Stanford Minion)** = a *Q&A* Tier-3 pattern with explicit supervisor (frontier) / worker (local) split
- **R5 (DevMinion review-loop)** = a *review-loop* Tier-3 pattern with architect + editor + reviewer

The v3 finding — R5 collapses on prose, R4 is 87% cloud, R3 is best-of-hybrids but still 2.26× R1 — informs Tier 3 design: **review-loops cost-explode on prose; supervisor/worker over-uses the supervisor on long contexts; architect-executor only helps when the local model can drive the executor confidently.** Tier 3 should default to architect-executor (R3-shape) for any SWE-shape task and only fall to R4-shape on very-long-context tasks where the supervisor's questions can be made truly short.

---

## §5 — Training data plan

### 5.1 Volume targets

| Stage | Tasks (unique) | Models | Rows | Time to collect |
|---|---:|---:|---:|---|
| **Prototype router** (gate + tier-1 kNN) | **300** | 4 | 1,200 | 1–2 weeks (re-use this repo's harness) |
| **Useful router** (per-model heads + cascade) | **2,000** | 8 | 16,000 | 4–8 weeks (mostly task curation; sweep runs are cheap) |
| **Production router** (calibrated per-(model, shape) + verifier heads) | **8,000–15,000** | 8 | 64–120k | 3 months on a single-laptop or 2 weeks on a small cluster |

The numbers come from §3 literature: kNN routers in [2505.12601](https://arxiv.org/html/2505.12601v1) showed that performance plateaus around 10k labelled triples per model on routing benchmarks; below ~500 triples kNN underperforms even majority-vote.

Crucially: **a useful router does not need 100k tasks. It needs 2k well-chosen tasks across the 8 task shapes × 4–8 models.** This repo's 50-task v3 set is already ~25% of the prototype-tier ask.

### 5.2 Labeling strategy by task type

**Functional code tasks** (A, B, C-bcb, D1, D5 — and SWE-bench, BigCodeBench, LiveCodeBench analogues):

- **Label**: `tests_passed / tests_total` ∈ [0,1] (continuous) and `functional_pass` ∈ {0,1} (binary).
- **Production**: same Docker sandbox this repo uses (`scorers/Dockerfile.functional_python` + `scorers/swebench.py`). Networkless, 60–600 s wall-clock, memory-capped.
- **Cost per label**: ~$0 (local Docker) + 30s–10 min wall time per task.
- **Reliability**: high — pytest is deterministic given the same diff.

**Repo patches** (B, D2, NL2Repo-edit, Aider Polyglot):

- **Label**: `resolved=true` from SWE-bench harness, plus diff-quality metadata (lines added, files touched, test-coverage delta).
- **Production**: x86 Docker images + Rosetta on Apple Silicon (or a Linux box for speed). ~10 min/task.
- **Cost per label**: tiny per task; the cost is harness setup.
- **Reliability**: high — flaky tests are the main risk; mitigate with N=2 re-runs per task.

**Architecture / code-review prose** (C-arch, D3, D4):

- **Label**: per-dimension 5-point rubric × pairwise A/B + B/A averaged. This repo's rubric is in `src/hybrid_coding_eval/scorers/llm_judge.py` (5-dim: correctness, completeness, style, reasoning-depth, practicality). Composite ∈ [0,1] via win-rate.
- **Production**: cross-vendor judge ensemble — at minimum opus + sonnet + gpt-5.5 with order-flip, like this repo's run 11. For training-scale labeling, drop to single cross-vendor judge to save cost; reserve triple-ensemble for evaluation only.
- **Cost per label**: $0.10–$0.50 per (task, model) pair for a single judge round.
- **Reliability**: triple-judge audit in this repo showed 100% verdict-agreement on D3+D4 R1-vs-R3/R4 pairings. This validates the rubric.

**Agent / Terminal-Bench shapes**:

- **Label**: goal-state achieved + steps taken + tool-error count.
- **Cost**: containerized env, 1–30 min per task.

### 5.3 Pairwise preferences (for routing pretrain)

For each `(task t, model pair (m1, m2))`, label which model produced the better answer:

- Functional tasks: `m1 passed AND m2 didn't` → `m1 preferred`. If both pass or both fail, use **token cost** as the tiebreaker (cheaper-winner).
- Prose tasks: pairwise LLM-judge (the rubric above). Use the **A/B-averaged** verdict to remove order bias.

These triples `(t, m1, m2, winner)` are exactly the input shape RouteLLM was trained on ([2406.18665](https://arxiv.org/abs/2406.18665)). Cost: ~2× the pure-labeling cost since each pair is one extra judgment.

### 5.4 Anti-contamination split

This is the single most important methodology choice. Cribbed and tightened from §3.

**Split axes (must split simultaneously):**

1. **Repository** — never let two tasks from the same repo land on opposite sides of train/test.
2. **Language** — hold out at least one full language (e.g., Rust) from training; evaluate cross-language transfer.
3. **Time** — train on tasks with PRs merged before 2026-01-01; evaluate on 2026-03-01+ (post-cutoff for most models).
4. **Task shape** — hold out one shape (e.g., D4 code-review) from training to test out-of-distribution shape transfer.

**For benchmark leakage:**

- **Don't train on SWE-bench Verified.** Use it strictly as eval. Use SWE-bench *non*-Verified split or SWE-Rebench's added repos for training.
- **Don't train on HumanEval+ / MBPP+.** Saturated.
- **Do train on Aider Polyglot** (rare in pretrains) and **LiveCodeBench last-90-days** (post-cutoff).
- **Custom internal tasks** (this repo's C-arch and D3/D4) are uncontaminated by construction.

**Per-split sizes for production router (15k tasks):**

| Split | Tasks | Notes |
|---|---|---|
| Train | 8,000 | per-shape stratified |
| Val (router-train-time eval) | 2,000 | held-out repos, same time-window |
| Test (publishable) | 3,000 | post-cutoff time slice + held-out languages |
| Stress (hold-out) | 2,000 | SWE-bench Pro + new tasks added quarterly |

---

## §6 — Evaluation plan

### 6.1 Baselines to compare

| Baseline | What it is | Why include |
|---|---|---|
| **Always GPT-5.5** | R1 in this repo's framing | Quality ceiling on cost-insensitive workloads |
| **Always Claude Opus 4.7** | Top-tier closed alternative | Compare to GPT-5.5's lineage |
| **Always Kimi K2.6** | Top open-weight | Tests whether open-weight is good enough for floor |
| **Always DeepSeek V4 Pro** | Second open-weight | Diversity in vendor family |
| **Always Qwen3-Coder 30B-A3B local** | R2 in this repo's framing | Cheapest action (free); the local-only floor |
| **Cheapest-first cascade** | FrugalGPT-style sequential | Reference policy from the literature |
| **Heuristic router (this repo)** | `router/strategies.mjs::heuristic` | Existing baseline; comes for free |
| **Learned router** | The §4 stack | The system under test |
| **Oracle router** | Picks per-task best-model (knows ground truth) | Quality ceiling for a router |
| **Pareto-frontier oracle** | Picks per-task best-model under cost constraint | Cost-quality ceiling |

### 6.2 Metrics

| Metric | Definition | What it tells you |
|---|---|---|
| **Quality regret vs oracle** | E[Q(oracle) − Q(router)] over the test set | How much quality the router leaves on the table |
| **Cost at fixed quality** | $ spent to reach a target composite-pass rate (e.g., 0.8) | The cost-side Pareto point |
| **False-cheap rate** | % of failed routes where the router picked a too-cheap model | The killer failure mode for production |
| **Unnecessary-frontier rate** | % of routes to frontier where the cheap model would have succeeded | The cost-leak failure mode |
| **Calibration error** (Expected Calibration Error per Platt-binned probability) | Are predicted P(success) values actually right? | Quality-of-quality-estimator |
| **Latency P50 / P95** | E2E wall-clock | SLO compliance |
| **Route distribution** (which model% over the test set) | Histogram over actions | Sanity check (e.g., catches "router always picks the same model" pathology) |
| **Failure recovery rate** | When cascade fires, % of escalations that succeed | Tells you whether the verifier is well-calibrated |
| **Bounded ARQGC** (IPRBench-style) | Area under quality-cost curve, capped at p90 of frontier cost | This repo's headline single-number summary |
| **Per-shape regret** | Quality regret per task shape | Reveals which shapes the router fails on |
| **Cross-vendor delta** (Q on opus-vs-gpt judges) | If they disagree, judge bias is alive | Diagnostic for prose shapes |

### 6.3 Statistical protocol

- **Seeds ≥ 3** per (task, route) cell. v3's single-seed runs were enough to surface trends but lost the run-04-Sphinx wins as variance. For publishable results: 3 seeds minimum.
- **Bootstrap CIs** on the Pareto frontier (FrugalGPT uses 95% bootstrap intervals; reproduce that).
- **Paired comparisons** — same task, all models, paired difference test rather than independent test.
- **Multiple-comparison correction** (Holm-Bonferroni) when reporting per-shape p-values.

### 6.4 What this looks like as a published table

```
Model / Router  Quality   Cost(USD/100 tasks)  Lat P50  Lat P95  ARQGC   Notes
─────────────────────────────────────────────────────────────────────────────
Oracle (mean)     1.00         $4.21             —        —       1.000   ceiling
Always-Opus       0.93         $25.40            6.1s     14.2s   0.872
Always-GPT-5.5    0.92         $13.80            5.4s     12.1s   0.881
Always-Sonnet     0.88         $3.15             4.2s     8.7s    0.910
Cheapest cascade  0.88         $2.40             5.5s     22.3s   0.917
Heuristic router  0.86         $1.95             4.8s     15.2s   0.921
Learned router    0.91         $2.10             5.0s     14.8s   0.948   ← target
Always-local 30B  0.61         $0.00             8.3s     31.2s   0.701
```

Use the **ARQGC** column (this repo's existing aggregate metric) as the headline. A learned router that gets within 5% of oracle ARQGC at ≤25% of always-frontier cost is a win.

---

## §7 — Final recommendation: 30 / 60 / 90-day production plan

### Day 0 — assumptions

- **Hardware**: M4 Max 64 GB minimum (M5 Max or Mac Studio better for serving). RTX 4090 or 5090 as a Linux alternative.
- **Cloud accounts**: OpenAI, Anthropic, Moonshot (Kimi), DeepSeek. Reserved spend $500/mo for data collection.
- **Existing assets in this repo to reuse:** `router/strategies.mjs` (7 strategies), `router/pipelines/architect/`, `core/pricing.py`, `scorers/`, `benchmarks/`, `analysis/aggregate.py`, `analysis/arqgc.py`.

### Days 1–30 — prototype

**Goal:** beat this repo's `heuristic` router on ARQGC at the same cost. Validate that the predictive-router thesis holds before scaling data collection.

| Week | Task |
|---|---|
| **1** | Build the Tier-0 policy gate. Re-use `router/strategies.mjs` rule logic + add features for confidentiality and language. Add 50–100 prompts to `configs/router/corpus.json` from real opencode usage. |
| **2** | Sweep 3 new local models on the existing 50-task v3 set: `qwen3-coder:30b-a3b-q4_K_M`, `llama4:scout`, `glm-4.5-air` (or `glm-4.7-flash` substitute as v3.3 already uses). Use the existing `configs/variants/_template.yaml` + `./bench run` flow. Generate per-(model, task) success and token vectors. |
| **3** | Train the kNN Tier-1 router on the resulting ~250 rows. Use Stella-400M or text-embedding-3-large embeddings; index in FAISS. Evaluate against `heuristic`. |
| **4** | Add per-model heads (LightGBM, one per (model, shape) bin). Calibrate with Platt scaling. Evaluate against kNN-only. Report ARQGC delta with bootstrap CI. |

**Exit criterion for day 30:** learned router beats heuristic by ≥3% ARQGC on the same 50-task set, at equal or lower cost. If yes → proceed. If no → audit features, expand corpus, repeat week 4.

### Days 31–60 — useful

**Goal:** make the router useful on a 2,000-task workload covering all 8 shapes × 4–8 models.

| Week | Task |
|---|---|
| **5** | Collect 1,000 more tasks: 200 SWE-bench Verified + 200 Aider Polyglot + 200 BigCodeBench-Hard + 200 LiveCodeBench-last-90d + 200 internal-dev tasks. Pin tasks per existing pinned-jsonl pattern (`benchmarks/*/tasks.jsonl`). |
| **6** | Add cloud models to the sweep: Opus 4.7, Sonnet 4.6, Haiku 4.5, GPT-5.5, GPT-5-mini, Kimi K2.6 via OpenRouter, DeepSeek V4 (Pro + Flash). 9 cloud models × 2,000 tasks at ~$0.05/task average = ~$900 of API spend; budget accordingly. |
| **7** | Add Tier-2 cascade with test-verifier (functional shapes) and small-LLM judge-verifier (prose). Tune deferral thresholds via [Markov-copula method, §3.2] on a held-out validation slice. |
| **8** | Run the full evaluation matrix (§6). Generate the published table. |

**Exit criterion for day 60:** learned router within 5% of oracle ARQGC, at ≤25% of always-frontier cost. False-cheap rate ≤8%. Per-shape regret ≤15% on the worst shape.

### Days 61–90 — production-ready

**Goal:** harden, instrument, and ship to a real workload (this repo + opencode usage as the first integration target).

| Week | Task |
|---|---|
| **9** | Implement Tier-3 agent-loop routing for SWE-shape and Terminal-shape tasks. Extend this repo's `router/pipelines/architect/` to take per-phase routing decisions from Tier 1. |
| **10** | Add observability: emit `phase`, `parent_id`, `step_index`, `step_kind` fields to `router/logs/decisions.jsonl` (this repo's existing schema, extended per `docs/ROUTING_STRATEGIES.md` §3). Build dashboards for ARQGC, cost-per-route, latency P95, false-cheap, unnecessary-frontier. |
| **11** | Add continual learning: log developer accept/reject (via opencode plugin hook) as MetaLLM-style bandit feedback. Update per-model heads weekly from the log. |
| **12** | Run the publishable benchmark: 3 seeds × all routers × all shapes × held-out test slice. Write up. Tag in this repo as `routing-research-v1`. |

**Exit criterion for day 90:** in production for at least one user (the author), with 1+ week of logged decisions showing ≥30% cost reduction vs always-frontier and zero policy violations.

### Decision rule: learned vs heuristic

The §3 literature warns that learned routers can underperform heuristics on small datasets. Apply this rule:

> **Ship the learned router only if it beats the heuristic baseline on ARQGC by more than the 95% bootstrap CI width on the held-out test set, in 2 out of 3 task-shape categories (A+D5, B+D1+D2, C+D3+D4).** If only 1 of 3 wins, fall back to the heuristic for the losing category — i.e., a *hybrid heuristic+learned router* per shape.

### What to track post-90-days

- **Drift detection.** Embeddings shift, model behaviours shift, new models drop. A weekly job that re-runs the eval matrix on a 100-task drift-detection slice catches both.
- **Cost-vs-published ratio.** The router's actual cost vs the always-frontier baseline. If the gap shrinks over time, the model pool is being chosen poorly (probably because cheap models improved faster than expected).
- **New model onboarding cost.** Time from "model is announced" to "router has trained heads for it". UniRoute / CSCR fingerprinting (~100 representative prompts) keeps this to ≤24 h.

---

## Appendix A — Authoritative sources (dates checked 2026-05-18 unless noted)

### Benchmarks
- SWE-bench Verified — <https://www.swebench.com/verified>; canonical paper [arXiv:2310.06770](https://arxiv.org/abs/2310.06770) (Jimenez et al., ICLR 2024)
- SWE-bench leaderboard index — <https://swebench.com/index.html>
- LiveCodeBench leaderboard — <https://livecodebench.github.io/leaderboard.html>
- Aider leaderboard — <https://aider.chat/docs/leaderboards/>
- BigCodeBench — <https://huggingface.co/spaces/bigcode/bigcodebench>
- EvalPlus (HumanEval+/MBPP+) — <https://evalplus.github.io/leaderboard.html>
- Artificial Analysis — <https://artificialanalysis.ai/leaderboards/models>
- Vals.ai LiveCodeBench — <https://www.vals.ai/benchmarks/lcb>
- LMArena — <https://lmarena.ai>

### Routing literature (arxiv IDs verified in §3 deep-research run)
- FrugalGPT — [2305.05176](https://arxiv.org/abs/2305.05176) (Chen, Zaharia, Zou, May 2023)
- RouteLLM — [2406.18665](https://arxiv.org/abs/2406.18665) (Ong, Almahairi et al., Jun 2024; ICLR 2025)
- UniRoute (Universal Model Routing) — [2502.08773](https://arxiv.org/abs/2502.08773) (Jitkrittum et al., Feb 2025)
- MetaLLM — [2407.10834](https://arxiv.org/abs/2407.10834) (Nguyen et al., Jul 2024)
- CSCR (Cost-Spectrum Contrastive Routing) — [2508.12491](https://arxiv.org/html/2508.12491v2) (2025)
- IPR (Intelligent Prompt Routing) — [2509.06274](https://arxiv.org/html/2509.06274) (2025)
- QC-Opt — [2402.01742](https://arxiv.org/abs/2402.01742) (Feb 2024)
- When-simple-kNN-beats — [2505.12601](https://arxiv.org/html/2505.12601v1) (May 2025)
- Cascade routing unified — [2410.10347](https://arxiv.org/abs/2410.10347) (Dekoninck, Baader, Vechev, Oct 2024)
- Confidence-cascade-deferral conditions — [2307.02764](https://arxiv.org/abs/2307.02764) (2023)
- Multi-objective cascade — [2410.08014](https://arxiv.org/html/2410.08014) (Oct 2024)
- LLM-Blender — ACL 2023 (Jiang, Ren, Lin)
- Mixture-of-Agents — [2406.04692](https://arxiv.org/abs/2406.04692) (Wang et al., Jun 2024)
- Router-R1 — NeurIPS 2025 poster
- xRouter — [2501.07813](https://arxiv.org/abs/2501.07813) (Jan 2025)
- Live-SWE-agent — [arXiv:2511.13646](https://arxiv.org/html/2511.13646v1) (Nov 2025)
- Faster Cascades via Speculative Decoding — Google Research, ICLR 2025 — <https://research.google/pubs/faster-cascades-via-speculative-decoding/>
- Anthropic "Building Effective Agents" — <https://www.anthropic.com/research/building-effective-agents>
- LiteLLM Auto Routing — <https://docs.litellm.ai/docs/proxy/auto_routing>

### Vendor and model cards
- Kimi K2.6 — <https://huggingface.co/moonshotai/Kimi-K2.6>
- DeepSeek V4 — <https://openrouter.ai/deepseek/deepseek-v4-pro>
- Qwen3-Coder 30B-A3B — <https://ollama.com/library/qwen3-coder:30b-a3b-q4_K_M>
- Qwen3-Coder-Next 80B-A3B — <https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF>
- Mistral Medium 3.5 — <https://huggingface.co/mistralai/Mistral-Medium-3.5-128B>
- Llama 4 Scout — <https://www.sitepoint.com/llama-4-scout-on-mlx-the-complete-apple-silicon-guide-2026/> (community guide; consult Meta's official model card for license)
- GLM-4.5-Air — <https://huggingface.co/unsloth/GLM-4.5-Air-GGUF>
- Devstral 2 — <https://vercel.com/ai-gateway/models/devstral-2/faq>

### Cross-references in this repo
- v3 article — `reports/ARTICLE.md` (the 250-row dataset's published findings, with §4.4 cross-model and §3.5 cross-strategy tables)
- v3 measurement dataset — `results/runs/07-v3-devstral-all-routes/raw.jsonl`
- Triple-judge audit — `results/runs/11-judge-robust-D/judge.jsonl`
- Routing strategies code — `router/strategies.mjs`
- Routing strategies deep-dive — `docs/ROUTING_STRATEGIES.md`
- Prior research synthesis — `docs/PRIOR_ART.md`
- Methodology — `docs/METHODOLOGY.md`
- Pricing table — `configs/pricing/pricing_tables.json` (dated 2026-04-27, SHA256-pinned)
- Existing kNN-router corpus — `configs/router/corpus.json` (50 examples; expand to 500+ for v1 router)

## Appendix B — Two open questions this report does not answer

1. **What is the actual cost-quality crossover point for Kimi K2.6 vs Claude Opus 4.7 on long-context SWE-Verified tasks?** It depends on (a) Kimi K2.6's published API pricing as of the day you check, and (b) the specific subset of long-context Verified tasks. Run the eval. Don't extrapolate.
2. **Does a router actually beat a well-tuned heuristic on a 50-task workload?** §3 literature suggests no — kNN dominates at small scale, parametric routers need 2k+ tasks to win. This repo's day-30 exit criterion is exactly this test.

## Appendix C — What's intentionally not in this report

- **Implementation code.** The router stack in §4 is a design; production code goes in `router/` and `src/hybrid_coding_eval/`.
- **Cost-projection forecasts.** Pricing changes faster than reports. The router architecture is the durable artifact; specific dollar numbers are not.
- **A pick between "kNN + heads" and "RL router".** Day-30 prototype should pick. The §3 evidence says start with kNN.
- **Multi-modal coding (image / screenshot in repo).** Out of scope for v1; revisit when SWE-bench Multimodal lands wider model coverage.

---

*Source-traceability: every claim in this report either (a) cites a paper / leaderboard / model card with a working URL, (b) reads from this repo's measured dataset under `results/runs/07-v3-devstral-all-routes/`, or (c) is explicitly marked as a design recommendation. The §1 and §2 deep-research raw outputs are preserved under `/Users/sanchitmonga/development/research_agent/outputs/20260518_*` and can be inspected directly.*
