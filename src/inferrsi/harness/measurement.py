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


# Profile evidence and declared mechanisms ---------------------------------------
#
# A measurement script may add per-step ``breakdown`` (region durations in one
# unit) and ``counters`` (work metrics such as kernel launches or DRAM bytes).
# Work metrics are largely independent of clock and thermal state, and region
# shares within one step cancel device-wide fluctuation, so they can explain a
# gain that end-to-end time alone cannot separate from noise. Directions are
# decided only from the paired data; no numeric tolerance is built in.

DIRECTIONS = ("decrease", "increase", "unchanged")


def _numeric_map(value) -> dict | None:
    if not isinstance(value, dict) or not value:
        return None
    if not all(isinstance(k, str) and k and type(v) in (int, float) and math.isfinite(v)
               and v >= 0 for k, v in value.items()):
        return None
    return value


def _paired_change(baseline: list, candidate: list, *, resamples: int, seed: int) -> dict:
    ratios = []
    for b, c in zip(baseline, candidate):
        if b > 0:
            ratios.append(c / b)
        elif c == 0:
            ratios.append(1.0)
        else:
            return {"ratio_median": None, "interval": None, "observed": "increase",
                    "note": "baseline value is zero and candidate value is positive"}
    report = {"ratio_median": median(ratios), "interval": None}
    if len(ratios) < MIN_PAIRS:
        return {**report, "observed": "insufficient_pairs"}
    low, high = bootstrap_median_interval(ratios, resamples=resamples, seed=seed)
    observed = "decrease" if high < 1 else "increase" if low > 1 else "no_clear_change"
    return {**report, "interval": [low, high], "observed": observed}


def _interval_report(values: list, *, resamples: int, seed: int) -> dict:
    report = {"median": median(values), "interval": None}
    if len(values) >= MIN_PAIRS:
        report["interval"] = bootstrap_median_interval(values, resamples=resamples, seed=seed)
    return report


def profile_evidence(baseline_profiles: list, candidate_profiles: list, *,
                     reference_regions=(), resamples: int = RESAMPLES,
                     seed: int = SEED) -> dict:
    """Compare per-repetition region durations and work counters between paired steps.

    ``reference_regions`` are regions the round declares unchanged. Within one step
    they act as an internal clock: dividing another region by them, and reading the
    reference share of the step total, cancels device-wide changes such as clock or
    temperature drift that scale every region of that step together.
    """
    if len(baseline_profiles) != len(candidate_profiles) or not baseline_profiles:
        return {"status": "unavailable", "reason": "Profiles must be paired per repetition"}
    sides = (baseline_profiles, candidate_profiles)
    result = {"status": "available", "pairs": len(baseline_profiles), "regions": {},
              "counters": {}, "reference_regions": [], "share_based_speedup": None}
    for kind in ("breakdown", "counters"):
        maps = [[_numeric_map((p or {}).get(kind)) for p in side] for side in sides]
        if not all(m is not None for side in maps for m in side):
            continue
        shared = sorted(set.intersection(*(set(m) for side in maps for m in side)))
        reference = [r for r in reference_regions if r in shared] if kind == "breakdown" else []
        if kind == "breakdown":
            result["reference_regions"] = reference
        target = result["regions" if kind == "breakdown" else "counters"]
        for name in shared:
            b = [m[name] for m in maps[0]]
            c = [m[name] for m in maps[1]]
            entry = {"baseline_median": median(b), "candidate_median": median(c),
                     **_paired_change(b, c, resamples=resamples, seed=seed), "basis": "raw"}
            clock = [r for r in reference if r != name]
            if clock:
                bn = [m[name] / sum(m[r] for r in clock) for m in maps[0]
                      if sum(m[r] for r in clock) > 0]
                cn = [m[name] / sum(m[r] for r in clock) for m in maps[1]
                      if sum(m[r] for r in clock) > 0]
                if len(bn) == len(cn) == len(b):
                    entry.update(_paired_change(bn, cn, resamples=resamples, seed=seed),
                                 basis="normalized_to_reference_regions")
            if kind == "breakdown":
                totals = [[sum(m.values()) for m in side] for side in maps]
                entry["baseline_share"] = median(v / t for v, t in zip(b, totals[0]) if t > 0)
                entry["candidate_share"] = median(v / t for v, t in zip(c, totals[1]) if t > 0)
            target[name] = entry
        if reference:
            ratios = []
            for mb, mc in zip(*maps):
                ref_b, ref_c = (sum(m[r] for r in reference) for m in (mb, mc))
                tot_b, tot_c = sum(mb.values()), sum(mc.values())
                if min(ref_b, ref_c, tot_b, tot_c) > 0:
                    ratios.append((ref_c / tot_c) / (ref_b / tot_b))
            if len(ratios) == len(maps[0]):
                result["share_based_speedup"] = _interval_report(
                    ratios, resamples=resamples, seed=seed)
    if not result["regions"] and not result["counters"]:
        return {**result, "status": "absent",
                "reason": "No breakdown or counters were present in every measured step"}
    return result if _finite(result) else {"status": "unavailable",
                                           "reason": "A derived profile value is not finite"}


def validate_mechanism(document) -> dict:
    """Validate a declared mechanism: a statement plus checkable expected signatures."""
    if not isinstance(document, dict) or set(document) - {"mechanism", "expect"}:
        raise ValueError("A mechanism declares only 'mechanism' and 'expect'")
    text = document.get("mechanism")
    expect = document.get("expect")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Describe the mechanism that should cause the change")
    if not isinstance(expect, list) or not expect:
        raise ValueError("List at least one expected region or counter signature")
    for item in expect:
        keys = set(item) if isinstance(item, dict) else set()
        kinds = keys & {"region", "counter"}
        if (len(kinds) != 1 or keys - {"region", "counter", "direction"}
                or not isinstance(item[next(iter(kinds))], str)
                or not item[next(iter(kinds))].strip()
                or item.get("direction") not in DIRECTIONS):
            raise ValueError("Each expectation names one region or counter and a direction "
                             "of decrease, increase or unchanged")
    if all(item["direction"] == "unchanged" for item in expect):
        raise ValueError("At least one expectation must predict a change")
    return document


def explain(mechanism: dict | None, evidence: dict) -> dict:
    """Check a declared mechanism against observed profile evidence, without judging prose."""
    if mechanism is None:
        return {"status": "not_declared"}
    checks, missing = [], False
    for item in mechanism["expect"]:
        kind = "region" if "region" in item else "counter"
        table = evidence.get("regions" if kind == "region" else "counters") or {}
        observed = table.get(item[kind], {}).get("observed")
        if observed in (None, "insufficient_pairs"):
            missing = True
        checks.append({"kind": kind, "name": item[kind], "expected": item["direction"],
                       "observed": observed or "missing"})
    report = {"mechanism": mechanism["mechanism"], "checks": checks}
    if any(c["expected"] in ("decrease", "increase") and c["observed"] in ("decrease", "increase")
           and c["observed"] != c["expected"] for c in checks) or any(
            c["expected"] == "unchanged" and c["observed"] in ("decrease", "increase")
            for c in checks):
        return {**report, "status": "contradicted"}
    if missing or evidence.get("status") != "available":
        return {**report, "status": "unverifiable"}
    if all(c["observed"] == c["expected"] or (c["expected"] == "unchanged"
                                              and c["observed"] == "no_clear_change")
           for c in checks):
        return {**report, "status": "explained"}
    return {**report, "status": "unsupported"}
