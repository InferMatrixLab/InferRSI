"""Export comparator-ready results from the authenticated v2 evidence archive."""

import argparse
import json
import runpy
import sys
import tempfile
from collections import Counter
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parents[1]
MANIFEST = CAMPAIGN / "results/artifacts.json"


def trial_row(record, archive_id):
    run_id = record["run_id"]
    excluded = record["label"] == "AA-excluded"
    return {
        "id": run_id,
        "artifact_id": archive_id,
        "source_record": f"results/trials.json#run_id={run_id}",
        "status": "excluded" if excluded else "completed",
        "conclusion": record["reason"] if excluded else record.get("native_verdict", "calibration"),
        "configuration": {"label": record["label"], "revision": record.get("revision")},
        **{
            key: record.get(key)
            for key in (
                "attempt_id",
                "parent_attempt_id",
                "promoted",
                "cleanup_verified",
                "tpot_ms",
                "gsm8k_correct",
            )
        },
    }


def project(replay, archive_id):
    read, measure, score, gains = (replay[name] for name in ("read", "measure", "score", "gains"))
    plan = read("plan/runspec.json")
    trials = read("results/trials.json")
    rows, rounds = [], []
    counts = {"aa_requests": 0, "evaluation_requests": 0, "quality_flags": 0}
    for trial in trials:
        stage = trial["stage"]
        record = dict(trial)
        if stage == "aa_excluded":
            record["label"] = "AA-excluded"
        else:
            record["tpot_ms"] = measure(trial, plan["timing_protocol"]["output_tokens"])
            counter = "aa_requests" if stage == "aa" else "evaluation_requests"
            counts[counter] += sum(
                len(wave) for waves in trial["timings"].values() for wave in waves
            )
            if stage == "aa":
                record["label"] = f"AA-{trial['launch']}"
            else:
                record["label"] = f"R{trial['round']:02d}" if stage == "round" else stage
                record["cleanup_verified"] = trial.get(
                    "outer_cleanup_verified", trial["native_cleanup_verified"]
                )
                record["gsm8k_correct"] = score(trial, plan["quality"]["samples"])
                counts["quality_flags"] += len(trial["gsm8k"].get("correct_by_item", []))
                if stage == "round":
                    rounds.append(record)
        rows.append(trial_row(record, archive_id))

    by_attempt = {row["attempt_id"]: row for row in rows if row["attempt_id"] is not None}
    references = plan["references"]
    final = by_attempt[references["final_attempt_id"]]
    baseline = by_attempt[references["initial_attempt_id"]]
    parent = by_attempt[final["parent_attempt_id"]]
    summary = {
        "counts": counts,
        "round_verdicts": dict(Counter(r["native_verdict"] for r in rounds)),
        "promoted_rounds": [r["round"] for r in rounds if r["promoted"]],
        "final": {
            "verdict": final["conclusion"],
            "quality_correct": final["gsm8k_correct"],
            "cleanup_verified": final["cleanup_verified"],
            "tpot_ms": final["tpot_ms"],
            "gain_vs_initial_percent": gains(baseline["tpot_ms"], final["tpot_ms"]),
            "gain_vs_acceptance_parent_percent": gains(parent["tpot_ms"], final["tpot_ms"]),
            "elapsed_including_calibration_seconds": (
                plan["physical_budget"]["final_started_elapsed_seconds"]
                + plan["physical_budget"]["final_spent_seconds"]
            ),
        },
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must name a new directory")

    sys.path.insert(0, str(CAMPAIGN.parents[1]))
    from tools.evidence_archives import normalize_manifest, read_json, verify_archive

    manifest = normalize_manifest(read_json(MANIFEST))
    members = {}
    verify_archive(args.archive, manifest, capture=members)
    with tempfile.TemporaryDirectory(prefix="deepseek-evidence-") as scratch:
        root = Path(scratch)
        for name, data in members.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        replay = runpy.run_path(str(root / "validator/replay.py"), run_name="__main__")
        rows, summary = project(replay, manifest["archive"]["id"])

    results = args.output / "results"
    results.mkdir(parents=True)
    (results / "replay-trials.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    (results / "replay-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
