"""Frozen CPU engineering-use probe; trusted authored candidates, no agent calls.

Prepare only writes a plan. Run consumes that exact plan once and keeps raw evidence.
Functionality, not a performance winner, determines this fixture's exit status.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from inferrsi.harness.benchmarks import load_task
from inferrsi.harness.benchmarks.consumers import grade_artifact, run_action
from inferrsi.harness.benchmarks.contract import digest
from inferrsi.harness.benchmarks.numpy_task import check_output, reference
from inferrsi.harness.runner import run_experiment
from inferrsi.harness.skill_evaluation import valid_checks
from inferrsi.infra.artifacts import atomic_write_json
from tools import engineering_benchmark_validate as integration

EINSUM = """import numpy as np
def compute(x, *, eps):
    rms = np.einsum('ij...,ij...->i...', x, x)
    rms /= np.float32(x.shape[1])
    rms += np.float32(eps)
    np.sqrt(rms, out=rms)
    return x / np.expand_dims(rms, axis=1)
"""
NO_EPS = """import numpy as np
def compute(x, *, eps):
    return x / np.sqrt(np.mean(x * x, axis=1, keepdims=True))
"""
ROLES = ("unchanged", "einsum", "no-eps")


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def normalized(value):
    return json.loads(json.dumps(value))


def specs(task, root, plan):
    return {
        role: task.runspec(
            root / (role + ".py"),
            repo=Path(plan["repo"]),
            output_dir=root / "results" / role / "workbench",
            **plan["comparison"],
        )
        for role in ROLES[:2]
    }


def prepare(args):
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(
        load_task("rmsnorm-cpu").root,
        root / "task",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    task = load_task(root / "task")
    shutil.copyfile(task.root / "baseline.py", root / "unchanged.py")
    (root / "einsum.py").write_text(EINSUM, encoding="utf-8")
    (root / "no-eps.py").write_text(NO_EPS, encoding="utf-8")
    plan = {
        "schema_version": 1,
        "repo": str(args.repo.resolve()),
        "script_sha256": digest(Path(__file__)),
        "replay_helper_sha256": digest(Path(integration.__file__)),
        "comparison": {
            key: getattr(args, key) for key in ("repetitions", "max_minutes", "min_improvement_pct")
        },
        "action_timeout_seconds": args.timeout_seconds,
        "replay_bounds_seconds": {"client": 20, "trial": 40},
        "identities": {role: task.identity(root / (role + ".py")) for role in ROLES},
        "smoke": {"seed": 2026, "shape": [4, 17, 9, 7], "scale": 4, "dtype": "float32"},
        "hypothesis": "Source suggests einsum may avoid the full-sized square temporary; "
        "CPU cProfile does not establish a memory bottleneck.",
        "sequence": [
            "profiles",
            "correctness-and-replay",
            "ordinary-smoke",
            "reject-wrong-measurement",
            "unchanged-comparison",
            "einsum-comparison",
        ],
        "success": "Both valid candidates accepted; no-eps rejected without a metric; "
        "complete profiles/comparisons and identical consumer tasks/workloads. "
        "Performance winner and ordinary-smoke outcome are not success gates.",
    }
    if not 0 < args.timeout_seconds <= 7 * 24 * 3600:
        raise ValueError("Action timeout must be positive and at most seven days")
    plan["runspecs"] = {role: spec.to_dict() for role, spec in specs(task, root, plan).items()}
    atomic_write_json(root / "plan.json", plan)
    print(json.dumps({"plan_sha256": digest(root / "plan.json"), "payload_executed": False}))
    return 0


def verify(root, expected):
    if digest(root / "plan.json") != expected:
        raise ValueError("Frozen plan changed")
    plan = read(root / "plan.json")
    if (
        digest(Path(__file__)) != plan["script_sha256"]
        or digest(Path(integration.__file__)) != plan["replay_helper_sha256"]
    ):
        raise ValueError("Probe or replay helper changed")
    task = load_task(root / "task")
    if any(task.identity(root / (role + ".py")) != plan["identities"][role] for role in ROLES):
        raise ValueError("Task, candidate, grader or runtime changed")
    current = specs(task, root, plan)
    if normalized({role: spec.to_dict() for role, spec in current.items()}) != plan["runspecs"]:
        raise ValueError("RunSpec changed")
    return plan, task, current


def smoke(root, plan, task):
    import numpy as np

    config = plan["smoke"]
    x = (
        np.random.default_rng(config["seed"]).standard_normal(config["shape"]) * config["scale"]
    ).astype(np.float32)
    expected = reference(x, task.manifest["oracle"], np)
    records = {}
    for role in ROLES:
        namespace = {}
        exec(compile((root / (role + ".py")).read_bytes(), "implementation.py", "exec"), namespace)
        actual_input = x.copy()
        output = namespace["compute"](actual_input, eps=task.manifest["oracle"]["eps"])
        assertions = check_output(output, actual_input, x, expected, task.manifest["oracle"], np)
        records[role] = {"passed": all(assertions.values()), "assertions": assertions}
    return {"input_sha256": hashlib.sha256(x.tobytes()).hexdigest(), "candidates": records}


def run(args):
    root = args.output_dir.resolve()
    plan, task, comparisons = verify(root, args.plan_sha256)
    output = root / "results"
    output.mkdir(exist_ok=False)  # An interrupted attempt cannot silently resume or be replaced.
    artifacts, profiles, candidates, measured = [], {}, {}, {}

    def checked():
        verify(root, args.plan_sha256)

    def retain(path, role):
        document = read(path)
        artifacts.append((role, document))
        return document

    for role in ROLES[:2]:
        checked()
        directory = output / role / "profile"
        execution = run_action(
            task,
            root / (role + ".py"),
            "profile",
            directory,
            timeout_seconds=plan["action_timeout_seconds"],
        )
        result = retain(directory / "result.json", role)
        profile = directory / "profile.txt"
        profiles[role] = {
            "status": execution["status"],
            "diagnostic": result.get("diagnostic"),
            "has_metric": "metrics" in result,
            "artifact_sha256": digest(profile) if profile.is_file() else None,
        }
    for role in ROLES:
        checked()
        source, directory = root / (role + ".py"), output / role
        grade = grade_artifact(
            task, source, directory / "correctness", timeout_seconds=plan["action_timeout_seconds"]
        )
        result = retain(directory / "correctness" / "result.json", role)
        checked()
        trial = integration.replay(task, source, directory / "skilleval")
        retain(directory / "skilleval/trial/verification/artifact/result.json", role)
        candidates[role] = {
            "correctness": grade["verdict"],
            "skilleval": trial["verdict"],
            "failed_assertions": [
                key for key, value in result.get("assertions", {}).items() if not value
            ],
        }
    checked()
    smoke_result = smoke(root, plan, task)
    atomic_write_json(output / "ordinary-smoke.json", smoke_result)
    checked()
    wrong = run_action(
        task,
        root / "no-eps.py",
        "measure",
        output / "no-eps/measure",
        timeout_seconds=plan["action_timeout_seconds"],
    )
    wrong_result = retain(output / "no-eps/measure/result.json", "no-eps")
    for role in ROLES[:2]:
        checked()
        run_dir = run_experiment(comparisons[role], {"scope": "CPU engineering-use probe"})
        evaluation = read(run_dir / "evaluation.json")
        trials = []
        for side in ("baseline", "candidate"):
            for path in sorted((run_dir / side).glob("trial-*/result.json")):
                result = retain(path, "unchanged" if side == "baseline" else role)
                trials.append(
                    {
                        "side": side,
                        "trial": path.parent.name,
                        "cases": result.get("cases", []),
                        "metrics": result.get("metrics"),
                    }
                )
        validation = retain(run_dir / "validation/result.json", role)
        quality_checks = {key: validation.get(key) for key in ("passed", "assertions")}
        measured[role] = {
            key: evaluation.get(key)
            for key in (
                "verdict",
                "baseline",
                "candidate",
                "improvement_pct",
                "statistical_significance",
            )
        }
        measured[role].update(
            final_quality_passed=(
                validation.get("status") == "completed"
                and validation.get("action") == "check"
                and validation.get("passed") is True
                and valid_checks(quality_checks)
            ),
            source_integrity=evaluation.get("source_integrity", {}).get("verified"),
            trials=trials,
            measured_calls=sum(
                len(case["samples_ms"]) for trial in trials for case in trial["cases"]
            ),
        )
    checked()
    workloads = artifacts[0][1].get("workloads")
    identities_match = all(
        result.get("identity") == plan["identities"][role] for role, result in artifacts
    )
    workloads_match = bool(workloads) and all(
        result.get("workloads") == workloads for _, result in artifacts
    )
    sequence = artifacts[0][1].get("input_sequence")
    executed = artifacts[0][1].get("executed_calls")
    checks = {
        "valid_candidates_accepted": all(
            candidates[r]["correctness"] == candidates[r]["skilleval"] == "PASS" for r in ROLES[:2]
        ),
        "wrong_candidate_rejected": candidates["no-eps"]["correctness"]
        == candidates["no-eps"]["skilleval"]
        == "FAIL",
        "wrong_has_no_metric": wrong["status"] == "failed" and "metrics" not in wrong_result,
        "profiles_complete": all(
            p["status"] == "completed"
            and p["artifact_sha256"]
            and p["diagnostic"]
            and p["diagnostic"].get("performance_verdict") is None
            and not p["has_metric"]
            for p in profiles.values()
        ),
        "consumer_identities_match": identities_match,
        "actual_workloads_match": workloads_match,
        "planned_input_sequences_match": bool(sequence)
        and all(result.get("input_sequence") == sequence for _, result in artifacts),
        "valid_executed_inputs_match": bool(executed)
        and all(
            result.get("executed_calls") == executed
            for _, result in artifacts
            if result.get("passed")
        ),
        "comparison_quality_passed": all(m["final_quality_passed"] for m in measured.values()),
        "comparisons_complete": all(
            m["source_integrity"]
            and len(m["trials"]) == 2 * plan["comparison"]["repetitions"]
            and m["measured_calls"]
            == 2
            * plan["comparison"]["repetitions"]
            * len(task.manifest["measurement"]["case_ids"])
            * task.manifest["measurement"]["samples"]
            and all(
                m[side] and m[side]["excluded_trials"] == 0 for side in ("baseline", "candidate")
            )
            for m in measured.values()
        ),
    }
    summary = {
        "scope": "CPU engineering-use probe with trusted authored candidates",
        "plan_sha256": args.plan_sha256,
        "script_sha256": plan["script_sha256"],
        "replay_helper_sha256": plan["replay_helper_sha256"],
        "smoke_config": plan["smoke"],
        "environment": artifacts[0][1].get("environment"),
        "checks": checks,
        "checks_succeeded": all(checks.values()),
        "identities": plan["identities"],
        "comparison": plan["comparison"],
        "workloads": workloads,
        "input_sequence": sequence,
        "profiles": profiles,
        "candidates": candidates,
        "ordinary_smoke": smoke_result,
        "comparisons": measured,
        "unchanged_raw_pass": measured["unchanged"]["verdict"] == "PASS",
        "interpretation": "Raw Workbench verdicts are descriptive; an unchanged PASS is "
        "a false-positive warning, not optimization. No speedup claim.",
        "campaign_acceptance": "INCONCLUSIVE",
        "agent_or_skill_benefit": "not measured",
        "accelerator_qualification": "not run",
    }
    atomic_write_json(output / "summary.json", summary)
    print(json.dumps({"checks_succeeded": summary["checks_succeeded"], "checks": checks}))
    return 0 if summary["checks_succeeded"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--repo", type=Path, required=True)
    setup.add_argument("--repetitions", type=int, required=True)
    setup.add_argument("--max-minutes", type=float, required=True)
    setup.add_argument("--min-improvement-pct", type=float, required=True)
    setup.add_argument("--timeout-seconds", type=float, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--plan-sha256", required=True)
    for command in (setup, execute):
        command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    return prepare(args) if args.action == "prepare" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
