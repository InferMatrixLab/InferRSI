"""Plot saved aggregate metrics; ranges are observed repeats, not confidence intervals."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baselines", type=Path, required=True)
    parser.add_argument("--integrated", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baselines.read_text())["rows"]
    series = [
        ("vLLM main aa3fd1d9", [row for row in baseline if row["engine"] == "vllm"], "#335c9d"),
        (
            "SGLang dbd923cd (terminal audio)",
            [row for row in baseline if row["engine"] == "sglang"],
            "#d98222",
        ),
        ("vLLM main 15bce345", json.loads(args.integrated.read_text())["baseline"], "#308664"),
        (
            "vLLM CPU-reference TRT + MPS 227a43e8",
            json.loads(args.integrated.read_text())["candidate"],
            "#8c5aa8",
        ),
    ]
    panels = [
        ("throughput_frames_s_mean", "Throughput (audio frames/s)"),
        ("ttfa_p50_ms_pooled", "TTFA p50 (ms)"),
        ("ttfa_p95_ms_pooled", "TTFA p95 (ms)"),
        ("rtf_mean", "RTF (mean)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    for ax, (key, title) in zip(axes.flat, panels):
        for label, rows, color in series:
            rows = sorted(rows, key=lambda row: row["concurrency"])
            assert len(rows) == 6, f"Incomplete series: {label}"
            x = [row["concurrency"] for row in rows]
            ax.plot(x, [row[key] for row in rows], marker="o", color=color, label=label)
            if key == "throughput_frames_s_mean":
                ax.fill_between(
                    x,
                    [min(row["throughput_frames_s_runs"]) for row in rows],
                    [max(row["throughput_frames_s_runs"]) for row in rows],
                    color=color,
                    alpha=0.12,
                )
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 2, 4, 8, 16, 32], labels=[1, 2, 4, 8, 16, 32])
        ax.set_xlabel("Concurrency")
        ax.set_title(title)
        ax.grid(alpha=0.2)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.04), fontsize=9)
    fig.suptitle("MiniCPM-o 4.5 · one L20X · Seed-TTS English · steady state")
    verdict = json.loads(args.integrated.read_text())["verdict"]
    fig.text(
        0.5,
        0.94,
        f"Combined service / quality verdict: {verdict}",
        ha="center",
        color="#9e2828" if verdict != "PASS" else "#308664",
        fontsize=10,
    )
    fig.text(
        0.5,
        0.015,
        "25 audio frames/s; 3 × 320 measured requests/cell. "
        "SGLang TTFA is terminal-waveform latency. Quality verdicts are separate.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.12, 1, 0.90))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out.with_suffix(".png"), dpi=160)
    svg = args.out.with_suffix(".svg")
    fig.savefig(svg)
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


if __name__ == "__main__":
    main()
