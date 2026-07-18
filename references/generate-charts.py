#!/usr/bin/env python3
"""generate-charts.py — Ponytail-Gain + 防御栈演进 + 规则增长可视化

Generates 4 PNG charts in references/charts/:
  1. defense-stack-evolution.png   — 硬规则/反模式/自检项 增长
  2. iteration-convergence.png     — 扫描发现数与P0 Bug收敛
  3. ponytail-benchmark.png        — 多臂基准对比 (LOC/tokens/cost/time)
  4. defense-hooks-timeline.png    — echo-guard/stop-guard/bearings 版本演进

Dependencies: matplotlib, numpy (standard python3 -m pip install)
"""

import os
import matplotlib
matplotlib.use("Agg")  # headless, no display needed

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

OUT = os.path.join(os.path.dirname(__file__), "charts")
os.makedirs(OUT, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# DATA  (all values extracted from code-shiniyaya iteration reports)
# ═══════════════════════════════════════════════════════════════

# ── 1. Defense stack growth ──
versions = ["v3.7.0", "v3.9.x", "v4.0.7", "v4.1.3", "v4.2.5", "v4.4.1", "v4.7.10"]
hard_rules   = [16, 18, 22, 24, 25, 27, 28]
anti_patterns = [9, 12, 16, 21, 23, 23, 23]
self_checks   = [5,  8, 12, 16, 16, 16, 20]
file_lines    = [480, 580, 720, 831, 889, 963, 1050]

# ── 2. Iteration convergence ──
iter_nums   = [1, 2, 6, 7, 8, 9, 10, 12, 14, 17, 18, 19, 20]
findings    = [208, 66, 71, 93, 73, 20, 13, 3, 4, 0, 0, 10, 0]
p0_bugs     = [67, 42, 20, 15, 3, 0, 0, 0, 0, 6, 0, 0, 0]  # iter 17 had 6 new category P0s

# ── 3. Ponytail agentic benchmark (Haiku 4.5, vs no-skill baseline) ──
# Values shown as % of baseline (baseline = 100% → lower is better)
arms        = ["ponytail", "caveman", "YAGNI +\none-liner"]
loc_pct     = [46, 80, 67]       # also expressible as -54%, -20%, -33%
tokens_pct  = [78, 107, 86]      # -22%, +7%, -14%
cost_pct    = [80, 103, 79]      # -20%, +3%, -21%
time_pct    = [73, 102, 70]      # -27%, +2%, -30%
safe_pct    = [100, 100, 95]     # safety score

# ── 4. Defense hook versions timeline ──
hook_versions = [
    ("echo-guard.js",   ["v3.4", "v4.0", "v4.1", "v4.3"],       [4.2, 4.4, 4.6, 4.7]),
    ("stop-guard.js",   ["v3.3", "v3.5"],                        [4.4, 4.7]),
    ("bearings.js",     ["v3.0-r9"],                              [4.6]),
]
# Approximate SKILL.md versions where each hook version was introduced


# ═══════════════════════════════════════════════════════════════
# CHART 1: Defense Stack Evolution
# ═══════════════════════════════════════════════════════════════
def plot_defense_stack():
    fig, ax1 = plt.subplots(figsize=(10, 5.5))

    x = np.arange(len(versions))
    w = 0.22

    bars1 = ax1.bar(x - w, hard_rules,    w, label="Hard Rules",    color="#2E86AB", edgecolor="white", linewidth=0.5)
    bars2 = ax1.bar(x,      anti_patterns, w, label="Anti-Patterns", color="#A23B72", edgecolor="white", linewidth=0.5)
    bars3 = ax1.bar(x + w, self_checks,   w, label="Self-Checks",   color="#F18F01", edgecolor="white", linewidth=0.5)

    # File size as line on secondary axis
    ax2 = ax1.twinx()
    line, = ax2.plot(x, file_lines, "o-", color="#1B998B", linewidth=2, markersize=6, label="File Lines (SKILL.md)")
    ax2.set_ylabel("File Lines", fontsize=11)

    ax1.set_xticks(x)
    ax1.set_xticklabels(versions, rotation=25, ha="right", fontsize=9)
    ax1.set_ylabel("Count", fontsize=11)
    ax1.set_title("Defense Stack Evolution\ncode-shiniyaya SKILL.md", fontsize=13, fontweight="bold")

    # Value labels on bars
    for bar in bars1:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 str(bar.get_height()), ha="center", va="bottom", fontsize=7, color="#2E86AB")
    for bar in bars2:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 str(bar.get_height()), ha="center", va="bottom", fontsize=7, color="#A23B72")
    for bar in bars3:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 str(bar.get_height()), ha="center", va="bottom", fontsize=7, color="#F18F01")
    for i, v in enumerate(file_lines):
        ax2.text(i, v + 15, str(v), ha="center", va="bottom", fontsize=7, color="#1B998B")

    # Legend combined
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)

    ax1.set_ylim(0, 32)
    ax2.set_ylim(0, 1300)
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "defense-stack-evolution.png"), dpi=200)
    plt.close(fig)
    print(f"  [OK] defense-stack-evolution.png")


# ═══════════════════════════════════════════════════════════════
# CHART 2: Iteration Convergence
# ═══════════════════════════════════════════════════════════════
def plot_iteration_convergence():
    fig, ax1 = plt.subplots(figsize=(10, 5))

    x = np.arange(len(iter_nums))
    w = 0.32

    bars1 = ax1.bar(x - w/2, findings, w, label="Scan Findings", color="#2E86AB", edgecolor="white", linewidth=0.5)
    bars2 = ax1.bar(x + w/2, p0_bugs,  w, label="P0 Bugs",       color="#C1292E", edgecolor="white", linewidth=0.5)

    ax1.set_xticks(x)
    ax1.set_xticklabels([f"Iter#{n}" for n in iter_nums], rotation=30, ha="right", fontsize=8)
    ax1.set_ylabel("Count", fontsize=11)
    ax1.set_title("Iteration Convergence\nScan Findings and P0 Bugs Over 20 Rounds", fontsize=13, fontweight="bold")
    ax1.set_yscale("symlog", linthresh=1)  # log scale to show wide range 0→208

    # Value annotations
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, h + 0.8, str(int(h)),
                     ha="center", va="bottom", fontsize=7, color="#2E86AB", rotation=90)
    for bar in bars2:
        h = bar.get_height()
        if h > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, h + 0.8, str(int(h)),
                     ha="center", va="bottom", fontsize=7, color="#C1292E", rotation=90)

    # Convergence zone annotation
    ax1.axvspan(7.5, 12.5, alpha=0.08, color="green", label="Convergence Zone")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "iteration-convergence.png"), dpi=200)
    plt.close(fig)
    print(f"  [OK] iteration-convergence.png")


# ═══════════════════════════════════════════════════════════════
# CHART 3: Ponytail Agentic Benchmark (multi-arm comparison)
# ═══════════════════════════════════════════════════════════════
def plot_ponytail_benchmark():
    fig, axes = plt.subplots(1, 4, figsize=(12, 4.5), sharey=False)
    metrics = [
        ("LOC", loc_pct, "#2E86AB", "% of baseline\n(lower = better)", 0, 120),
        ("Tokens", tokens_pct, "#A23B72", "% of baseline\n(lower = better)", 0, 130),
        ("Cost", cost_pct, "#F18F01", "% of baseline\n(lower = better)", 0, 130),
        ("Time", time_pct, "#1B998B", "% of baseline\n(lower = better)", 0, 130),
    ]

    for ax, (name, vals, color, ylabel, ymin, ymax) in zip(axes, metrics):
        x = np.arange(len(arms))
        bars = ax.bar(x, vals, 0.5, color=color, edgecolor="white", linewidth=0.5, alpha=0.9)

        # Baseline line at 100%
        ax.axhline(y=100, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.text(2.3, 101, "baseline", fontsize=7, color="gray", va="bottom", alpha=0.6)

        ax.set_xticks(x)
        ax.set_xticklabels(arms, fontsize=7)
        ax.set_title(name, fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=7)
        ax.set_ylim(ymin, ymax)

        for bar, v in zip(bars, vals):
            pct_str = f"{v:.0f}%"
            if v < 100:
                pct_str += f"\n(-{100-v:.0f}%)"
            elif v > 100:
                pct_str += f"\n(+{v-100:.0f}%)"
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                    pct_str, ha="center", va="bottom", fontsize=6.5, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Ponytail Agentic Benchmark (Haiku 4.5 · 12 tasks · n=4)\n"
                 "Values as % of no-skill baseline — lower is better",
                 fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "ponytail-benchmark.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] ponytail-benchmark.png")


# ═══════════════════════════════════════════════════════════════
# CHART 4: Defense Hook Version Timeline
# ═══════════════════════════════════════════════════════════════
def plot_defense_hooks_timeline():
    fig, ax = plt.subplots(figsize=(10, 4))

    sk_version_map = {
        4.0: "v4.0.7", 4.2: "v4.2.5", 4.4: "v4.4.1",
        4.6: "v4.6.9", 4.7: "v4.7.10",
    }

    colors = {"echo-guard.js": "#2E86AB", "stop-guard.js": "#C1292E", "bearings.js": "#1B998B"}
    y_positions = {"echo-guard.js": 3, "stop-guard.js": 2, "bearings.js": 1}

    for hook, versions_list, sk_versions in hook_versions:
        y = y_positions[hook]
        color = colors[hook]

        for i, (ver, skv) in enumerate(zip(versions_list, sk_versions)):
            ax.plot(skv, y, "o", color=color, markersize=12, zorder=5)
            ax.text(skv, y + 0.15, ver, ha="center", va="bottom", fontsize=9,
                    fontweight="bold", color=color)
            # connector line between versions
            if i > 0:
                prev_skv = sk_versions[i - 1]
                ax.plot([prev_skv, skv], [y, y], "-", color=color, linewidth=2, alpha=0.6)

        # Hook label on the left
        ax.text(3.85, y, hook, ha="left", va="center", fontsize=10, color=color, fontweight="bold")

    # Version annotations at top
    for skv, label in sorted(sk_version_map.items()):
        ax.axvline(x=skv, color="gray", linestyle=":", alpha=0.3, ymax=0.85)
        ax.text(skv, 3.7, label, ha="center", va="bottom", fontsize=8, color="gray", rotation=30)

    ax.set_xlim(3.8, 4.85)
    ax.set_ylim(0.5, 4.0)
    ax.set_yticks([])
    ax.set_xlabel("SKILL.md Version", fontsize=10)
    ax.set_title("Defense Hook Version Timeline", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "defense-hooks-timeline.png"), dpi=200)
    plt.close(fig)
    print(f"  [OK] defense-hooks-timeline.png")


# ═══════════════════════════════════════════════════════════════
# BONUS: Ponytail Gain KPI Card (single compact chart)
# ═══════════════════════════════════════════════════════════════
def plot_ponytail_gain_card():
    """Recreates the ponytail-gain ASCII scoreboard as a vertical bar chart."""
    fig, ax = plt.subplots(figsize=(6, 4))

    categories = ["LOC", "Cost", "Time"]
    no_skill   = [100, 100, 100]           # baseline
    ponytail_min = [6, 23, 17]             # best case (% of baseline)
    ponytail_max = [20, 53, 33]            # worst case (% of baseline)
    speed_factor = "3-6× faster"

    x = np.arange(len(categories))
    w = 0.3

    ax.bar(x - w/2, no_skill, w, label="No Skill (baseline)", color="#C4C4C4", edgecolor="white", alpha=0.7)
    ax.bar(x + w/2, ponytail_max, w, label="Ponytail (max)", color="#2E86AB", edgecolor="white", alpha=0.8)
    ax.bar(x + w/2, ponytail_min, w, label="Ponytail (min)", color="#1B998B", edgecolor="white", alpha=0.9)

    # Speed annotation
    ax.text(2, 80, f"Speed: {speed_factor}", ha="center", fontsize=12,
            fontweight="bold", color="#A23B72",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#A23B72", alpha=0.9))

    # Savings labels
    reductions = ["−80–94%", "−47–77%", "−67–83%"]
    for i, (cat, red) in enumerate(zip(categories, reductions)):
        mid = (ponytail_min[i] + ponytail_max[i]) / 2
        ax.text(i + w/2, mid + 3, red, ha="center", va="bottom", fontsize=8,
                fontweight="bold", color="white",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#2E86AB", alpha=0.7))

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylabel("% of Baseline (lower = better)", fontsize=9)
    ax.set_title("Ponytail Gain — Benchmark Medians\n5 tasks × 3 models (Haiku / Sonnet / Opus)",
                 fontsize=11, fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_ylim(0, 115)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "ponytail-gain-card.png"), dpi=200)
    plt.close(fig)
    print(f"  [OK] ponytail-gain-card.png")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("Generating charts...")
    plot_defense_stack()
    plot_iteration_convergence()
    plot_ponytail_benchmark()
    plot_defense_hooks_timeline()
    plot_ponytail_gain_card()
    print(f"\nAll charts saved to: {os.path.normpath(OUT)}")
    print("Files:")
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".png"):
            fpath = os.path.join(OUT, f)
            size = os.path.getsize(fpath)
            print(f"  {f}  ({size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
