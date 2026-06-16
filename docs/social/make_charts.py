#!/usr/bin/env python3
"""Regenerate the shareable launch images in docs/social/images/.

All numbers are hard-coded from the OFFICIAL bootstrap_cis.json shipped in the
v1.4.0 / v1.4.1 release tarballs + the recomputed v1.5.0 D6 set. Run from the
repo root with the project venv:  .venv/bin/python docs/social/make_charts.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

OUT = "docs/social/images"
os.makedirs(OUT, exist_ok=True)

# Brand-ish palette
LOCAL = "#2E7D32"   # green  = local / cheap
CLOUD = "#1565C0"   # blue   = cloud
HYBRID = "#6A1B9A"  # purple = hybrid
GREY = "#555555"
BG = "#FFFFFF"
plt.rcParams.update({
    "font.size": 13, "font.family": "DejaVu Sans",
    "axes.edgecolor": "#CCCCCC", "axes.linewidth": 1.0,
    "figure.facecolor": BG, "axes.facecolor": BG,
})

FOOT = "github.com/RunanywhereAI/hybrid-coding-eval  ·  one M4 Max laptop  ·  95% bootstrap CIs"

# ---------------------------------------------------------------------------
# Chart 1 — Headline bar: pass-rate by configuration, annotated with cloud %.
# All numbers from official bootstrap_cis.json (v1.4.0/v1.4.1/v1.5.0).
# ---------------------------------------------------------------------------
labels = [
    "cline+qwen3.6\ncascade\n(refactors)",
    "cline+qwen3.6\nlocal-only\n(puzzles)",
    "aider+gemma4\nheuristic\n(refactors)",
    "cline+qwen3.6\nlocal-only\n(HARD/D6)",
    "aider+gemma4\nheuristic\n(HARD/D6)",
    "any agent\nalways-cloud\n(HARD/D6)",
]
passrate = [100, 100, 96, 67, 58, 100]
cloudpct = [8, 0, 34, 0, 68, 100]
colors = [HYBRID, LOCAL, HYBRID, LOCAL, HYBRID, CLOUD]

fig, ax = plt.subplots(figsize=(12, 6.5))
bars = ax.bar(range(len(labels)), passrate, color=colors, width=0.62, zorder=3)
for i, (b, p, c) in enumerate(zip(bars, passrate, cloudpct)):
    ax.text(b.get_x()+b.get_width()/2, p+1.5, f"{p}%", ha="center", va="bottom",
            fontsize=16, fontweight="bold", color="#222")
    ax.text(b.get_x()+b.get_width()/2, 6, f"{c}%\ncloud", ha="center", va="bottom",
            fontsize=11, color="white", fontweight="bold")
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, fontsize=10.5)
ax.set_ylim(0, 112)
ax.set_ylabel("Tasks passed (functional pytest)", fontsize=13)
ax.set_title("A local 30B-class model carries everyday coding — the cloud earns its keep on hard tasks",
             fontsize=15.5, fontweight="bold", pad=14)
ax.grid(axis="y", color="#EEEEEE", zorder=0)
for s in ("top","right"): ax.spines[s].set_visible(False)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=LOCAL,label="local-only ($0 cloud)"),
                   Patch(color=HYBRID,label="hybrid routing"),
                   Patch(color=CLOUD,label="cloud-only")],
          loc="upper center", frameon=True, framealpha=0.9, edgecolor="#DDDDDD",
          fontsize=11.5, ncol=1, bbox_to_anchor=(0.62,0.99))
fig.text(0.5, 0.005, FOOT, ha="center", fontsize=9.5, color=GREY)
fig.tight_layout(rect=(0,0.03,1,0.99))
fig.savefig(f"{OUT}/headline-results.png", dpi=150)
plt.close(fig)
print("wrote headline-results.png")

# ---------------------------------------------------------------------------
# Chart 2 — Pareto: cloud-fraction vs pass-rate, qwen3.6 refactors (D1/D5).
# Official: always-local 90.9%/0%, cascade 100%/8.1%, heuristic 95.7%/17.8%, cloud 100%/100%.
# ---------------------------------------------------------------------------
pts = [
    ("always-local",  0.0,   90.9, LOCAL),
    ("cascade",       8.1,  100.0, HYBRID),
    ("heuristic",    17.8,   95.7, HYBRID),
    ("always-cloud",100.0,  100.0, CLOUD),
]
fig, ax = plt.subplots(figsize=(11, 6.5))
for name, x, y, c in pts:
    ax.scatter(x, y, s=420, color=c, zorder=3, edgecolor="white", linewidth=2)
    dy = -7 if name=="cascade" else 6
    ax.annotate(name, (x, y), textcoords="offset points", xytext=(10, dy),
                fontsize=13, fontweight="bold", color=c)
# frontier line local -> cascade -> cloud
fx = [0.0, 8.1, 100.0]; fy=[90.9,100.0,100.0]
ax.plot(fx, fy, "--", color="#999", lw=1.4, zorder=1)
ax.annotate("cascade: 100% at 8% cloud\n≈ $0.022 / task",
            (8.1,100.0), textcoords="offset points", xytext=(40,-40),
            fontsize=12, color=HYBRID, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=HYBRID))
ax.set_xlabel("Cloud usage  (% of tokens sent to the frontier model)  →  cost", fontsize=13)
ax.set_ylabel("Tasks passed  (%)", fontsize=13)
ax.set_xlim(-5, 110); ax.set_ylim(84, 103)
ax.set_title("Hybrid routing sits on the cost/quality frontier\ncline + qwen3.6:35B · real-developer refactors",
             fontsize=15.5, fontweight="bold", pad=12)
ax.grid(color="#EEEEEE", zorder=0)
for s in ("top","right"): ax.spines[s].set_visible(False)
fig.text(0.5, 0.005, FOOT, ha="center", fontsize=9.5, color=GREY)
fig.tight_layout(rect=(0,0.03,1,1))
fig.savefig(f"{OUT}/pareto-cost-quality.png", dpi=150)
plt.close(fig)
print("wrote pareto-cost-quality.png")

# ---------------------------------------------------------------------------
# Chart 3 — Architecture / routing diagram.
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, 7))
ax.set_xlim(0, 12); ax.set_ylim(0, 8); ax.axis("off")

def box(x, y, w, h, text, color, tc="white", fs=12, bold=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                 fc=color, ec="white", lw=2, zorder=2))
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", color=tc,
            fontsize=fs, fontweight="bold" if bold else "normal", zorder=3)

def arrow(x1,y1,x2,y2,color=GREY):
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2), arrowstyle="-|>",
                 mutation_scale=18, color=color, lw=2, zorder=1))

# agents
box(0.3, 5.6, 3.0, 1.7,
    "4 coding agents\naider · opencode\nmini-swe-agent · cline", "#37474F", fs=12)
# router
box(4.6, 5.7, 3.0, 1.5, "Router proxy :8787\nOpenAI-compatible", "#455A64", fs=12)
arrow(3.3, 6.45, 4.6, 6.45)
# strategies box
box(4.4, 2.6, 3.4, 2.6,
    "8 routing strategies\n\nalways-local · always-cloud\nrules · heuristic\nllm-classifier · embedding-knn\ncascade · phase-aware",
    "#6A1B9A", fs=11)
arrow(6.1, 5.7, 6.1, 5.2)
# local + cloud
box(9.0, 5.9, 2.7, 1.4, "LOCAL\nOllama 30B\n$0 / call", LOCAL, fs=12)
box(9.0, 3.0, 2.7, 1.4, "CLOUD\nfrontier LLM\ngpt-5.5", CLOUD, fs=12)
arrow(7.6, 6.5, 9.0, 6.6, LOCAL)
arrow(7.8, 3.6, 9.0, 3.7, CLOUD)
ax.text(8.35, 6.75, "per-call decision", fontsize=9.5, color=GREY, style="italic")
# scorer
box(4.4, 0.5, 3.4, 1.3, "Functional scorer\nDocker pytest sandbox\n→ raw.jsonl (tokens, not $)", "#00695C", fs=11)
arrow(6.1, 2.6, 6.1, 1.8)
ax.text(6.0, 7.7, "hybrid-coding-eval — route every LLM call to laptop or cloud, measure the trade-off",
        ha="center", fontsize=14.5, fontweight="bold", color="#222")
fig.text(0.5, 0.02, "github.com/RunanywhereAI/hybrid-coding-eval", ha="center", fontsize=10, color=GREY)
fig.savefig(f"{OUT}/architecture.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print("wrote architecture.png")

# ---------------------------------------------------------------------------
# Chart 4 — D6 hard-task ladder (the honest-limit / credibility image).
# cline + qwen3.6, D6: local-only 67% (8/12 conservative) / cascade 75% (9/12) / cloud 100%.
# Conservative published framing (errors counted as failures), matches release notes.
# ---------------------------------------------------------------------------
labels4 = ["always-local\n$0 cloud", "cascade\nhybrid", "always-cloud\ngpt-5.5"]
pass4 = [67, 75, 100]
cloud4 = [0, 14, 100]
colors4 = [LOCAL, HYBRID, CLOUD]
fig, ax = plt.subplots(figsize=(10.5, 6.3))
bars = ax.bar(range(3), pass4, color=colors4, width=0.55, zorder=3)
for b, p, c in zip(bars, pass4, cloud4):
    ax.text(b.get_x()+b.get_width()/2, p+1.5, f"{p}%", ha="center", va="bottom",
            fontsize=20, fontweight="bold", color="#222")
    ax.text(b.get_x()+b.get_width()/2, 5, f"{c}% cloud", ha="center", va="bottom",
            fontsize=12, color="white", fontweight="bold")
ax.set_xticks(range(3)); ax.set_xticklabels(labels4, fontsize=13)
ax.set_ylim(0, 112); ax.set_ylabel("Hard tasks passed (D6)", fontsize=13)
ax.set_title("The honest limit: on HARD tasks the cloud still wins\ncline + qwen3.6:35B · 4 algorithmic builds · 80 pytest assertions",
             fontsize=15, fontweight="bold", pad=12)
ax.annotate("a real 33-point gap\n— not noise", (0, 67), textcoords="offset points",
            xytext=(60, 30), fontsize=12.5, color=GREY, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=GREY))
ax.grid(axis="y", color="#EEEEEE", zorder=0)
for s in ("top","right"): ax.spines[s].set_visible(False)
fig.text(0.5, 0.005, "67% counts 3 cline session-bugs as misses; analyzer (errors excluded) = 8/9 = 89%   ·   "+FOOT,
         ha="center", fontsize=8.3, color=GREY)
fig.tight_layout(rect=(0,0.035,1,1))
fig.savefig(f"{OUT}/d6-hard-limit.png", dpi=150)
plt.close(fig)
print("wrote d6-hard-limit.png")
