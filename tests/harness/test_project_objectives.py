"""Pure objective boundaries; these numbers are test controls, never campaign defaults."""

import copy
import json

import pytest

from inferrsi.harness import evaluator
from inferrsi.harness.evaluator import service_evidence


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


@pytest.mark.parametrize(("mode", "limit", "verdict"), [
    ("absolute", 100, "PASS"),
    ("absolute", 99, "FAIL"),
    ("relative_improvement_pct", 1, "FAIL"),
])
def test_service_gate_replays_frozen_final_target(tmp_path, mode, limit, verdict):
    metric = dict(objective(), key="latency", aggregate="median", scenario="case",
                  domain={"min": 0, "max": 200})
    config = {
        "objectives": [metric], "ranking": ["a"],
        "sampling": {"final": {"warmups": 0, "repetitions": 1}},
        "scenarios": [
            {"id": "case", "workload": "fixture", "requests": 1, "required_successes": 1},
        ],
        "quality": {
            "mode": "absolute", "direction": "minimize", "threshold": 1, "key": "errors",
            "dataset": "fixture", "scorer": "test-scorer", "samples": 1, "unit": "%",
        },
    }
    plan = {"evaluation_settings": config,
            "performance_target": {"target_kind": mode, "target_value": limit}}
    measure = {"scenarios": {"case": {
        "workload": "fixture", "requests": 1, "successes": 1, "units": {"a": "ms"}, "latency": 100,
    }}}
    measured = evaluator.aggregate_service_measurements(config, [measure], "final")
    initial = {"measurements": measured, "quality_score": 0.5}
    record = {
        "path": "final/attempt", "role": "final", "parent": None, "initial": initial,
        "revision": "fixture", "attempt_id": "final", "conditions": {"effective_config": {}},
    }
    binding = {key: record[key] for key in ("revision", "attempt_id", "conditions")}
    binding.update(service_id="service", run_id="run", effective_config={})

    def write(path, document):
        target = tmp_path / record["path"] / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document), encoding="utf-8")

    def stage(name, **document):
        write(f"execution/{name}/result.json", dict(document, binding=binding, status="completed"))

    write("request.json", binding)
    write("effective-config.json", {})
    write("service/owner.json", dict(binding, cwd="fixture", pid=123))
    stage("precheck", passed=True)
    stage("ready", ready=True, ownership="local_process_domain", owner_pid=123,
          loaded_root="fixture", loaded_revision=record["revision"])
    stage("measure-001", **measure)

    gate = evaluator.service_trial_gate(plan, record, measured)
    decision = evaluator.service_measurement_decision("final", None, gate, config["quality"])
    score = None
    if decision.assessment is None:
        receipt = {"errors": 0.005, "unit": "fraction", "dataset": "fixture",
                   "scorer": "test-scorer", "samples": 1}
        stage("quality", **receipt)
        score = evaluator.service_quality_score(config, receipt)
        quality_ok = evaluator.service_quality_passed(config, score, initial["quality_score"])
        decision = evaluator.service_quality_decision("final", gate, quality_ok)
    assert decision.assessment["verdict"] == verdict
    record.update(assessment=decision.assessment, execution={
        "binding": binding, "measurements": measured, "quality_score": score,
    })
    assert service_evidence.evaluation_reason(tmp_path, plan, record) is None
    record["assessment"]["performance"]["passed"] = verdict != "PASS"
    assert service_evidence.evaluation_reason(tmp_path, plan, record) == (
        "unverifiable_evaluation_evidence"
    )


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
