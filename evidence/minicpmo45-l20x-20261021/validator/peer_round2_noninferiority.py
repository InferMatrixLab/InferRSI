"""Frozen, paired prompt bootstrap for the round-two frozen 256-prompt holdout."""

import argparse
import json
from pathlib import Path

import numpy as np


def evaluate(baseline, candidate, margins, expected_ids):
    b, c = baseline["rows"], candidate["rows"]
    if len(expected_ids) != 256 or len(set(expected_ids)) != 256:
        raise ValueError("Expected exactly 256 unique frozen IDs")
    if set(b) != set(expected_ids) or set(c) != set(expected_ids):
        raise ValueError("Scores must exactly match the frozen holdout IDs")
    if any(set(doc["tasks"]) != {"wer", "sim", "utmos"} for doc in (baseline, candidate)):
        raise ValueError("Incomplete scorers")
    ids = sorted(b)
    rng = np.random.default_rng(20261022)
    draws = rng.integers(0, len(ids), size=(20000, len(ids)))
    result = {}
    for metric in ("wer_percentage_points", "sim_x100_drop", "utmos_drop"):
        if metric == "wer_percentage_points":
            values = []
            for rows in (b, c):
                errors = np.array(
                    [
                        sum(rows[i]["wer"][k] for k in ("substitutions", "deletions", "insertions"))
                        for i in ids
                    ]
                )
                words = np.array(
                    [
                        sum(rows[i]["wer"][k] for k in ("substitutions", "deletions", "hits"))
                        for i in ids
                    ]
                )
                if np.any(words <= 0):
                    raise ValueError("Invalid reference count")
                values.append((errors, words))
            if not np.array_equal(values[0][1], values[1][1]):
                raise ValueError("Different reference denominators")
            point = 100 * (
                values[1][0].sum() / values[1][1].sum() - values[0][0].sum() / values[0][1].sum()
            )
            distribution = 100 * (
                (values[1][0] - values[0][0])[draws].sum(axis=1) / values[0][1][draws].sum(axis=1)
            )
        else:
            key = "sim" if metric.startswith("sim") else "utmos"
            delta = np.array([b[i][key] - c[i][key] for i in ids])
            point = delta.mean()
            distribution = delta[draws].mean(axis=1)
        upper = float(np.percentile(distribution, 95))
        if not np.isfinite(distribution).all() or not np.isfinite(point):
            raise ValueError("Nonfinite scores")
        result[metric] = {
            "degradation": float(point),
            "upper_one_sided_95": upper,
            "margin": margins[metric],
            "verdict": "PASS" if upper <= margins[metric] else "FAIL",
        }
    return {
        "n": len(ids),
        "metrics": result,
        "verdict": "PASS" if all(x["verdict"] == "PASS" for x in result.values()) else "FAIL",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--quality-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())
    report = {"scope": "Unused holdout noninferiority; original strict gate unchanged", "cells": {}}
    try:
        for concurrency in plan["quality_concurrency"]:
            docs = [
                json.loads(
                    (a.quality_dir / f"peer-round2-holdout-{role}-c{concurrency}.json").read_text()
                )
                for role in ("main", "candidate")
            ]
            if any(set(doc["rows"]) != set(plan["quality_holdout_ids"]) for doc in docs):
                raise ValueError("Outputs do not match frozen unused holdout IDs")
            report["cells"][str(concurrency)] = evaluate(
                *docs, plan["margins"], plan["quality_holdout_ids"]
            )
        report["verdict"] = (
            "PASS" if all(x["verdict"] == "PASS" for x in report["cells"].values()) else "FAIL"
        )
    except (OSError, ValueError, KeyError) as exc:
        report.update(verdict="INCONCLUSIVE", reason=str(exc))
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
