"""The old ``run`` evidence gates (v0), independent from execution and composition."""

import math
from collections.abc import Callable
from dataclasses import dataclass

from ..model.protocols.metrics import read_metric as read_metric
from ..model.protocols.metrics import validate_metric

# The v0 protocol's own labels. Benchmark shares no verdict type with another module.
PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"


@dataclass(frozen=True)
class RunRules:
    """The frozen conditions these gates read; the composing application fills them."""

    repetitions: int
    required_trial_checks: tuple[str, ...]
    metric_key: str
    metric_unit: str
    comparison_scope: str
    direction: str
    min_improvement_pct: float


def trial_metric(
    document: dict, key: str, *, reader: Callable[[dict, str], float] = read_metric
) -> float:
    """Validate one trial's metric before it enters the trial record."""
    # A reader is a conversion, not an exemption: the common metric contract
    # applies to whatever it returns.
    return validate_metric(key, reader(document, key))


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
    rules: RunRules,
    baseline: list[dict],
    candidate: list[dict],
    validation: dict | None,
    integrity: dict | None = None,
    *,
    run_error: str | None = None,
) -> dict:
    failed, incomplete = [], []
    trials_qualified = True
    for label, trials in (("baseline", baseline), ("candidate", candidate)):
        if len(trials) != rules.repetitions:
            incomplete.append(
                f"{label}: expected {rules.repetitions} trials, recorded {len(trials)}"
            )
        for index, trial in enumerate(trials, 1):
            checks = trial.get("trial_checks")
            for key in rules.required_trial_checks:
                value = checks.get(key) if isinstance(checks, dict) else None
                if value is not True:
                    trials_qualified = False
                    incomplete.append(
                        f"{label} trial {index}: required check {key} "
                        + ("was false" if value is False else "missing or not boolean")
                    )
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
    all_metrics = len(baseline) == len(candidate) == rules.repetitions and all(
        t.get("status") == "completed" and t.get("metric") is not None for t in baseline + candidate
    )
    if all_metrics and trials_qualified:
        improvement = (after["median"] - before["median"]) / before["median"] * 100
        if rules.direction == "minimize":
            improvement *= -1
        if not math.isfinite(improvement):
            improvement = None
            incomplete.append("derived improvement is not finite; check metric scale and units")
        elif improvement <= 0 or improvement < rules.min_improvement_pct:
            failed.append(
                f"measured gain {improvement:.6g}% must be positive and meet "
                f"{rules.min_improvement_pct:.6g}% threshold"
            )
    # A run that stopped outside its trials cannot establish a result either.
    if run_error:
        incomplete.append(run_error)
    # Execution failures describe missing evidence, not a failed performance gate.
    # A completed quality command may reject its gate, but an interrupted one
    # cannot establish a result. Incomplete evidence takes precedence either way.
    verdict = INCONCLUSIVE if incomplete else FAIL if failed else PASS
    return {
        "verdict": verdict,
        "reasons": failed + incomplete,
        "required_trial_checks": list(rules.required_trial_checks),
        "metric_key": rules.metric_key,
        "metric_unit": rules.metric_unit,
        "comparison_scope": rules.comparison_scope,
        "direction": rules.direction,
        "min_improvement_pct": rules.min_improvement_pct,
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
