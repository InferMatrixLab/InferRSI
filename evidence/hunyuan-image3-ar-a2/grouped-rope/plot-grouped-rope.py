"""Plot measured stage gains relative to the reference actually used by each round."""
import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def draw(ax, rows, labels, title):
    ax.axhline(0, color="#5a6c78", linewidth=1)
    ax.grid(axis="y", color="#e1e7ea", linewidth=.8)
    ax.set_axisbelow(True)
    best = 0
    steps = [0]
    for index, (pairs, gain, qualified, status) in enumerate(rows, 1):
        if gain is not None:
            ax.scatter([index - .085, index, index + .085], pairs,
                       color="#8394a9", s=30, zorder=3)
            ax.scatter(index, gain, color="#d56621", marker="D", s=55, zorder=4)
            ax.annotate(f"{gain:+.2f}%", (index, gain), xytext=(3, 9),
                        textcoords="offset points", fontsize=9, color="#984300")
            if qualified:
                best = max(best, gain)
        else:
            label = "Pending" if status == "pending" else "No stage result"
            ax.annotate(label, (index, 0), xytext=(0, -17), ha="center",
                        textcoords="offset points", color="#546575", fontsize=8)
        steps.append(float("nan") if status == "pending" else best)
    measured = [i for i, value in enumerate(steps) if math.isfinite(value)]
    ax.step(measured, [steps[i] for i in measured], where="post", color="#007c72", lw=2.4)
    ax.scatter(measured, [steps[i] for i in measured], color="#007c72", s=20)
    ax.set_xticks(range(len(steps)), ["Reference", *labels])
    ax.set_xlim(-.28, len(rows) + .45)
    ax.set_title(title, loc="left", fontsize=12)
    ax.spines[["right", "top"]].set_visible(False)
    ax.margins(y=.25)


def main():
    args = argparse.ArgumentParser()
    for field in ("previous", "grouped", "output"):
        args.add_argument(field, type=Path)
    ns = args.parse_args()
    previous = json.loads(ns.previous.read_text(encoding="utf-8"))["rounds"]
    grouped = json.loads(ns.grouped.read_text(encoding="utf-8"))["rounds"]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.6), constrained_layout=True)
    fig.suptitle("HunyuanImage-3.0  |  Batched AR on Ascend A2", fontsize=16)
    draw(axes[0], [(r["stage"]["pairs_pct"], r["stage"]["gain_pct"], r["accepted"], "measured")
                   for r in previous], ["R1  Mask", "R2  Positions", "R3  Shared RoPE"],
         "Earlier rounds  ·  gain over each matched stock baseline")
    draw(axes[1], [(r.get("paired_pct"), r.get("relative_gain_pct"), r["qualified"], r["status"])
                   for r in grouped], ["R4  Factors", "R5  Packed Q/K", "R6  Combined"],
         "Grouped rounds  ·  additional gain over the shared-RoPE baseline")
    for ax in axes:
        ax.set_ylabel("Output tokens/s change (%)")
    axes[1].axhline(2, ls="--", color="#7d6879", lw=1)
    handles = [Line2D([], [], color="#007c72", lw=2, label="Best verified gain"),
               Line2D([], [], ls="", marker="D", color="#d56621", label="Change in medians"),
               Line2D([], [], ls="", marker="o", color="#8394a9", label="Three A/B pairs"),
               Line2D([], [], ls="--", color="#7d6879", label="2% minimum for a bundle")]
    axes[1].legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, -.13),
                   ncols=4, frameon=False, fontsize=9)
    fig.savefig(ns.output, dpi=160, facecolor="white")


if __name__ == "__main__":
    main()
