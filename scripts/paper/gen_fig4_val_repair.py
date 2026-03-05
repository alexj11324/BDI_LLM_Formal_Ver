#!/usr/bin/env python3
"""
Generate Figure 4: VAL error-driven repair analysis.

Left panel:  Repair trigger rate and success rate by domain.
Right panel: Distribution of repair attempts needed.

Data sources:
  - artifacts/paper_eval_20260213/checkpoint_logistics.json
  - artifacts/paper_eval_20260213/checkpoint_depots.json
  - (Blocksworld has 0 repairs, included for completeness)

Output: BDI_Paper/figures/val_repair.pdf
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
OUT_PDF  = ROOT / "BDI_Paper" / "figures" / "val_repair.pdf"

CHECKPOINT_FILES = {
    "Blocksworld": DATA_DIR / "checkpoint_blocksworld.json",
    "Logistics":   DATA_DIR / "checkpoint_logistics.json",
    "Depots":      DATA_DIR / "checkpoint_depots.json",
}

# ── Extract repair statistics ──────────────────────────────────────────────
domain_stats = {}  # domain -> {total, triggered, success, attempts_dist}
all_attempts_dist = defaultdict(lambda: {"total": 0, "succeeded": 0})

for domain, path in CHECKPOINT_FILES.items():
    with open(path) as f:
        ckpt = json.load(f)

    total = len(ckpt["results"])
    triggered = 0
    succeeded = 0
    total_attempts = 0

    for r in ckpt["results"]:
        vr = r["bdi_metrics"].get("val_repair", {})
        attempts = vr.get("attempts", 0)
        if attempts > 0:
            triggered += 1
            total_attempts += attempts
            if r["success"]:
                succeeded += 1
            # Track per-attempt-count distribution
            all_attempts_dist[attempts]["total"] += 1
            if r["success"]:
                all_attempts_dist[attempts]["succeeded"] += 1

    domain_stats[domain] = {
        "total": total,
        "triggered": triggered,
        "succeeded": succeeded,
        "total_attempts": total_attempts,
    }

# ── Plot ───────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8,
    "figure.dpi": 300,
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.2),
                                gridspec_kw={"width_ratios": [1.2, 1]})

# ── Left panel: trigger rate & success rate by domain ──────────────────────
domains = ["Blocksworld", "Logistics", "Depots"]
x = np.arange(len(domains))
width = 0.35

trigger_rates = []
success_rates = []
for d in domains:
    s = domain_stats[d]
    trigger_rates.append(s["triggered"] / s["total"] * 100 if s["total"] > 0 else 0)
    success_rates.append(
        s["succeeded"] / s["triggered"] * 100 if s["triggered"] > 0 else 0
    )

bars1 = ax1.bar(x - width / 2, trigger_rates, width,
                label="Trigger Rate", color="#F77F00", edgecolor="black", linewidth=0.5)
bars2 = ax1.bar(x + width / 2, success_rates, width,
                label="Repair Success Rate", color="#2E86AB", edgecolor="black", linewidth=0.5)

# Annotate with counts
for i, d in enumerate(domains):
    s = domain_stats[d]
    if s["triggered"] > 0:
        ax1.text(x[i] - width / 2, trigger_rates[i] + 1.5,
                 f"{s['triggered']}/{s['total']}", ha="center", va="bottom",
                 fontsize=7, color="#555555")
        ax1.text(x[i] + width / 2, success_rates[i] + 1.5,
                 f"{s['succeeded']}/{s['triggered']}", ha="center", va="bottom",
                 fontsize=7, color="#555555")
    else:
        ax1.text(x[i], 3, "No repairs\nneeded", ha="center", va="bottom",
                 fontsize=7, color="#999999", style="italic")

ax1.set_xticks(x)
ax1.set_xticklabels(domains)
ax1.set_ylabel("Percentage (%)")
ax1.set_ylim(0, 115)
ax1.set_title("Repair Rates by Domain")
ax1.legend(loc="upper right", framealpha=0.9)
ax1.grid(axis="y", alpha=0.3, linewidth=0.5)
ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)

# ── Right panel: distribution of repair attempts ───────────────────────────
attempt_counts = sorted(all_attempts_dist.keys())
if not attempt_counts:
    attempt_counts = [1, 2, 3]

totals_per_attempt = [all_attempts_dist[a]["total"] for a in attempt_counts]
succeeded_per_attempt = [all_attempts_dist[a]["succeeded"] for a in attempt_counts]
failed_per_attempt = [t - s for t, s in zip(totals_per_attempt, succeeded_per_attempt)]

x2 = np.arange(len(attempt_counts))
width2 = 0.5

bars_s = ax2.bar(x2, succeeded_per_attempt, width2,
                 label="Succeeded", color="#4CAF50", edgecolor="black", linewidth=0.5)
bars_f = ax2.bar(x2, failed_per_attempt, width2, bottom=succeeded_per_attempt,
                 label="Failed", color="#E53935", edgecolor="black", linewidth=0.5)

# Annotate totals
for i, (s, f) in enumerate(zip(succeeded_per_attempt, failed_per_attempt)):
    total = s + f
    ax2.text(i, total + 1.5, str(total), ha="center", va="bottom",
             fontsize=8, fontweight="bold")

ax2.set_xticks(x2)
ax2.set_xticklabels([f"{a} attempt{'s' if a > 1 else ''}" for a in attempt_counts])
ax2.set_ylabel("Number of Instances")
ax2.set_title("Repair Attempts Distribution")
ax2.legend(loc="upper right", framealpha=0.9)
ax2.grid(axis="y", alpha=0.3, linewidth=0.5)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)

plt.tight_layout()
OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT_PDF, bbox_inches="tight")
print(f"Saved: {OUT_PDF}")
