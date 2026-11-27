"""Decide service stages from frozen rules and already collected receipts."""

from dataclasses import dataclass
from decimal import Decimal
from statistics import mean, median

from ..records import service_io
from ._project import meets_target, quality_score_in_unit


def _metric_value(document, key):
    for part in key.split("."):
        if not isinstance(document, dict) or part not in document:
            raise ValueError(f"Missing metric: {key}")
        document = document[part]
    return document


def aggregate_service_measurements(settings, documents, role):
    if len(documents) != settings["sampling"][role]["repetitions"]:
        raise ValueError("Incomplete performance repetitions")
    samples = {obj["id"]: [] for obj in settings["objectives"]}
    for document in documents:
        for scenario in settings["scenarios"]:
            result = document.get("scenarios", {}).get(scenario["id"], {})
            if (
                result.get("workload") != scenario["workload"]
                or type(result.get("requests")) is not int
                or result["requests"] != scenario["requests"]
                or type(result.get("successes")) is not int
                or not scenario["required_successes"] <= result["successes"] <= (result["requests"])
            ):
                raise ValueError("Incomplete or incompatible scenario requests")
        for obj in settings["objectives"]:
            result = document["scenarios"][obj["scenario"]]
            metric = _metric_value(result, obj["key"])
            if (
                result.get("units", {}).get(obj["id"]) != obj["unit"]
                or not service_io.finite_number(metric)
                or not (obj["domain"]["min"] <= metric <= obj["domain"]["max"])
            ):
                raise ValueError(f"Invalid metric domain or unit: {obj['id']}")
            samples[obj["id"]].append(metric)
    aggregates = {
        obj["id"]: (median if obj["aggregate"] == "median" else mean)(samples[obj["id"]])
        for obj in settings["objectives"]
    }
    if not all(service_io.finite_number(v) for v in aggregates.values()):
        raise ValueError("Nonfinite aggregate")
    return {"values": aggregates, "samples": samples}


def service_metric_change(obj, candidate, reference):
    sign = 1 if obj["direction"] == "maximize" else -1
    delta = sign * (candidate - reference)
    if obj["threshold_type"] == "relative_percent":
        if reference == 0:
            if candidate != 0:
                raise ValueError(f"Undefined relative change from zero: {obj['id']}")
            return 0
        delta = 100 * delta / abs(reference)
    if not service_io.finite_number(delta):
        raise ValueError("Nonfinite derived change")
    return delta


def assess_service_performance(settings, measured, parent, initial, *, screening=False,
                               target=None, target_failure="performance_gate_not_met"):
    metrics, limits, gain, actual_gain = {}, True, False, False
    objectives = settings["objectives"] if parent is not None else ()
    for obj in objectives:
        name = obj["id"]
        p = service_metric_change(obj, measured["values"][name], parent["values"][name])
        b = service_metric_change(obj, measured["values"][name], initial["values"][name])
        bounded = p >= -obj["parent_regression_limit"] and b >= -obj["cumulative_regression_limit"]
        improved = obj["gain"] and p > 0
        metrics[name] = {
            "value": measured["values"][name],
            "unit": obj["unit"],
            "parent_change": p,
            "initial_change": b,
            "limits_passed": bounded,
            "gain_passed": improved and p >= obj["gain_threshold"],
            "thresholds": {
                key: obj[key]
                for key in (
                    "threshold_type",
                    "gain_threshold",
                    "parent_regression_limit",
                    "cumulative_regression_limit",
                )
            },
        }
        limits &= bounded
        actual_gain |= improved
        gain |= metrics[name]["gain_passed"]
    passed = parent is None or (limits and (actual_gain if screening else gain))
    reason = "performance_gate_satisfied" if passed else "performance_gate_not_met"
    if passed and target:
        name = settings["ranking"][0]
        objective = next(obj for obj in settings["objectives"] if obj["id"] == name)
        passed = meets_target(target, baseline=initial["values"][name],
                              candidate=measured["values"][name], direction=objective["direction"])
        if passed is None:
            raise ValueError("Undefined relative performance target against the baseline")
        if not passed:
            reason = target_failure
    return {"passed": passed, "metrics": metrics, "reason": reason}


def assess_service_attempt_performance(plan, attempt, measured):
    """Apply the frozen gates identically during execution and evidence replay."""
    role = attempt["role"]
    target = None
    failure = "performance_gate_not_met"
    if role == "candidate" and "candidate_min_improvement_pct" in plan:
        target = {"target_kind": "relative_improvement_pct",
                  "target_value": plan["candidate_min_improvement_pct"]}
    elif role == "final":
        target = plan.get("performance_target")
        failure = "final_performance_target_not_met"
    parent = attempt["parent"]
    if parent is None and target is None:
        return {"passed": True, "metrics": {}}
    return assess_service_performance(
        plan["evaluation_settings"], measured, None if parent is None else parent["measurements"],
        attempt["initial"]["measurements"], target=target, target_failure=failure,
    )


def prefer_service_measurements(settings, left, right):
    by_id = {obj["id"]: obj for obj in settings["objectives"]}
    for name in settings["ranking"]:
        if left[name] != right[name]:
            return (
                left[name] < right[name]
                if by_id[name]["direction"] == "minimize"
                else left[name] > right[name]
            )
    return False


def service_quality_score(settings, document):
    config = settings["quality"]
    if document.get("dataset") != config["dataset"] or document.get("scorer") != config["scorer"]:
        raise ValueError("Incompatible quality dataset/scorer")
    score = _metric_value(document, config["key"])
    if (
        not service_io.finite_number(score)
        or type(document.get("samples")) is not int
        or document["samples"] != config["samples"]
    ):
        raise ValueError("Missing numerical quality evidence")
    # Retained pre-intake plans used scores in the scorer's native scale.
    if "unit" not in config:
        return score
    return quality_score_in_unit(score, document.get("unit"), config["unit"])


def service_quality_passed(settings, score, reference=None):
    config = settings["quality"]
    sign = 1 if config["direction"] == "maximize" else -1
    if config["mode"] == "absolute":
        return sign * (score - config["threshold"]) >= 0
    if reference is None or not service_io.finite_number(reference):
        raise ValueError("Missing compatible baseline quality reference")
    if "unit" not in config:
        return sign * (score - reference) >= -config["tolerance"]
    delta = Decimal(str(score)) - Decimal(str(reference))
    return sign * delta >= -Decimal(str(config["tolerance"]))


def service_assessment(verdict, reason, **fields):
    return {
        "status": "infrastructure_failure" if verdict == "INCONCLUSIVE" else "completed",
        "verdict": verdict,
        "eligible": verdict == "PASS",
        "reason": reason,
        **fields,
    }


def service_ready(ready, *, revision, pid):
    return (
        ready.get("ready") is True
        and ready.get("ownership") == "local_process_domain"
        and ready.get("owner_pid") == pid
        and ready.get("loaded_revision") == revision
    )


@dataclass(frozen=True)
class ServiceStageDecision:
    """Ordered groups of skipped steps, followed by a verdict or a quality evidence request."""

    assessment: dict | None
    skipped: tuple[tuple[tuple[str, ...], str], ...] = ()
    quality_reference: str | None = None


def service_precheck_passed(receipt):
    if receipt.get("status") == "candidate_failure" or receipt.get("passed") is False:
        return False
    if receipt.get("passed") is not True:
        raise ValueError("Missing functional/numerical check evidence")
    return True


def service_measurement_decision(role, reference_kind, gate, quality):
    if not gate["passed"]:
        skipped = ((("quality",), "performance_gate_not_met"),)
        if role != "candidate":
            skipped += ((("profile",), "not_required"),)
        reason = gate.get("reason", "performance_gate_not_met")
        return ServiceStageDecision(
            service_assessment("FAIL", reason, performance=gate),
            skipped,
        )
    if reference_kind == "parent":
        return ServiceStageDecision(
            service_assessment(
                "PASS", "performance_reference_refreshed", performance=gate, eligible=False
            ),
            ((("quality", "profile"), "performance_reference_only"),),
        )
    reference = quality.get("reference_path") if role == "baseline" else None
    return ServiceStageDecision(None, quality_reference=reference)


def check_service_quality_reference(settings, receipt, revision, conditions):
    if (
        receipt.get("revision") != revision
        or receipt.get("conditions") != conditions
        or not receipt.get("service_id")
        or not receipt.get("run_id")
    ):
        raise ValueError("quality: missing/stale/incompatible baseline reference")
    service_quality_score(settings, receipt)


def service_quality_decision(role, gate, passed):
    if not passed:
        return ServiceStageDecision(
            service_assessment(
                "FAIL", "quality_gate_not_met", quality_passed=False, performance=gate
            ),
            ((("profile",), "quality_gate_not_met"),),
        )
    skipped = ((("profile",), "not_required"),) if role != "candidate" else ()
    return ServiceStageDecision(
        service_assessment("PASS", "fixed_checks_satisfied", quality_passed=True, performance=gate),
        skipped,
    )


def service_profile_eligible(reason):
    return reason in ("fixed_checks_satisfied", "performance_gate_not_met")
