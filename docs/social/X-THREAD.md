# X / Twitter launch thread

Copy-paste ready. 8 tweets. Every number verified against the official
`bootstrap_cis.json` in the release tarballs.

**Posting mechanics (important):**
- Post all 8 back-to-back yourself (don't drip over hours).
- **Tweet 1 carries NO link** — links in the first tweet tank reach. Put the
  repo URL in your **first reply** to tweet 1 *and* in tweet 8.
- One image per tweet (native upload, not a link). Images are in
  `docs/social/images/`.
- Pin the thread on launch day. Reply to every comment in the first hour.
- Hashtags: 0–2 max, at the end.

---

### Tweet 1 — hook  · 🖼 `headline-results.png`

```
A 35B model running on my laptop solved 100% of a real-world coding-refactor benchmark — while sending just 8% of its tokens to the cloud. Cost: ~$0.022/task.

The full local vs cloud vs hybrid benchmark, on one M4 Max, with 95% CIs on every number 🧵👇
```

### Tweet 2 — why it exists  · 🖼 `architecture.png`

```
The price gap between a frontier cloud model and a capable local one is now ~100×.

So I stopped asking "can the cloud do it?" and measured "which coding tasks can stay on my laptop?"

Same agent, same task, 8 routing strategies — a router decides local vs cloud per call.
```

### Tweet 3 — the hybrid win  · 🖼 `pareto-cost-quality.png`

```
Result #1 — the sweet spot:

cline + qwen3.6 (local) + "cascade" routing
→ 24/24 = 100% on real-developer refactors
→ only 8% of tokens go to the cloud
→ ~$0.022 per task

Same quality as always-cloud, at a fraction of the cost.
```

### Tweet 4 — the honest limit  · 🖼 `d6-hard-limit.png`

```
Result #2 — the honest limit (the part hype benchmarks skip):

On genuinely HARD tasks (an LRU+TTL cache, a template engine, toposort):
→ local-only: 67%, $0 cloud
→ cloud-only: 100%

A real 33-point gap. The cloud still earns its keep.
```

### Tweet 5 — the non-obvious finding  · (text-only)

```
The non-obvious finding:

The biggest lever is the LOCAL MODEL, not the routing cleverness.

And fancy "cloud-plans / local-executes" orchestration? It cost 1.9×–5× MORE than just calling the cloud — for zero quality gain.

Boring per-call routing wins.
```

### Tweet 6 — why trust it  · 🖼 `headline-results.png` (or a CI table screenshot)

```
Why you can trust the numbers:

→ every result = one row in raw.jsonl
→ cost = tokens × a pinned price table (re-price under any model, no re-run)
→ bootstrap 95% CIs on every cell

1,704 rows · 3 local models · 3 agents · 8 strategies · 17 tasks · one laptop.
```

### Tweet 7 — reproduce it  · 🖼 code screenshot (carbon.now.sh / ray.so)

```
You can reproduce it from a clean clone:

  git clone … && ./bench setup
  ./bench sweep --config configs/v1.4-smoke.yaml --strategies always-cloud
  ./bench analyze …

~30s smoke run (cloud-only, no model pull). Full sweep ~10–15h on an M4 Max. Repo 👇
```

### Tweet 8 — CTA + link  · (text-only)

```
It's MIT-licensed and reproducible from a clean clone.

Star it, run the sweep on your own hardware, and tell me where your local model breaks 👇

github.com/RunanywhereAI/hybrid-coding-eval

#LocalLLM #opensource
```

### First reply to Tweet 1 (post immediately after the thread)

```
Repo, full dataset, per-task breakdowns and reproduction steps:
github.com/RunanywhereAI/hybrid-coding-eval
```

---

**Suggested @-mentions** (only where they add value — e.g. crediting the tools
you wrapped): the upstream agents (aider, cline, opencode, mini-swe-agent) and
Ollama. Don't tag-spam big accounts.
