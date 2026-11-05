"""Aggregate saved runs and apply the campaign's frozen directional gates."""

import argparse
import json
import statistics
from pathlib import Path

import numpy as np


def aggregate(root):
    rows = []
    for concurrency in (1, 2, 4, 8, 16, 32):
        summaries, requests = [], []
        for repeat in (1, 2, 3):
            folder = root / f"c{concurrency}/run{repeat}"
            if not (folder / "summary.json").exists():
                continue
            summaries.append(json.loads((folder / "summary.json").read_text()))
            requests.extend(
                json.loads(line) for line in (folder / "requests.jsonl").read_text().splitlines()
            )
        if not summaries:
            continue
        rates = [row["throughput_frames_s"] for row in summaries]
        rows.append(
            {
                "concurrency": concurrency,
                "requests_per_repeat": [row["n_requests"] for row in summaries],
                "repeats": len(summaries),
                "n_failed": sum(row["n_failed"] for row in summaries),
                "throughput_frames_s_mean": statistics.mean(rates),
                "throughput_frames_s_runs": rates,
                "ttfa_p50_ms_pooled": float(
                    np.percentile([row["ttfa_s"] for row in requests], 50) * 1000
                ),
                "ttfa_p95_ms_pooled": float(
                    np.percentile([row["ttfa_s"] for row in requests], 95) * 1000
                ),
                "rtf_mean": statistics.mean(row["rtf"] for row in requests),
                "mean_audio_seconds": statistics.mean(row["duration_s"] for row in requests),
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--quality-dir", type=Path, required=True)
    parser.add_argument("--baseline-quality-prefix", default="vllm-repeated")
    parser.add_argument("--candidate-quality-prefix", default="vllm-speaker-repeated")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    baseline, candidate = aggregate(args.baseline), aggregate(args.candidate)
    complete = all(
        len(rows) == 6
        and all(row["repeats"] == 3 and row["requests_per_repeat"] == [320] * 3 for row in rows)
        for rows in (baseline, candidate)
    )
    performance = []
    for concurrency in (16, 32):
        b = next((row for row in baseline if row["concurrency"] == concurrency), None)
        c = next((row for row in candidate if row["concurrency"] == concurrency), None)
        if b and c:
            performance.append(
                {
                    "concurrency": concurrency,
                    "gain_ratio": c["throughput_frames_s_mean"] / b["throughput_frames_s_mean"],
                    "all_candidate_runs_exceed_all_baseline_runs": min(
                        c["throughput_frames_s_runs"]
                    )
                    > max(b["throughput_frames_s_runs"]),
                }
            )
    quality = []
    for concurrency in (1, 16, 32):
        paths = [
            args.quality_dir / f"{prefix}-c{concurrency}.json"
            for prefix in (args.baseline_quality_prefix, args.candidate_quality_prefix)
        ]
        if not all(path.exists() for path in paths):
            continue
        b, c = [json.loads(path.read_text()) for path in paths]
        if not all(set(doc["tasks"]) == {"wer", "sim", "utmos"} for doc in (b, c)):
            continue
        b, c = b["summary"], c["summary"]
        quality.append(
            {
                "concurrency": concurrency,
                "baseline": b,
                "candidate": c,
                "gates": {
                    "wer_nonincrease": c["wer"] <= b["wer"],
                    "sim_nondecrease": c["sim"] >= b["sim"],
                    "utmos_nondecrease": c["utmos"] >= b["utmos"],
                },
            }
        )
    if not complete or len(quality) != 3:
        verdict = "INCONCLUSIVE"
    elif any(row["n_failed"] for row in baseline + candidate) or not all(
        all(row["gates"].values()) for row in quality
    ):
        verdict = "FAIL"
    elif len(performance) != 2 or not all(
        row["all_candidate_runs_exceed_all_baseline_runs"] for row in performance
    ):
        verdict = "FAIL"
    else:
        verdict = "PASS"
    args.out.write_text(
        json.dumps(
            {
                "verdict": verdict,
                "scope": (
                    "Frozen steady-state throughput and point-estimate speech gates; "
                    "no global optimum or cold-cache certification"
                ),
                "baseline": baseline,
                "candidate": candidate,
                "performance": performance,
                "quality": quality,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
