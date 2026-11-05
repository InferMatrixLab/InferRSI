"""Aggregate three fixed-seed repetitions within each frozen prompt cluster."""

import argparse
import json
import math
from pathlib import Path

from peer_round2_noninferiority import evaluate

COUNTS = ("substitutions", "deletions", "insertions", "hits")


def aggregate(docs, expected_ids):
    if len(docs) != 3:
        raise ValueError("Require exactly three measured repetitions")
    expected = set(expected_ids)
    if len(expected_ids) != 256 or len(expected) != 256:
        raise ValueError("Require 256 frozen prompt clusters")
    for doc in docs:
        if set(doc["rows"]) != expected or set(doc["tasks"]) != {"wer", "sim", "utmos"}:
            raise ValueError("Incomplete repetition or mismatched prompt IDs")
    rows = {}
    for prompt in sorted(expected):
        samples = [doc["rows"][prompt] for doc in docs]
        for sample in samples:
            counts = sample["wer"]
            if any(type(counts[k]) is not int or counts[k] < 0 for k in COUNTS):
                raise ValueError("Invalid WER counts")
            if not all(math.isfinite(sample[k]) for k in ("sim", "utmos")):
                raise ValueError("Nonfinite quality scores")
        words = [sum(s["wer"][k] for k in ("substitutions", "deletions", "hits")) for s in samples]
        if words[0] <= 0 or len(set(words)) != 1:
            raise ValueError("Reference denominator changed between repetitions")
        rows[prompt] = {
            "wer": {k: sum(s["wer"][k] for s in samples) for k in COUNTS},
            "sim": sum(s["sim"] for s in samples) / 3,
            "utmos": sum(s["utmos"] for s in samples) / 3,
        }
    return {"rows": rows, "tasks": ["wer", "sim", "utmos"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--repeat-plan", type=Path, required=True)
    parser.add_argument("--quality-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("Refusing to overwrite an acceptance report")
    plan = json.loads(args.plan.read_text())
    repeated = json.loads(args.repeat_plan.read_text())
    report = {
        "scope": "Unused 256-prompt holdout, three repetitions clustered by prompt",
        "bootstrap_unit": "prompt; not individual generated waveform",
        "cells": {},
    }
    try:
        import hashlib

        if hashlib.sha256(args.plan.read_bytes()).hexdigest() != repeated["base_plan_sha256"]:
            raise ValueError("Base acceptance plan changed after repeat design was frozen")
        if repeated["measured_runs"] != [1, 2, 3]:
            raise ValueError("Unexpected measured repetitions")
        if set(plan["quality_concurrency"]) != {1, 16, 32}:
            raise ValueError("Require all three frozen concurrency cells")
        for concurrency in plan["quality_concurrency"]:
            merged = []
            for role in ("main", "candidate"):
                docs = [
                    json.loads(
                        (
                            args.quality_dir
                            / f"peer-round2-holdout-{role}-c{concurrency}-run{run}.json"
                        ).read_text()
                    )
                    for run in repeated["measured_runs"]
                ]
                merged.append(aggregate(docs, plan["quality_holdout_ids"]))
            report["cells"][str(concurrency)] = evaluate(
                *merged, plan["margins"], plan["quality_holdout_ids"]
            )
        report["verdict"] = (
            "PASS"
            if all(cell["verdict"] == "PASS" for cell in report["cells"].values())
            else "FAIL"
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.update(verdict="INCONCLUSIVE", reason=str(exc))
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
