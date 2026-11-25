"""Assemble the shared Harness lifecycle for project and supplied task protocols.

The CLI supplies a task directory only when starting a packaged task. Ordinary
projects and all subsequent operations use Harness and the retained inputs.
"""

import json
import os
import runpy
import shlex
import sys
import time
from functools import partial
from importlib.resources import files
from itertools import count
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
    from inferrsi.harness.task_protocol import run as run_protocol
    from inferrsi.harness.trials.external import execute_trial

    if plan["task_source"] == "project":
        return _project_execute(root, directory, plan, deadline)
    task = root / "frozen"
    arguments = run_protocol(task, plan["frozen_files"]["optimization.py"], "arguments",
                             launch_directory=directory,
                             candidate=directory / "candidate.py",
                             output=directory / "measurement",
                             settings=plan["evaluation_settings"])
    execution = directory / "execution"
    command = (*plan["evaluation_prefix"], plan["python"], str(Path(__file__).resolve()),
               "--session-launch-directory", str(execution),
               str(task / "benchmark.py"), *arguments)
    timeout = min(plan["evaluation_timeout_seconds"], max(0, deadline - time.time()))
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return execute_trial(command, root, execution, time.monotonic() + timeout,
                         None, environment=environment, launch_path=execution / "launch-task.json")


def _session_assess(root, directory, plan, execution, mechanism=None):
    from inferrsi.harness.task_protocol import run as run_protocol

    if plan["task_source"] == "project":
        from inferrsi.harness.project import assess

        return assess(directory, plan["evaluation_settings"], execution, mechanism=mechanism)
    return run_protocol(root / "frozen", plan["frozen_files"]["optimization.py"], "assess",
                        launch_directory=directory, directory=directory,
                        settings=plan["evaluation_settings"],
                        execution=execution)


def _project_execute(root, directory, plan, deadline):
    from inferrsi.harness.atomic_json import atomic_write_json
    from inferrsi.harness.candidates import identity, members, retain
    from inferrsi.harness.project import inspect_step, steps
    from inferrsi.harness.trials.external import execute_trial

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
        if inspect_step(directory, plan["evaluation_settings"], step, execution)["status"] != (
            "completed"
        ):
            break  # A frozen check explicitly rejected the candidate or the protocol failed.
    record["elapsed_seconds"] = time.monotonic() - started
    atomic_write_json(output / "execution.json", record)
    return record


def _runtime_identity():
    from inferrsi.harness.artifact_primitives import sha256
    from inferrsi.harness.session_runtime import source_files

    root = Path(str(files("inferrsi")))
    return {name: sha256(root / name) for name in source_files(root)}


def session_command(args, *, task_source: Path | None = None, knowledge_reader=None,
                    retain_context=None, external_knowledge=None, external_provider=None,
                    external_project=None, external_provider_for=None,
                    report_metadata=None) -> dict:
    """Run one operation; discovery and knowledge access are supplied by the caller."""
    from inferrsi.harness import optimization

    root = args.session.resolve()
    if args.session_action == "start":
        import math

        from inferrsi.harness.artifact_primitives import sha256
        from inferrsi.harness.candidates import identity, retain
        from inferrsi.harness.task_protocol import prepare

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
        if external_knowledge and args.knowledge != "on":
            raise ValueError("External knowledge requires --knowledge on")
        if (external_knowledge and args.project_task
                and args.evaluation_mode == "service_reuse"):
            raise ValueError("External round knowledge requires a benchmark or AB/BA campaign")
        if args.project_task:
            names = (
                "metric_key",
                "metric_unit",
                "quality_key",
                "scope",
                "direction",
                "min_improvement_pct",
                "repetitions",
                "warmups",
                "measure_command",
                "quality_command",
            )
            if args.evaluation_mode == "service_reuse":
                from inferrsi.harness.project_service import prepare as prepare_service

                if args.evaluation_config is None or any(
                    getattr(args, key) is not None for key in names
                ):
                    raise ValueError(
                        "Service reuse requires --evaluation-config without AB/BA options"
                    )
                if args.decision != "point" or args.require_explanation:
                    # Both switches read AB/BA pairs and per-measurement breakdown/counters;
                    # this mode's optional profiling stage does not produce those inputs.
                    raise ValueError(
                        "--decision paired and --require-explanation apply to AB/BA campaigns"
                    )
                settings = prepare_service(root, args)
                plan = {
                    "schema_version": 3,
                    "condition": args.condition,
                    "round_limit": args.rounds,
                    "max_seconds": args.max_minutes * 60,
                    "round_mode": args.round_mode,
                    "final_reserve_seconds": reserve,
                    "knowledge_allowed": args.knowledge == "on",
                    "evaluation_timeout_seconds": args.evaluation_timeout_seconds,
                    "evaluation_prefix": evaluation_prefix,
                    "python": args.python,
                    **settings,
                }
                result = optimization.initialize(root, plan)
                result["instructions"] = (
                    "Run campaign baseline before candidate search. Record the measured "
                    "bottleneck with campaign diagnose before knowledge or rounds. "
                    "Use campaign round for each "
                    "committed candidate; investigate INCONCLUSIVE results before explicit retry. "
                    "Finish with campaign final; final does not collect a profile."
                )
                return result
            if args.evaluation_config is not None or any(
                getattr(args, key) is None for key in names
            ):
                raise ValueError(
                    "AB/BA requires its existing metric, quality, command and sampling options"
                )
            from inferrsi.harness.project import prepare as prepare_project

            repo = args.repo.resolve()
            if not repo.is_dir() or root.is_relative_to(repo):
                raise ValueError("Campaign output must be outside the editable project")
            identity(repo, args.include)  # Reject invalid inputs before preparation writes.
            specification = {key: getattr(args, key) for key in (
                "metric_key", "metric_unit", "quality_key", "scope", "direction",
                "min_improvement_pct", "repetitions", "warmups", "decision",
                "require_explanation")}
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
                         "selection": (
                             # Paired mode ranks by the speedup its decision reads.
                             {"direction": "maximize", "initial_score": 1.0,
                              "metric": "paired_median_speedup"}
                             if args.decision == "paired" else
                             {"direction": args.direction, "initial_score": None,
                              "metric": args.metric_key})}
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
        if external_knowledge:
            plan["external_knowledge"] = external_knowledge
            plan["external_knowledge_project"] = external_project
        if report_metadata is not None:
            plan["report_metadata"] = report_metadata
        result = optimization.initialize(root, plan)
        operation = "campaign" if args.project_task else "benchmarks session"
        result["instructions"] = (
            f"Read the frozen TASK.md. Record the measured bottleneck with {operation} "
            f"diagnose first. Use {operation} knowledge when needed and permitted. "
            "Edit the returned working_candidate within its declared input scope. "
            f"Before each {operation} round, declare its hypothesis. "
            "Record other options you considered with --alternative and why you chose the "
            "submitted candidate with --selection-reason. "
            "Read the observation, keep failures and use feedback for the next change. "
            f"Follow the frozen round policy, then run {operation} final to retest independently. "
            "Report summary.json and its curve. Import actual usage exports when available."
        )
        if external_knowledge:
            result["instructions"] += (
                f" Read external hits with {operation} knowledge-read. Cite the delivered "
                "item or read receipt with --knowledge-ref when submitting a candidate."
            )
        return result

    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    if (
        plan.get("evaluation_mode") == "service_reuse"
        or plan.get("schema_version") == 3
        or manifest.get("evaluation_mode") == "service_reuse"
    ):
        if getattr(args, "confirm_domain_empty", False):
            raise ValueError("Service-reuse cleanup requires --cleanup-receipt")
        if args.session_action == "profile":
            try:
                return optimization.service_command(root, args)
            except (ValueError, OSError) as exc:
                message = "Campaign lock is busy" if isinstance(exc, BlockingIOError) else str(exc)
                return {
                    "exit_code": 2,
                    "round": args.round,
                    "profiling_error": {
                        "status": "failed", "stage": "campaign", "message": message,
                    },
                }
        if args.session_action == "knowledge-read":
            raise ValueError("External round knowledge requires a benchmark or AB/BA campaign")
        if getattr(args, "mechanism_file", None) is not None:
            raise ValueError("Mechanism checks apply to AB/BA project campaign rounds only")
        if getattr(args, "alternative", None) is not None or getattr(
                args, "selection_reason", None) is not None:
            raise ValueError("Round decision declarations require a benchmark or AB/BA campaign")
        return optimization.service_command(root, args, knowledge_reader=knowledge_reader)
    if (
        args.session_action in ("baseline", "refresh-references", "resume", "profile")
        or getattr(args, "retry_of", None)
        or getattr(args, "repair_reason", None)
        or getattr(args, "cleanup_receipt", None)
        or getattr(args, "repair_protocol", None)
    ):
        raise ValueError("Service lifecycle/retry operations require a service-reuse campaign")
    if plan["runtime_identity"] != _runtime_identity():
        raise ValueError("Optimization runtime changed, use its frozen runtime to resume")
    if args.session_action == "status":
        return optimization.status(root)
    if args.session_action == "diagnose":
        return optimization.record_diagnosis(root, args.bottleneck, args.evidence)
    if args.session_action == "knowledge":
        if knowledge_reader is None or retain_context is None:
            raise ValueError("A knowledge reader and capture callback are required")
        return optimization.capture_context(
            root,
            knowledge_reader,
            retain_context=retain_context,
            external_provider=external_provider,
            external_provider_for=external_provider_for,
            query="",
            relevance=args.query,
            relevance_method=args.relevance_method,
            scenario=getattr(args, "scenario", None),
            context_bytes=args.context_bytes,
            limit=args.limit,
        )
    if args.session_action == "knowledge-read":
        return optimization.read_external_context(
            root, external_provider, search_ref=args.search_ref, locator=args.locator,
            page=args.page, external_provider_for=external_provider_for,
        )
    if args.session_action == "recover":
        return optimization.recover(
            root, _session_assess, confirm_domain_empty=getattr(args, "confirm_domain_empty", False)
        )
    final = args.session_action == "final"
    mechanism = None
    if not final and getattr(args, "mechanism_file", None) is not None:
        if plan.get("task_source") != "project":
            raise ValueError("Mechanism checks apply to project campaign rounds only")
        from inferrsi.harness.measurement import CONFIDENCE, min_pairs, validate_mechanism

        mechanism = validate_mechanism(
            json.loads(Path(args.mechanism_file).read_text(encoding="utf-8")))
        settings = plan["evaluation_settings"]
        needed = min_pairs(1 - (1 - CONFIDENCE) / len(mechanism["expect"]))
        if settings.get("require_explanation") and needed > settings["repetitions"]:
            # Reject before execution so an uncheckable declaration spends no round.
            raise ValueError(
                f"{len(mechanism['expect'])} expectations need {needed} repetitions under "
                f"--require-explanation; the campaign froze {settings['repetitions']}. "
                "Declare fewer expectations")
    return optimization.evaluate_round(
        root, candidate=None if final else args.candidate,
        hypothesis="Independent final of the selected candidate" if final else args.hypothesis,
        usage=args.usage_export, execute=_session_execute, assess=_session_assess, final=final,
        reason=getattr(args, "reason", None),
        strategy=getattr(args, "strategy", None),
        alternatives=getattr(args, "alternative", None),
        selection_reason=getattr(args, "selection_reason", None),
        knowledge_refs=getattr(args, "knowledge_ref", None),
        mechanism=mechanism,
    )


def _nested_trial(execute_trial, directory, sequence, *args, **kwargs):
    return execute_trial(
        *args, launch_path=directory / f"launch-nested-{next(sequence):04d}.json", **kwargs
    )


def _run_entry(entry: str, arguments: list[str], *, launch_directory: Path | None = None) -> None:
    # Direct-file launch avoids importing a caller's cwd/inferrsi.py. Once the
    # bundled runner is selected, remove its directory so task imports cannot
    # resolve generic names such as project or candidates from Harness.
    runner = Path(__file__).resolve().parent
    sys.path[:] = [path for path in sys.path if Path(path).resolve() != runner]
    # Extended-path launches on Windows may leave cwd before PYTHONPATH. Select
    # this runner's package root explicitly before importing its executor.
    runtime_root = str(runner.parent.parent)
    sys.path.insert(0, runtime_root)
    try:
        from inferrsi.harness.trials.external import execute_trial
    finally:
        sys.path.remove(runtime_root)

    if launch_directory is not None:
        execute_trial = partial(_nested_trial, execute_trial, launch_directory, count(1))
    sys.argv = [entry, *arguments]
    sys.path.insert(0, str(Path(entry).parent))
    runpy.run_path(entry, run_name="__main__", init_globals={"execute_trial": execute_trial})


if __name__ == "__main__":
    if sys.argv[1] == "--session-launch-directory":
        _run_entry(sys.argv[3], sys.argv[4:], launch_directory=Path(sys.argv[2]))
    else:
        _run_entry(sys.argv[1], sys.argv[2:])
