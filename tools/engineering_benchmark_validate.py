"""Reproduce the #252 CPU task integration with retained, authored controls.

No models, hardware allocators or downloaded programs are invoked. Output is a
local validation bundle, not campaign acceptance or a skill-benefit experiment.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from inferrsi.harness.benchmarks import builtin_tasks, load_task, skill_verifier
from inferrsi.harness.benchmarks.consumers import grade_artifact, run_action
from inferrsi.harness.runner import run_experiment
from inferrsi.harness.skill_evaluation import run_trial
from inferrsi.infra.artifacts import atomic_write_json


class AuthoredControl:
    """A local fixture emits a retained artifact identity, never a claimed score."""

    timeout_seconds = 20

    def __init__(self, identity):
        self.identity = identity

    def command(self, workspace, final, schema, prompt):
        script = (
            "import json, pathlib, sys; "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'candidate_sha256':sys.argv[2]})); "
            "print(json.dumps({'type':'turn.completed'}))"
        )
        return sys.executable, "-B", "-c", script, str(final), self.identity


def replay(task, candidate, directory):
    descriptor = skill_verifier.task_descriptor(task, candidate)
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    atomic_write_json(workspace / "task.json", descriptor)
    return run_trial(
        AuthoredControl(descriptor["benchmark"]["identity"]["candidate_sha256"]),
        descriptor,
        "N",
        1,
        workspace,
        directory / "trial",
        directory / "unused-schema.json",
        Path(skill_verifier.__file__),
        "Reviewed offline control",
        time.monotonic() + 40,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for name in builtin_tasks():
        # This historical replay utility has a NumPy-only candidate protocol.
        if load_task(name).manifest["adapter"] != "numpy-axis1-v2":
            continue
        directory = output / name
        directory.mkdir()
        original = load_task(name)
        shutil.copytree(
            original.root, directory / "task", ignore=shutil.ignore_patterns("__pycache__")
        )
        task = load_task(directory / "task")
        candidate = directory / "implementation.py"
        shutil.copyfile(task.root / "candidate.py", candidate)
        # Freeze the plan before any payload execution.
        spec = task.runspec(
            candidate,
            repo=args.repo,
            output_dir=directory / "workbench",
            repetitions=args.repetitions,
            max_minutes=2,
            min_improvement_pct=0,
        )
        atomic_write_json(directory / "runspec.json", spec.to_dict())
        atomic_write_json(directory / "identity.json", task.identity(candidate))
        grade = grade_artifact(task, candidate, directory / "correctness", timeout_seconds=20)
        profile = run_action(task, candidate, "profile", directory / "profile", timeout_seconds=20)
        run = run_experiment(
            spec, {"scope": "CPU development integration", "identity": task.identity(candidate)}
        )
        evaluation = json.loads((run / "evaluation.json").read_text(encoding="utf-8"))
        good = replay(task, candidate, directory / "skilleval-good")
        bad_source = directory / "wrong.py"
        bad_source.write_text(
            "import numpy as np\ndef compute(x, *, eps): return np.zeros_like(x)\n",
            encoding="utf-8",
        )
        bad = replay(task, bad_source, directory / "skilleval-bad")
        rejected = run_action(
            task, bad_source, "measure", directory / "wrong-measure", timeout_seconds=20
        )
        measured = [
            json.loads(p.read_text(encoding="utf-8"))
            for side in ("baseline", "candidate")
            for p in sorted((run / side).glob("trial-*/result.json"))
        ]
        consumers = measured + [
            json.loads((directory / path).read_text(encoding="utf-8"))
            for path in (
                "correctness/result.json",
                "profile/result.json",
                "skilleval-good/trial/verification/artifact/result.json",
                "skilleval-bad/trial/verification/artifact/result.json",
            )
        ]
        frozen_identity = task.identity(candidate)
        record = {
            "task": name,
            "adapter": task.manifest["adapter"],
            "identity": task.identity(candidate),
            "correctness": grade["verdict"],
            "profile_status": profile["status"],
            "skilleval_good": good["verdict"],
            "skilleval_bad": bad["verdict"],
            "bad_measurement_status": rejected["status"],
            "measurement_trials": len(measured),
            "measured_calls": sum(len(c["samples_ms"]) for r in measured for c in r["cases"]),
            "source_integrity": evaluation["source_integrity"]["verified"],
            "descriptive_workbench_verdict": evaluation["verdict"],
            "workbench_run": run.relative_to(output).as_posix(),
            "all_consumer_identities_match": all(
                all(
                    r["identity"][key] == frozen_identity[key]
                    for key in ("task_id", "task_sha256", "grader_sha256", "runtime_sha256")
                )
                for r in consumers
            ),
            "all_workloads_match": all(
                r["workloads"] == consumers[0]["workloads"] for r in consumers
            ),
            "input_sequence": consumers[0]["input_sequence"],
            "all_input_sequences_match": all(
                r["input_sequence"] == consumers[0]["input_sequence"] for r in consumers
            ),
            "all_valid_executed_calls_match": all(
                r["executed_calls"] == consumers[0]["executed_calls"]
                for r in consumers
                if r["passed"]
            ),
            "expected_measured_calls": (
                2
                * args.repetitions
                * len(task.manifest["measurement"]["case_ids"])
                * task.manifest["measurement"]["samples"]
            ),
        }
        records.append(record)
        print(json.dumps(record), flush=True)
    succeeded = all(
        r["correctness"] == r["skilleval_good"] == "PASS"
        and r["skilleval_bad"] == "FAIL"
        and r["bad_measurement_status"] == "failed"
        and r["profile_status"] == "completed"
        and r["source_integrity"]
        and r["all_consumer_identities_match"]
        and r["all_workloads_match"]
        and r["all_input_sequences_match"]
        and r["all_valid_executed_calls_match"]
        and r["measured_calls"] == r["expected_measured_calls"]
        and r["measurement_trials"] == 2 * args.repetitions
        for r in records
    )
    atomic_write_json(
        output / "summary.json",
        {
            "scope": "local CPU integration with authored controls",
            "checks_succeeded": succeeded,
            "campaign_acceptance": "INCONCLUSIVE",
            "agent_or_skill_benefit": "not measured",
            "accelerator_qualification": "not run",
            "tasks": records,
        },
    )
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
