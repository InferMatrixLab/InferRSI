"""Preparation inputs for project campaign tests with synthetic metric values."""

import json

from inferrsi.harness.candidates import identity


def calibration(unit, direction):
    return {
        "metric": "metric",
        "direction": direction,
        "unit": unit,
        "threshold_type": "relative_percent",
        "method": "workload_measurement",
        "baseline_samples": [10, 10],
        "attainable_value": 20 if direction == "maximize" else 5,
        "calibration_evidence": "Both synthetic controls return fixed metric values.",
    }


def write_review(path, context, measurements, targets):
    receipt = path.with_suffix(".calibration.json")
    receipt.write_text(json.dumps({"context": context, "objectives": measurements}))
    goals = {
        key: {"source": "derived", "target_reference": "Synthetic protocol", "target": value}
        for key, value in targets.items()
    }
    path.write_text(json.dumps({"calibration": receipt.name, "objectives": goals}))
    return str(path)


def project_review(root, repo, unit="synthetic-units", direction="maximize", target=1):
    context = {
        "scope": "synthetic-software-control",
        "device_scope": "synthetic CPU",
        "baseline_snapshot": identity(repo, ["engine.py", "config.json"]),
    }
    return write_review(
        root.with_suffix(".review.json"),
        context,
        {"metric": calibration(unit, direction)},
        {"metric": target},
    )
