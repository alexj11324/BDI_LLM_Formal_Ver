#!/usr/bin/env python3
"""Generate PlanBench evaluation results chart from summary data."""
import json
import matplotlib.pyplot as plt
import numpy as np

def main():
    with open("runs/planbench_real_summary.json") as f:
        data = json.load(f)

    domains = list(data["domains"].keys())
    accuracies = [data["domains"][d]["accuracy"] * 100 for d in domains]
    totals = [data["domains"][d]["total"] for d in domains]
    successes = [data["domains"][d]["success"] for d in domains]

    overall_acc = data["overall"]["accuracy"] * 100
    overall_total = data["overall"]["total"]
    overall_success = data["overall"]["success"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [2, 1]})

    # Bar chart: accuracy by domain
    colors = ["#2E86AB", "#F77F00", "#A23B72"]
    x = np.arange(len(domains))
    bars = ax1.bar(x, accuracies, color=colors, alpha=0.85, edgecolor="black", linewidth=0.8)

    for bar, acc, s, t in zip(bars, accuracies, successes, totals):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                 f"{acc:.1f}%\n({s}/{t})", ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax1.set_xticks(x)
    ax1.set_xticklabels([d.capitalize() for d in domains], fontsize=12)
    ax1.set_ylabel("Accuracy (%)", fontsize=12)
    ax1.set_ylim(0, max(accuracies) * 1.3 if max(accuracies) > 0 else 10)
    ax1.set_title("Accuracy by Domain", fontsize=14, fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)

    # Overall summary
    ax2.bar(["Overall"], [overall_acc], color="#4CAF50", alpha=0.85, edgecolor="black", linewidth=0.8)
    ax2.text(0, overall_acc + 1, f"{overall_acc:.1f}%\n({overall_success}/{overall_total})",
             ha="center", va="bottom", fontsize=13, fontweight="bold")
    ax2.set_ylabel("Accuracy (%)", fontsize=12)
    ax2.set_ylim(0, max(overall_acc * 1.5, 10))
    ax2.set_title("Overall", fontsize=14, fontweight="bold")
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("BDI-LLM PlanBench Evaluation Results", fontsize=16, fontweight="bold")
    plt.tight_layout()
    plt.savefig("runs/planbench_results.png", dpi=300, bbox_inches="tight")
    print("Chart saved: runs/planbench_results.png")

if __name__ == "__main__":
    main()
