"""Paired report-only statistics; every sample below is a synthetic software control."""

import json
import math
import random
from statistics import median

import pytest

from inferrsi.harness import optimization_session
from inferrsi.harness.measurement import (
    bootstrap_median_interval,
    gate_speedup,
    paired_speedups,
    paired_statistics,
)

BASE = [10.0, 10.1, 9.9, 10.05, 9.95]


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
    result = report(BASE, [5.0, 5.1, 4.9, 5.02, 4.98], gate_pct=100, passed=False)
    assert result["gate_speedup"] is None and result["gate_relation"] == "gate_unreachable"
    assert result["agrees_with_point_gate"] is True
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("pairs", [2, 4])
def test_too_few_repetitions_report_no_interval(pairs):
    # Below five pairs the simulated coverage of the nominal 95% interval is ~75%.
    result = report(BASE[:pairs], [8.0, 8.1, 7.9, 8.05][:pairs])
    assert result["status"] == "insufficient_pairs" and result["pairs"] == pairs
    assert result["interval"] is None and result["agrees_with_point_gate"] is None


def test_interval_is_deterministic_for_the_recorded_seed():
    values = [1.02, 0.99, 1.05, 1.01, 0.97, 1.03]
    assert bootstrap_median_interval(values, seed=7) == bootstrap_median_interval(values, seed=7)
    result = report([10.0] * 6, [10 / v for v in values])
    assert result["seed"] == 0 and result["resamples"] == 10_000


def test_consistent_real_gain_is_above_gate():
    baseline = [10.0, 10.1, 9.9, 10.05, 9.95]
    candidate = [8.0, 8.1, 7.9, 8.02, 7.98]
    result = report(baseline, candidate, gate_pct=5)
    low, high = result["interval"]
    assert low > result["gate_speedup"] and low <= result["median_speedup"] <= high
    assert result["gate_relation"] == "above_gate" and result["excludes_no_change"] is True
    assert result["agrees_with_point_gate"] is True


def test_aa_noise_straddles_gate_even_when_point_estimate_clears_it():
    # A/A control: identical code, noisy alternation. Independent medians differ by
    # more than the 1% gate, so the current point gate passes; the pairs do not.
    baseline = [10.0, 10.6, 9.6, 10.4, 9.9]
    candidate = [9.7, 10.2, 9.8, 10.1, 9.75]
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
    result = report(BASE, [12.0, 12.1, 11.9, 12.02, 11.98], gate_pct=1, passed=False)
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
        result = report(baseline, candidate, gate_pct=1, resamples=1000, seed=index)
        paired_false += result["gate_relation"] == "above_gate"
    assert paired_false / campaigns <= 0.05
    assert paired_false < point_false


def test_measurement_module_is_part_of_runtime_identity():
    assert "harness/measurement.py" in optimization_session._runtime_identity()


@pytest.mark.parametrize("resamples", [0, -1, 1.5])
def test_invalid_resample_count_reports_unavailable(resamples):
    result = report(BASE, [8.0, 8.1, 7.9, 8.02, 7.98], resamples=resamples)
    assert result["status"] == "unavailable" and result["interval"] is None
