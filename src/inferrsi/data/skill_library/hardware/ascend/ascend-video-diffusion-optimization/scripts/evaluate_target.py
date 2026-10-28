#!/usr/bin/env python3
"""Pre-check a campaign's final samples against frozen target and safety gates.

This is a local aid, not the campaign verdict. The authoritative verdict is
produced by the acceptance issue's frozen gates and its evidence tree, and it
stays INCONCLUSIVE while a required level or artifact is missing.

Verdicts follow the repository claim contract: PASS, FAIL, INCONCLUSIVE.
An unreadable or malformed input file reports INVALID with exit code 2, which
is a tool error rather than a campaign verdict.

Exit codes: 0 PASS, 1 FAIL, 2 INVALID, 3 INCONCLUSIVE.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

OPS = {
    "<": lambda value, threshold: value < threshold,
    "<=": lambda value, threshold: value <= threshold,
    ">": lambda value, threshold: value > threshold,
    ">=": lambda value, threshold: value >= threshold,
    "==": lambda value, threshold: value == threshold,
}


def finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def samples(value: Any, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError(f"{field} must contain at least three samples")
    return [finite_number(item, f"{field}[{index}]") for index, item in enumerate(value)]


def summarize(values: list[float]) -> dict[str, float]:
    median = statistics.median(values)
    spread = max(values) - min(values)
    relative_range = math.inf if median == 0 and spread else (
        0.0 if median == 0 else spread / abs(median)
    )
    return {
        "median": median,
        "min": min(values),
        "max": max(values),
        "relative_range": relative_range,
    }


def evaluate_gates(data: Any, field: str) -> list[dict[str, Any]]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{field} must be a list")

    results = []
    for index, gate in enumerate(data):
        if not isinstance(gate, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        name = gate.get("name")
        op = gate.get("op")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{field}[{index}].name must be non-empty")
        if not isinstance(op, str) or op not in OPS:
            raise ValueError(f"{field}[{index}].op must be one of {sorted(OPS)}")
        value = finite_number(gate.get("value"), f"{field}[{index}].value")
        threshold = finite_number(
            gate.get("threshold"), f"{field}[{index}].threshold"
        )
        results.append(
            {
                "name": name,
                "value": value,
                "op": op,
                "threshold": threshold,
                "passed": OPS[op](value, threshold),
            }
        )
    return results


def evaluate(campaign: dict[str, Any]) -> tuple[dict[str, Any], int]:
    primary = campaign.get("primary_metric")
    if not isinstance(primary, dict):
        raise ValueError("primary_metric must be an object")

    name = primary.get("name")
    direction = primary.get("direction")
    if not isinstance(name, str) or not name:
        raise ValueError("primary_metric.name must be non-empty")
    if not isinstance(direction, str) or direction not in {"lower", "higher"}:
        raise ValueError("primary_metric.direction must be lower or higher")

    target = finite_number(primary.get("target"), "primary_metric.target")
    minimum_improvement = finite_number(
        primary.get("minimum_improvement_percent"),
        "primary_metric.minimum_improvement_percent",
    )
    max_relative_range = finite_number(
        primary.get("max_relative_range"), "primary_metric.max_relative_range"
    )
    if minimum_improvement < 0:
        raise ValueError("minimum_improvement_percent must be non-negative")
    if max_relative_range < 0:
        raise ValueError("max_relative_range must be non-negative")

    baseline_values = samples(primary.get("baseline"), "primary_metric.baseline")
    candidate_values = samples(primary.get("candidate"), "primary_metric.candidate")
    baseline = summarize(baseline_values)
    candidate = summarize(candidate_values)

    if baseline["median"] == 0:
        improvement = (
            math.inf
            if direction == "higher" and candidate["median"] > 0
            else 0.0
        )
    elif direction == "lower":
        improvement = (
            (baseline["median"] - candidate["median"])
            / abs(baseline["median"])
            * 100.0
        )
    else:
        improvement = (
            (candidate["median"] - baseline["median"])
            / abs(baseline["median"])
            * 100.0
        )

    target_passed = (
        candidate["median"] <= target
        if direction == "lower"
        else candidate["median"] >= target
    )
    improvement_passed = improvement >= minimum_improvement
    variance_passed = (
        baseline["relative_range"] <= max_relative_range
        and candidate["relative_range"] <= max_relative_range
    )

    quality_gates = evaluate_gates(campaign.get("quality_gates"), "quality_gates")
    resource_gates = evaluate_gates(
        campaign.get("resource_gates"), "resource_gates"
    )
    failed_gates = [
        gate for gate in quality_gates + resource_gates if not gate["passed"]
    ]

    reasons = []
    if not variance_passed:
        verdict = "INCONCLUSIVE"
        reasons.append(
            "sample variance exceeds max_relative_range, so the comparison is not qualified"
        )
        exit_code = 3
    elif failed_gates:
        verdict = "FAIL"
        reasons.append("one or more quality or resource gates failed")
        exit_code = 1
    elif not target_passed:
        verdict = "FAIL"
        reasons.append("primary metric target was not reached")
        exit_code = 1
    elif not improvement_passed:
        verdict = "FAIL"
        reasons.append("improvement did not exceed the required minimum")
        exit_code = 1
    else:
        verdict = "PASS"
        reasons.append("target, improvement, variance, and automated gates passed")
        exit_code = 0

    result = {
        "verdict": verdict,
        "reasons": reasons,
        "scope_note": (
            "Local pre-check only. A public PASS additionally requires pinned "
            "baseline and candidate revisions, validators frozen before candidate "
            "search, and a complete evidence tree for the campaign."
        ),
        "primary_metric": {
            "name": name,
            "direction": direction,
            "target": target,
            "baseline": baseline,
            "candidate": candidate,
            "improvement_percent": improvement,
            "minimum_improvement_percent": minimum_improvement,
            "max_relative_range": max_relative_range,
            "target_passed": target_passed,
            "improvement_passed": improvement_passed,
            "variance_passed": variance_passed,
        },
        "quality_gates": quality_gates,
        "resource_gates": resource_gates,
    }
    return result, exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-check final benchmark samples against campaign gates."
    )
    parser.add_argument(
        "campaign",
        help="Campaign JSON path, or - to read JSON from standard input.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw = sys.stdin.read() if args.campaign == "-" else Path(args.campaign).read_text()
        campaign = json.loads(raw)
        if not isinstance(campaign, dict):
            raise ValueError("campaign root must be an object")
        result, exit_code = evaluate(campaign)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        result = {"verdict": "INVALID", "reasons": [str(error)]}
        exit_code = 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
