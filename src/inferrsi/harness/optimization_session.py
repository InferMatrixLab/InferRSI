"""Assemble the shared Harness lifecycle for project and supplied task protocols.

The CLI supplies a task directory only when starting a packaged task. Ordinary
projects and all subsequent operations use Harness and the retained inputs.
"""

import os
import runpy
import shlex
import sys
import time
from importlib.resources import files
from pathlib import Path


def runtime_environment() -> dict:
    environment = dict(os.environ)
    # Children use the same installed/runtime bundle as this process, including
    # when a different editable installation is present in site-packages.
    import_paths = [str(Path(str(files("inferrsi"))).resolve().parent)]
    if inherited := environment.get("PYTHONPATH"):
        import_paths.append(inherited)
    environment["PYTHONPATH"] = os.pathsep.join(import_paths)
    if sys.dont_write_bytecode:
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _session_execute(root, directory, plan, deadline):
    from inferrsi.harness.scenarios.external import execute_trial
    from inferrsi.harness.task_protocol import protocol

    if plan["task_source"] == "project":
        return _project_execute(root, directory, plan, deadline)
    task = root / "frozen"
    arguments = protocol(task).arguments(directory / "candidate.py", directory / "measurement",
                                         plan["evaluation_settings"])
    command = (*plan["evaluation_prefix"], plan["python"], str(Path(__file__).resolve()),
               str(task / "benchmark.py"), *arguments)
    timeout = min(plan["evaluation_timeout_seconds"], max(0, deadline - time.time()))
    environment = runtime_environment()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return execute_trial(command, root, directory / "execution", time.monotonic() + timeout,
                         None, environment=environment)


def _session_assess(root, directory, plan, execution):
    from inferrsi.harness.task_protocol import protocol

    if plan["task_source"] == "project":
        from inferrsi.harness.project import assess

        return assess(directory, plan["evaluation_settings"], execution)
    return protocol(root / "frozen").assess(directory, plan["evaluation_settings"], execution)


def _project_execute(root, directory, plan, deadline):
    from inferrsi.harness.candidates import identity, members, retain
    from inferrsi.harness.project import inspect_step, steps
    from inferrsi.harness.scenarios.external import execute_trial
    from inferrsi.infra.artifacts import atomic_write_json

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
    for step in steps(plan["evaluation_settings"]):
        source = baseline if step["side"] == "baseline" else candidate
        values = {"candidate": str(source), "baseline": str(baseline),
                  "protocol": str(root / "frozen/protocol"), "python": plan["python"]}
        command = []
        for arg in step["argv"]:
            for key, value in values.items():
                arg = arg.replace("{" + key + "}", value)
            command.append(arg)
        environment = runtime_environment()
        environment["PYTHONPATH"] = str(source) + os.pathsep + environment["PYTHONPATH"]
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        execution = execute_trial((*plan["evaluation_prefix"], *command), source,
                                  output / step["id"], end, None, environment=environment)
        record["steps"].append({"id": step["id"], **execution})
        actual = {"baseline": identity(baseline, declared["baseline"]),
                  "candidate": identity(candidate, declared["candidate"])}
        record["source_checks"].append({"step": step["id"], "expected": expected,
                                        "actual": actual, "verified": actual == expected})
        if actual != expected or execution["status"] != "completed":
            record["status"] = "failed" if actual != expected else execution["status"]
            record["returncode"] = execution["returncode"]
            break
        if inspect_step(directory, plan["evaluation_settings"], step, execution)["status"] != (
            "completed"
        ):
            break  # A frozen check explicitly rejected the candidate or the protocol failed.
    record["elapsed_seconds"] = time.monotonic() - started
    atomic_write_json(output / "execution.json", record)
    return record


def _runtime_identity():
    from inferrsi.infra.artifacts import sha256

    root = Path(str(files("inferrsi")))
    names = ("harness/optimization_session.py", "harness/optimization.py",
             "harness/local_process.py",
             "infra/processes.py", "infra/artifacts.py", "harness/scenarios/external.py",
             "harness/usage.py", "harness/agent_sessions.py", "harness/task_protocol.py",
             "harness/candidates.py", "harness/project.py",
             "harness/records/knowledge_capture.py", "apps/campaign.py",
             "knowledge/context_projection.py")
    return {name: sha256(root / name) for name in names}


def session_command(args, *, task_source: Path | None = None, knowledge_reader=None,
                    retain_context=None) -> dict:
    """Run one operation; discovery and knowledge access are supplied by the caller."""
    from inferrsi.harness import optimization

    root = args.session.resolve()
    if args.session_action == "start":
        import math

        from inferrsi.harness.candidates import identity, retain
        from inferrsi.harness.task_protocol import prepare
        from inferrsi.infra.artifacts import sha256

        if args.rounds < 1 or any(not math.isfinite(value) or value <= 0 for value in (
            args.max_minutes, args.evaluation_timeout_seconds
        )) or not args.condition.strip() or not args.python.strip():
            raise ValueError("A positive round/time budget and condition label are required")
        if root.exists():
            raise ValueError("Session directory must be new")
        reserve = (args.final_reserve_seconds if args.final_reserve_seconds is not None
                   else args.evaluation_timeout_seconds)
        if not math.isfinite(reserve) or not 0 < reserve < args.max_minutes * 60:
            raise ValueError("Reserve time for final within the total budget")
        evaluation_prefix = shlex.split(args.evaluation_prefix)
        if args.project_task:
            from inferrsi.harness.project import prepare as prepare_project

            repo = args.repo.resolve()
            if not repo.is_dir() or root.is_relative_to(repo):
                raise ValueError("Campaign output must be outside the editable project")
            identity(repo, args.include)  # Reject invalid inputs before preparation writes.
            specification = {key: getattr(args, key) for key in (
                "metric_key", "metric_unit", "quality_key", "scope", "direction",
                "min_improvement_pct", "repetitions", "warmups")}
            specification.update(measure_command=shlex.split(args.measure_command),
                                 quality_command=shlex.split(args.quality_command))
            settings = prepare_project(root / "frozen", args.protocol.resolve(),
                                       args.instructions.resolve(), specification)
            retain(repo, root / "frozen/baseline", args.include)
            settings["frozen_files"].update({p.relative_to(root / "frozen").as_posix(): sha256(p)
                for p in (root / "frozen/baseline").rglob("*") if p.is_file()})
            candidate = {"task": "project:" + repo.name, "task_source": "project",
                         "candidate_kind": "directory", "candidate_name": "candidate",
                         "candidate_includes": args.include, "baseline_path": "frozen/baseline",
                         "working_candidate": str(repo),
                         "selection": {"direction": args.direction, "initial_score": None,
                                       "metric": args.metric_key}}
        else:
            if task_source is None:
                raise ValueError("A resolved task resource directory is required to start")
            settings = prepare(task_source, root / "frozen", shlex.split(args.evaluation_args))
            (root / "work").mkdir()
            (root / "work/candidate.py").write_bytes((root / "frozen/baseline.py").read_bytes())
            candidate = {"task": args.task, "task_source": "benchmark", "candidate_kind": "file",
                         "candidate_name": "candidate.py", "baseline_path": "frozen/baseline.py",
                         "working_candidate": "work/candidate.py",
                         "selection": {"direction": "maximize", "initial_score": 1.0,
                                       "metric": "speedup"}}
        plan = {"schema_version": 2, "condition": args.condition,
                "round_limit": args.rounds, "max_seconds": args.max_minutes * 60,
                "round_mode": args.round_mode, "final_reserve_seconds": reserve,
                "knowledge_allowed": args.knowledge == "on",
                "evaluation_timeout_seconds": args.evaluation_timeout_seconds,
                "evaluation_prefix": evaluation_prefix, "python": args.python,
                "runtime_identity": _runtime_identity(), **candidate, **settings}
        result = optimization.initialize(root, plan)
        operation = "campaign" if args.project_task else "benchmarks session"
        result["instructions"] = (
            f"Read the frozen TASK.md. Use {operation} knowledge when the condition allows it. "
            "Edit the returned working_candidate within its declared input scope. "
            f"Before each {operation} round, declare its hypothesis. "
            "Read the observation, keep failures and use feedback for the next change. "
            f"Follow the frozen round policy, then run {operation} final to retest independently. "
            "Report summary.json and its curve. Import actual usage exports when available."
        )
        return result
    import json

    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    if plan["runtime_identity"] != _runtime_identity():
        raise ValueError("Optimization runtime changed, use its frozen runtime to resume")
    if args.session_action == "status":
        return optimization.status(root)
    if args.session_action == "knowledge":
        if knowledge_reader is None or retain_context is None:
            raise ValueError("A knowledge reader and capture callback are required")
        return optimization.capture_context(root, knowledge_reader, retain_context=retain_context,
            query="", relevance=args.query,
            relevance_method=args.relevance_method, context_bytes=args.context_bytes,
            limit=args.limit,
        )
    if args.session_action == "recover":
        return optimization.recover(root, _session_assess)
    final = args.session_action == "final"
    return optimization.evaluate_round(
        root, candidate=None if final else args.candidate,
        hypothesis="Independent final of the selected candidate" if final else args.hypothesis,
        usage=args.usage_export, execute=_session_execute, assess=_session_assess, final=final,
        reason=getattr(args, "reason", None),
    )


def _run_entry(entry: str, arguments: list[str]) -> None:
    # Direct-file launch avoids importing a caller's cwd/inferrsi.py. Once the
    # bundled runner is selected, remove its directory so task imports cannot
    # resolve generic names such as project or candidates from Harness.
    runner = Path(__file__).resolve().parent
    sys.path[:] = [path for path in sys.path if Path(path).resolve() != runner]
    from inferrsi.harness.scenarios.external import execute_trial

    sys.argv = [entry, *arguments]
    sys.path.insert(0, str(Path(entry).parent))
    runpy.run_path(entry, run_name="__main__", init_globals={"execute_trial": execute_trial})


if __name__ == "__main__":
    _run_entry(sys.argv[1], sys.argv[2:])
