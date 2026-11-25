"""Pure objective boundaries; these numbers are test controls, never campaign defaults."""

import copy

import pytest

from inferrsi.harness.project_service import better, change, performance, quality_passed


def objective(direction="minimize", kind="relative_percent"):
    return {
        "id": "a",
        "unit": "ms",
        "direction": direction,
        "threshold_type": kind,
        "gain": True,
        "gain_threshold": 4,
        "parent_regression_limit": 3,
        "cumulative_regression_limit": 3,
    }


@pytest.mark.parametrize("direction,sign", [("minimize", -1), ("maximize", 1)])
def test_zero_thresholds_and_both_directions(direction, sign):
    obj = objective(direction)
    assert change(obj, 0, 0) == 0
    with pytest.raises(ValueError, match="Undefined"):
        change(obj, 1, 0)
    for kind in ("absolute", "percentage_point"):
        obj["threshold_type"] = kind
        assert change(obj, 2, 0) == sign * 2
        assert change(obj, 0, 0) == 0
    obj.update(gain_threshold=0, parent_regression_limit=0, cumulative_regression_limit=0)
    config = {"objectives": [obj]}
    assert not performance(
        config, {"values": {"a": 1}}, {"values": {"a": 1}}, {"values": {"a": 1}}
    )["passed"]


def test_combined_gain_and_dual_limits_include_exact_boundary():
    a, b = objective(), objective()
    b["id"] = "b"
    config = {"objectives": [a, b], "ranking": ["a", "b"]}
    base = {"values": {"a": 100, "b": 100}}
    assert performance(config, {"values": {"a": 95, "b": 103}}, base, base)["passed"]
    assert not performance(config, {"values": {"a": 95, "b": 104}}, base, base)["passed"]
    parent = {"values": {"a": 95, "b": 102}}
    assert not performance(config, {"values": {"a": 90, "b": 104}}, parent, base)["passed"]
    assert better(config, {"a": 95, "b": 103}, base["values"])
    assert not better(config, base["values"], base["values"])
    assert not better(config, {"a": 101, "b": 10}, base["values"])


def test_screening_actual_gain_is_not_an_estimated_or_formal_threshold():
    obj = objective()
    config = {"objectives": [obj]}
    reference, measured = {"values": {"a": 100}}, {"values": {"a": 99}}
    assert performance(config, measured, reference, reference, screening=True)["passed"]
    assert not performance(config, measured, reference, reference)["passed"]
    obj["gain_threshold"] = 0
    assert performance(config, measured, reference, reference)["passed"]


def test_quality_requires_reference_and_has_absolute_semantics():
    config = {"quality": {"mode": "absolute", "direction": "maximize", "threshold": 0.9}}
    assert quality_passed(config, 0.9)
    comparison = copy.deepcopy(config)
    comparison["quality"].update(mode="baseline_comparison", tolerance=0)
    with pytest.raises(ValueError, match="Missing compatible"):
        quality_passed(comparison, 0.9)
    assert quality_passed(comparison, 0.9, 0.9)
    assert not quality_passed(comparison, 0.8, 0.9)


@pytest.mark.parametrize("bad", [None, True, float("nan"), float("inf"), -1, 101])
def test_metric_evidence_requires_finite_domain_valid_numbers(bad):
    from inferrsi.harness.project_service import aggregate

    obj = objective()
    obj.update(scenario="s", key="metric", aggregate="mean", domain={"min": 0, "max": 100})
    config = {
        "sampling": {"candidate": {"repetitions": 1}},
        "objectives": [obj],
        "scenarios": [{"id": "s", "workload": "fixed", "requests": 2, "required_successes": 2}],
    }
    doc = {
        "scenarios": {
            "s": {
                "workload": "fixed",
                "requests": 2,
                "successes": 2,
                "metric": bad,
                "units": {"a": "ms"},
            }
        }
    }
    with pytest.raises(ValueError):
        aggregate(config, [doc], "candidate")


@pytest.mark.parametrize(("updates", "error"), [
    ({"baseline_samples": [100, 104]}, "indistinguishable_from_baseline"),
    ({"baseline_samples": [100]}, "repeated baseline"),
    ({"baseline_samples": [True, 100]}, "repeated baseline"),
    ({"attainable_value": None}, "calibrated attainable value"),
    ({"unit": "seconds"}, "not comparable"),
    ({"calibration_evidence": " "}, "calibration evidence"),
    ({"method": "theoretical_peak"}, "measurement or calibrated projection"),
])
def test_unsupported_target_calibration(tmp_path, updates, error):
    from inferrsi.harness.project_objectives import review_targets
    from tests.fixtures.target_review import calibration, write_review

    ctx = {"scope": "test"}
    obj = {**objective(kind="absolute"), "aggregate": "mean", "key": "metric"}
    record = {**calibration("ms", "minimize"), "threshold_type": "absolute",
              "baseline_samples": [100, 100], "attainable_value": 90, **updates}
    path = tmp_path / "goal.json"
    write_review(path, ctx, {"a": record}, {"a": 4})
    with pytest.raises(ValueError, match=error):
        review_targets(path, ctx, [obj])


def test_percentage_point_review_uses_native_units_and_the_service_aggregate(tmp_path):
    from inferrsi.harness.project_objectives import review_targets
    from tests.fixtures.target_review import calibration, write_review

    obj = {**objective("maximize", "percentage_point"), "key": "metric", "unit": "%",
           "aggregate": "mean", "scenario": "a", "domain": {"min": 0, "max": 100}}
    context = {"scope": "test"}
    calibrated = {**calibration("%", "maximize"), "threshold_type": "percentage_point",
                  "aggregate": "mean", "scenario": "a", "baseline_samples": [90, 90, 93],
                  "attainable_value": 95}
    path = tmp_path / "goals.json"
    write_review(path, context, {"a": calibrated}, {"a": 4})
    row = review_targets(path, context, [obj])["objectives"]["a"]
    assert (row["decision"], row["baseline"], row["observed_noise"], row["attainable_gain"]) == (
        "supported", 91, 3, 4,
    )
