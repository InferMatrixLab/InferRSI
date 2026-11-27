"""Pure objective boundaries; these numbers are test controls, never campaign defaults."""

import copy
import json

import pytest

from inferrsi.harness import evaluator
from inferrsi.harness.evaluator import _service_evidence


def test_service_decisions_use_the_recorded_role_and_performance_gate():
    gate = {"passed": True}
    quality = {"reference_path": "quality/baseline.json"}
    baseline = evaluator.service_measurement_decision("baseline", None, gate, quality)
    candidate = evaluator.service_measurement_decision("candidate", None, gate, quality)
    assert baseline.assessment is candidate.assessment is None
    assert baseline.quality_reference == quality["reference_path"]
    assert candidate.quality_reference is None

    parent = evaluator.service_measurement_decision("baseline", "parent", gate, quality)
    assert parent.assessment["reason"] == "performance_reference_refreshed"
    assert parent.assessment["eligible"] is False
    assert parent.skipped == ((("quality", "profile"), "performance_reference_only"),)

    missed = evaluator.service_measurement_decision("candidate", None, {"passed": False}, quality)
    assert missed.assessment["verdict"] == "FAIL"
    assert missed.skipped == ((("quality",), "performance_gate_not_met"),)
    assert evaluator.service_profile_eligible(missed.assessment["reason"])
    rejected = evaluator.service_quality_decision("candidate", gate, False)
    assert rejected.skipped == ((("profile",), "quality_gate_not_met"),)
    assert not evaluator.service_profile_eligible(rejected.assessment["reason"])


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
    assert evaluator.service_metric_change(obj, 0, 0) == 0
    with pytest.raises(ValueError, match="Undefined"):
        evaluator.service_metric_change(obj, 1, 0)
    for kind in ("absolute", "percentage_point"):
        obj["threshold_type"] = kind
        assert evaluator.service_metric_change(obj, 2, 0) == sign * 2
        assert evaluator.service_metric_change(obj, 0, 0) == 0
    obj.update(gain_threshold=0, parent_regression_limit=0, cumulative_regression_limit=0)
    config = {"objectives": [obj]}
    assert not evaluator.assess_service_performance(
        config, {"values": {"a": 1}}, {"values": {"a": 1}}, {"values": {"a": 1}}
    )["passed"]


def test_combined_gain_and_dual_limits_include_exact_boundary():
    a, b = objective(), objective()
    b["id"] = "b"
    config = {"objectives": [a, b], "ranking": ["a", "b"]}
    base = {"values": {"a": 100, "b": 100}}
    assert evaluator.assess_service_performance(
        config, {"values": {"a": 95, "b": 103}}, base, base
    )["passed"]
    assert not evaluator.assess_service_performance(
        config, {"values": {"a": 95, "b": 104}}, base, base
    )["passed"]
    parent = {"values": {"a": 95, "b": 102}}
    assert not evaluator.assess_service_performance(
        config, {"values": {"a": 90, "b": 104}}, parent, base
    )["passed"]
    assert evaluator.prefer_service_measurements(config, {"a": 95, "b": 103}, base["values"])
    assert not evaluator.prefer_service_measurements(config, base["values"], base["values"])
    assert not evaluator.prefer_service_measurements(config, {"a": 101, "b": 10}, base["values"])


@pytest.mark.parametrize(("kind", "limit", "passed"), [
    ("absolute", 110, True),
    ("absolute", 95, False),
    ("relative_improvement_pct", 1, False),
])
def test_service_final_target_replays_without_a_comparison_parent(tmp_path, kind, limit, passed):
    obj = dict(objective(), scenario="workload", key="metric", aggregate="median",
               domain={"min": 0, "max": 1000})
    config = {
        "objectives": [obj], "ranking": ["a"],
        "sampling": {"final": {"warmups": 0, "repetitions": 1}},
        "scenarios": [
            {"id": "workload", "workload": "fixture", "requests": 1, "required_successes": 1},
        ],
        "quality": {"mode": "absolute", "direction": "minimize", "threshold": 1,
                    "key": "score", "dataset": "fixture", "scorer": "exact", "samples": 1,
                    "unit": "%"},
    }
    plan = {"evaluation_settings": config,
            "performance_target": {"target_kind": kind, "target_value": limit}}
    measured = {"values": {"a": 100}, "samples": {"a": [100]}}
    binding = {"attempt_id": "attempt", "revision": "revision", "service_id": "service",
               "run_id": "run", "conditions": {"effective_config": {}}, "effective_config": {}}
    final = {**binding, "role": "final", "parent": None, "path": "final/attempt",
             "initial": {"measurements": measured, "quality_score": 0.5}}
    gate = evaluator.assess_service_attempt_performance(plan, final, measured)
    assert gate["passed"] is passed
    decision = evaluator.service_measurement_decision("final", None, gate, config["quality"])

    def retain(path, **data):
        target = tmp_path / final["path"] / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding="utf-8")

    retain("request.json", **binding)
    retain("effective-config.json")
    retain("service/owner.json", **binding, pid=123, cwd="fixture")
    retain("execution/precheck/result.json", status="completed", passed=True)
    retain("execution/ready/result.json", binding=binding, status="completed", ready=True,
           ownership="local_process_domain", owner_pid=123, loaded_root="fixture",
           loaded_revision=binding["revision"])
    retain("execution/measure-001/result.json", binding=binding, status="completed",
           scenarios={
               "workload": {"workload": "fixture", "requests": 1, "successes": 1,
                            "metric": 100, "units": {"a": "ms"}},
           })

    quality_score = None
    if passed:
        assert decision.assessment is None
        retain("execution/quality/result.json", binding=binding, status="completed",
               dataset="fixture", scorer="exact", samples=1, unit="fraction", score=0.005)
        quality_score = 0.5
        decision = evaluator.service_quality_decision("final", gate, True)
        assert decision.assessment["verdict"] == "PASS"
    else:
        assert decision.assessment["reason"] == "final_performance_target_not_met"
    final.update(execution={"binding": binding, "measurements": measured,
                            "quality_score": quality_score}, assessment=decision.assessment)
    assert _service_evidence.evaluation_reason(tmp_path, plan, final) is None
    final["assessment"]["performance"]["passed"] = not passed
    assert _service_evidence.evaluation_reason(
        tmp_path, plan, final
    ) == "unverifiable_evaluation_evidence"


def test_screening_actual_gain_is_not_an_estimated_or_formal_threshold():
    obj = objective()
    config = {"objectives": [obj]}
    reference, measured = {"values": {"a": 100}}, {"values": {"a": 99}}
    assert evaluator.assess_service_performance(
        config, measured, reference, reference, screening=True
    )["passed"]
    assert not evaluator.assess_service_performance(config, measured, reference, reference)[
        "passed"
    ]
    obj["gain_threshold"] = 0
    assert evaluator.assess_service_performance(config, measured, reference, reference)["passed"]


def test_quality_requires_reference_and_has_absolute_semantics():
    config = {"quality": {"mode": "absolute", "direction": "maximize", "threshold": 0.9}}
    assert evaluator.service_quality_passed(config, 0.9)
    comparison = copy.deepcopy(config)
    comparison["quality"].update(mode="baseline_comparison", tolerance=0)
    with pytest.raises(ValueError, match="Missing compatible"):
        evaluator.service_quality_passed(comparison, 0.9)
    assert evaluator.service_quality_passed(comparison, 0.9, 0.9)
    assert not evaluator.service_quality_passed(comparison, 0.8, 0.9)


@pytest.mark.parametrize("bad", [None, True, float("nan"), float("inf"), -1, 101])
def test_metric_evidence_requires_finite_domain_valid_numbers(bad):
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
        evaluator.aggregate_service_measurements(config, [doc], "candidate")
