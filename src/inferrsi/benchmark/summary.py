"""Versioned benchmark metrics over retained facts; no execution or I/O."""

import math
import statistics

POLICY = {
    "metrics_schema_version": 1,
    "counting_rule": "retained-round-v1",
    "token_scope": "trial_agent_session",
    "objective": {"key": "speedup", "unit": "ratio", "direction": "maximize"},
}


def supported_policy(policy):
    """Keep schema types strict: JSON true must never be treated as version one."""
    return (isinstance(policy, dict)
            and type(policy.get("metrics_schema_version")) is int and policy == POLICY)


def _number(value, *, zero=False):
    try:
        return (type(value) in (int, float) and math.isfinite(value)
                and (value >= 0 if zero else value > 0))
    except OverflowError:
        return False


def token_usage(record=None):
    """A subtotal never becomes a complete session merely because it has numbers."""
    record = record or {}
    value = record.get("value") or {}
    counts = {key: value.get(key) if type(value.get(key)) is int and value[key] >= 0 else None
              for key in ("input_tokens", "output_tokens", "cached_input_tokens")}
    valid = counts["input_tokens"] is not None and counts["output_tokens"] is not None
    if valid and counts["cached_input_tokens"] is not None:
        valid = counts["cached_input_tokens"] <= counts["input_tokens"]
    observed = counts["input_tokens"] + counts["output_tokens"] if valid else None
    complete = (valid and record.get("coverage") == "complete"
                and record.get("scope") == POLICY["token_scope"]
                and bool(record.get("source")))
    return {**counts, "total_tokens": observed if complete else None,
            "observed_tokens": observed, "coverage": "complete" if complete else
            "partial" if observed is not None else "unknown",
            "scope": record.get("scope"), "source": record.get("source"),
            "missing_reason": None if complete else "complete_session_usage_unavailable"}


def single(policy, rounds, final, selected, *, final_verified=False, usage=None, selection=None):
    """Project actual promotions, including rejected candidates and unresolved attempts."""
    supported = supported_policy(policy)
    result = {"metrics_schema_version": (policy.get("metrics_schema_version")
                                         if isinstance(policy, dict) else None),
              "final_speedup": None, "final_kind": None, "step_acceptance_rate": None,
              "accepted_steps": 0, "assessed_steps": 0, "submitted_steps": 0,
              "infrastructure_failures": 0, "unresolved_steps": 0,
              "step_coverage": "unknown", "token_usage": token_usage(usage),
              "missing_reasons": {}}
    if not supported:
        for key in ("accepted_steps", "assessed_steps", "submitted_steps",
                    "infrastructure_failures", "unresolved_steps"):
            result[key] = None
        result["missing_reasons"] = {key: ["unsupported_or_legacy_metrics_policy"] for key in
                                     ("final_speedup", "step_acceptance_rate", "token_usage")}
        result["token_usage"] = token_usage()
        return result
    if (final_verified and isinstance(final, dict) and selection
            and selection.get("metric") == "speedup" and selection.get("direction") == "maximize"):
        speedup = final.get("speedup")
        if speedup is None:
            speedup = final.get("score")
        if _number(speedup):
            result["final_speedup"] = 1.0 if selected.get("kind") == "baseline" else speedup
            result["final_kind"] = ("baseline_fallback" if selected.get("kind") == "baseline"
                                    else "candidate")
    if result["final_speedup"] is None:
        result["missing_reasons"]["final_speedup"] = ["verified_speedup_final_unavailable"]
    for row in rounds or []:
        if row.get("phase") == "final":
            continue
        result["submitted_steps"] += 1
        if (not row.get("record_verified")
                or row.get("execution_state") not in ("completed", "failed")
                or type(row.get("execution_returncode")) is not int
                or row["execution_returncode"] < 0):
            result["unresolved_steps"] += 1
        elif row.get("assessment_status") == "infrastructure_failure":
            result["infrastructure_failures"] += 1
        elif row.get("assessment_status") in ("completed", "candidate_failure"):
            result["assessed_steps"] += 1
            accepted = (row.get("assessment_status") == "completed"
                        and row.get("selection_decision") == "retained"
                        and bool(row.get("candidate_id"))
                        and row["candidate_id"] == (row.get("best_candidate") or {}).get(
                            "candidate_id"))
            result["accepted_steps"] += int(accepted)
        else:
            result["unresolved_steps"] += 1
    if result["assessed_steps"]:
        result["step_acceptance_rate"] = result["accepted_steps"] / result["assessed_steps"]
    else:
        result["missing_reasons"]["step_acceptance_rate"] = ["no_assessed_steps"]
    result["step_coverage"] = "partial" if result["unresolved_steps"] else "complete"
    if result["token_usage"]["total_tokens"] is None:
        result["missing_reasons"]["token_usage"] = [result["token_usage"]["missing_reason"]]
    return result


def _median_ratio(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    a, b = ordered[middle - 1:middle + 1]
    return math.exp((math.log(a) + math.log(b)) / 2) if a and b else 0.0


def comparison(trials, tasks, repeats, policy):
    """Each metric has its own required paired observations, independent of old verdicts."""
    rows = []
    supported = supported_policy(policy)
    for task in tasks:
        metrics = {}
        for field in ("performance_benefit_ratio", "token_consumption_ratio",
                      "acceptance_rate_delta_pp"):
            values, reasons = [], []
            for repeat in range(1, repeats + 1):
                pair = {}
                for side in ("on", "off"):
                    matches = [t for t in trials if t["task"] == task
                               and t["repeat"] == repeat and t["condition"] == side]
                    if len(matches) != 1 or not matches[0].get("metrics_comparable"):
                        reasons.append(f"repeat {repeat} {side}: incomparable_or_missing_trial")
                    else:
                        trial = matches[0]
                        summary = trial.get("benchmark_metrics") or {}
                        if field == "performance_benefit_ratio":
                            value = summary.get("final_speedup")
                        elif field == "token_consumption_ratio":
                            value = summary.get("token_usage", {}).get("total_tokens")
                        else:
                            value = (summary.get("step_acceptance_rate")
                                     if summary.get("step_coverage") == "complete" else None)
                        if not supported or summary.get("metrics_schema_version") != 1:
                            value = None
                        if not _number(value, zero=field != "performance_benefit_ratio"):
                            reasons.append(f"repeat {repeat} {side}: {field}_input_unavailable")
                        else:
                            pair[side] = value
                if len(pair) == 2:
                    if field == "acceptance_rate_delta_pp":
                        value = 100 * (pair["on"] - pair["off"])
                    elif pair["off"] == 0:
                        reasons.append(f"repeat {repeat}: zero_reference_denominator")
                        continue
                    else:
                        value = pair["on"] / pair["off"]
                    if (_number(value, zero=field != "performance_benefit_ratio")
                            or (field == "acceptance_rate_delta_pp" and math.isfinite(value))):
                        values.append(value)
                    else:
                        reasons.append(f"repeat {repeat}: nonfinite_ratio")
            observed = (statistics.median(values) if field == "acceptance_rate_delta_pp"
                        else _median_ratio(values)) if values else None
            metrics[field] = {"value": observed if len(values) == repeats and not reasons else None,
                              "observed_only": observed, "planned_pairs": repeats,
                              "eligible_pairs": len(values), "missing_reasons": reasons,
                              "unit": "percentage_points" if field.endswith("_pp") else "ratio"}
        rows.append({"task": task, "metrics": metrics})
    values = [row["metrics"]["performance_benefit_ratio"]["value"] for row in rows]
    total = (math.exp(statistics.mean(math.log(v) for v in values))
             if values and all(v is not None for v in values) else None)
    return {"metrics_schema_version": (policy.get("metrics_schema_version")
                                        if isinstance(policy, dict) else None),
            "treatment": "on", "reference": "off", "tasks": rows,
            "performance_benefit_ratio": total}
