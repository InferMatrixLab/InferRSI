"""Assemble the shared Harness lifecycle for project and supplied task protocols.

The CLI supplies a task directory only when starting a packaged task. Ordinary
projects and all subsequent operations use Harness and the retained inputs.
"""

import json
import shlex
from functools import partial
from importlib.resources import files
from pathlib import Path


def _runtime_identity():
    from inferrsi.harness.records.artifact_primitives import sha256
    from inferrsi.harness.session_runtime import source_files

    root = Path(str(files("inferrsi")))
    return {name: sha256(root / name) for name in source_files(root)}


def session_command(args, *, ranking_policy_for, assess_packaged, task_source: Path | None = None,
                    knowledge_reader=None,
                    prepare_context=None, external_knowledge=None, external_provider=None,
                    external_project=None, external_provider_for=None,
                    report_metadata=None) -> dict:
    """Run one operation; discovery and knowledge access are supplied by the caller."""
    from inferrsi.harness import evaluator, executor, indexer, optimization

    root = args.session.resolve()
    if args.session_action == "start":
        import math

        from inferrsi.harness.executor import prepare_task_protocol
        from inferrsi.harness.executor.candidates import identity, retain
        from inferrsi.harness.records.artifact_primitives import sha256

        if args.rounds < 1 or any(not math.isfinite(value) or value <= 0 for value in (
            args.max_minutes, args.evaluation_timeout_seconds
        )) or not args.condition.strip() or not args.python.strip():
            raise ValueError("A positive round/time budget and condition label are required")
        if root.exists():
            raise ValueError("Session directory must be new")
        ranking_policy = ranking_policy_for(args.ranking_policy)
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
        allow_continuation = getattr(args, "allow_final_continuation", False)
        if allow_continuation and (
            args.evaluation_mode != "service_reuse" or args.round_mode != "up_to"
        ):
            raise ValueError("Final continuation requires an up-to-budget service-reuse campaign")
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
                    "ranking_policy": ranking_policy.configuration(),
                    "evaluation_timeout_seconds": args.evaluation_timeout_seconds,
                    "evaluation_prefix": evaluation_prefix,
                    "python": args.python,
                    **({"allow_final_continuation": True} if allow_continuation else {}),
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
            from inferrsi.harness.executor import prepare_project

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
            settings = prepare_task_protocol(
                task_source, root / "frozen", shlex.split(args.evaluation_args)
            )
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
                "ranking_policy": ranking_policy.receipt(),
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
                return optimization.service_command(
                    root, args, ranking_policy_for=ranking_policy_for,
                )
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
        return optimization.service_command(root, args, knowledge_reader=knowledge_reader,
                                            ranking_policy_for=ranking_policy_for)
    if (
        args.session_action in ("baseline", "refresh-references", "resume", "profile")
        or getattr(args, "retry_of", None)
        or getattr(args, "repair_reason", None)
        or getattr(args, "cleanup_receipt", None)
        or getattr(args, "repair_protocol", None)
        or getattr(args, "continue_after_final", None) is not None
        or getattr(args, "continuation_reason", None) is not None
    ):
        raise ValueError("Service lifecycle/retry operations require a service-reuse campaign")
    if plan["runtime_identity"] != _runtime_identity():
        raise ValueError("Optimization runtime changed, use its frozen runtime to resume")
    ranking_policy = indexer.resolve_frozen_ranking(
        plan, ranking_policy_for, read_only=args.session_action == "status",
    )
    if args.session_action == "status":
        return optimization.status(root)
    if args.session_action == "diagnose":
        return optimization.record_diagnosis(root, args.bottleneck, args.evidence)
    if args.session_action == "knowledge":
        if knowledge_reader is None or prepare_context is None:
            raise ValueError("A knowledge reader and capture callback are required")
        return optimization.capture_context(
            root,
            knowledge_reader,
            prepare_context=prepare_context,
            ranking_policy=ranking_policy,
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
    assess = partial(evaluator.assess_ordinary, assess_packaged=assess_packaged)
    if args.session_action == "recover":
        return optimization.recover(
            root, assess, confirm_domain_empty=getattr(args, "confirm_domain_empty", False)
        )
    final = args.session_action == "final"
    mechanism = None
    if not final and getattr(args, "mechanism_file", None) is not None:
        if plan.get("task_source") != "project":
            raise ValueError("Mechanism checks apply to project campaign rounds only")
        from inferrsi.harness.evaluator import CONFIDENCE, min_pairs, validate_mechanism

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
        usage=args.usage_export, execute=executor.execute_ordinary, assess=assess, final=final,
        reason=getattr(args, "reason", None),
        strategy=getattr(args, "strategy", None),
        alternatives=getattr(args, "alternative", None),
        selection_reason=getattr(args, "selection_reason", None),
        knowledge_refs=getattr(args, "knowledge_ref", None),
        mechanism=mechanism,
    )
