"""Bounded, verifier-guided harness selection; no execution or model access."""

import math
from dataclasses import dataclass

from .skill_evaluation import normalize_usage


@dataclass(frozen=True)
class SelectionPolicy:
    min_success_rate: float
    max_regressions: int

    def __post_init__(self):
        if (type(self.min_success_rate) not in (int, float)
                or not math.isfinite(self.min_success_rate)
                or not 0 <= self.min_success_rate <= 1):
            raise ValueError("min_success_rate must be finite and within [0, 1]")
        if type(self.max_regressions) is not int or self.max_regressions < 0:
            raise ValueError("max_regressions must be a nonnegative integer")


def usage_totals(trials: list[dict]) -> dict:
    """Unknown and invalid metrics stay unknown; cached input is not added twice."""
    result = {"calls": len(trials), "cost": None}
    usage = [normalize_usage(t["observations"].get("usage")) for t in trials]
    for field in ("input_tokens", "output_tokens", "cached_input_tokens"):
        values = [(u or {}).get(field) for u in usage]
        result[field] = sum(values) if values and all(
            type(value) is int and value >= 0 for value in values) else None
    for field, values in (
        ("tool_calls", [t["observations"].get("tool_calls") for t in trials]),
        ("elapsed_seconds", [t.get("elapsed_seconds") for t in trials]),
    ):
        result[field] = sum(values) if values and all(
            type(value) in (int, float) and math.isfinite(value) and value >= 0
            for value in values) else None
    tokens = [result["input_tokens"], result["output_tokens"]]
    result["total_tokens"] = sum(tokens) if None not in tokens else None
    return result


def assessment(report: dict, policy: SelectionPolicy) -> dict:
    """Only complete, receipt-verified matched evidence can qualify a successor."""
    pairs = report["pairs"]
    base = [p["baseline"] for p in pairs]
    candidate = [p["candidate"] for p in pairs]
    costs = {"baseline": usage_totals(base), "candidate": usage_totals(candidate)}
    passed = sum(t["verdict"] == "PASS" for t in candidate)
    base_passed = sum(t["verdict"] == "PASS" for t in base)
    regressions = sum(p["outcome"] == "regression" for p in pairs)
    complete = (bool(pairs) and report["status"]["execution_state"] == "completed"
                and all(p["outcome"] not in ("missing_pair", "inconclusive") for p in pairs))
    known = all(costs[role]["total_tokens"] is not None for role in costs)
    reason = "eligible"
    if not complete:
        reason = "incomplete_evidence"
    elif not known:
        reason = "unknown_usage"
    elif passed < base_passed or passed / len(pairs) < policy.min_success_rate:
        reason = "quality_floor"
    elif regressions > policy.max_regressions:
        reason = "regression_limit"
    elif passed == base_passed and costs["candidate"]["total_tokens"] >= (
            costs["baseline"]["total_tokens"]):
        reason = "no_improvement"
    return {"eligible": reason == "eligible", "reason": reason, "complete": complete,
            "successes": passed, "baseline_successes": base_passed,
            "trials": len(pairs), "regressions": regressions, "usage": costs}


def choose(probes: dict[str, dict], policy: SelectionPolicy, *, composable: bool) -> dict:
    """Quality first, then tokens; compose only two individually eligible edits.

    This lexicographic rule selects a Pareto member without arbitrary weights.
    Composition is only a proposal: its mandatory rerun may reject it.
    """
    scores = {name: assessment(report, policy) for name, report in probes.items()}
    if any(s["reason"] in ("incomplete_evidence", "unknown_usage") for s in scores.values()):
        return {"successor": "h0", "reason": "uncertain_probe", "probes": scores}
    signatures = {
        tuple((p["case_id"], p["repeat"], p["baseline"]["verdict"]) for p in r["pairs"])
        for r in probes.values()
    }
    if len(signatures) > 1:
        return {"successor": "h0", "reason": "unstable_baseline", "probes": scores}
    eligible = [name for name, score in scores.items() if score["eligible"]]
    if len(eligible) == 2 and composable:
        return {"successor": "composed", "reason": "compose_eligible", "probes": scores}
    winner = min(eligible, key=lambda name: (
        -scores[name]["successes"], scores[name]["usage"]["candidate"]["total_tokens"], name
    )) if eligible else "h0"
    return {"successor": winner, "reason": "quality_then_tokens" if eligible else "retain_h0",
            "probes": scores}


def holdout_accepts(report: dict, policy: SelectionPolicy) -> bool:
    score = assessment(report, policy)
    # Holdout checks acceptance, not a new search/ranking opportunity. Equal quality/cost is OK.
    return score["reason"] == "eligible" or (score["reason"] == "no_improvement" and
        score["usage"]["candidate"]["total_tokens"] == score["usage"]["baseline"]["total_tokens"])


def rerun_assessment(report: dict, probes: dict[str, dict], policy: SelectionPolicy) -> dict:
    score = assessment(report, policy)
    if not score["eligible"]:
        return score
    if choose({**probes, "rerun": report}, policy, composable=False)["reason"] == (
            "unstable_baseline"):
        return {**score, "eligible": False, "reason": "unstable_baseline"}
    rank = (-score["successes"], score["usage"]["candidate"]["total_tokens"])
    for probe in probes.values():
        other = assessment(probe, policy)
        if other["eligible"] and (
                -other["successes"], other["usage"]["candidate"]["total_tokens"]) < rank:
            return {**score, "eligible": False, "reason": "worse_than_eligible_probe"}
    return score
