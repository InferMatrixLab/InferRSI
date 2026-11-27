"""Paired statistics for alternating baseline/candidate measurements.

The project protocol alternates AB/BA order inside each repetition, so the k-th
baseline and k-th candidate sample share one repetition. Their per-pair ratio
cancels drift shared within a repetition, which independent per-side medians
retain. By default this module only describes retained samples; the caller-frozen
``--decision paired`` switch is the only path on which its interval decides a
verdict, and the record then says ``report_only: false``.

The estimand is the median per-repetition speedup. Its interval is the exact
distribution-free order-statistic interval for a median (the inverted sign test):
with n independent pairs drawn from a continuous distribution, the j-th smallest
pair lies above the true median with probability P(Bin(n, 1/2) <= j - 1). The rank
j is the largest one keeping that tail at or below (1 - confidence) / 2, so each
side errs at most 2.5% for a 95% interval and the achieved confidence is recorded.
No rank satisfies this below MIN_PAIRS (six at 95%), so no interval is reported.
Repetitions are assumed independent; pairing cannot remove contention shared by
both sides of one pair and does not qualify the environment.
"""

import math
from fractions import Fraction
from statistics import median

METHOD = "paired_median_speedup_sign_test_interval"
CONFIDENCE = 0.95


def interval_rank(pairs: int, confidence: float = CONFIDENCE) -> int | None:
    """Largest order-statistic rank whose one-sided binomial tail fits the confidence."""
    if type(pairs) is not int or pairs < 1 or not 0 < confidence < 1:
        return None
    # Exact rational comparison: a float 2 ** pairs overflows near a thousand pairs.
    allowed = (1 - Fraction(confidence)) / 2 * 2 ** pairs
    rank, tail = None, 0
    for k in range(pairs):
        tail += math.comb(pairs, k)
        if tail > allowed:
            break
        rank = k + 1
    return rank


def min_pairs(confidence: float = CONFIDENCE) -> int:
    """Fewest independent pairs for which an exact interval exists at this confidence."""
    pairs = 1
    while interval_rank(pairs, confidence) is None:
        pairs += 1
    return pairs


MIN_PAIRS = min_pairs()


def median_interval(values: list, confidence: float = CONFIDENCE) -> dict | None:
    """Exact order-statistic interval for the median, or None when too few values."""
    pairs = len(values)
    rank = interval_rank(pairs, confidence)
    if rank is None:
        return None
    ordered = sorted(values)
    tail = Fraction(sum(math.comb(pairs, k) for k in range(rank)), 2 ** pairs)
    return {"interval": [ordered[rank - 1], ordered[pairs - rank]], "rank": rank,
            "achieved_confidence": float(1 - 2 * tail)}


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


def _describe(baseline, candidate, *, direction, min_improvement_pct,
              point_gate_passed) -> dict:
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
    exact = median_interval(speedups)
    if exact is None:
        return {**report, "status": "insufficient_pairs", "gate_relation": "insufficient_pairs",
                "agrees_with_point_gate": None,
                "reason": f"At least {MIN_PAIRS} repetitions are needed for an interval"}
    low, high = exact["interval"]
    if not math.isfinite(gate):
        relation = "gate_unreachable"
    elif low > gate:
        relation = "above_gate"
    elif high < gate:
        relation = "below_gate"
    else:
        relation = "straddles_gate"
    return {**report, "interval": [low, high], "order_statistic_rank": exact["rank"],
            "achieved_confidence": exact["achieved_confidence"], "gate_relation": relation,
            "excludes_no_change": low > 1 or high < 1,
            "agrees_with_point_gate": point_gate_passed == (relation == "above_gate")}


def paired_statistics(baseline: list, candidate: list, *, direction: str,
                      min_improvement_pct: float, point_gate_passed: bool,
                      decides: bool = False) -> dict:
    """Describe paired samples against the frozen gate.

    ``decides`` records whether the caller uses this interval for the verdict; the
    statistics themselves are identical either way. Every returned number is finite
    so the record stays strict-JSON serializable; anything that cannot be computed is
    reported with ``status="unavailable"``.
    """
    header = {"method": METHOD, "report_only": not decides, "confidence": CONFIDENCE,
              "coverage": "exact_one_sided_bound_for_independent_continuous_pairs",
              "pairing": "kth baseline with kth candidate; AB/BA order alternates by repetition"}
    try:
        report = _describe(baseline, candidate, direction=direction,
                           min_improvement_pct=min_improvement_pct,
                           point_gate_passed=point_gate_passed)
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


def _paired_change(baseline: list, candidate: list, *, confidence: float) -> dict:
    """Paired ratio direction; a zero baseline makes the ratio undefined, never decisive."""
    if interval_rank(len(baseline), confidence) is None:
        return {"ratio_median": None, "interval": None, "observed": "insufficient_pairs",
                "note": f"At least {min_pairs(confidence)} pairs are needed at this confidence"}
    if any(b <= 0 for b in baseline):
        return {"ratio_median": None, "interval": None, "observed": "undefined",
                "note": "A zero baseline value has no paired ratio"}
    ratios = [c / b for b, c in zip(baseline, candidate)]
    low, high = median_interval(ratios, confidence)["interval"]
    # no_clear_change means only that no change was detected; it is not evidence that
    # the value stayed the same, because no equivalence margin is defined.
    observed = "decrease" if high < 1 else "increase" if low > 1 else "no_clear_change"
    return {"ratio_median": median(ratios), "interval": [low, high], "observed": observed}


def _shares(values: list, totals: list) -> float | None:
    shares = [v / t for v, t in zip(values, totals) if t > 0]
    return median(shares) if len(shares) == len(values) else None


def profile_evidence(baseline_profiles: list, candidate_profiles: list, *,
                     reference_regions=(), family_size: int = 1) -> dict:
    """Compare per-repetition region durations and work counters between paired steps.

    ``family_size`` is the number of declared expectations judged together. Each
    region and counter interval uses the Bonferroni confidence 1 - (1 - CONFIDENCE) /
    family_size, so the chance that any declared check is wrong by noise alone stays
    at or below 1 - CONFIDENCE; too few pairs for that confidence is reported as
    ``insufficient_pairs``. Every region and counter is compared raw.
    ``reference_regions`` are regions the round declares unchanged; they are an
    assumption, not a conclusion. Other regions are additionally compared after
    dividing by the reference total of the same step, which cancels a change that
    scales every region of that step by the same factor. References themselves are
    only ever checked raw, against each other never.
    """
    if len(baseline_profiles) != len(candidate_profiles) or not baseline_profiles:
        return {"status": "unavailable", "reason": "Profiles must be paired per repetition"}
    sides = (baseline_profiles, candidate_profiles)
    if type(family_size) is not int or family_size < 1:
        return {"status": "unavailable", "reason": "family_size must be a positive integer"}
    confidence = 1 - (1 - CONFIDENCE) / family_size
    result = {"status": "available", "pairs": len(baseline_profiles), "regions": {},
              "counters": {}, "reference_regions": [], "share_based_speedup": None,
              "method": METHOD, "family_size": family_size, "confidence": confidence,
              "adjustment": "bonferroni_over_declared_expectations",
              "pairs_needed": min_pairs(confidence)}
    for kind in ("breakdown", "counters"):
        maps = [[_numeric_map((p or {}).get(kind)) for p in side] for side in sides]
        if not all(m is not None for side in maps for m in side):
            continue
        shared = sorted(set.intersection(*(set(m) for side in maps for m in side)))
        target = result["regions" if kind == "breakdown" else "counters"]
        reference = [r for r in dict.fromkeys(reference_regions) if r in shared] if (
            kind == "breakdown") else []
        clock = [[sum(m[r] for r in reference) for m in side] for side in maps]
        usable_clock = bool(reference) and min(min(side) for side in clock) > 0
        totals = [[sum(m.values()) for m in side] for side in maps]
        for name in shared:
            b = [m[name] for m in maps[0]]
            c = [m[name] for m in maps[1]]
            raw = _paired_change(b, c, confidence=confidence)
            entry = {"baseline_median": median(b), "candidate_median": median(c),
                     "raw": raw, "observed": raw["observed"], "basis": "raw"}
            if usable_clock and name not in reference:
                normalized = _paired_change([v / k for v, k in zip(b, clock[0])],
                                            [v / k for v, k in zip(c, clock[1])],
                                            confidence=confidence)
                observed = normalized["observed"]
                if {observed, raw["observed"]} == {"decrease", "increase"}:
                    # Opposite definite directions: the absolute and the relative-to-
                    # reference change disagree. No declaration predicts a relative
                    # effect, so neither direction may be read as the result.
                    observed = "raw_normalized_conflict"
                entry.update(normalized=normalized, observed=observed,
                             basis="normalized_to_reference_regions")
            if kind == "breakdown":
                entry["baseline_share"] = _shares(b, totals[0])
                entry["candidate_share"] = _shares(c, totals[1])
            target[name] = entry
        if kind == "breakdown":
            result["reference_regions"] = reference
            if usable_clock and min(min(side) for side in totals) > 0:
                ratios = [(kc / tc) / (kb / tb) for kb, tb, kc, tc in zip(
                    clock[0], totals[0], clock[1], totals[1])]
                exact = median_interval(ratios)  # report-only, never judged: CONFIDENCE
                report = {"median": median(ratios),
                          "interval": exact["interval"] if exact else None}
                result["share_based_speedup"] = report
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
    names = [("region" if "region" in item else "counter",
              item.get("region") or item.get("counter")) for item in expect]
    if len(names) != len(set(names)):
        raise ValueError("Declare each region or counter once")
    return document


def _check_outcome(expected: str, observed: str) -> str:
    if observed not in ("decrease", "increase", "no_clear_change"):
        return "unverifiable"
    if expected == "unchanged":
        # Only "no detected change": without an equivalence margin this never proves
        # that the value stayed the same, so it is reported as not contradicted.
        return "not_contradicted" if observed == "no_clear_change" else "contradicted"
    if observed == expected:
        return "confirmed"
    return "not_shown" if observed == "no_clear_change" else "contradicted"


def explain(mechanism: dict | None, evidence: dict) -> dict:
    """Check a declared mechanism against observed profile evidence, without judging prose.

    ``explained`` needs every predicted change confirmed and no declared-unchanged item
    contradicted, with the evidence adjusted for at least as many expectations as were
    declared. A declared-unchanged item is never confirmed, only not contradicted.
    """
    if mechanism is None:
        return {"status": "not_declared"}
    checks = []
    for item in mechanism["expect"]:
        kind = "region" if "region" in item else "counter"
        table = evidence.get("regions" if kind == "region" else "counters") or {}
        observed = table.get(item[kind], {}).get("observed") or "missing"
        checks.append({"kind": kind, "name": item[kind], "expected": item["direction"],
                       "observed": observed,
                       "outcome": _check_outcome(item["direction"], observed)})
    report = {"mechanism": mechanism["mechanism"], "checks": checks,
              "family_size": evidence.get("family_size"),
              "confidence": evidence.get("confidence")}
    outcomes = {c["outcome"] for c in checks}
    adjusted = (type(evidence.get("family_size")) is int
                and evidence["family_size"] >= len(checks))
    if evidence.get("status") == "available" and adjusted and "contradicted" in outcomes:
        return {**report, "status": "contradicted"}
    if evidence.get("status") != "available" or not adjusted or "unverifiable" in outcomes:
        return {**report, "status": "unverifiable"}
    if "not_shown" in outcomes:
        return {**report, "status": "unsupported"}
    return {**report, "status": "explained"}
