"""Quality-first selection for one bounded, verifier-guided improvement step.

The caller supplies receipt-checked Skill Eval reports. This module cannot run
models, read holdout tasks, modify skills or promote knowledge.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SelectionPolicy:
    min_success_rate: float
    max_regressions: int
    quality_weight: float
    token_weight: float

    def __post_init__(self):
        for value in (self.min_success_rate, self.quality_weight, self.token_weight):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Selection values must be finite and nonnegative")
        if self.min_success_rate > 1:
            raise ValueError("min_success_rate must be within [0, 1]")
        if type(self.max_regressions) is not int or self.max_regressions < 0:
            raise ValueError("max_regressions must be a nonnegative integer")
        if self.quality_weight + self.token_weight <= 0:
            raise ValueError("Selection needs a positive weight")


def assess(report: dict, policy: SelectionPolicy, *, split: str,
           require_improvement: bool = False) -> dict:
    """Reject missing/invalid evidence before comparing quality or cost."""
    reason = None
    pairs = report["pairs"]
    if report["status"].get("execution_state") != "completed" or not pairs:
        reason = "incomplete_execution"
    elif any(p[role]["split"] != split for p in pairs for role in ("baseline", "candidate")):
        reason = "wrong_split"
    elif any(p["outcome"] in ("missing_pair", "inconclusive") for p in pairs):
        reason = "inconclusive_evidence"
    before, after = (report["conditions"][role] for role in ("baseline", "candidate"))
    quality = after["verdicts"].get("PASS", 0) / len(pairs) if pairs else 0
    baseline_quality = before["verdicts"].get("PASS", 0) / len(pairs) if pairs else 0
    tokens = after.get("total_tokens")
    baseline_tokens = before.get("total_tokens")
    if reason is None:
        if tokens is None or baseline_tokens is None:
            reason = "unknown_usage"
        elif quality < max(policy.min_success_rate, baseline_quality):
            reason = "quality_floor"
        elif report["counts"]["regression"] > policy.max_regressions:
            reason = "regressions"
        elif require_improvement and not (quality > baseline_quality or tokens < baseline_tokens):
            reason = "no_retained_improvement"
    return {"eligible": reason is None, "reason": reason, "success_rate": quality,
            "baseline_success_rate": baseline_quality, "total_tokens": tokens,
            "baseline_total_tokens": baseline_tokens,
            "regressions": report["counts"]["regression"]}


def select(reports: dict[str, dict], policy: SelectionPolicy) -> dict:
    """Choose INV, DOM, or H0; composition may retain one whole candidate.

    Only strict improvements over the paired H0 are eligible. Equal evidence
    retains H0. Pareto filtering precedes normalized weighted squared distance;
    a flat dimension contributes zero. Candidate IDs break remaining ties.
    """
    if not reports or set(reports) - {"INV", "DOM"}:
        raise ValueError("Only one INV and one DOM report are supported")
    identities = [{(p["case_id"], p["repeat"]) for p in r["pairs"]} for r in reports.values()]
    if any(keys != identities[0] for keys in identities):
        raise ValueError("Probes must use matched cases and repeats")
    first = next(iter(reports.values()))
    if any(r["model"] != first["model"] or r["exam"] != first["exam"]
           or r["arms"]["baseline"] != first["arms"]["baseline"] for r in reports.values()):
        raise ValueError("Probes must share H0, model/settings and frozen exam")
    assessments = {name: assess(report, policy, split="development")
                   for name, report in reports.items()}
    # An incomplete probe makes this bounded decision inconclusive, not a reason
    # to cherry-pick a different successful arm.
    uncertain = {"incomplete_execution", "wrong_split", "inconclusive_evidence", "unknown_usage"}
    if any(a["reason"] in uncertain for a in assessments.values()):
        return {"selected": "H0", "reason": "inconclusive_probe", "assessments": assessments,
                "pareto": [], "scores": {}}
    eligible = {}
    for name, a in assessments.items():
        if a["eligible"] and (a["success_rate"] > a["baseline_success_rate"]
                              or a["total_tokens"] < a["baseline_total_tokens"]):
            eligible[name] = a
    # Each probe contains the same number of matched H0 trials. Pool those
    # independent reference executions instead of cherry-picking a baseline.
    eligible["H0"] = {
        "success_rate": sum(a["baseline_success_rate"] for a in assessments.values())
        / len(assessments),
        "total_tokens": sum(a["baseline_total_tokens"] for a in assessments.values())
        / len(assessments),
    }
    frontier = {name: a for name, a in eligible.items() if not any(
        b["success_rate"] >= a["success_rate"] and b["total_tokens"] <= a["total_tokens"]
        and (b["success_rate"] > a["success_rate"] or b["total_tokens"] < a["total_tokens"])
        for b in eligible.values()
    )}
    scores = {name: 0.0 for name in frontier}
    for key, weight, maximize in (("success_rate", policy.quality_weight, True),
                                  ("total_tokens", policy.token_weight, False)):
        values = [a[key] for a in frontier.values()]
        if values and max(values) > min(values):
            low, high = min(values), max(values)
            for name, a in frontier.items():
                distance = (high - a[key] if maximize else a[key] - low) / (high - low)
                scores[name] += weight * distance ** 2
    selected = min(scores, key=lambda name: (scores[name], name != "H0", name))
    return {"selected": selected,
            "reason": "quality_then_cost" if selected != "H0" else "retain_baseline",
            "assessments": assessments, "pareto": sorted(frontier), "scores": scores}
