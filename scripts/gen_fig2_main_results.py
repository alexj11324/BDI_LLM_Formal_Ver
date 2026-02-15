#!/usr/bin/env python3
"""
Generate Figure 2: Per-domain accuracy comparison between LLM baselines and BDI-LLM.

Data sources:
  - BDI-LLM results: artifacts/paper_eval_20260213/MANIFEST.json (paper_primary_counts)
  - Baselines: from Valmeekam et al. (PlanBench), as cited in the paper

Output: BDI_Paper/figures/main_results.pdf
"""
import json
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "artifacts" / "paper_eval_20260213" / "MANIFEST.json"
OUT_PDF  = ROOT / "BDI_Paper" / "figures" / "main_results.pdf"

# ── Load data ──────────────────────────────────────────────────────────────
with open(MANIFEST) as f:
    manifest = json.load(f)

counts = manifest["paper_primary_counts"]

# Domain order and display names
domains = ["blocksworld", "logistics", "depots"]
labels  = ["Blocksworld", "Logistics", "Depots"]

bdi_acc = [counts[d]["accuracy"] * 100 for d in domains]
bdi_passed = [counts[d]["passed"] for d in domains]
bdi_total  = [counts[d]["total"] for d in domains]

# PlanBench baselines (GPT-4, from Valmeekam et al. 2023, as cited in paper)
baseline_acc = [35.0, 5.0, 5.0]  # approximate values from paper Table 2

# ── Plot ───────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "figure.dpi": 300,
})

fig, ax = plt.subplots(figsize=(5.5, 3.5))

x = np.arange(len(domains))
width = 0.35

bars_base = ax.bar(x - width / 2, baseline_acc, width,
                   label="GPT-4 Baseline (PlanBench)",
                   color="#BDBDBD", edgecolor="black", linewidth=0.6)
bars_bdi  = ax.bar(x + width / 2, bdi_acc, width,
                   label="BDI-LLM (Ours)",
                   color="#2E86AB", edgecolor="black", linewidth=0.6)

# Annotate BDI bars with passed/total
for bar, p, t in zip(bars_bdi, bdi_passed, bdi_total):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
            f"{p}/{t}", ha="center", va="bottom", fontsize=8, fontweight="bold")

# Annotate baseline bars
for bar, acc in zip(bars_base, baseline_acc):
    label = f"~{acc:.0f}%" if acc >= 10 else f"<{acc:.0f}%"
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
            label, ha="center", va="bottom", fontsize=8, color="#555555")

ax.set_ylabel("Accuracy (%)")
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_ylim(0, 115)
ax.set_yticks([0, 20, 40, 60, 80, 100])
ax.legend(loc="upper left", framealpha=0.9)
ax.grid(axis="y", alpha=0.3, linewidth=0.5)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT_PDF, bbox_inches="tight")
print(f"Saved: {OUT_PDF}")
