"""Paired report-only statistics; every sample below is a synthetic software control."""

import json
import math
import random
from statistics import median

import pytest

from inferrsi.harness import optimization_session
from inferrsi.harness.measurement import (
    MIN_PAIRS,
    explain,
    gate_speedup,
    interval_rank,
    median_interval,
    min_pairs,
    paired_speedups,
    paired_statistics,
    profile_evidence,
    validate_mechanism,
)

BASE = [10.0, 10.1, 9.9, 10.05, 9.95, 10.02]
GAIN = [8.0, 8.1, 7.9, 8.02, 7.98, 8.01]


def report(baseline, candidate, *, direction="minimize", gate_pct=1.0, passed=True, **kwargs):
    return paired_statistics(baseline, candidate, direction=direction,
                             min_improvement_pct=gate_pct, point_gate_passed=passed, **kwargs)


def point_gate(baseline, candidate, gate_pct):
    """The current project.assess rule: independent medians, minimize direction."""
    improvement = (median(baseline) - median(candidate)) / median(baseline) * 100
    return improvement > 0 and improvement >= gate_pct


def test_gate_speedup_matches_improvement_pct_definition():
    assert gate_speedup(10, "maximize") == pytest.approx(1.10)
    # Minimize: a 10% lower latency is a 1/0.9 speedup, not 1.10.
    assert gate_speedup(10, "minimize") == pytest.approx(1 / 0.9)
    assert gate_speedup(0, "minimize") == 1
    assert gate_speedup(100, "minimize") == math.inf
    with pytest.raises(ValueError):
        gate_speedup(1, "sideways")


def test_pair_direction_and_input_validation():
    assert paired_speedups([10, 20], [5, 10], "minimize") == [2.0, 2.0]
    assert paired_speedups([10, 20], [5, 10], "maximize") == [0.5, 0.5]
    for baseline, candidate in (([1, 2], [1]), ([1, 0], [1, 1]), ([1, math.nan], [1, 1])):
        with pytest.raises(ValueError):
            paired_speedups(baseline, candidate, "minimize")


@pytest.mark.parametrize("baseline,candidate", [
    ([10, 10, 10], [9, 9]),            # lost pair
    ([10, 0, 10], [9, 9, 9]),          # zero sample
    ([10, math.nan, 10], [9, 9, 9]),   # non-finite sample
])
def test_invalid_samples_report_unavailable_instead_of_raising(baseline, candidate):
    result = report(baseline, candidate)
    assert result["status"] == "unavailable" and result["interval"] is None
    assert result["report_only"] is True


@pytest.mark.parametrize("baseline,candidate", [
    ([1e-300, 10, 10], [1e300, 5, 5]),   # paired ratio underflows to zero
    ([1e300, 10, 10], [1e-300, 5, 5]),   # paired ratio overflows to infinity
])
def test_ratio_overflow_reports_unavailable_and_stays_strict_json(baseline, candidate):
    result = report(baseline, candidate)
    assert result["status"] == "unavailable"
    json.dumps(result, allow_nan=False)


def test_unreachable_minimize_gate_is_serializable_not_infinite():
    result = report(BASE, [v / 2 for v in GAIN], gate_pct=100, passed=False)
    assert result["gate_speedup"] is None and result["gate_relation"] == "gate_unreachable"
    assert result["agrees_with_point_gate"] is True
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("pairs", [2, 5])
def test_too_few_repetitions_report_no_interval(pairs):
    # Five pairs cannot give a 95% interval: even the extreme pair errs 1/32 > 2.5%.
    result = report(BASE[:pairs], GAIN[:pairs])
    assert result["status"] == "insufficient_pairs" and result["pairs"] == pairs
    assert result["interval"] is None and result["agrees_with_point_gate"] is None


def tail(pairs, rank):
    """P(Bin(pairs, 1/2) <= rank - 1): the chance the rank-th smallest exceeds the median."""
    return sum(math.comb(pairs, k) for k in range(rank)) / 2 ** pairs


@pytest.mark.parametrize("pairs", range(1, 41))
def test_interval_rank_is_the_largest_exact_rank_within_two_and_a_half_percent(pairs):
    rank = interval_rank(pairs)
    if pairs < MIN_PAIRS:
        assert rank is None
        return
    assert tail(pairs, rank) <= 0.025 < tail(pairs, rank + 1)
    values = [float(v) for v in range(pairs)]
    exact = median_interval(values)
    assert exact["interval"] == [values[rank - 1], values[pairs - rank]]
    assert exact["achieved_confidence"] == pytest.approx(1 - 2 * tail(pairs, rank))


def test_exact_ranks_and_minimum_pairs():
    assert MIN_PAIRS == 6 and min_pairs(0.95) == 6
    assert [interval_rank(n) for n in (6, 7, 8, 9, 12, 13, 20)] == [1, 1, 1, 2, 3, 3, 6]
    # Bonferroni over k expectations needs a tail of 0.025 / k on each side.
    assert [min_pairs(1 - 0.05 / k) for k in (1, 2, 3, 4, 6, 7)] == [6, 7, 7, 8, 8, 9]


def test_many_pairs_use_exact_arithmetic_without_overflow():
    # A float 2 ** n overflows near n = 1024; the rank must still be exact and finite.
    for pairs in (1023, 1024, 3000):
        rank = interval_rank(pairs)
        assert rank is not None and 1 < rank < pairs // 2
    evidence = profile_evidence([{"counters": {"x": 10}}] * 1024,
                                [{"counters": {"x": 8}}] * 1024)
    assert evidence["counters"]["x"]["observed"] == "decrease"
    result = report([10.0] * 1024, [8.0] * 1024)
    assert result["status"] == "available" and result["gate_relation"] == "above_gate"
    json.dumps(result, allow_nan=False)


def test_report_only_follows_whether_the_interval_decides():
    assert report(BASE, GAIN)["report_only"] is True
    decided = report(BASE, GAIN, decides=True)
    assert decided["report_only"] is False
    assert decided["method"] == "paired_median_speedup_sign_test_interval"
    assert decided["order_statistic_rank"] == 1
    assert decided["achieved_confidence"] == pytest.approx(1 - 2 / 64)


def test_consistent_real_gain_is_above_gate():
    result = report(BASE, GAIN, gate_pct=5)
    low, high = result["interval"]
    assert low > result["gate_speedup"] and low <= result["median_speedup"] <= high
    assert result["gate_relation"] == "above_gate" and result["excludes_no_change"] is True
    assert result["agrees_with_point_gate"] is True


def test_aa_noise_straddles_gate_even_when_point_estimate_clears_it():
    # A/A control: identical code, noisy alternation. Independent medians differ by
    # more than the 1% gate, so the current point gate passes; the pairs do not.
    baseline = [10.0, 10.6, 9.6, 10.4, 9.9, 10.3]
    candidate = [9.7, 10.2, 9.8, 10.1, 9.75, 10.35]
    assert point_gate(baseline, candidate, 1)
    result = report(baseline, candidate, gate_pct=1, passed=True)
    assert result["gate_relation"] == "straddles_gate"
    assert result["excludes_no_change"] is False
    assert result["agrees_with_point_gate"] is False


def test_pairing_cancels_shared_drift():
    # Both sides slow down 2% per repetition; the true speedup is 1.25 in every pair.
    drift = [1.0 + 0.02 * k for k in range(6)]
    result = report([10.0 * d for d in drift], [8.0 * d for d in drift], gate_pct=10)
    assert result["pair_speedups"] == pytest.approx([1.25] * 6)
    assert result["interval"] == pytest.approx([1.25, 1.25])
    assert result["baseline_relative_mad"] > 0.02


def test_alternating_order_penalty_does_not_create_a_gain():
    # A/A with a 5% penalty for whichever side runs second in a repetition.
    baseline, candidate = [], []
    for k in range(8):
        first, second = 10.0, 10.5
        baseline.append(first if k % 2 == 0 else second)
        candidate.append(second if k % 2 == 0 else first)
    result = report(baseline, candidate, gate_pct=1, passed=False)
    assert result["gate_relation"] != "above_gate"


def test_clear_regression_is_below_gate():
    result = report(BASE, [v * 1.5 for v in GAIN], gate_pct=1, passed=False)
    assert result["gate_relation"] == "below_gate"
    assert result["agrees_with_point_gate"] is True


@pytest.mark.parametrize("noise", ["lognormal", "heavy_tail"])
def test_aa_simulation_paired_false_gains_stay_rare_and_below_point_gate(noise):
    """Ablation: independent medians vs paired interval on simulated A/A campaigns.

    Each campaign has 10 repetitions with a shared random-walk drift, per-sample
    3% noise and, for heavy_tail, a 10% chance of a 1.3x stall. Fixed settings:
    200 campaigns, gate 1%, seed 20261115.
    """
    rng = random.Random(20261115)
    point_false = paired_false = 0
    campaigns = 200
    for index in range(campaigns):
        level, baseline, candidate = 10.0, [], []
        for _ in range(10):
            level *= math.exp(rng.gauss(0, 0.02))

            def sample():
                value = level * math.exp(rng.gauss(0, 0.03))
                if noise == "heavy_tail" and rng.random() < 0.1:
                    value *= 1.3
                return value

            baseline.append(sample())
            candidate.append(sample())
        point_false += point_gate(baseline, candidate, 1)
        result = report(baseline, candidate, gate_pct=1)
        paired_false += result["gate_relation"] == "above_gate"
    assert paired_false / campaigns <= 0.05
    assert paired_false < point_false


@pytest.mark.parametrize("pairs", [6, 7, 10, 13])
def test_aa_pass_rate_at_the_gate_stays_within_the_exact_bound(pairs):
    """A/A with the true median speedup exactly at a 0% gate: PASS is a false gain.

    The exact bound is the binomial tail of the chosen rank (at most 2.5%); the
    simulated rate must not exceed it beyond Monte Carlo error. 4000 campaigns, seed 7.
    """
    rng = random.Random(7)
    campaigns, passes = 4000, 0
    for _ in range(campaigns):
        baseline = [10.0 * math.exp(rng.gauss(0, 0.03)) for _ in range(pairs)]
        candidate = [10.0 * math.exp(rng.gauss(0, 0.03)) for _ in range(pairs)]
        passes += report(baseline, candidate, gate_pct=0)["gate_relation"] == "above_gate"
    bound = tail(pairs, interval_rank(pairs))
    assert bound <= 0.025
    assert passes / campaigns <= bound + 3 * math.sqrt(bound * (1 - bound) / campaigns)


def test_measurement_module_is_part_of_runtime_identity():
    assert "harness/measurement.py" in optimization_session._runtime_identity()


def profiles(rows, jitter=None):
    """Per-repetition profiles; jitter scales every region of a step together."""
    jitter = jitter or [1.0] * len(rows)
    return [{"breakdown": {k: v * g for k, v in r["breakdown"].items()},
             "counters": r.get("counters", {"launches": 10})} for r, g in zip(rows, jitter)]


STEP_B = {"breakdown": {"gemm": 6.0, "norm": 2.0}, "counters": {"launches": 12, "bytes": 900}}
STEP_C = {"breakdown": {"gemm": 6.0, "norm": 1.0}, "counters": {"launches": 8, "bytes": 900}}
JITTER_B = [1.0, 1.08, 0.93, 1.05, 0.97, 1.03, 0.96, 1.01]
JITTER_C = [1.06, 0.94, 1.02, 0.95, 1.09, 0.98, 1.04, 0.99]
N = len(JITTER_B)  # eight pairs: enough for Bonferroni over up to six expectations


def test_reference_regions_cancel_device_wide_jitter():
    evidence = profile_evidence(profiles([STEP_B] * N, JITTER_B),
                                profiles([STEP_C] * N, JITTER_C), reference_regions=["gemm"])
    assert evidence["status"] == "available" and evidence["reference_regions"] == ["gemm"]
    norm = evidence["regions"]["norm"]
    assert norm["basis"] == "normalized_to_reference_regions"
    assert norm["normalized"]["ratio_median"] == pytest.approx(0.5)
    assert norm["observed"] == "decrease"
    assert evidence["share_based_speedup"]["median"] == pytest.approx(8 / 7)
    assert evidence["share_based_speedup"]["interval"] == pytest.approx([8 / 7, 8 / 7])
    assert evidence["counters"]["launches"]["observed"] == "decrease"
    assert evidence["counters"]["bytes"]["observed"] == "no_clear_change"
    # Without a reference the same region is only compared raw, jitter included.
    raw = profile_evidence(profiles([STEP_B] * N, JITTER_B), profiles([STEP_C] * N, JITTER_C))
    assert raw["regions"]["norm"]["basis"] == "raw" and raw["share_based_speedup"] is None


def test_profile_evidence_absent_or_unpaired():
    assert profile_evidence([{}] * 5, [{}] * 5)["status"] == "absent"
    assert profile_evidence([STEP_B], [STEP_C, STEP_C])["status"] == "unavailable"
    few = profile_evidence(profiles([STEP_B] * 2), profiles([STEP_C] * 2))
    assert few["counters"]["launches"]["observed"] == "insufficient_pairs"


MECHANISM = {"mechanism": "Fuse the norm into the GEMM epilogue",
             "expect": [{"region": "norm", "direction": "decrease"},
                        {"region": "gemm", "direction": "unchanged"},
                        {"counter": "launches", "direction": "decrease"}]}


@pytest.mark.parametrize("expect,status", [
    (MECHANISM["expect"], "explained"),
    ([{"region": "norm", "direction": "increase"}], "contradicted"),
    ([{"counter": "bytes", "direction": "decrease"}], "unsupported"),
    ([{"counter": "l2_hits", "direction": "increase"}], "unverifiable"),
    ([{"counter": "launches", "direction": "decrease"},
      {"counter": "bytes", "direction": "unchanged"}], "explained"),
])
def test_explain_classifies_declared_mechanisms(expect, status):
    mechanism = validate_mechanism({"mechanism": "m", "expect": expect})
    reference = [e["region"] for e in expect if "region" in e and e["direction"] == "unchanged"]
    evidence = profile_evidence(profiles([STEP_B] * N, JITTER_B),
                                profiles([STEP_C] * N, JITTER_C), reference_regions=reference,
                                family_size=len(expect))
    assert evidence["confidence"] == pytest.approx(1 - 0.05 / len(expect))
    assert explain(mechanism, evidence)["status"] == status
    assert explain(None, evidence) == {"status": "not_declared"}


def test_unchanged_is_reported_as_not_contradicted_never_confirmed():
    mechanism = validate_mechanism(MECHANISM)
    evidence = profile_evidence(profiles([STEP_B] * N, JITTER_B),
                                profiles([STEP_C] * N, JITTER_C), reference_regions=["gemm"],
                                family_size=3)
    result = explain(mechanism, evidence)
    assert result["status"] == "explained" and result["family_size"] == 3
    assert [c["outcome"] for c in result["checks"]] == [
        "confirmed", "not_contradicted", "confirmed"]


@pytest.mark.parametrize("pairs,family,status", [
    (6, 1, "explained"),       # 95%: rank 1 exists at six pairs
    (6, 2, "unverifiable"),    # 97.5% needs seven pairs
    (7, 2, "explained"),
    (7, 4, "unverifiable"),    # 98.75% needs eight pairs
    (8, 4, "explained"),
])
def test_bonferroni_family_sets_the_pairs_needed(pairs, family, status):
    expect = [{"counter": "launches", "direction": "decrease"}] + [
        {"counter": f"same{k}", "direction": "unchanged"} for k in range(family - 1)]
    rows = [{"breakdown": {"x": 1.0},
             "counters": {"launches": 12, **{f"same{k}": 5 for k in range(family - 1)}}}]
    cand = [{"breakdown": {"x": 1.0},
             "counters": {"launches": 8, **{f"same{k}": 5 for k in range(family - 1)}}}]
    evidence = profile_evidence(rows * pairs, cand * pairs, family_size=family)
    assert evidence["pairs_needed"] == min_pairs(1 - 0.05 / family)
    mechanism = validate_mechanism({"mechanism": "m", "expect": expect})
    assert explain(mechanism, evidence)["status"] == status


def test_evidence_adjusted_for_fewer_expectations_is_not_trusted():
    mechanism = validate_mechanism(MECHANISM)
    evidence = profile_evidence(profiles([STEP_B] * N, JITTER_B),
                                profiles([STEP_C] * N, JITTER_C), reference_regions=["gemm"])
    assert evidence["family_size"] == 1
    assert explain(mechanism, evidence)["status"] == "unverifiable"
    assert profile_evidence([STEP_B], [STEP_C], family_size=0)["status"] == "unavailable"


@pytest.mark.parametrize("document", [
    {"mechanism": "", "expect": [{"region": "a", "direction": "decrease"}]},
    {"mechanism": "m", "expect": []},
    {"mechanism": "m", "expect": [{"region": "a", "direction": "faster"}]},
    {"mechanism": "m", "expect": [{"region": "a", "counter": "b", "direction": "decrease"}]},
    {"mechanism": "m", "expect": [{"region": "a", "direction": "unchanged"}]},
    {"mechanism": "m", "expect": [{"region": "a", "direction": "decrease"}], "extra": 1},
])
def test_invalid_mechanisms_are_rejected(document):
    with pytest.raises(ValueError):
        validate_mechanism(document)


def test_zero_baseline_counter_is_undefined_not_decisive():
    one = profile_evidence([{"counters": {"new_work": 0}}], [{"counters": {"new_work": 1}}])
    assert one["counters"]["new_work"]["observed"] == "insufficient_pairs"
    mixed = profile_evidence([{"counters": {"w": v}} for v in (0, 100, 100, 100, 100, 100)],
                             [{"counters": {"w": v}} for v in (1, 50, 50, 50, 50, 50)])
    assert mixed["counters"]["w"]["observed"] == "undefined"
    mechanism = validate_mechanism({"mechanism": "m", "expect": [
        {"counter": "w", "direction": "increase"}]})
    assert explain(mechanism, mixed)["status"] == "unverifiable"


def test_all_zero_candidate_breakdown_is_reported_not_raised():
    evidence = profile_evidence([{"breakdown": {"only": 2.0}}] * 6,
                                [{"breakdown": {"only": 0.0}}] * 6)
    assert evidence["status"] == "available"
    assert evidence["regions"]["only"]["candidate_share"] is None
    assert evidence["regions"]["only"]["observed"] == "decrease"


def test_references_are_checked_raw_never_against_each_other():
    base = [{"breakdown": {"r1": 2.0, "r2": 2.0, "t": 2.0}}] * 7
    cand = [{"breakdown": {"r1": 1.0, "r2": 1.0, "t": 0.5}}] * 7
    evidence = profile_evidence(base, cand, reference_regions=["r1", "r2"], family_size=3)
    assert evidence["regions"]["r1"]["basis"] == "raw"
    assert evidence["regions"]["r1"]["observed"] == "decrease"
    mechanism = validate_mechanism({"mechanism": "m", "expect": [
        {"region": "r1", "direction": "unchanged"}, {"region": "r2", "direction": "unchanged"},
        {"region": "t", "direction": "decrease"}]})
    assert explain(mechanism, evidence)["status"] == "contradicted"


def test_raw_and_normalized_sign_reversal_is_not_read_as_either_direction():
    """Raw +20% but normalized decrease, while each reference interval crosses 1.

    Two references each dip below 1 in different pairs, so neither is contradicted,
    yet their sum (the per-step reference) rises in every pair. Dividing by it turns
    an absolute increase into an apparent decrease.
    """
    r1 = [0.9, 0.9, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6]
    r2 = [1.6, 1.6, 0.9, 0.9, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6]
    base = [{"breakdown": {"target": 2.0, "r1": 5.0, "r2": 5.0}}] * 10
    cand = [{"breakdown": {"target": 2.4, "r1": 5.0 * a, "r2": 5.0 * b}}
            for a, b in zip(r1, r2)]
    mechanism = validate_mechanism({"mechanism": "m", "expect": [
        {"region": "target", "direction": "decrease"},
        {"region": "r1", "direction": "unchanged"}, {"region": "r2", "direction": "unchanged"}]})
    evidence = profile_evidence(base, cand, reference_regions=["r1", "r2"], family_size=3)
    target = evidence["regions"]["target"]
    assert target["raw"]["observed"] == "increase"
    assert target["normalized"]["observed"] == "decrease"
    assert target["observed"] == "raw_normalized_conflict"
    assert evidence["regions"]["r1"]["observed"] == "no_clear_change"
    assert evidence["regions"]["r2"]["observed"] == "no_clear_change"
    result = explain(mechanism, evidence)
    assert result["checks"][0]["outcome"] == "unverifiable"
    assert result["status"] == "unverifiable"


def test_normalization_still_resolves_a_raw_change_hidden_by_drift():
    # Raw shows no clear change, normalized shows a decrease: not a conflict.
    jitter = [1.0, 1.3, 0.8, 1.25, 0.85, 1.2, 0.9, 1.15]
    base = [{"breakdown": {"t": 2.0, "ref": 6.0}}] * 8
    cand = [{"breakdown": {"t": 1.6 * g, "ref": 6.0 * g}} for g in jitter]
    evidence = profile_evidence(base, cand, reference_regions=["ref"], family_size=2)
    t = evidence["regions"]["t"]
    assert t["raw"]["observed"] == "no_clear_change" and t["observed"] == "decrease"


def test_duplicate_expectations_are_rejected():
    with pytest.raises(ValueError):
        validate_mechanism({"mechanism": "m", "expect": [
            {"region": "a", "direction": "unchanged"}, {"region": "a", "direction": "decrease"}]})
