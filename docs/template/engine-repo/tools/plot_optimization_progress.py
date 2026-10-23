"""Draw README throughput progress from one comparable E2E measurement series.

Matplotlib is an optional documentation dependency. See docs/optimization-progress.md.
"""

import argparse
import csv
import math
import textwrap
from pathlib import Path


def read_points(path: Path, *, illustrative: bool = False) -> list[dict]:
    """Validate plotting inputs without claiming to validate their evidence."""
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"day", "phase", "optimization", "throughput", "verdict", "evidence"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV requires columns: {', '.join(sorted(required))}")
        points = []
        for row_number, row in enumerate(reader, start=2):
            point = {key: (row.get(key) or "").strip() for key in required}
            try:
                day = float(point["day"])
                throughput = float(point["throughput"])
            except ValueError as exc:
                raise ValueError(f"Row {row_number}: day and throughput must be numeric") from exc
            if not math.isfinite(day) or day < 0:
                raise ValueError(f"Row {row_number}: day must be finite and nonnegative")
            if not math.isfinite(throughput) or throughput <= 0:
                raise ValueError(f"Row {row_number}: throughput must be positive and finite")
            if (not points and day != 0) or (points and day <= points[-1]["day"]):
                raise ValueError("Days must start at zero and strictly increase")
            if not point["phase"] or not point["optimization"]:
                raise ValueError(f"Row {row_number}: phase and optimization are required")
            if point["verdict"] not in {"PASS", "FAIL", "INCONCLUSIVE"}:
                raise ValueError(f"Row {row_number}: use PASS, FAIL or INCONCLUSIVE")
            if not illustrative and not point["evidence"]:
                raise ValueError(f"Row {row_number}: measured points require an evidence link/path")
            points.append({**point, "day": day, "throughput": throughput})
    if not points:
        raise ValueError("CSV must contain at least a measured baseline or an illustrative row")
    baseline = points[0]["throughput"]
    for point in points:
        point["gain"] = point["throughput"] / baseline
        if not math.isfinite(point["gain"]) or point["gain"] <= 0:
            raise ValueError("Normalized gain must be positive and finite")
    return points


def plot_progress(
    points: list[dict], output: Path, title: str, unit: str, *, illustrative: bool = False
) -> None:
    # Keep CSV validation usable without installing plotting dependencies.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "svg.hashsalt": "engine-progress", "svg.fonttype": "none"}
    )
    fig, ax = plt.subplots(figsize=(16, 7.8), facecolor="white")
    fig.subplots_adjust(left=0.075, right=0.975, bottom=0.16, top=0.79)
    fig.text(0.075, 0.935, title, fontsize=23, weight="bold", color="#202c3a")
    status = (
        "ILLUSTRATIVE ONLY · synthetic data · no performance claim"
        if illustrative
        else "Recorded E2E measurements · verdicts and scope: see evidence ledger"
    )
    fig.text(0.075, 0.88, status, fontsize=13, color="#995c00" if illustrative else "#536176")
    days = [p["day"] for p in points]
    gains = [p["gain"] for p in points]
    padding = max(days[-1] * 0.06, 0.5)
    edges = [days[0] - padding]
    edges += [(left + right) / 2 for left, right in zip(days, days[1:])]
    edges += [days[-1] + padding]
    colors = ["#edf2f8", "#e4eef9", "#edf2f8", "#e6f3f2"]
    start = 0
    phase_number = 0
    for end in range(1, len(points) + 1):
        if end < len(points) and points[end]["phase"] == points[start]["phase"]:
            continue
        ax.axvspan(edges[start], edges[end], color=colors[phase_number % len(colors)], zorder=0)
        ax.text(
            (edges[start] + edges[end]) / 2,
            1.02,
            textwrap.fill(points[start]["phase"], 23),
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=12,
            weight="bold",
            color="#293747",
        )
        start = end
        phase_number += 1
    ax.plot(days, gains, color="#326ec4", linewidth=2.8, zorder=2)
    ax.fill_between(days, gains, min(1, min(gains)), color="#326ec4", alpha=0.06)
    styles = {"PASS": ("o", "#326ec4"), "FAIL": ("X", "#b94e45"), "INCONCLUSIVE": ("D", "#65748a")}
    seen = set()
    for index, point in enumerate(points):
        verdict = point["verdict"]
        marker, color = ("o", "#326ec4") if illustrative else styles[verdict]
        label = verdict if not illustrative and verdict not in seen else None
        ax.scatter(
            point["day"], point["gain"], marker=marker, color=color, s=54, zorder=3, label=label
        )
        seen.add(verdict)
        above = index % 2 == 0
        offset = 22 if above else -28
        alignment = "bottom" if above else "top"
        ax.annotate(
            f"{point['gain']:.2f}×",
            (point["day"], point["gain"]),
            xytext=(0, offset),
            textcoords="offset points",
            ha="center",
            va=alignment,
            fontsize=16,
            weight="bold",
            color="#218a8a",
        )
        ax.annotate(
            textwrap.fill(point["optimization"], 21),
            (point["day"], point["gain"]),
            xytext=(0, offset + (24 if above else -24)),
            textcoords="offset points",
            ha="center",
            va=alignment,
            fontsize=10.5,
            color="#293747",
        )
    span = max(max(gains) - min(gains), 0.5)
    ax.set_ylim(max(0, min(gains) - span * 0.40), max(gains) + span * 0.48)
    ax.set_xlim(edges[0] - padding * 0.45, edges[-1] + padding * 0.45)
    ax.set_xticks(days, [f"T+{day:g}" for day in days])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}×"))
    ax.set_xlabel("Development time (elapsed days)", fontsize=12, labelpad=16)
    ax.set_ylabel("End-to-end throughput / baseline", fontsize=12, labelpad=12)
    ax.grid(axis="y", color="#cfd8e3", alpha=0.55)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=11, length=0, pad=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    if not illustrative:
        ax.legend(loc="upper left", fontsize=10, frameon=False, ncol=3)
    fig.text(
        0.075,
        0.035,
        f"Baseline: {points[0]['throughput']:g} {unit} = 1.00×. "
        "Each point is cumulative; plateaus and regressions are retained.",
        fontsize=11,
        color="#536176",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"Date": None} if output.suffix.lower() == ".svg" else None
    fig.savefig(output, dpi=180, metadata=metadata, facecolor="white")
    plt.close(fig)
    if output.suffix.lower() == ".svg":
        # Keep generated SVG diffs clean and stable across Windows/Linux checkouts.
        lines = output.read_text(encoding="utf-8").splitlines()
        output.write_text(
            "\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8", newline="\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="CSV for one comparable E2E throughput series")
    parser.add_argument("--output", type=Path, required=True, help="Output SVG or PNG")
    parser.add_argument("--title", required=True, help="Engine name and comparison scope")
    parser.add_argument("--unit", required=True, help="Throughput unit, e.g. tokens/s")
    parser.add_argument("--illustrative", action="store_true", help="Label synthetic example data")
    args = parser.parse_args()
    if args.output.suffix.lower() not in {".svg", ".png"}:
        parser.error("--output must end in .svg or .png")
    try:
        points = read_points(args.data, illustrative=args.illustrative)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    plot_progress(points, args.output, args.title, args.unit, illustrative=args.illustrative)


if __name__ == "__main__":
    main()
