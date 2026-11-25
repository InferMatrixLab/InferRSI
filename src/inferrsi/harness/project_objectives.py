"""Check a project's proposed gain against its workload-specific calibration before freeze."""

import json
import math
from pathlib import Path
from statistics import mean, median

from .records.evidence import bounded_record_bytes


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def change(obj, candidate, reference):
    sign = 1 if obj["direction"] == "maximize" else -1
    delta = sign * (candidate - reference)
    if obj["threshold_type"] == "relative_percent":
        if reference == 0:
            if candidate != 0:
                raise ValueError(f"Undefined relative change from zero: {obj['id']}")
            return 0
        delta = 100 * delta / abs(reference)
    if not number(delta):
        raise ValueError("Nonfinite derived change")
    return delta


def _assess(objective, goal, calibration):
    name = objective["id"]
    target = objective["gain_threshold"]
    if not isinstance(goal, dict) or not number(goal.get("target")) or goal["target"] != target:
        raise ValueError(f"Target review for {name} must preserve the proposed target {target}")
    if goal.get("source") not in ("user", "derived"):
        raise ValueError(f"Identify target source for {name} as user or derived")
    if not isinstance(goal.get("target_reference"), str) or not goal["target_reference"].strip():
        raise ValueError(f"Target review for {name} requires target_reference")

    binding = {
        "metric": objective["key"],
        "unit": objective["unit"],
        "direction": objective["direction"],
        "threshold_type": objective["threshold_type"],
    }
    if "scenario" in objective:
        binding.update(scenario=objective["scenario"], aggregate=objective["aggregate"])
    if not isinstance(calibration, dict) or any(
        calibration.get(key) != expected for key, expected in binding.items()
    ):
        raise ValueError(f"Calibration for {name} is not comparable to the proposed metric")
    if calibration.get("method") not in ("workload_measurement", "calibrated_projection"):
        raise ValueError(f"Identify measurement or calibrated projection for {name}")
    evidence = calibration.get("calibration_evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError(f"Supply calibration evidence and assumptions for {name}")
    samples = calibration.get("baseline_samples")
    attainable = calibration.get("attainable_value")
    if not isinstance(samples, list) or len(samples) < 2 or not all(number(v) for v in samples):
        raise ValueError(f"Insufficient evidence for {name}: supply repeated baseline samples")
    if not number(attainable):
        raise ValueError(f"Insufficient evidence for {name}: supply a calibrated attainable value")
    for value in [*samples, attainable]:
        if domain := objective.get("domain"):
            if not domain["min"] <= value <= domain["max"]:
                raise ValueError(f"Target calibration outside the declared domain for {name}")
        elif value <= 0:  # The ordinary AB/BA evaluator accepts only positive metric values.
            raise ValueError(f"Target calibration for {name} requires positive metric values")

    baseline = (mean if objective["aggregate"] == "mean" else median)(samples)
    if not number(baseline):
        raise ValueError(f"Nonfinite baseline for {name}")
    if objective["threshold_type"] == "relative_percent" and baseline == 0:
        raise ValueError(f"Relative target for {name} needs a nonzero calibrated baseline")
    # Use the observed baseline range in the evaluator's gain units. This is a
    # conservative planning screen, not a statistical confidence interval.
    noise = abs(
        change(objective, max(samples), baseline) - change(objective, min(samples), baseline)
    )
    headroom = change(objective, attainable, baseline)
    if not number(noise):
        raise ValueError(f"Nonfinite target calibration for {name}")
    if headroom <= 0 or target > headroom:
        verdict = "outside_attainable_range"
    elif noise > 0 and target <= noise:
        verdict = "indistinguishable_from_baseline"
    else:
        verdict = "supported"
    return {
        **binding,
        "target": target,
        "source": goal["source"],
        "target_reference": goal["target_reference"],
        "method": calibration["method"],
        "calibration_evidence": evidence,
        "attainable_value": attainable,
        "baseline_samples": samples,
        "baseline": baseline,
        "observed_noise": noise,
        "attainable_gain": headroom,
        "decision": verdict,
    }


def _read(root, relative):
    raw, status = bounded_record_bytes(root, relative, 4 * 1024 * 1024)
    if raw is None:
        raise ValueError(f"Invalid target review input {relative!r}: {status}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid JSON in target review input {relative!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Target review input {relative!r} must be a JSON object")
    return data


def review_targets(path: Path | None, context: dict, objectives: list[dict]) -> dict:
    """Bind the requested goals to independently recorded calibration and compute feasibility."""
    if path is None:
        raise ValueError("--target-review requires a calibration-backed goal review")
    review = _read(path.parent, path.name)
    calibration = _read(path.parent, review.get("calibration"))
    if calibration.get("context") != context:
        raise ValueError(
            "Target calibration is not comparable: check baseline, workload and device"
        )
    names = {obj["id"] for obj in objectives}
    goals, samples = review.get("objectives"), calibration.get("objectives")
    if any(not isinstance(rows, dict) or set(rows) != names for rows in (goals, samples)):
        raise ValueError("Supply a goal and calibration for every declared gain objective")
    decisions = {
        obj["id"]: _assess(obj, goals[obj["id"]], samples[obj["id"]]) for obj in objectives
    }
    # Service selection accepts a gain on any enabled objective (and checks all
    # regression guards). Report each assessment and use the same any-gain rule.
    if not any(row["decision"] == "supported" for row in decisions.values()):
        detail = ", ".join(
            f"{name}: {row['decision']} ({row['source']} target {row['target']:g}, "
            f"noise {row['observed_noise']:g}, attainable {row['attainable_gain']:g})"
            for name, row in decisions.items()
        )
        raise ValueError(f"Unsupported performance target: {detail}. Revisit goal or calibration.")
    return {"context": context, "calibration": review["calibration"], "objectives": decisions}
