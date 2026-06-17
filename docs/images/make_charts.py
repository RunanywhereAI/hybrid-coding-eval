#!/usr/bin/env python3
"""Regenerate the shareable charts in docs/images/.

All numbers are hard-coded from the OFFICIAL bootstrap_cis.json shipped in the
v1.4.0 / v1.4.1 release tarballs + the recomputed v1.5.0 D6 set. Run from the
repo root with the project venv:  .venv/bin/python docs/images/make_charts.py

Design goals: one cohesive light theme, strong type hierarchy, no chart junk,
a source line on every figure. 16:9-ish, 170 dpi - crisp on README and social.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch
from matplotlib import font_manager as fm
import os

OUT = os.path.join(os.path.dirname(__file__))
DPI = 170

# ---- design system --------------------------------------------------------
INK    = "#0B1F33"   # near-black navy - primary text
MUTED  = "#5B6B7B"   # secondary text
FAINT  = "#9AA7B4"
LOCAL  = "#0E8C6B"   # teal-green  = local / $0
HYBRID = "#7C3AED"   # violet      = hybrid routing
CLOUD  = "#1D5FAD"   # blue        = cloud
GRID   = "#E9EDF1"
BG     = "#FFFFFF"
PANEL  = "#F4F7FA"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 13,
    "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": "#D7DEE5", "axes.linewidth": 1.0,
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
})

SRC = "github.com/RunanywhereAI/hybrid-arena   ·   one M4 Max 64GB   ·   functional pytest scoring   ·   95% bootstrap CIs"

def titled(fig, title, subtitle=None):
    fig.text(0.012, 0.965, title, fontsize=20, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.012, 0.905, subtitle, fontsize=13, color=MUTED, va="top")

def footer(fig, extra=None):
    fig.text(0.012, 0.022, (extra + "   ·   " if extra else "") + SRC,
             fontsize=8.6, color=FAINT, va="bottom")

def despine(ax, keep=("left","bottom")):
    for s in ("top","right","left","bottom"):
        ax.spines[s].set_visible(s in keep)
    ax.tick_params(length=0)

# ===========================================================================
# 1 - Headline bar: bar height = pass-rate; cloud share is a SEPARATE,
#     clearly-labeled line beneath each x-axis label (never inside the bar).
# ===========================================================================
labels = ["cline + qwen3.6\ncascade\nrefactors",
          "cline + qwen3.6\nlocal-only\npuzzles",
          "aider + gemma4\nheuristic\nrefactors",
          "cline + qwen3.6\nlocal-only\nHARD (D6)",
          "aider + gemma4\nheuristic\nHARD (D6)",
          "any agent\nalways-cloud\nHARD (D6)"]
passrate = [100, 100, 96, 67, 58, 100]
cloudpct = [8, 0, 34, 0, 68, 100]
colors   = [HYBRID, LOCAL, HYBRID, LOCAL, HYBRID, CLOUD]

fig, ax = plt.subplots(figsize=(11.6, 7.0))
fig.subplots_adjust(top=0.72, bottom=0.30, left=0.115, right=0.975)
bars = ax.bar(range(len(labels)), passrate, color=colors, width=0.62, zorder=3)
# Pass-rate: the bar height, labeled big and bold on top of each bar.
for b, p in zip(bars, passrate):
    ax.text(b.get_x()+b.get_width()/2, p+1.8, f"{p}%", ha="center", va="bottom",
            fontsize=19, fontweight="bold", color=INK)
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylim(0, 108); ax.set_yticks([0,25,50,75,100])
ax.set_ylabel("Share of tasks passed  (bar height)", fontsize=12.5)
ax.grid(axis="y", color=GRID, zorder=0); ax.set_axisbelow(True)
despine(ax)

# Cloud share: a SEPARATE muted indicator on its own row, well below the
# 3-line x-axis labels, so there is no chance of conflating it with pass%.
y_cloud = -0.275                   # in axes fraction, below the tick labels
ax.text(-0.105, y_cloud, "tokens\nto cloud:", transform=ax.transAxes,
        ha="left", va="center", fontsize=10, color=MUTED, fontweight="bold",
        linespacing=1.15)
for i, c in enumerate(cloudpct):
    swatch = MUTED if c > 0 else FAINT
    ax.annotate(f"{c}%", xy=(i, y_cloud), xycoords=("data", "axes fraction"),
                ha="center", va="center", fontsize=13, fontweight="bold",
                color=swatch, annotation_clip=False,
                bbox=dict(boxstyle="round,pad=0.40", fc=PANEL, ec=GRID, lw=1.1))

titled(fig, "A local 30B-class model carries everyday coding",
       "Bar = share of tasks passed.  Below each bar = share of tokens sent to the cloud (the cost side).")
footer(fig)
ax.legend(handles=[Patch(color=LOCAL,label="local-only · $0 cloud"),
                   Patch(color=HYBRID,label="hybrid routing"),
                   Patch(color=CLOUD,label="cloud-only")],
          loc="upper center", bbox_to_anchor=(0.66, 0.985), frameon=True,
          framealpha=0.96, edgecolor=GRID, fontsize=10.5, ncol=1)
fig.savefig(f"{OUT}/headline-results.png", dpi=DPI); plt.close(fig)
print("headline-results.png")

# ===========================================================================
# 2 - Cost/quality Pareto (cline + qwen3.6, real-developer refactors).
# ===========================================================================
pts = [("always-local",  0.0,  90.9, LOCAL),
       ("cascade",       8.1, 100.0, HYBRID),
       ("heuristic",    17.8,  95.7, HYBRID),
       ("always-cloud",100.0, 100.0, CLOUD)]
fig, ax = plt.subplots(figsize=(11.0, 6.5))
fig.subplots_adjust(top=0.74, bottom=0.16, left=0.085, right=0.965)
ax.plot([0.0,8.1,100.0],[90.9,100.0,100.0], "--", color=FAINT, lw=1.5, zorder=1)
lbl = {"always-local": (10,8,"left"), "cascade": (12,6,"left"),
       "heuristic": (12,6,"left"), "always-cloud": (-12,8,"right")}
for name,x,y,c in pts:
    ax.scatter(x,y, s=460, color=c, zorder=3, edgecolor="white", linewidth=2.5)
    dx,dy,ha = lbl[name]
    ax.annotate(name,(x,y),textcoords="offset points",xytext=(dx,dy),
                fontsize=13,fontweight="bold",color=c,ha=ha)
ax.annotate("100% quality · 8% cloud\n≈ $0.022 / task",
            xy=(8.1,100.0), xytext=(34,90.5), ha="left", va="center",
            fontsize=12.5, color=HYBRID, fontweight="bold", linespacing=1.4,
            arrowprops=dict(arrowstyle="->", color=HYBRID, lw=1.6,
                            connectionstyle="arc3,rad=-0.2"))
ax.set_xlabel("Cloud usage:  % of tokens sent to the frontier model  (→ cost)", fontsize=12.5)
ax.set_ylabel("Tasks passed  (%)", fontsize=12.5)
ax.set_xlim(-6,116); ax.set_ylim(84,103); ax.set_yticks([85,90,95,100])
ax.grid(color=GRID, zorder=0); ax.set_axisbelow(True); despine(ax)
titled(fig, "Hybrid routing sits on the cost/quality frontier",
       "cline + qwen3.6:35B  ·  real-developer refactors (D1/D5)  ·  ~100× price gap between the two backends")
footer(fig)
fig.savefig(f"{OUT}/pareto-cost-quality.png", dpi=DPI); plt.close(fig)
print("pareto-cost-quality.png")

# ===========================================================================
# 3 - D6 honest-limit ladder.
# ===========================================================================
l4 = ["always-local\n$0 cloud", "cascade\nhybrid", "always-cloud\ngpt-5.5"]
p4 = [67, 75, 100]; c4 = [0, 14, 100]; col4 = [LOCAL, HYBRID, CLOUD]
fig, ax = plt.subplots(figsize=(10.6, 6.4))
fig.subplots_adjust(top=0.74, bottom=0.13, left=0.085, right=0.965)
bars = ax.bar(range(3), p4, color=col4, width=0.56, zorder=3)
for b,p,c in zip(bars,p4,c4):
    ax.text(b.get_x()+b.get_width()/2, p+1.6, f"{p}%", ha="center", va="bottom",
            fontsize=21, fontweight="bold", color=INK)
    ax.text(b.get_x()+b.get_width()/2, 4, f"{c}% cloud", ha="center", va="bottom",
            fontsize=11.5, color="white", fontweight="bold")
ax.annotate("a real ~33-point gap", xy=(0,67), xytext=(0.34,88), ha="center",
            fontsize=13, color=MUTED, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.5,
                            connectionstyle="arc3,rad=0.25"))
ax.set_xticks(range(3)); ax.set_xticklabels(l4, fontsize=13)
ax.set_ylim(0,112); ax.set_yticks([0,25,50,75,100]); ax.set_ylabel("Hard tasks passed (D6)", fontsize=12.5)
ax.grid(axis="y", color=GRID, zorder=0); ax.set_axisbelow(True); despine(ax)
titled(fig, "The honest limit: on hard tasks, the cloud still wins",
       "cline + qwen3.6:35B  ·  4 single-file algorithmic builds  ·  80 pytest assertions")
fig.text(0.012, 0.022,
         "67% counts 3 cline session-bugs as misses; analyzer (errors excluded) = 8/9 = 89%   ·   "
         "github.com/RunanywhereAI/hybrid-arena   ·   95% bootstrap CIs",
         fontsize=8.6, color=FAINT, va="bottom")
fig.savefig(f"{OUT}/d6-hard-limit.png", dpi=DPI); plt.close(fig)
print("d6-hard-limit.png")

# ===========================================================================
# 4 - Architecture diagram.
# ===========================================================================
fig, ax = plt.subplots(figsize=(11.8, 6.7))
fig.subplots_adjust(top=0.80, bottom=0.06, left=0.02, right=0.98)
ax.set_xlim(0,12); ax.set_ylim(0,7.4); ax.axis("off")
def box(x,y,w,h,text,fc,fs=12,tc="white"):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.04,rounding_size=0.14",
                 fc=fc, ec="white", lw=2, zorder=2))
    ax.text(x+w/2,y+h/2,text,ha="center",va="center",color=tc,fontsize=fs,
            fontweight="bold",zorder=3,linespacing=1.35)
def arrow(x1,y1,x2,y2,c=MUTED):
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle="-|>",mutation_scale=20,color=c,lw=2.2,zorder=1))
box(0.25,5.35,3.0,1.65,"4 coding agents\naider · opencode\nmini-swe · cline","#243B53",fs=12)
box(4.55,5.5,3.0,1.35,"Router proxy :8787\nOpenAI-compatible","#334E68",fs=12)
arrow(3.25,6.17,4.55,6.17)
box(4.35,2.35,3.4,2.55,"8 routing strategies\n\nalways-local · always-cloud\nrules · heuristic\nllm-classifier · embedding-kNN\ncascade · phase-aware",HYBRID,fs=11)
arrow(6.05,5.5,6.05,4.9)
box(8.7,5.6,2.55,1.35,"LOCAL\nOllama 30B-class\n$0 / call",LOCAL,fs=11.5)
box(8.7,2.75,2.55,1.35,"CLOUD\nfrontier LLM\ngpt-5.5",CLOUD,fs=11.5)
arrow(7.75,6.2,8.7,6.27,LOCAL); arrow(7.75,3.5,8.7,3.42,CLOUD)
ax.text(8.2,6.62,"per-call",fontsize=9.5,color=MUTED,style="italic",ha="center")
box(4.35,0.45,3.4,1.3,"Functional scorer\nDocker pytest sandbox\n→ raw.jsonl  (tokens, never $)","#0E7C66",fs=11)
arrow(6.05,2.35,6.05,1.75)
titled(fig, "Route every LLM call to the laptop or the cloud",
       "Same agent, same task, 8 strategies. Cost is derived from tokens, so any model's pricing swaps in at analysis time.")
fig.text(0.012,0.02,"github.com/RunanywhereAI/hybrid-arena",fontsize=8.8,color=FAINT)
fig.savefig(f"{OUT}/architecture.png", dpi=DPI); plt.close(fig)
print("architecture.png")

# ===========================================================================
# 5 - Complexity spectrum: where these tasks sit vs the frontier.
# ===========================================================================
fig, ax = plt.subplots(figsize=(12.0, 6.8))
fig.subplots_adjust(top=0.78, bottom=0.04, left=0.02, right=0.98)
ax.set_xlim(0,12); ax.set_ylim(0,6.6); ax.axis("off")

# "measured here" band vs "frontier (out of scope)" band
ax.add_patch(FancyBboxPatch((0.2,1.15),7.55,4.05,boxstyle="round,pad=0.02,rounding_size=0.1",
             fc=PANEL, ec="#D7DEE5", lw=1.2, zorder=0))
ax.add_patch(FancyBboxPatch((7.95,1.15),3.85,4.05,boxstyle="round,pad=0.02,rounding_size=0.1",
             fc="#FBF1F1", ec="#EBD3D3", lw=1.2, zorder=0))
ax.text(3.97,5.0,"WHAT THIS BENCHMARK MEASURES",fontsize=11,fontweight="bold",color=LOCAL,ha="center")
ax.text(9.87,5.0,"REAL-WORLD → FRONTIER  ·  beyond current sweeps",fontsize=10.5,fontweight="bold",color="#B23A48",ha="center")

# difficulty arrow
ax.add_patch(FancyArrowPatch((0.5,0.78),(11.5,0.78),arrowstyle="-|>",mutation_scale=22,color=MUTED,lw=2))
ax.text(0.5,0.36,"seconds to minutes",fontsize=9.5,color=MUTED)
ax.text(6.0,0.36,"30 min to 1 hr (single file)",fontsize=9.5,color=MUTED,ha="center")
ax.text(11.5,0.36,"hours to days (whole repos)",fontsize=9.5,color=MUTED,ha="right")
ax.text(6.0,0.04,"human effort per task  →",fontsize=10,color=INK,ha="center",fontweight="bold")

def card(x, w, title, sub, color, y=1.5, h=3.1):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.03,rounding_size=0.1",
                 fc="white", ec=color, lw=2.2, zorder=2))
    ax.add_patch(FancyBboxPatch((x,y+h-0.62),w,0.62,boxstyle="round,pad=0.03,rounding_size=0.1",
                 fc=color, ec=color, lw=0, zorder=3))
    ax.text(x+w/2, y+h-0.31, title, ha="center", va="center", color="white",
            fontsize=11.5, fontweight="bold", zorder=4)
    ax.text(x+w/2, y+(h-0.62)/2, sub, ha="center", va="center", color=INK,
            fontsize=9.6, zorder=4, linespacing=1.45)

card(0.45, 1.7, "Puzzles", "Exercism Python\n5 tasks\nsingle function\n~30 to 100 LOC\n\njunior", LOCAL, h=3.1)
card(2.35, 1.7, "Refactors\nD1 / D5", "feature-adds +\nscripts\n8 tasks\nsingle file,\ntiny fixture repo\n\nmid-level", HYBRID, h=3.1)
card(4.25, 3.35, "Hard builds, D6   ◀ ceiling here", "LRU+TTL cache · token bucket · toposort · template engine\n4 tasks · 55 to 273 LOC each · 80 pytest tests · corner-case heavy\n\nsenior · single file", "#5B2BC4", h=3.1)
card(8.15, 1.55, "Real PRs", "SWE-bench\nVerified\nreal merged PRs\nrepo-scale\n\nMVP-era /\nv1.6 roadmap", "#C97A2B", h=3.1)
card(9.95, 1.65, "Long-horizon", "SWE-bench Pro /\nSWE-Marathon\nmulti-hour,\nfull repos\nfrontier <26%\n(Opus 4.8)", "#B23A48", h=3.1)

titled(fig, "What complexity are we talking about?",
       "Deliberately the everyday tier: the bread-and-butter tasks that dominate a workday, not the multi-hour frontier.")
fig.text(0.012,0.02,"Frontier figure: Abundant AI, SWE-Marathon (2026): 20 long-horizon tasks, top model ~26%.   "+SRC,
         fontsize=8.4, color=FAINT)
fig.savefig(f"{OUT}/complexity-spectrum.png", dpi=DPI); plt.close(fig)
print("complexity-spectrum.png")
