"""Replot the published values; English labels need no optional CJK font.

Requires matplotlib. The historical Chinese PNG is preserved separately; this
portable renderer reproduces its data and three-panel view, not its exact pixels.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent
MODELS = {
    "gpt-6.1-sol": ("GPT-6.1 Sol", "#2164b5"),
    "gpt-5.6-sol": ("GPT-5.6 Sol", "#12856a"),
    "gpt-6-astra": ("GPT-6 Astra", "#d96125"),
}


def main(output):
    source = ROOT / "results/summary.json"
    original = source.read_bytes()
    sessions = json.loads(original)["sessions"]
    assert len(sessions) == 6
    # Outputs stay outside the frozen bundle.
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Choose an output prefix outside this frozen evidence bundle")
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig = plt.figure(figsize=(15, 11.3), facecolor="white")
    grid = fig.add_gridspec(
        2,
        2,
        left=0.075,
        right=0.975,
        top=0.825,
        bottom=0.15,
        hspace=0.36,
        wspace=0.20,
        height_ratios=[1, 1.30],
    )
    by_round, token_growth, efficiency = (
        fig.add_subplot(grid[0, 0]),
        fig.add_subplot(grid[0, 1]),
        fig.add_subplot(grid[1, :]),
    )
    handles = []
    for session in sessions:
        rows = [r for r in session["observations"] if r["role"] == "exploratory"]
        final = next(r for r in session["observations"] if r["role"] == "final")
        assert [r["round_index"] for r in rows] == list(range(1, 9))
        model, color = MODELS[session["model"]]
        enabled = session["knowledge"] == "on"
        style, marker = ("-", "o") if enabled else ((0, (5, 3)), "s")
        label = f"{model} / KB {'ON' if enabled else 'OFF'}"
        rounds = [0] + [r["round_index"] for r in rows]
        tokens = [0.0] + [r["cumulative_total_tokens"] / 1e6 for r in rows]
        best = [1.0] + [r["best_exploration_speedup"] for r in rows]
        kwargs = dict(color=color, linestyle=style, linewidth=2.1, alpha=0.92)
        by_round.step(rounds, best, where="post", **kwargs)
        token_growth.plot(
            rounds,
            tokens,
            marker=marker,
            markersize=3.8,
            markerfacecolor=color if enabled else "white",
            **kwargs,
        )
        efficiency.step(tokens, best, where="post", **kwargs)
        for ax, xs in ((by_round, rounds), (efficiency, tokens)):
            ax.scatter(
                xs[1:],
                best[1:],
                edgecolors=color,
                marker=marker,
                s=22,
                facecolors=color if enabled else "white",
                zorder=4,
            )
        efficiency.scatter(
            final["cumulative_total_tokens"] / 1e6,
            final["effective_speedup"],
            marker="D",
            s=72,
            facecolors=color if enabled else "white",
            edgecolors=color,
            linewidths=1.8,
            zorder=6,
        )
        handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                linestyle=style,
                linewidth=2.5,
                marker=marker,
                markerfacecolor=color if enabled else "white",
                label=label,
            )
        )
    for ax in (by_round, token_growth, efficiency):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#dce2e7", linewidth=0.7)
        ax.set_axisbelow(True)
    for ax in (by_round, efficiency):
        ax.set_ylim(0.95, 2.60)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}x"))
        ax.set_ylabel("Best valid speedup found")
    for ax in (by_round, token_growth):
        ax.set_xlim(0, 8.2)
        ax.set_xticks(range(9))
        ax.set_xlabel("Consumed optimization rounds")
    by_round.set_title("1. Optimization progress", loc="left", fontsize=13, pad=12)
    token_growth.set_title("2. Cumulative token usage", loc="left", fontsize=13, pad=12)
    token_growth.set_ylabel("Tokens (millions; includes cached input)")
    token_growth.set_ylim(bottom=0)
    efficiency.set_title(
        "3. Search results versus cumulative token usage", loc="left", fontsize=13, pad=12
    )
    efficiency.set_xlabel("Cumulative tokens through evaluation completion (millions)")
    efficiency.set_xlim(left=0)
    fig.suptitle(
        "Six configurations: optimization progress and token usage",
        x=0.075,
        y=0.985,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.075,
        0.949,
        "Two-NPU MoE / eight rounds each / solid-filled: KB ON; dashed-hollow: KB OFF",
        fontsize=11,
        color="#52606c",
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.07, 0.94),
        ncols=3,
        frameon=False,
        fontsize=10.5,
        columnspacing=3,
    )
    notes = (
        "Steps/dots: best valid exploration result. Diamonds: independent final; "
        "its cost is included, its result does not rewrite the curve.",
        "Both Astra R4 failures consume rounds/tokens; best stays unchanged. "
        "Report-tail tokens are excluded. Speedups use paired task baselines.",
        "One trajectory per condition; tokens include cached input and are not money or wall time. "
        "Astra ON queued 41.42 min; OFF ~1.28 sec.",
    )
    for y, note in zip((0.091, 0.066, 0.041), notes):
        fig.text(0.075, y, note, fontsize=9, color="#46505a")
    fig.savefig(output.with_suffix(".png"), dpi=180, bbox_inches="tight")
    plt.close(fig)
    assert source.read_bytes() == original
    print("Reproduced the public numerical curves; original data and historical PNG unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Output prefix outside the evidence bundle"
    )
    main(parser.parse_args().output)
