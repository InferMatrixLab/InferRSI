"""Evidence gates, independent from command execution and Agent assertions."""

import math

from ..claim import Verdict
from ..model.protocols.metrics import read_metric as read_metric
from ..runspec import RunSpec


def _summary(trials: list[dict]) -> dict | None:
    # Only a completed trial recorded a measurement. A timed-out or failed trial
    # may still have written a result file, but its metric is not a datapoint;
    # `evaluate` reports the exclusion in `reasons` instead of dropping it silently.
    measured = [trial for trial in trials if trial.get("status") == "completed"]
    values = [trial["metric"] for trial in measured if trial.get("metric") is not None]
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    middle = (
        ordered[midpoint]
        if len(ordered) % 2
        else ordered[midpoint - 1] + (ordered[midpoint] - ordered[midpoint - 1]) / 2
    )
    spread = (max(values) - min(values)) / middle * 100
    return {
        "values": values,
        "median": middle,
        "min": min(values),
        "max": max(values),
        "range_pct_of_median": spread if math.isfinite(spread) else None,
        "excluded_trials": len(trials) - len(values),
    }


def evaluate(
    spec: RunSpec,
    baseline: list[dict],
    candidate: list[dict],
    validation: dict | None,
    integrity: dict | None = None,
) -> dict:
    failed, incomplete = [], []
    for label, trials in (("baseline", baseline), ("candidate", candidate)):
        if len(trials) != spec.repetitions:
            incomplete.append(
                f"{label}: expected {spec.repetitions} trials, recorded {len(trials)}"
            )
        for index, trial in enumerate(trials, 1):
            if trial.get("status") != "completed":
                incomplete.append(
                    f"{label} trial {index}: {trial.get('status')} trial excluded from "
                    "the recorded measurements"
                )
            if trial.get("metric") is None:
                incomplete.append(
                    f"{label} trial {index}: {trial.get('metric_error') or 'metric missing'}"
                )
    if validation is None:
        incomplete.append("quality validation command was not supplied")
    elif validation.get("status") == "failed":
        failed.append(f"quality validation: {validation.get('status')}")
    elif validation.get("status") != "completed":
        incomplete.append(f"quality validation: {validation.get('status')}")
    if integrity is None or not integrity.get("verified"):
        incomplete.append((integrity or {}).get("reason", "source integrity was not verified"))

    before, after = _summary(baseline), _summary(candidate)
    improvement = None
    all_metrics = len(baseline) == len(candidate) == spec.repetitions and all(
        t.get("status") == "completed" and t.get("metric") is not None for t in baseline + candidate
    )
    if all_metrics:
        improvement = (after["median"] - before["median"]) / before["median"] * 100
        if spec.direction == "minimize":
            improvement *= -1
        if not math.isfinite(improvement):
            improvement = None
            incomplete.append("derived improvement is not finite; check metric scale and units")
        elif improvement <= 0 or improvement < spec.min_improvement_pct:
            failed.append(
                f"measured gain {improvement:.6g}% must be positive and meet "
                f"{spec.min_improvement_pct:.6g}% threshold"
            )
    # Execution failures describe missing evidence, not a failed performance gate.
    # A completed quality command may reject its gate, but an interrupted one
    # cannot establish a result. Incomplete evidence takes precedence either way.
    verdict = Verdict.INCONCLUSIVE if incomplete else Verdict.FAIL if failed else Verdict.PASS
    return {
        "verdict": verdict.value,
        "reasons": failed + incomplete,
        "metric_key": spec.metric_key,
        "metric_unit": spec.metric_unit,
        "comparison_scope": spec.comparison_scope,
        "direction": spec.direction,
        "min_improvement_pct": spec.min_improvement_pct,
        "baseline": before,
        "candidate": after,
        "improvement_pct": improvement,
        "measurement_method": "Alternating AB/BA sequential trials; median "
        "and range are descriptive only.",
        "quality_contract": "Exit zero covers only the supplied validation "
        "command; inspect its logs and coverage.",
        "source_integrity": integrity,
        "statistical_significance": "not established",
    }
