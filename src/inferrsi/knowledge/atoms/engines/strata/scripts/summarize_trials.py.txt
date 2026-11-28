#!/usr/bin/env python3
"""Summarize quality-passing CSV trials; generated for this skill, not Strata code."""

import argparse
import csv
import json
import math
from pathlib import Path

CONTEXT = ("experiment_id", "hardware_id", "workload_id", "baseline_id")
METRICS = ("ttft_ms", "decode_tps", "peak_vram_mib", "peak_ram_mib")
REQUIRED = CONTEXT + ("trial_id", "config_id", "quality_ok", "valid") + METRICS


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    return (
        ordered[middle]
        if len(ordered) % 2
        else ordered[middle - 1] + (ordered[middle] - ordered[middle - 1]) / 2
    )


def summarize(csv_path):
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, strict=True)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not set(REQUIRED) <= set(header):
            raise ValueError("CSV requires unique headers including: " + ",".join(REQUIRED))
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no trial rows")
    context = tuple((rows[0].get(key) or "").strip() for key in CONTEXT)
    if not all(context):
        raise ValueError("Context IDs must be nonempty")
    seen = set()
    for line, row in enumerate(rows, 2):
        if tuple((row.get(key) or "").strip() for key in CONTEXT) != context:
            raise ValueError(f"Mixed or missing context IDs at CSV line {line}")
        trial = (row.get("trial_id") or "").strip()
        if trial and trial in seen:
            raise ValueError(f"Duplicate trial_id: {trial}")
        seen.add(trial)
    groups, rejected = {}, []
    for line, row in enumerate(rows, 2):
        trial = (row.get("trial_id") or "").strip()
        config = (row.get("config_id") or "").strip()
        if config:
            groups.setdefault(config, [])
        reasons = []
        if None in row or any(value is None for value in row.values()):
            reasons.append("row width differs from header")
        if not trial or not config:
            reasons.append("trial_id and config_id must be nonempty")
        for key in ("valid", "quality_ok"):
            if (row.get(key) or "").strip().lower() != "true":
                reasons.append(f"{key} is not true")
        values = {}
        for key in METRICS:
            try:
                value = float(row.get(key) or "")
                if not math.isfinite(value) or value < 0 or (key in METRICS[:2] and value == 0):
                    raise ValueError()
                values[key] = value
            except ValueError:
                reasons.append(
                    f"{key} must be finite and "
                    f"{'positive' if key in METRICS[:2] else 'nonnegative'}"
                )
        if reasons:
            rejected.append(
                {"line": line, "trial_id": trial, "config_id": config, "reasons": reasons}
            )
        else:
            groups[config].append(values)
    configs = []
    for name, trials in sorted(groups.items()):
        rejected_count = sum(row["config_id"] == name for row in rejected)
        configs.append(
            {
                "config_id": name,
                "n": len(trials),
                "rejected_trial_count": rejected_count,
                "eligible_for_pareto": bool(trials) and rejected_count == 0,
                **{
                    key: median(trial[key] for trial in trials) if trials else None
                    for key in METRICS
                },
            }
        )
    eligible = [item for item in configs if item["eligible_for_pareto"]]
    pareto = []
    for candidate in eligible:
        dominated = any(
            other["ttft_ms"] <= candidate["ttft_ms"]
            and other["decode_tps"] >= candidate["decode_tps"]
            and (
                other["ttft_ms"] < candidate["ttft_ms"]
                or other["decode_tps"] > candidate["decode_tps"]
            )
            for other in eligible
        )
        if not dominated:
            pareto.append(candidate["config_id"])
    return {
        "schema": "strata.trial-summary.v1",
        "context": dict(zip(CONTEXT, context)),
        "accepted_trials": sum(item["n"] for item in configs),
        "configs": configs,
        "pareto_config_ids": pareto,
        "rejected_trials": rejected,
        "note": (
            "Descriptive medians of accepted trials only; any rejected trial makes its config "
            "ineligible for Pareto. No significance claim. Memory is not a Pareto objective."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path", help="CSV containing trial metrics and fixed comparison context IDs"
    )
    args = parser.parse_args()
    try:
        result = summarize(args.csv_path)
    except (OSError, ValueError, csv.Error) as error:
        print(json.dumps({"error": str(error)}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["accepted_trials"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
