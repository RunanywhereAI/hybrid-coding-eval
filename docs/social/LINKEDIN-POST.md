# LinkedIn launch post

Copy-paste ready. Every number verified against the official
`bootstrap_cis.json` in the release tarballs.

**Posting mechanics (important):**
- **Put the GitHub link in the FIRST COMMENT, not the post body** (links in the
  body cut reach). The body already signals "in the comments."
- Attach the **PDF carousel** (slides below) — it's the highest-engagement
  format on LinkedIn. Images are in `docs/social/images/`.
- Post Tue–Thu morning (your audience's timezone). Don't edit for ~30 min.
  Reply to every comment in the first 60–90 min.
- 3 hashtags, on their own line at the bottom.

---

## Post body (copy everything in the block)

```
I gave a 30B model running on my laptop the hard coding tasks. It solved two-thirds of them — for $0 in cloud spend.

The real question for coding LLMs isn't "can the cloud do it?" anymore. It's "which tasks can stay on my laptop?"

A frontier cloud model now costs roughly 100× a 30B local one.

And the agents got good enough that the bottleneck isn't raw capability — it's routing: which calls actually need the cloud.

So I built hybrid-coding-eval: a reproducible benchmark that runs real coding agents on a single M4 Max laptop and routes every LLM call — local or cloud — per call. Every published number traces back to one row in a log, priced by a versioned table.

What 1,704 runs showed:

→ 100% pass-rate at 8% cloud usage, ~$0.022/task — cline + qwen3.6 + cascade routing, on real-developer refactors. Same quality as cloud-only, a fraction of the cost.

→ 67% of genuinely HARD tasks solved fully local, $0 cloud. A real privacy/cost option, not a toy.

→ Where it breaks (the honest negative): heuristic routing drops to 58% on hard tasks while spending 68% of tokens on the cloud — scoring less and costing more.

→ The biggest lever is the local model, not the routing trick. And multi-step "cloud-plans / local-executes" orchestration cost 1.9–5× more for no quality gain.

The bottleneck isn't the model anymore. It's the routing.

It's MIT-licensed and reproducible from a clean clone — you can benchmark your own local model in three commands.

If you route coding tasks today: where do you think local stops being good enough? Run it on your model and tell me where my routing breaks.

Repo (MIT) + full dataset and per-task numbers in the first comment 👇

#LLM #OpenSource #LocalLLM
```

## First comment (post immediately after publishing)

```
Repo, full dataset, and per-task breakdowns: github.com/RunanywhereAI/hybrid-coding-eval

Built on one M4 Max 64GB. 3 local models · 3 coding agents · 8 routing strategies · 17 tasks. Reproduce the smoke run in ~30 seconds; full sweep in ~10–15h. Stars + new-model requests welcome.
```

---

## PDF carousel (6 slides — build as a document/PDF and attach)

Each slide = one idea, dark background, big type, monospace for numbers.

1. **Title** — "Should this coding task run on my laptop, the cloud, or split
   between them?" + sub: "1,704 runs · one M4 Max · MIT". 🖼 `headline-results.png`
2. **The question** — "Frontier cloud ≈ 100× the price of a 30B local model. So:
   which tasks can stay on the laptop?" 🖼 `architecture.png`
3. **The method** — "3 coding agents × 8 routing strategies × 3 local models ×
   17 tasks = 1,704 runs. A router picks local vs cloud per call. Every number =
   one row, priced by a pinned table, with 95% CIs."
4. **The win** — "100% of real refactors at 8% cloud, ~$0.022/task." 🖼 `pareto-cost-quality.png`
5. **The honest limit** — "On HARD tasks: local 67% ($0) vs cloud 100%. A real
   33-point gap." 🖼 `d6-hard-limit.png`
6. **Reproduce it** — "git clone → ./bench setup → ./bench sweep → ./bench
   analyze. MIT. Run it on your hardware: github.com/RunanywhereAI/hybrid-coding-eval"
