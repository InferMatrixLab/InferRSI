"""Reproduce H0 / equal-call-budget H0 / bounded-loop offline controls."""

import argparse
import json
import time
from pathlib import Path

from inferrsi.infra.artifacts import sha256, write_json
from tests.fixtures.skill_eval_improvement_support import ImprovementClient, configuration
from tools import skill_eval_compare as comparison
from tools import skill_eval_improve as improvement


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, repeats in (("H0", 3), ("repeated-H0", 12), ("bounded", 3)):
        root = output / name
        started = time.monotonic()
        config_path, repo = configuration(root, repeats=repeats, max_calls=48)
        client = ImprovementClient(root)
        directory = root / "run"
        if name == "bounded":
            digest = improvement.prepare(config_path, repo, directory)
        else:
            config = comparison.read_json(config_path)
            tasks = comparison.read_json(root / "cases.json")
            write_json(root / "cases.json", [t for t in tasks if t["split"] == "holdout"])
            control = {k: config[k] for k in ("skill", "skill_root", "cases", "model", "limits")}
            control.update(mode="update", snapshots={
                "baseline": config["snapshots"]["H0"], "candidate": config["snapshots"]["H0"]})
            write_json(config_path, control)
            digest = comparison.prepare(config_path, repo, directory)
        preparation = time.monotonic() - started
        started = time.monotonic()
        if name == "bounded":
            result = improvement.execute_offline(directory, digest, client=client)
            totals = result["observed_execution"]
            heldout = comparison.read_report(directory / "comparisons/holdout-INV")
        else:
            result = comparison.execute(directory, digest, client=client)
            heldout = result
            conditions = result["conditions"].values()
            totals = {"calls": len(client.calls),
                      "total_tokens": sum(c["total_tokens"] for c in conditions),
                      "command_calls": sum(c["command_calls"] for c in conditions)}
        execution = time.monotonic() - started
        rows.append({
            "condition": name, "preparation_seconds": preparation,
            "execution_seconds": execution, "calls": len(client.calls),
            "scripted_total_tokens": totals["total_tokens"],
            "scripted_command_calls": totals["command_calls"],
            "holdout_candidate_trials": heldout["conditions"]["candidate"]["trials"],
            "holdout_candidate_verdicts": heldout["conditions"]["candidate"]["verdicts"],
            "holdout_regressions": heldout["counts"]["regression"],
            "effective_candidate": result.get("effective_candidate", "H0"),
            "plan_sha256": digest, "report_sha256": sha256(directory / "report.json"),
        })
    summary = {
        "kind": "offline_fixture_control", "rows": rows,
        "scope": "Actual subprocess calls and pipeline wall time; scripted answers and tokens. "
        "H0 is a paired H0/H0 control, repeated-H0 has the bounded loop's 48-call budget. "
        "No best-of-N answer selection. Different repeat counts are not efficacy estimates.",
        "model_calls": 0, "monetary_cost": None, "proposal_authoring_cost": None,
        "efficacy_verdict": "INCONCLUSIVE", "engine_performance_verdict": "INCONCLUSIVE",
    }
    write_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve()), indent=2))
