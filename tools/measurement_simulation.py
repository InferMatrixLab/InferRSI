"""Reproduce the synthetic ablation behind harness paired statistics.

Simulated campaigns (software only, not device measurements) compare four rules
on the same samples, so the contribution of pairing and of the interval can be
separated:

* point_rule        current project.assess: ratio of independent medians >= gate
* paired_point      median of per-repetition speedups >= gate, no interval
* unpaired_interval percentile bootstrap of the ratio of independently resampled
                    medians; lower bound > gate
* paired_interval   harness.measurement.paired_statistics: above_gate

The data seed generates samples; the paired interval uses the production
bootstrap configuration (RESAMPLES, SEED) unless overridden. Coverage is the
fraction of campaigns whose paired bootstrap interval contains the true median
speedup (computed even below MIN_PAIRS, where the harness reports no interval),
which equals the configured true speedup under this symmetric noise model.

    python tools/measurement_simulation.py            # production bootstrap config
    python tools/measurement_simulation.py --resamples 1000 --campaigns 100   # quick
"""

import argparse
import json
import math
import random
from statistics import median

from inferrsi.harness.measurement import (
    MIN_PAIRS,
    RESAMPLES,
    SEED,
    bootstrap_median_interval,
    gate_speedup,
    paired_statistics,
)

REPETITIONS = (3, 5, 10, 20)
TRUE_SPEEDUPS = (1.0, 1.01, 1.03, 1.05, 1.10)
NOISES = ("lognormal", "heavy_tail")


def campaign(rng, repetitions, true_speedup, noise):
    level, baseline, candidate = 10.0, [], []
    for _ in range(repetitions):
        level *= math.exp(rng.gauss(0, 0.02))  # drift shared by both sides of a pair

        def sample(scale):
            value = level * scale * math.exp(rng.gauss(0, 0.03))
            if noise == "heavy_tail" and rng.random() < 0.1:
                value *= 1.3
            return value

        baseline.append(sample(1.0))
        candidate.append(sample(1 / true_speedup))
    return baseline, candidate


def unpaired_lower_bound(baseline, candidate, rng, resamples):
    ratios = sorted(
        median(rng.choices(baseline, k=len(baseline)))
        / median(rng.choices(candidate, k=len(candidate)))
        for _ in range(resamples)
    )
    return ratios[int(0.025 * (resamples - 1))]


def rates(*, repetitions, true_speedup, noise, gate_pct, campaigns, data_seed, resamples,
          bootstrap_seed):
    rng = random.Random(f"{data_seed}-{noise}-{repetitions}-{true_speedup}")
    unpaired_rng = random.Random(f"unpaired-{data_seed}")
    gate = gate_speedup(gate_pct, "minimize")
    counts = dict.fromkeys(("point_rule", "paired_point", "unpaired_interval",
                            "paired_interval", "covered"), 0)
    widths = []
    for _ in range(campaigns):
        baseline, candidate = campaign(rng, repetitions, true_speedup, noise)
        point = median(baseline) / median(candidate)
        counts["point_rule"] += point >= gate and point > 1
        pairs = [b / c for b, c in zip(baseline, candidate)]
        counts["paired_point"] += median(pairs) >= gate
        counts["unpaired_interval"] += (
            unpaired_lower_bound(baseline, candidate, unpaired_rng, resamples) > gate
        )
        result = paired_statistics(baseline, candidate, direction="minimize",
                                   min_improvement_pct=gate_pct, point_gate_passed=True,
                                   resamples=resamples, seed=bootstrap_seed)
        # Coverage is computed for every repetition count, including those below
        # MIN_PAIRS where the harness deliberately reports no interval.
        low, high = bootstrap_median_interval(pairs, resamples=resamples, seed=bootstrap_seed)
        counts["covered"] += low <= true_speedup <= high
        widths.append(high / low)
        counts["paired_interval"] += result.get("gate_relation") == "above_gate"
    row = {"noise": noise, "repetitions": repetitions, "true_speedup": true_speedup,
           "harness_reports_interval": repetitions >= MIN_PAIRS}
    for name, count in counts.items():
        p = count / campaigns
        row[name] = {"rate": round(p, 4),
                     "monte_carlo_se": round(math.sqrt(p * (1 - p) / campaigns), 4)}
    row["median_interval_width_ratio"] = round(median(widths), 4) if widths else None
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--campaigns", type=int, default=200)
    parser.add_argument("--gate-pct", type=float, default=1.0)
    parser.add_argument("--data-seed", type=int, default=20261115)
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--bootstrap-seed", type=int, default=SEED)
    args = parser.parse_args()
    rows = [rates(repetitions=r, true_speedup=t, noise=n, gate_pct=args.gate_pct,
                  campaigns=args.campaigns, data_seed=args.data_seed,
                  resamples=args.resamples, bootstrap_seed=args.bootstrap_seed)
            for n in NOISES for r in REPETITIONS for t in TRUE_SPEEDUPS]
    print(json.dumps({"settings": vars(args), "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
