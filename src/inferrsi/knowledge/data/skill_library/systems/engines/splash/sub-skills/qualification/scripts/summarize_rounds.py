#!/usr/bin/env python3
"""Describe existing positive lower-is-better samples in four ABBA rounds.

Adapted from incoai/splash dev/benchmarks/abba.py (Apache-2.0), as identified
in the owning skill's pinned source provenance. Changes: file-based offline
CLI; descriptive output only; all fixed acceptance/noise gates removed.
No engine, model, network, external process or verdict is involved.

Example: python summarize_rounds.py --input rounds.json
Input: {"rounds": [[100, 101], [95, 96], [96, 97], [101, 102]]}
Round order: baseline, candidate, candidate, baseline.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def summarize(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != {"rounds"}:
        raise ValueError("input must contain only a rounds array")
    rounds = document["rounds"]
    if not isinstance(rounds, list) or len(rounds) != 4:
        raise ValueError("exactly four ABBA rounds are required")
    medians = []
    for samples in rounds:
        if not isinstance(samples, list) or not samples:
            raise ValueError("each round needs a nonempty sample array")
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
            for value in samples
        ):
            raise ValueError("every sample must be a finite positive number")
        medians.append(statistics.median(samples))
    baseline = medians[0] / 2 + medians[3] / 2
    candidate = medians[1] / 2 + medians[2] / 2
    if not (
        math.isfinite(baseline) and math.isfinite(candidate) and baseline > 0 and candidate > 0
    ):
        raise ValueError("round reductions are outside the finite positive range")
    change = candidate / baseline - 1
    spread = max(
        abs(medians[0] - medians[3]) / baseline,
        abs(medians[1] - medians[2]) / candidate,
    )
    if not (math.isfinite(change) and math.isfinite(spread)):
        raise ValueError("relative metrics are outside the finite range")
    return {
        "round_order": ["baseline", "candidate", "candidate", "baseline"],
        "round_medians": medians,
        "baseline": baseline,
        "candidate": candidate,
        "relative_change_lower_is_better": change,
        "within_pair_relative_spread": spread,
        "scope": "descriptive only; apply separately frozen experiment gates",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = summarize(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, OverflowError) as error:
        parser.exit(2, f"invalid round samples: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
