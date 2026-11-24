"""Re-assess the real task outputs and emit an index from the retained measurements."""

import argparse
import hashlib
import json
import math
import runpy
from collections import Counter
from pathlib import Path
from statistics import geometric_mean

from inferrsi.benchmark.registry import task_resources
from inferrsi.harness.run_store import RunStoreReader
from inferrsi.harness.work_control import WorkControl

PLAN = Path(__file__).resolve().parents[1] / "plan"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def close(left, right):
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def main(completed, failed):
    plan = read(PLAN / "plan.json")
    task = Path(str(task_resources(plan["task"])))
    protocol = runpy.run_path(str(task / "optimization.py"))
    settings = protocol["validate_arguments"](plan["sampling"])
    spec = read(PLAN / "runspec.json")
    for name, expected_hash in spec["input_sha256"].items():
        require(sha(PLAN.parent / name) == expected_hash, name)
    for name, expected_hash in spec["packaged_task_sha256"].items():
        require(sha(task / name) == expected_hash, name)
    summary = read(completed / "summary.json")
    expected = [(arm, seed) for seed, arms in plan["blocks"] for arm in arms]
    rows = {(item["arm"], item["seed"]): item for item in summary["blocks"]}
    require(list(rows) == expected and len(rows) == len(summary["blocks"]), "Deployment order")
    control = WorkControl(RunStoreReader(completed / "store", "speculative"))
    campaigns = ["training", *(f"{a}-{s}" for a, s in expected if a != "serial")]
    labels = {}
    for campaign in campaigns:
        doc = control.read(campaign)
        require(not doc["blocked"], campaign)
        for operation, op in doc["operations"].items():
            require(op["status"] == "settled", operation)
            if op["category"] in ("root", "verify", "final"):
                search = operation.rsplit("-", 1)[0] if op["category"] == "verify" else campaign
                labels[operation] = (op["category"], search)
    names = {sha(p): p.parent.name for p in completed.glob("sources/*/candidate.py")}
    train = control.read("training")["state"]
    require(train["checkpoint"] == summary["trained"], "Retained checkpoint")
    require(summary["initial"] == plan["checkpoint"], "Initial role weights")
    group = train["training"]
    require(group == summary["training"] and len(group) == plan["train"]["rounds"], "Update count")
    for update in group:
        ids = update["search_ids"]
        records = [train["searches"][i] for i in ids]
        require(len(set(ids)) == len(records) == plan["train"]["group_size"], "Collection size")
        require(len({r["initial_conditions"] for r in records}) == 1, "Collection start")
        require(
            all(r["status"] == "complete" and r["collect"] and not r["forced"] for r in records),
            "Expected completed natural collection",
        )
        returns = [r["gain"] - r["initial_gain"] for r in records]
        require(returns == update["returns"], "Replayed unpenalized returns")
        for i, observed in enumerate(update["advantages"]):
            others = returns[:i] + returns[i + 1 :]
            require(close(observed, returns[i] - math.fsum(others) / len(others)), "Advantage")
    index = []
    checked_ops = set()
    for root in (failed, completed):
        for path in (root / "frozen").iterdir():
            if path.is_file():
                require(
                    sha(path) == sha(task / path.name), f"Frozen validator changed: {path.name}"
                )
        for measure in sorted(root.rglob("measurement/result.json")):
            folder = measure.parents[1]
            raw = read(measure)
            execution = read(folder / "execution/execution.json")
            assessment = protocol["assess"](folder, settings, execution)
            require(assessment == read(folder / "assessment.json"), "Retained task assessment")
            relative = folder.relative_to(root)
            source_hash = sha(folder / "candidate.py")
            name = names[source_hash]
            if root == failed:
                phase, owner = "root", "initialization-failure"
                require(
                    raw["status"] == "infrastructure_failure" and assessment["score"] is None,
                    "Initial attempt status",
                )
            elif relative.parts[0] == "artifacts":
                phase, owner = labels[folder.name]
                checked_ops.add(folder.name)
            else:
                owner = relative.parts[0]
                phase = "final" if relative.parts[-1] == "final" else "verify"
                require(owner.startswith("serial-"), "Unrecognized direct evaluation")
            if root == completed:
                require(
                    assessment["verdict"] == "PASS" and execution["cleanup_verified"] is True,
                    "Task quality or cleanup",
                )
                if phase == "final":
                    arm, seed = owner.split("-")
                    row = rows[arm, int(seed)]
                    require(
                        name == row["selected"] and close(assessment["score"], row["final_score"]),
                        "Final artifact or final score mismatch",
                    )
            index.append(
                {
                    "attempt": "initialization" if root == failed else "completed",
                    "owner": owner,
                    "phase": phase,
                    "selection": name,
                    "candidate_sha256": source_hash,
                    "source_result": str(measure.relative_to(root)),
                    "result_sha256": sha(measure),
                    "verdict": assessment["verdict"],
                    "cleanup_verified": execution["cleanup_verified"],
                    "score": assessment["score"],
                    "calls": len(raw.get("calls", [])),
                }
            )
    require(checked_ops == set(labels), "Missing retained execution result")
    require(sum(r["attempt"] == "initialization" for r in index) == 1, "Failed attempt count")
    counts = Counter((r["owner"], r["phase"]) for r in index)
    require(counts["training", "root"] == 1, "Shared qualification count")
    for (arm, seed), row in rows.items():
        name = f"{arm}-{seed}"
        require(counts[name, "final"] == 1, name)
        require(counts[name, "verify"] == row["candidate_checks"] <= 2, name)
    require(
        sum(counts[i, "verify"] for i in train["searches"]) == summary["training_candidate_checks"],
        "Training call count",
    )
    for left, right in (("trained", "frozen"), ("trained", "serial"), ("frozen", "serial")):
        ratios = [
            rows[left, seed]["final_score"] / rows[right, seed]["final_score"]
            for seed, _ in plan["blocks"]
        ]
        result = summary[f"{left}_over_{right}"]
        require(
            ratios == result["paired_ratios"] and close(geometric_mean(ratios), result["geomean"]),
            "Paired aggregate",
        )
    for row in index:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("completed", type=Path)
    parser.add_argument("failed", type=Path)
    args = parser.parse_args()
    main(args.completed.resolve(), args.failed.resolve())
