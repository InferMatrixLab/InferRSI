"""Render the lossless AR campaign ledger. Input gains are measured percentages."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.ledger.read_text(encoding="utf-8"))
    rounds = data["rounds"]
    fig, (ax, ops) = plt.subplots(2, 1, figsize=(10, 7.3), constrained_layout=True,
                                 gridspec_kw={"height_ratios": [2.4, 1]})
    fig.suptitle("HunyuanImage-3.0  |  Lossless AR throughput on Ascend A2", fontsize=16)
    x = range(len(rounds) + 1)
    committed = [0] + [row["accepted_cumulative_gain_pct"] for row in rounds]
    ax.step(x, committed, where="post", color="#00796b", linewidth=2.4,
            label="Verified cumulative stage gain")
    ax.scatter(x, committed, color="#00796b", s=40, zorder=3)
    for index, entry in enumerate(rounds, start=1):
        stage = entry.get("stage")
        if stage and stage.get("gain_pct") is not None:
            pairs = stage.get("pairs_pct", [])
            offsets = [0] if len(pairs) == 1 else [
                (i - (len(pairs) - 1) / 2) * .065 for i in range(len(pairs))
            ]
            ax.scatter([index + offset for offset in offsets], pairs, s=35, color="#8091aa",
                       zorder=2, label="Independent A/B pairs" if index == 1 else None)
            ax.scatter(index, stage["gain_pct"], s=65, color="#d96519", marker="D",
                       label="Change in stage median" if index == 1 else None, zorder=4)
            ax.annotate(f'{stage["gain_pct"]:+.2f}%', (index, stage["gain_pct"]),
                        xytext=(7, 8), textcoords="offset points", fontsize=9, color="#964100")
        else:
            ax.annotate("No stage estimate", (index, committed[index]), xytext=(0, 12),
                        ha="center", textcoords="offset points", fontsize=9, color="#596677")
    ax.set_xticks(list(x), ["Baseline"] + [row["label"] for row in rounds])
    ax.set_xlim(-.3, len(rounds) + .45)
    lo, hi = ax.get_ylim()
    ax.set_ylim(min(-1, lo - (hi-lo)*.12), max(2, hi + (hi-lo)*.30))
    ax.set_ylabel("Change in offline output tokens/s (%)")
    ax.grid(axis="y", color="#dce1e6")
    ax.spines[["right", "top"]].set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), frameon=False, ncols=3, fontsize=9)
    values = [row["component"]["speedup"] for row in rounds]
    rows = list(range(len(rounds)))
    ops.barh(rows, values, height=.46, color="#537999")
    ops.set_yticks(rows, labels=[row["operation"] for row in rounds])
    ops.invert_yaxis()
    ops.axvline(1, ls=":", color="#596677")
    for pos, value in enumerate(values):
        ops.text(value + .18, pos, f"{value:.2f}×", va="center", fontsize=9)
    ops.set_xlim(0, max(values)*1.17)
    ops.set_xlabel("Isolated operation throughput relative to its own baseline (×)")
    ops.spines[["top", "right", "left"]].set_visible(False)
    fig.savefig(args.output, dpi=165, facecolor="white")


if __name__ == "__main__":
    main()
