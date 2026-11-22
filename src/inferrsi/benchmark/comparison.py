"""Knowledge-comparison rules over normalized retained facts; no execution or I/O."""

import math
import statistics

DEFAULT_TASKS = ("qwen21-denoise-npu", "moe-forward-npu")
DEFAULT_POLICY = {
    "metrics": ["speedup", "wall_seconds"],
    "tolerances": {"speedup": 0.0, "wall_seconds": 0.0, "tokens": 0.0},
    "minimum_pairs": 1,
}
METRICS = ("speedup", "wall_seconds", "tokens")
STATUSES = ("pending", "running", "completed", "failed", "blocked")


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_policy(policy: dict) -> dict:
    """Return an independent policy, rejecting unknown or ambiguous requirements."""
    if not isinstance(policy, dict) or set(policy) != set(DEFAULT_POLICY):
        raise ValueError("Comparison policy requires metrics, tolerances and minimum_pairs")
    metrics = policy["metrics"]
    if (not isinstance(metrics, list) or not metrics
            or any(not isinstance(metric, str) or metric not in METRICS for metric in metrics)
            or len(set(metrics)) != len(metrics) or "speedup" not in metrics):
        raise ValueError("Select unique comparison metrics including speedup")
    tolerances = policy["tolerances"]
    if (not isinstance(tolerances, dict) or set(tolerances) != set(METRICS)
            or any(not _number(value) or value < 0 for value in tolerances.values())):
        raise ValueError("Metric tolerances must be finite nonnegative relative fractions")
    minimum = policy["minimum_pairs"]
    if type(minimum) is not int or minimum < 1:
        raise ValueError("minimum_pairs must be a positive integer")
    return {"metrics": list(metrics), "tolerances": dict(tolerances), "minimum_pairs": minimum}


def _factor(on, off, metric):
    if not _number(on) or not _number(off):
        return None
    if metric == "tokens" and (type(on) is not int or type(off) is not int):
        return None
    if metric == "tokens" and on == off == 0:
        return 1.0
    if on <= 0 or off <= 0:
        return None
    try:
        value = math.exp(math.log(on) - math.log(off) if metric == "speedup"
                         else math.log(off) - math.log(on))
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _direction(factor, tolerance):
    # Reciprocal bounds make swapping on/off symmetric. Tolerance is a relative
    # neutral band, not a significance test or an acceptance threshold.
    log_factor, band = math.log(factor), math.log1p(tolerance)
    return 1 if log_factor > band else -1 if log_factor < -band else 0


def _median(values):
    # These are nonnegative observations. statistics.median adds the middle
    # two values first, which can overflow for valid large finite measurements.
    ordered = sorted(values)
    middle = len(ordered) // 2
    return (ordered[middle] if len(ordered) % 2
            else ordered[middle - 1] + (ordered[middle] - ordered[middle - 1]) / 2)


def _kind(signs, complete=True):
    if not complete:
        return "insufficient_evidence"
    if 1 in signs and -1 in signs:
        return "tradeoff"
    if 1 in signs:
        return "efficiency_improved"
    return "regression" if -1 in signs else "no_gain"


def _conclusion(kind, tasks, repeats, metrics):
    descriptions = {
        "efficiency_improved": (
            "Knowledge on improved the observed selected efficiency metrics without a "
            "measured tradeoff in this comparison."
        ),
        "no_gain": (
            "Knowledge on showed no improvement beyond the frozen neutral tolerances "
            "in this comparison."
        ),
        "regression": (
            "Knowledge on worsened selected efficiency metrics without an offsetting "
            "improvement in this comparison."
        ),
        "tradeoff": "Observed benefits and costs differ between selected metrics or tasks.",
        "insufficient_evidence": (
            "The declared comparison is incomplete or lacks comparable evidence; "
            "knowledge efficiency cannot be determined."
        ),
    }
    return {
        "kind": kind,
        "text": descriptions[kind],
        "inference": "descriptive_only",
        "scope": {"tasks": list(tasks), "repeats": repeats, "metrics": list(metrics),
                  "aggregation": "median_of_paired_log_ratios"},
        "limitation": (
            "Results describe these tasks, frozen conditions and observed repeats only; "
            "they establish no statistical significance or general RSI efficacy."
        ),
    }


def _index(trials, tasks, repeats):
    if (not isinstance(tasks, (tuple, list)) or not tasks
            or any(not isinstance(task, str) or not task.strip() for task in tasks)
            or len(set(tasks)) != len(tasks)):
        raise ValueError("Comparison tasks must be unique nonempty names")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("Comparison repeats must be a positive integer")
    if not isinstance(trials, list):
        raise ValueError("Comparison trials must be a list")
    indexed, identities = {}, set()
    for trial in trials:
        if not isinstance(trial, dict):
            raise ValueError("Comparison trial must be an object")
        task, repeat, condition = (trial.get(key) for key in ("task", "repeat", "condition"))
        if (task not in tasks or type(repeat) is not int or not 1 <= repeat <= repeats
                or condition not in ("on", "off")):
            raise ValueError("Trial is outside the declared comparison matrix")
        key = task, repeat, condition
        identity = trial.get("id")
        if (not isinstance(identity, str) or not identity.strip() or identity in identities
                or key in indexed):
            raise ValueError("Comparison trial IDs and matrix cells must be unique")
        if (trial.get("status") not in STATUSES or type(trial.get("eligible")) is not bool
                or not isinstance(trial.get("metrics"), dict)):
            raise ValueError("Trial requires a known status, eligibility and metric object")
        identities.add(identity)
        indexed[key] = trial
    return indexed


def _pair(indexed, task, repeat, policy):
    sides = {condition: indexed.get((task, repeat, condition)) for condition in ("on", "off")}
    gaps = []
    for condition, trial in sides.items():
        if trial is None:
            gaps.append(f"{condition}: trial missing")
        elif trial["status"] != "completed" or not trial["eligible"]:
            gaps.append(f"{condition}: comparable completed final unavailable")
            gaps.extend(f"{condition}: {gap}" for gap in trial.get("gaps", []))
    metrics = {}
    for metric in METRICS:
        values = {side: (trial["metrics"].get(metric) if trial else None)
                  for side, trial in sides.items()}
        factor = _factor(values["on"], values["off"], metric)
        if metric in policy["metrics"] and factor is None:
            gaps.append(f"{metric}: positive finite comparable paired values unavailable")
        metrics[metric] = {**values, "factor": factor}
    return {"task": task, "repeat": repeat,
            "on": sides["on"]["id"] if sides["on"] else None,
            "off": sides["off"]["id"] if sides["off"] else None,
            "eligible": not gaps, "metrics": metrics, "gaps": gaps}


def summarize(trials: list[dict], tasks, repeats: int, policy: dict) -> dict:
    """Assess every planned pair, retaining failures and missing matrix cells.

    Benefit factors above one favor knowledge on. Speedup is on/off; wall time
    and tokens are off/on. Only complete, comparable pairs contribute to paired
    aggregates. A missing declared pair cannot disappear from the conclusion.
    """
    policy = validate_policy(policy)
    indexed = _index(trials, tasks, repeats)
    pairs = [_pair(indexed, task, repeat, policy)
             for task in tasks for repeat in range(1, repeats + 1)]
    task_rows, all_signs = [], []
    for task in tasks:
        declared = [pair for pair in pairs if pair["task"] == task]
        eligible = [pair for pair in declared if pair["eligible"]]
        complete = len(eligible) == repeats and len(eligible) >= policy["minimum_pairs"]
        gaps = [f"repeat {pair['repeat']}: {gap}"
                for pair in declared for gap in pair["gaps"]]
        if len(eligible) < policy["minimum_pairs"]:
            gaps.append("The frozen minimum number of eligible pairs was not reached")
        metrics, signs = {}, []
        for metric in METRICS:
            observed = [pair["metrics"][metric] for pair in eligible
                        if pair["metrics"][metric]["factor"] is not None]
            factor = (math.exp(statistics.median(math.log(row["factor"]) for row in observed))
                      if observed else None)
            direction = (_direction(factor, policy["tolerances"][metric])
                         if factor is not None else None)
            metrics[metric] = {
                "on_median": _median(row["on"] for row in observed) if observed else None,
                "off_median": (_median(row["off"] for row in observed)
                               if observed else None),
                "paired_factor": factor, "direction": direction, "pair_count": len(observed),
                "selected": metric in policy["metrics"],
            }
            if metric in policy["metrics"]:
                if direction is None:
                    complete = False
                else:
                    signs.append(direction)
        kind = _kind(signs, complete)
        task_rows.append({"task": task, "planned_pairs": repeats,
                          "eligible_pairs": len(eligible), "metrics": metrics,
                          "conclusion": _conclusion(kind, [task], repeats, policy["metrics"]),
                          "gaps": gaps})
        all_signs.extend(signs)
    complete = all(row["conclusion"]["kind"] != "insufficient_evidence" for row in task_rows)
    kind = _kind(all_signs, complete)
    return {
        "conclusion": _conclusion(kind, tasks, repeats, policy["metrics"]),
        "tasks": task_rows,
        "counts": {
            "planned_trials": len(tasks) * repeats * 2, "planned_pairs": len(tasks) * repeats,
            "observed_trials": len(trials),
            "eligible_trials": sum(t["eligible"] and t["status"] == "completed" for t in trials),
            "eligible_pairs": sum(pair["eligible"] for pair in pairs),
            "statuses": {status: sum(t["status"] == status for t in trials) for status in STATUSES},
            "missing_trials": len(tasks) * repeats * 2 - len(trials),
        },
        "pairs": pairs,
    }
