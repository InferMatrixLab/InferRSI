"""Paired, report-only statistics for alternating baseline/candidate measurements.

The project protocol alternates AB/BA order inside each repetition, so the k-th
baseline and k-th candidate sample share one repetition. Their per-pair ratio
cancels drift shared within a repetition, which independent per-side medians
retain. This module only describes retained samples: it never changes a verdict,
eligibility or gate, and any value it cannot compute is reported as unavailable.

The estimand is the median per-repetition speedup. The interval is a nominal 95%
percentile bootstrap over repetitions with a recorded seed. Its coverage is not
calibrated in general: with few repetitions it collapses towards the observed pair
range and under-covers (about 75% at three pairs in tools/measurement_simulation.py),
so no interval is reported below MIN_PAIRS. Repetitions are assumed independent;
pairing cannot
remove contention shared by both sides of one pair and does not qualify the
environment.
"""

import math
import random
from statistics import median

METHOD = "paired_median_speedup_percentile_bootstrap"
CONFIDENCE = 0.95
MIN_PAIRS = 5
RESAMPLES = 10_000
SEED = 0


def gate_speedup(min_improvement_pct: float, direction: str) -> float:
    """Express the frozen improvement gate as the equivalent speedup ratio.

    A minimize gate of 100% or more has no finite speedup and returns ``inf``.
    """
    fraction = min_improvement_pct / 100
    if direction == "maximize":
        return 1 + fraction
    if direction == "minimize":
        return math.inf if fraction >= 1 else 1 / (1 - fraction)
    raise ValueError("Metric direction must be explicit")


def paired_speedups(baseline: list, candidate: list, direction: str) -> list[float]:
    if len(baseline) != len(candidate):
        raise ValueError("Paired statistics need one candidate sample per baseline sample")
    if direction not in ("minimize", "maximize"):
        raise ValueError("Metric direction must be explicit")
    values = [*baseline, *candidate]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Paired statistics need finite positive samples")
    speedups = [b / c if direction == "minimize" else c / b
                for b, c in zip(baseline, candidate)]
    if any(not math.isfinite(s) or s <= 0 for s in speedups):
        raise ValueError("A paired ratio overflowed or underflowed")
    return speedups


def relative_mad(values: list) -> float | None:
    """Median absolute deviation divided by the median, a robust spread indicator."""
    if not values:
        return None
    center = median(values)
    return median(abs(v - center) for v in values) / center


def _percentile(ordered: list, q: float) -> float:
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def bootstrap_median_interval(values: list, *, resamples: int = RESAMPLES,
                              seed: int = SEED) -> list[float]:
    if type(resamples) is not int or resamples < 1 or not values:
        raise ValueError("Bootstrap needs a positive resample count and at least one value")
    rng = random.Random(seed)
    medians = sorted(median(rng.choices(values, k=len(values))) for _ in range(resamples))
    tail = (1 - CONFIDENCE) / 2
    return [_percentile(medians, tail), _percentile(medians, 1 - tail)]


def _finite(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, (list, tuple)):
        return all(_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    return False


def _describe(baseline, candidate, *, direction, min_improvement_pct, point_gate_passed,
              resamples, seed) -> dict:
    speedups = paired_speedups(baseline, candidate, direction)
    gate = gate_speedup(min_improvement_pct, direction)
    report = {
        "status": "available", "pairs": len(speedups), "pair_speedups": speedups,
        "median_speedup": median(speedups) if speedups else None,
        "geomean_speedup": (math.exp(sum(map(math.log, speedups)) / len(speedups))
                            if speedups else None),
        "gate_speedup": gate if math.isfinite(gate) else None,
        "baseline_relative_mad": relative_mad(baseline),
        "candidate_relative_mad": relative_mad(candidate), "interval": None,
    }
    if len(speedups) < MIN_PAIRS:
        return {**report, "status": "insufficient_pairs", "gate_relation": "insufficient_pairs",
                "agrees_with_point_gate": None,
                "reason": f"At least {MIN_PAIRS} repetitions are needed for an interval"}
    low, high = bootstrap_median_interval(speedups, resamples=resamples, seed=seed)
    if not math.isfinite(gate):
        relation = "gate_unreachable"
    elif low > gate:
        relation = "above_gate"
    elif high < gate:
        relation = "below_gate"
    else:
        relation = "straddles_gate"
    return {**report, "interval": [low, high], "gate_relation": relation,
            "excludes_no_change": low > 1 or high < 1,
            "agrees_with_point_gate": point_gate_passed == (relation == "above_gate")}


def paired_statistics(baseline: list, candidate: list, *, direction: str,
                      min_improvement_pct: float, point_gate_passed: bool,
                      resamples: int = RESAMPLES, seed: int = SEED) -> dict:
    """Describe paired samples against the frozen gate without changing any verdict.

    Every returned number is finite so the record stays strict-JSON serializable;
    anything that cannot be computed is reported with ``status="unavailable"``.
    """
    header = {"method": METHOD, "report_only": True, "confidence": CONFIDENCE,
              "coverage": "nominal_uncalibrated",
              "pairing": "kth baseline with kth candidate; AB/BA order alternates by repetition",
              "resamples": resamples, "seed": seed}
    try:
        report = _describe(baseline, candidate, direction=direction,
                           min_improvement_pct=min_improvement_pct,
                           point_gate_passed=point_gate_passed,
                           resamples=resamples, seed=seed)
    except (ArithmeticError, TypeError, ValueError) as error:
        return {**header, "status": "unavailable", "reason": str(error), "interval": None}
    if not _finite(report):
        return {**header, "status": "unavailable",
                "reason": "A derived statistic is not finite", "interval": None}
    return {**header, **report}
