"""Execute ordinary projects and packaged benchmarks within the frozen attempt budget."""

import os
import sys
import time
from pathlib import Path

from . import _benchmark_child


def benchmark_command(entry, arguments, *, python=None, prefix=(), launch_directory=None):
    """Build argv for the installed child, including its optional launch-receipt directory."""
    command = [*prefix, sys.executable if python is None else python,
               str(Path(_benchmark_child.__file__).resolve())]
    if launch_directory is not None:
        command.extend(("--session-launch-directory", str(launch_directory)))
    return [*command, str(entry), *arguments]


def execute_ordinary(root, directory, plan, deadline):
    from inferrsi.harness.executor import run_task_protocol
    from inferrsi.harness.executor.trials.external import execute_trial

    if plan["task_source"] == "project":
        return _project_execute(root, directory, plan, deadline)
    task = root / "frozen"
    arguments = run_task_protocol(
        task, plan["frozen_files"]["optimization.py"], "arguments",
        launch_directory=directory, candidate=directory / "candidate.py",
        output=directory / "measurement", settings=plan["evaluation_settings"],
    )
    execution = directory / "execution"
    command = benchmark_command(task / "benchmark.py", arguments, python=plan["python"],
                                prefix=plan["evaluation_prefix"], launch_directory=execution)
    timeout = min(plan["evaluation_timeout_seconds"], max(0, deadline - time.time()))
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return execute_trial(command, root, execution, time.monotonic() + timeout,
                         None, environment=environment, launch_path=execution / "launch-task.json")


def _project_execute(root, directory, plan, deadline):
    from inferrsi.harness.evaluator import inspect_project_step, project_steps
    from inferrsi.harness.executor.candidates import identity, members, retain
    from inferrsi.harness.executor.trials.external import execute_trial
    from inferrsi.harness.records.atomic_json import atomic_write_json

    output = directory / "execution"
    output.mkdir()
    # Programs commonly write logs/caches into cwd. Execute disposable copies,
    # keeping the frozen baseline and submitted candidate immutable.
    workspace = output / "workspace"
    workspace.mkdir()
    baseline, candidate = workspace / "baseline", workspace / "candidate"
    retain(root / plan["baseline_path"], baseline)
    retain(directory / plan["candidate_name"], candidate)
    declared = {"baseline": list(members(baseline)), "candidate": list(members(candidate))}
    expected = {"baseline": identity(baseline), "candidate": identity(candidate)}
    record = {"status": "completed", "returncode": 0, "steps": [], "source_checks": []}
    started = time.monotonic()
    end = started + min(plan["evaluation_timeout_seconds"], max(0, deadline - time.time()))
    for step in project_steps(plan["evaluation_settings"]):
        source = baseline if step["side"] == "baseline" else candidate
        values = {"candidate": str(source), "baseline": str(baseline),
                  "protocol": str(root / "frozen/protocol"), "python": plan["python"]}
        command = []
        for arg in step["argv"]:
            for key, value in values.items():
                arg = arg.replace("{" + key + "}", value)
            command.append(arg)
        environment = dict(os.environ)
        inherited = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            os.pathsep.join((str(source), inherited)) if inherited else str(source)
        )
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        execution = execute_trial((*plan["evaluation_prefix"], *command), source,
                                  output / step["id"], end, None, environment=environment,
                                  launch_path=output / f"launch-{step['id']}.json")
        record["steps"].append({"id": step["id"], **execution})
        actual = {"baseline": identity(baseline, declared["baseline"]),
                  "candidate": identity(candidate, declared["candidate"])}
        record["source_checks"].append({"step": step["id"], "expected": expected,
                                        "actual": actual, "verified": actual == expected})
        if actual != expected or execution["status"] != "completed":
            record["status"] = "failed" if actual != expected else execution["status"]
            record["returncode"] = execution["returncode"]
            break
        decision = inspect_project_step(directory, plan["evaluation_settings"], step, execution)
        if decision["status"] != "completed":
            break  # A frozen check explicitly rejected the candidate or the protocol failed.
    record["elapsed_seconds"] = time.monotonic() - started
    atomic_write_json(output / "execution.json", record)
    return record
