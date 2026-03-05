#!/usr/bin/env python3
"""
Generate Figure 3: Relationship between instance complexity (num_goals) and success rate.

Data sources:
  - artifacts/paper_eval_20260213/checkpoint_blocksworld.json
  - artifacts/paper_eval_20260213/checkpoint_logistics.json
  - artifacts/paper_eval_20260213/checkpoint_depots.json

Output: BDI_Paper/figures/complexity_analysis.pdf
"""
import json
import pathlib
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "artifacts" / "paper_eval_20260213"
OUT_PDF  = ROOT / "BDI_Paper" / "figures" / "complexity_analysis.pdf"

CHECKPOINT_FILES = {
    "Blocksworld": DATA_DIR / "checkpoint_blocksworld.json",
    "Logistics":   DATA_DIR / "checkpoint_logistics.json",
    "Depots":      DATA_DIR / "checkpoint_depots.json",
}

# ── Load and aggregate ─────────────────────────────────────────────────────
domain_data = {}  # domain -> {num_goals: [success_bools]}

for domain, path in CHECKPOINT_FILES.items():
    with open(path) as f:
        ckpt = json.load(f)
    groups = defaultdict(list)
    for r in ckpt["results"]:
        ng = r["pddl_data"]["num_goals"]
        groups[ng].append(r["success"])
    domain_data[domain] = dict(sorted(groups.items()))

# ── Plot ───────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 300,
})

colors = {"Blocksworld": "#2E86AB", "Logistics": "#F77F00", "Depots": "#A23B72"}
markers = {"Blocksworld": "o", "Logistics": "s", "Depots": "D"}

fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.8), sharey=True)

for ax, (domain, groups) in zip(axes, domain_data.items()):
    goals = sorted(groups.keys())
    rates = []
    counts = []
    for g in goals:
        successes = groups[g]
        rate = sum(successes) / len(successes) * 100
        rates.append(rate)
        counts.append(len(successes))

    color = colors[domain]
    ax.bar(range(len(goals)), rates, color=color, alpha=0.75,
           edgecolor="black", linewidth=0.4)

    # Annotate instance counts on top of bars
    for i, (r, c) in enumerate(zip(rates, counts)):
        ax.text(i, r + 1.5, f"n={c}", ha="center", va="bottom",
                fontsize=6, color="#555555")

    ax.set_xticks(range(len(goals)))
    ax.set_xticklabels([str(g) for g in goals], fontsize=7)
    ax.set_xlabel("Number of Goals")
    ax.set_title(domain, fontweight="bold", fontsize=10)
    ax.set_ylim(0, 115)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

axes[0].set_ylabel("Success Rate (%)")

plt.tight_layout()
OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT_PDF, bbox_inches="tight")
print(f"Saved: {OUT_PDF}")
