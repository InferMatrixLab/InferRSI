"""Qualify a trusted NPU task with controls, profiling and existing Workbench.

Run inside a caller-owned NPU allocation. All policy values are explicit CLI
inputs, frozen before execution. This is an authored software-control exercise,
not a model-generated optimization campaign or formal NPU SkillEval sandbox.
"""

import argparse
import json
import math
import shutil
import statistics
import subprocess
from pathlib import Path

from inferrsi.harness.benchmarks import load_builtin_task
from inferrsi.harness.benchmarks.consumers import run_action
from inferrsi.harness.runner import run_experiment
from inferrsi.infra.artifacts import atomic_write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validation_passed(validation):
    result = validation.get("result", {})
    return (validation.get("execution_status") == "completed"
            and validation.get("returncode") == 0
            and result.get("status") == "completed" and result.get("passed") is True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--min-improvement-pct", type=float, required=True)
    parser.add_argument("--max-aa-difference-pct", type=float, required=True)
    parser.add_argument("--max-minutes", type=float, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args()
    if args.repetitions < 2 or any(not math.isfinite(v) or v <= 0 for v in (
        args.min_improvement_pct, args.max_aa_difference_pct,
        args.max_minutes, args.timeout_seconds,
    )):
        parser.error("Use at least two pairs and positive finite policy values")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("plan", "validator", "patch", "results"):
        (output / directory).mkdir()
    task = load_builtin_task("rmsnorm-npu")
    baseline = task.root / "baseline.py"
    candidate = task.root / "candidate.py"
    controls = {
        "zeros": "return torch.zeros_like(x)",
        "missing-epsilon": "return x * torch.rsqrt((x*x).mean(-1,keepdim=True)) * weight",
        "missing-weight": "return x * torch.rsqrt((x*x).mean(-1,keepdim=True) + eps)",
        "wrong-axis": "return x * torch.rsqrt((x*x).mean(0,keepdim=True) + eps) * weight",
        "input-shape": "x.squeeze_(0); "
                       "return x * torch.rsqrt((x*x).mean(-1,keepdim=True) + eps) * weight",
    }
    wrong_paths = {}
    for name, body in controls.items():
        path = output / "patch" / f"{name}.py"
        path.write_text(f"import torch\ndef compute(x, weight, *, eps):\n    {body}\n")
        wrong_paths[name] = path
    # A correct precheck followed by stale output must also fail before scoring.
    replay = output / "patch" / "replay.py"
    replay.write_text(
        "import torch\ncache = {}\n"
        "def compute(x, weight, *, eps):\n"
        "    key = tuple(x.shape)\n"
        "    if key not in cache:\n"
        "        cache[key] = x * torch.rsqrt((x*x).mean(-1,keepdim=True) + eps) * weight\n"
        "    return cache[key]\n"
    )
    wrong_paths["replay"] = replay
    policy = {key: getattr(args, key) for key in (
        "repetitions", "min_improvement_pct", "max_aa_difference_pct",
        "max_minutes", "timeout_seconds",
    )}
    frozen = {
        "scope": "NPU software controls; no model/skill benefit or service claim",
        "source_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=args.repo, text=True
        ).strip(),
        "policy": policy,
        "implementations": {name: task.identity(path) for name, path in {
            "baseline": baseline, "reference": candidate, **wrong_paths
        }.items()},
    }
    atomic_write_json(output / "plan" / "frozen.json", frozen)
    atomic_write_json(output / "validator" / "task.json", task.manifest)
    for path in (baseline, candidate):
        shutil.copyfile(path, output / "patch" / path.name)
    actions = {}

    def action(name, path, mode):
        execution = run_action(task, path, mode, output / "results" / name,
                               timeout_seconds=args.timeout_seconds)
        result = read(execution["result_path"])
        record = {"execution_status": execution["status"],
                  "returncode": execution["returncode"], "result": result}
        actions[name] = record
        print(json.dumps({"action": name, "status": execution["status"],
                          "passed": result.get("passed")}), flush=True)
        return record

    for name, path in (("baseline", baseline), ("reference", candidate)):
        action(name + "-check", path, "check")
        action(name + "-profile", path, "profile")
    for name, path in wrong_paths.items():
        action(name, path, "measure")
    comparisons = {}
    # Same implementation in both arms is the explicit no-op/A-A control.
    for name, path in (("aa", baseline), ("reference", candidate)):
        spec = task.runspec(path, repo=args.repo, output_dir=output / "results" / name,
                             repetitions=args.repetitions, max_minutes=args.max_minutes,
                             min_improvement_pct=args.min_improvement_pct)
        run = run_experiment(spec, {"benchmark": task.identity(path),
                                    "backend": "ascend", "qualification": "pending"})
        evaluation = read(run / "evaluation.json")
        validation_dir = run / "validation"
        execution = (read(validation_dir / "execution.json")
                     if (validation_dir / "execution.json").is_file() else {})
        validated = (read(validation_dir / "result.json")
                     if (validation_dir / "result.json").is_file() else {})
        validation = {"execution_status": execution.get("status"),
                      "returncode": execution.get("returncode"), "result": validated}
        trials = {side: [read(p) for p in sorted((run / side).glob("trial-*/result.json"))]
                  for side in ("baseline", "candidate")}
        comparisons[name] = {"run": run.relative_to(output).as_posix(),
                             "evaluation": evaluation, "trials": trials,
                             "validation": validation}
        print(json.dumps({"comparison": name, "verdict": evaluation["verdict"]}), flush=True)

    def correct(name):
        record = actions[name]
        return (record["execution_status"] == "completed" and record["returncode"] == 0
                and record["result"].get("status") == "completed"
                and record["result"].get("passed") is True)

    checks = {"correctness": all(correct(name + "-check") for name in ("baseline", "reference")),
              "device_profiles": all(correct(name + "-profile")
                                     for name in ("baseline", "reference")),
              "reject_wrong_outputs": all(actions[name]["execution_status"] == "failed"
                  and actions[name]["returncode"] == 1
                  and actions[name]["result"].get("status") == "completed"
                  and actions[name]["result"].get("passed") is False
                  and "metrics" not in actions[name]["result"] for name in wrong_paths)}
    all_results = [record["result"] for record in actions.values()]
    all_results.extend(trial for comparison in comparisons.values()
                       for trials in comparison["trials"].values() for trial in trials)
    all_results.extend(comparison["validation"]["result"] for comparison in comparisons.values())
    environments = [result.get("environment") for result in all_results]
    checks["fixed_environment"] = bool(environments) and all(
        env and env == environments[0] for env in environments
    )
    task.assert_unchanged()
    shape_comparisons = {}
    for name, comparison in comparisons.items():
        by_shape = {}
        valid = validation_passed(comparison["validation"]) and all(len(trials) == args.repetitions
                    and all(trial.get("passed") and "cases" in trial for trial in trials)
                    for trials in comparison["trials"].values())
        for case in task.manifest["measurement"]["case_ids"] if valid else []:
            medians = {side: statistics.median(
                next(c["median_ms"] for c in trial["cases"] if c["id"] == case)
                for trial in trials) for side, trials in comparison["trials"].items()}
            medians["improvement_pct"] = (1 - medians["candidate"] / medians["baseline"]) * 100
            by_shape[case] = medians
        shape_comparisons[name] = by_shape
        checks[name + "_qualified"] = valid and bool(by_shape) and (
            all(abs(values["improvement_pct"]) <= args.max_aa_difference_pct
                for values in by_shape.values()) and comparison["evaluation"]["verdict"] == "FAIL"
            if name == "aa" else all(values["improvement_pct"] >= args.min_improvement_pct
                                     for values in by_shape.values())
            and comparison["evaluation"]["verdict"] == "PASS"
        )
    summary = {"scope": frozen["scope"], "frozen": frozen, "checks": checks,
               "software_qualification": "PASS" if all(checks.values()) else "INCONCLUSIVE",
               "campaign_acceptance": "not established", "agent_benefit": "not measured",
               "shape_comparisons": shape_comparisons,
               "actions": actions, "comparisons": comparisons}
    atomic_write_json(output / "summary.json", summary)
    print(json.dumps({"checks": checks,
                      "software_qualification": summary["software_qualification"]}))
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
