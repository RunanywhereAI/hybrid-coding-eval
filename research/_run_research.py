#!/usr/bin/env python3
"""
Run 4 deep-research queries in parallel for the hybrid-coding-eval project.

Each query uses Exa deep search (15 sources, 25k chars each) + Perplexity
sonar-deep-research (12k tokens, high context) in parallel. Output saved
to research/<slug>/.

Invoke:
  /Users/sanchitmonga/development/research_agent/.venv/bin/python \\
    /Users/sanchitmonga/development/ODLM/MONOREPOOO/CODING/hybrid-coding-eval/research/_run_research.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import concurrent.futures
import time

sys.path.insert(0, "/Users/sanchitmonga/development/research_agent")
from research_agent import ResearchAgent  # noqa: E402

OUTPUT_ROOT = Path(
    "/Users/sanchitmonga/development/ODLM/MONOREPOOO/CODING/hybrid-coding-eval/research"
)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

QUERIES: list[tuple[str, str]] = [
    (
        "01_coding_eval_benchmarks",
        (
            "Comprehensive survey of open-source code-generation evaluation "
            "benchmarks suitable for measuring local-vs-cloud-vs-hybrid LLM "
            "routing as of May 2026. For each benchmark report: dataset size, "
            "task types covered (function completion, multi-file edit, "
            "repo-level edit, debugging, test writing, refactor, architecture "
            "design), automation difficulty (does it ship a runnable harness "
            "and a sandbox?), license, recency of test data (data-contamination "
            "concerns), and what flagship + open-weights models score on it as "
            "of late 2025 / early 2026. Cover at minimum: HumanEval, MBPP, "
            "MBPP+, EvalPlus, BigCodeBench-Hard, LiveCodeBench, SWE-bench "
            "Verified, SWE-bench Lite, SWE-bench Pro, RepoBench, ClassEval, "
            "CodeContests, CRUXEval, Aider Polyglot, Aider Refactor, Spider, "
            "StackEval, MultiPL-E, CodeXGLUE, DS-1000, R2E, Stack Overflow QA, "
            "AppWorld, ML-Bench, RepoCoder, CoderEval, ComplexCodeEval. "
            "Identify which benchmarks are designed/usable for routing "
            "evaluation specifically (RouterBench coding subset, RouterArena, "
            "RouterEval — coding splits if any). For each: how easy is it to "
            "wire into a custom harness that runs the same task through 4 "
            "different routes (cloud-only, local-only, hybrid-architect, "
            "hybrid-minion) and produces a comparable score? Be detailed; "
            "cite leaderboards, per-task automation requirements, and known "
            "contamination findings. Also note any benchmarks specifically "
            "for measuring quality vs cost trade-offs."
        ),
    ),
    (
        "02_local_coding_model_performance",
        (
            "Empirical performance of open-source local coding LLMs on standard "
            "coding benchmarks as of May 2026. Compare 20-40B parameter range "
            "models suitable for 64 GB Apple Silicon and 24 GB consumer NVIDIA: "
            "Qwen3-Coder-30B-A3B-Instruct, Qwen3.6-27B-Coding and any -A3B "
            "variants, Devstral-Small-2-24B, DeepSeek-Coder-V3-33B and "
            "DeepSeek-V3-Coder, Granite-Code-34B, Llama-Coder-30B, StarCoder3, "
            "Codestral-Mamba-7B, Yi-Coder-30B, Mistral-Codestral-22B, "
            "GLM-4.5-Coding-32B, internLM3-Coder. For each: HumanEval+, MBPP+, "
            "BigCodeBench-Hard, SWE-bench Verified pass@1, LiveCodeBench, Aider "
            "Polyglot scores published by the model authors AND by community "
            "leaderboards (HuggingFace BigCode leaderboard, Aider's official "
            "leaderboard, EvalPlus leaderboard). Also report quantization "
            "formats (GGUF Q4_K_M / Q5_K_M / Q8_0 / Q6_K, MLX bf16, mxfp8, "
            "AWQ-INT4, NVFP4) and Apple Silicon M3/M4 tok/s benchmarks for "
            "each (cite community measurements). Where do these local models "
            "match GPT-5 / GPT-5.5 / Claude Sonnet 4.6 / Claude Opus 4.7 / "
            "Gemini 2.5 Pro quality? Where do they fall apart? Be specific "
            "about task type: function-completion (do they match cloud), "
            "multi-file refactoring (do they match), agentic tool-use loops "
            "(do they match), explanation/architecture questions (do they "
            "match), debugging unfamiliar codebases (do they match), test "
            "generation (do they match), API design (do they match). Cite "
            "specific scores and papers/blog posts published in 2025-2026."
        ),
    ),
    (
        "03_hybrid_coding_architectures_with_empirics",
        (
            "Detailed survey of hybrid local/cloud LLM architectures applied "
            "to coding workloads, with empirical measurements, as of May 2026. "
            "Cover in depth: Stanford Hazy Research Minions protocol (arXiv "
            "2502.15964) and the DevMinion variant for coding (find the "
            "implementation in the published code repo); Aider's "
            "architect+editor split (the most-deployed real example); Cursor "
            "Tab + Composer model split + Cursor Auto routing; GitHub Copilot "
            "Auto routing (the chat.model / models/session/intent endpoint); "
            "Cline / Roo Code / Continue.dev hybrid routing implementations; "
            "Warp terminal harness system (the bring-your-own-CLI-agent "
            "pattern); opencode chat.model plugin hook discussions; "
            "Sourcegraph Cody local-cloud split; Tabby local + cloud chat; "
            "JetBrains AI Assistant; Replit Agent; Sweep AI; Codeium / "
            "Windsurf Adaptive (Cascade); Augment Code. For each: what tasks "
            "go local vs cloud, how is the routing decision made, what cost "
            "savings are reported with actual numbers, what quality regression "
            "is observed, what failure modes are documented in postmortems or "
            "blog posts. Also cover academic papers measuring hybrid coding "
            "agents specifically (not generic Q&A): RouteLLM coding sweep, "
            "FrugalGPT coding adaptation, Cascade routing for code, Process "
            "Reward Models for coding (CodePRM, ThinkPRM-Code, FunPRM, "
            "DreamPRM-Code), AdaptiveLLM, DAAO-Code, BaRP-Code, contextual "
            "bandit routers for code, R2-Router on coding tasks, xRouter for "
            "tool-using coding agents. Cite arXiv numbers and published "
            "cost-vs-quality numbers. Then synthesise: of all these "
            "approaches, which are reported to actually save money in "
            "production AND maintain quality? Where are the honest failures?"
        ),
    ),
    (
        "04_hardware_reality_and_cost_calibration",
        (
            "Practical guide to running 20-40B parameter coding LLMs locally "
            "on consumer hardware as of May 2026 PLUS honest cost analysis "
            "of the cloud-only alternative. Hardware coverage: Apple Silicon "
            "M1/M2/M3/M4 in Pro/Max/Ultra variants, especially the 64 GB and "
            "128 GB unified-memory tiers; NVIDIA consumer (RTX 4090 24 GB, "
            "RTX 5090 32 GB, RTX 5080 16 GB) including dual-GPU setups; AMD "
            "Ryzen AI Max 395 (96 GB unified) and Radeon RX 7900 XTX; "
            "CPU-only (DDR5 with AVX-512). For each tier: max model size "
            "that fits, supported quantization formats, realistic tok/s for "
            "Qwen3-Coder-30B / Qwen3.6-27B-Coding / Devstral-24B / "
            "DeepSeek-Coder-V3 measured by the community (cite specific posts "
            "from r/LocalLLaMA, hackernews, individual blog posts), memory "
            "math (weights + KV cache at 32K-context vs 128K-context), and "
            "first-token latency vs sustained throughput. Quantization "
            "deep-dive: GGUF Q4_K_M vs MLX bf16 vs mxfp8 vs AWQ-INT4 — "
            "which preserves coding quality best per benchmark scores? Cloud "
            "side: actual per-developer-per-month costs reported in 2026 by "
            "Cursor (Free / Pro / Business / Ultra tiers), Cline, Aider, "
            "GitHub Copilot Pro / Business, Anthropic Claude Code, OpenAI "
            "Codex CLI. Token usage estimates for typical coding sessions "
            "(small task, 1-day session, 1-week heavy use). Round-trip "
            "latency from M-series Mac to OpenAI / Anthropic / Google APIs "
            "in 2026 (typical p50/p95). What's the break-even point where "
            "buying a M4 Max 64 GB or RTX 4090 pays off vs paying cloud "
            "subscriptions for one developer? For two? For ten? Also: "
            "honest assessments from people who've actually run hybrid "
            "setups in production — did it really save money once "
            "electricity, AC, hardware amortisation, dev-time on local "
            "outages are counted? Find blog posts that publish honest "
            "before/after numbers, not marketing."
        ),
    ),
]


def run_one(slug: str, query: str) -> tuple[str, bool, str]:
    out_dir = OUTPUT_ROOT / slug
    print(f"[{slug}] starting…", flush=True)
    t0 = time.monotonic()
    try:
        agent = ResearchAgent()
        agent.research(
            query,
            save=True,
            output_dir=out_dir,
            exa_num_results=15,
            exa_max_characters=25_000,
            perplexity_tokens=12_000,
        )
        elapsed = time.monotonic() - t0
        print(f"[{slug}] DONE in {elapsed:.0f}s", flush=True)
        return (slug, True, f"{elapsed:.0f}s")
    except Exception as exc:
        elapsed = time.monotonic() - t0
        msg = f"{type(exc).__name__}: {exc}"
        print(f"[{slug}] FAILED after {elapsed:.0f}s — {msg}", flush=True)
        return (slug, False, msg)


def main() -> int:
    print(f"Output root: {OUTPUT_ROOT}")
    print(f"Running {len(QUERIES)} queries in parallel…\n")
    t_overall = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(QUERIES)) as pool:
        futures = {pool.submit(run_one, slug, q): slug for slug, q in QUERIES}
        results = []
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    elapsed = time.monotonic() - t_overall
    print("\n" + "=" * 60)
    print(f"ALL DONE in {elapsed:.0f}s\n")
    successes = sum(1 for _, ok, _ in results if ok)
    failures = len(results) - successes
    print(f"Success: {successes}  Failed: {failures}")
    for slug, ok, info in results:
        status = "OK " if ok else "FAIL"
        print(f"  [{status}] {slug}  ({info})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
