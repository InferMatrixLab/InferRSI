"""Offline first slice of issue #93, above the existing comparison runner.

Preparation and reporting are model-free. Execution is a Python interface for a
trusted fixed-output client; there is deliberately no real-client CLI here.
"""

import argparse
import json
import time
from pathlib import Path

from inferrsi.harness.improvement import SelectionPolicy, assess, select
from inferrsi.harness.skill_evaluation import CodexClient, TrialBudget, usage_totals
from inferrsi.infra.artifacts import sha256, write_json
from inferrsi.knowledge_operations import safe_path
from tools import skill_eval_compare as comparison

ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = (*comparison.CONTROLLERS, "tools/skill_eval_improve.py",
               "src/inferrsi/harness/improvement.py",
               "src/inferrsi/knowledge_operations.py", "tools/skill_eval_verifier.py")


def prepare(config_path: Path, repo: Path, output: Path) -> str:
    config = comparison.read_json(config_path)
    required = {"skill", "skill_root", "cases", "snapshots", "model", "limits",
                "policy", "allowlist", "budget"}
    if set(config) != required or set(config["snapshots"]) != {"H0", "INV", "DOM"}:
        raise ValueError("Declare H0, one INV, one DOM and the supported configuration fields")
    SelectionPolicy(**config["policy"])
    budget = config["budget"]
    if set(budget) != {"max_task_calls", "campaign_seconds", "token_stop_new_trials"} or any(
        type(n) is not int or n <= 0 for n in budget.values()
    ):
        raise ValueError("Declare positive outer call, time and observed-token limits")
    allowlist = config["allowlist"]
    if not isinstance(allowlist, list) or not allowlist or len(set(allowlist)) != len(allowlist):
        raise ValueError("Declare a nonempty unique resource allowlist")
    for path in allowlist:
        if not safe_path(path).endswith(".md"):
            raise ValueError("Only explicitly allowlisted Markdown resources may change")
    tasks = comparison.read_json(config_path.parent / config["cases"])
    if any(t["split"] not in ("development", "holdout") for t in tasks):
        raise ValueError("Improvement requires development/holdout splits only")
    splits = {split: [t for t in tasks if t["split"] == split]
              for split in ("development", "holdout")}
    if not all(splits.values()) or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Nonempty disjoint development and holdout cases are required")
    output.mkdir(parents=True, exist_ok=False)
    (output / "inputs").mkdir()
    (output / "results").mkdir()
    for split, cases in splits.items():
        write_json(output / "inputs" / (split + ".json"), cases)
    stages = [("probe-INV", "INV", "development"), ("probe-DOM", "DOM", "development")]
    stages += [("rerun-" + name, name, "development") for name in ("H0", "INV", "DOM")]
    stages += [("holdout-" + name, name, "holdout") for name in ("INV", "DOM")]
    plans = {}
    for stage, name, split in stages:
        child_config = {key: config[key] for key in ("skill", "skill_root", "model", "limits")}
        child_config.update(mode="update", cases=split + ".json", snapshots={
            "baseline": config["snapshots"]["H0"], "candidate": config["snapshots"][name]})
        path = output / "inputs" / (stage + ".json")
        write_json(path, child_config)
        directory = output / "comparisons" / stage
        plans[stage] = comparison.prepare(path, repo, directory)
        plan = comparison.load_plan(directory)
        if plan["arms"]["baseline"]["bundle"]["entrypoint"] != (
            plan["arms"]["candidate"]["bundle"]["entrypoint"]
        ):
            raise ValueError("Candidate may not change the skill entrypoint")
        if any(c["path"] not in allowlist for c in plan["bundle_changes"]):
            raise ValueError("Candidate changed a resource outside the Markdown allowlist")
        if any(c["baseline"] is None or c["candidate"] is None for c in plan["bundle_changes"]):
            raise ValueError("The first slice supports edits to existing resources only")
    plan = {"format_version": 1, "config": config, "plans": plans,
            "inputs": {p.name: sha256(p) for p in (output / "inputs").iterdir()},
            "controllers": {name: sha256(ROOT / name) for name in CONTROLLERS},
            "execution": "trusted_offline_client_only", "composition": "select_INV_DOM_or_H0",
            "promotion": "not_evaluated"}
    write_json(output / "freeze.json", plan)
    return sha256(output / "freeze.json")


def load_plan(output: Path) -> dict:
    plan = comparison.read_json(output / "freeze.json")
    for name, digest in plan["controllers"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Improvement controller changed after freeze: " + name)
    if {p.name for p in (output / "inputs").iterdir()} != set(plan["inputs"]):
        raise ValueError("Frozen input set changed")
    for name, digest in plan["inputs"].items():
        if sha256(output / "inputs" / name) != digest:
            raise ValueError("Frozen improvement input changed: " + name)
    for stage, digest in plan["plans"].items():
        directory = output / "comparisons" / stage
        if sha256(directory / "plan/freeze.json") != digest:
            raise ValueError("Frozen comparison plan changed: " + stage)
        comparison.load_plan(directory)
    return plan


def save_record(path: Path, data: dict) -> None:
    write_json(path, data)
    write_json(path.with_suffix(".receipt.json"), {"result_sha256": sha256(path)})


def read_record(path: Path) -> dict:
    error = comparison.receipt_error(path.read_bytes(), path.with_suffix(".receipt.json"),
                                     "improvement")
    if error:
        raise ValueError(error)
    return comparison.read_json(path)


def execute_offline(output: Path, authorization: str, *, client) -> dict:
    """Run only a caller-reviewed offline adapter, never infer a model client.

    This is not a sandbox for arbitrary adapters. Real-model generation and
    execution require external read/write isolation and separate qualification.
    """
    if isinstance(client, CodexClient):
        raise ValueError("Real-model execution is outside the offline improvement slice")
    if authorization != sha256(output / "freeze.json"):
        raise ValueError("Execution requires the exact improvement plan SHA-256")
    plan = load_plan(output)
    # Exclusive marker consumes the whole step, even after a crash. No retry may
    # tune a new candidate against this output's already exposed holdout.
    with (output / "results/started.json").open("x", encoding="utf-8") as stream:
        json.dump({"plan_sha256": authorization}, stream)
    started = time.monotonic()
    limits = plan["config"]["budget"]
    budget = TrialBudget(limits["max_task_calls"], started + limits["campaign_seconds"],
                         limits["token_stop_new_trials"])
    policy = SelectionPolicy(**plan["config"]["policy"])
    stages = []

    def run(stage):
        stages.append(stage)
        return comparison.execute(output / "comparisons" / stage, plan["plans"][stage],
                                  client=client, budget=budget)

    probes = {name: run("probe-" + name) for name in ("INV", "DOM")}
    decision = select(probes, policy)
    selected = decision["selected"]
    # Freeze before successor execution, then again verify before the holdout.
    decision["plan_sha256"] = authorization
    save_record(output / "results/selection.json", decision)
    rerun = run("rerun-" + selected)
    rerun_assessment = assess(rerun, policy, split="development",
                              require_improvement=selected != "H0")
    if selected != "H0" and rerun_assessment["eligible"]:
        load_plan(output)
        if read_record(output / "results/selection.json") != decision:
            raise ValueError("Selection changed before holdout")
        run("holdout-" + selected)
    save_record(output / "results/state.json", {
        "plan_sha256": authorization, "stages": stages,
        "selection_sha256": sha256(output / "results/selection.json"),
        "elapsed_seconds": time.monotonic() - started,
        "budget": {"calls": budget.calls, "observed_tokens": budget.tokens,
                   "usage_complete": budget.usage_complete, "stop_reason": budget.stop_reason()},
    })
    return report(output)


def report(output: Path) -> dict:
    """Recheck retained receipts and evidence; do not trust a cached verdict."""
    plan = load_plan(output)
    state = read_record(output / "results/state.json")
    if state["plan_sha256"] != sha256(output / "freeze.json"):
        raise ValueError("Completed run belongs to a different improvement plan")
    if state["selection_sha256"] != sha256(output / "results/selection.json"):
        raise ValueError("Frozen selection changed")
    decision = read_record(output / "results/selection.json")
    reports = {stage: comparison.read_report(output / "comparisons" / stage)
               for stage in state["stages"]}
    policy = SelectionPolicy(**plan["config"]["policy"])
    replay = select({name: reports["probe-" + name] for name in ("INV", "DOM")}, policy)
    selected = decision["selected"]
    consistent = all(decision[key] == value for key, value in replay.items())
    rerun = assess(reports["rerun-" + selected], policy, split="development",
                   require_improvement=selected != "H0")
    holdout = (assess(reports["holdout-" + selected], policy, split="holdout",
                      require_improvement=True)
               if "holdout-" + selected in reports else None)
    accepted = consistent and selected != "H0" and rerun["eligible"] and (
        holdout is not None and holdout["eligible"])
    phase_usage = {}
    all_trials = []
    for stage, result in reports.items():
        trials = [p[role] for p in result["pairs"] for role in ("baseline", "candidate")
                  if not p[role]["missing"]]
        all_trials.extend(trials)
        phase_usage[stage] = {"calls": len(trials), **usage_totals(trials),
                              "elapsed_seconds": sum(t["elapsed_seconds"] for t in trials)
                              if all(t["elapsed_seconds"] is not None for t in trials) else None}
    result = {
        "plan_sha256": state["plan_sha256"], "selection": decision,
        "retained_selection_consistent": consistent, "rerun": rerun, "holdout": holdout,
        "accepted": accepted, "effective_candidate": selected if accepted else "H0",
        "phase_usage": phase_usage, "observed_execution": {
            "calls": len(all_trials), **usage_totals(all_trials),
            "elapsed_seconds": state["elapsed_seconds"], "cost": None},
        "budget": state["budget"],
        "proposal_cost": None,
        "proposal_cost_note": "Caller-prepared snapshots; authoring cost is unknown and excluded.",
        "selected_execution": reports["rerun-" + selected]["conditions"]["candidate"],
        "promotion": "not_evaluated",
        "claim": "Offline control-flow evidence only. Fixture tokens are scripted, not billed. "
        "No measured model efficacy, end-to-end savings, sandbox isolation or engine speedup.",
    }
    write_json(output / "report.json", result)
    # Improver-facing experience deliberately excludes holdout scores and answers.
    write_json(output / "development-experience.json", {
        "kind": "improvement_experience", "plan_sha256": state["plan_sha256"],
        "selection": replay, "rerun": rerun, "applicability": "offline performance-report audit",
        "limitations": ["Candidate only; no automatic Store write or promotion",
                        "No cross-task transfer evaluation", "Caller-authored proposals"],
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "report"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        if args.config is None or args.repo is None:
            parser.error("prepare requires --config and --repo")
        result = {"plan_sha256": prepare(args.config.resolve(), args.repo.resolve(),
                                         args.output.resolve())}
    else:
        result = report(args.output.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
