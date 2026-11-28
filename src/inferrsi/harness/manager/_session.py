"""Assemble the shared Harness lifecycle for project and supplied task protocols.

The CLI supplies a task directory only when starting a packaged task. Ordinary
projects and all subsequent operations use Harness and the retained inputs.
"""

import json
import shlex
import sys
from functools import partial
from pathlib import Path

from ._requests import SessionRequest, StartBenchmarkSession, StartProjectSession


def run_session(
    request: SessionRequest, *, ranking_policy_for, assess_packaged,
    task_source: Path | None = None,
    external_knowledge=None, external_provider=None,
    external_project=None, external_provider_for=None, report_metadata=None,
    complete_project=None,
) -> dict:
    """Run one typed session operation with dependencies supplied by the host."""
    from .. import evaluator, executor, indexer
    from . import _state as state
    from ._runtime import session_runtime_identity

    if not isinstance(request, SessionRequest):
        raise TypeError("run_session requires a managed session request")
    root = request.session.resolve()
    if isinstance(request, (StartProjectSession, StartBenchmarkSession)):
        project = isinstance(request, StartProjectSession)
        initialize = state.initialize
        if project and complete_project is not None:
            initialize = partial(complete_project, initialize=state.initialize)
        from inferrsi.harness.executor import prepare_task_protocol
        from inferrsi.harness.executor.candidates import identity, retain
        from inferrsi.harness.records.artifact_primitives import sha256

        budgets = (request.max_minutes, request.evaluation_timeout_seconds)
        if (type(request.rounds) is not int or request.rounds < 1
                or any(type(value) not in (int, float) or not 0 < value <= sys.float_info.max
                       for value in budgets)
                or not request.condition.strip() or not request.python.strip()):
            raise ValueError("A positive round/time budget and condition label are required")
        max_seconds = request.max_minutes * 60
        if max_seconds > sys.float_info.max:
            raise ValueError("The session time budget must be finite in seconds")
        if request.round_mode not in ("exact", "up_to") or request.knowledge not in ("on", "off"):
            raise ValueError("Choose a supported round mode and knowledge setting")
        if project and (request.evaluation_mode not in ("abba", "service_reuse")
                        or request.decision not in ("point", "paired")
                        or type(request.allow_final_continuation) is not bool
                        or type(request.require_explanation) is not bool):
            raise ValueError("Choose valid project evaluation settings")
        if root.exists():
            raise ValueError("Session directory must be new")
        ranking_policy = ranking_policy_for(request.ranking_policy)
        reserve = (request.final_reserve_seconds if request.final_reserve_seconds is not None
                   else request.evaluation_timeout_seconds)
        if type(reserve) not in (int, float) or not 0 < reserve < max_seconds:
            raise ValueError("Reserve time for final within the total budget")
        evaluation_prefix = shlex.split(request.evaluation_prefix)
        if external_knowledge and request.knowledge != "on":
            raise ValueError("External knowledge requires --knowledge on")
        if (external_knowledge and project
                and request.evaluation_mode == "service_reuse"):
            raise ValueError("External round knowledge requires a benchmark or AB/BA campaign")
        allow_continuation = getattr(request, "allow_final_continuation", False)
        if allow_continuation and request.round_mode != "up_to":
            raise ValueError("Final continuation requires an up-to-budget project campaign")
        if project:
            names = (
                "metric_key",
                "metric_unit",
                "quality_key",
                "quality_benchmark",
                "scope",
                "direction",
                "min_improvement_pct",
                "repetitions",
                "warmups",
                "measure_command",
                "quality_command",
            )
            if request.evaluation_mode == "service_reuse":
                from inferrsi.harness.executor import prepare_service

                if request.evaluation_config is None or any(
                    getattr(request, key) is not None for key in names
                ):
                    raise ValueError(
                        "Service reuse requires --evaluation-config without AB/BA options"
                    )
                if request.decision != "point" or request.require_explanation:
                    # Both switches read AB/BA pairs and per-measurement breakdown/counters;
                    # this mode's optional profiling stage does not produce those inputs.
                    raise ValueError(
                        "--decision paired and --require-explanation apply to AB/BA campaigns"
                    )
                settings = prepare_service(root, request)
                plan = {
                    "schema_version": 3,
                    "condition": request.condition,
                    "round_limit": request.rounds,
                    "max_seconds": max_seconds,
                    "round_mode": request.round_mode,
                    "final_reserve_seconds": reserve,
                    "knowledge_allowed": request.knowledge == "on",
                    "ranking_policy": ranking_policy.configuration(),
                    "evaluation_timeout_seconds": request.evaluation_timeout_seconds,
                    "evaluation_prefix": evaluation_prefix,
                    "python": request.python,
                    **({"allow_final_continuation": True} if allow_continuation else {}),
                    **settings,
                }
                result = initialize(root, plan)
                result["instructions"] = (
                    "Run campaign baseline before candidate search. Record the measured "
                    "bottleneck with campaign diagnose before knowledge or rounds. "
                    "Use campaign round for each "
                    "committed candidate; investigate INCONCLUSIVE results before explicit retry. "
                    "Finish with campaign final; final does not collect a profile."
                )
                return result
            if request.evaluation_config is not None or any(
                getattr(request, key) is None for key in names
            ):
                raise ValueError(
                    "AB/BA requires its existing metric, quality, command and sampling options"
                )
            from inferrsi.harness.executor import prepare_project

            repo = request.repo.resolve()
            if not repo.is_dir() or root.is_relative_to(repo):
                raise ValueError("Campaign output must be outside the editable project")
            identity(repo, request.include)  # Reject invalid inputs before preparation writes.
            specification = {key: getattr(request, key) for key in (
                "metric_key", "metric_unit", "quality_key", "quality_benchmark",
                "scope", "direction",
                "min_improvement_pct", "repetitions", "warmups", "decision",
                "require_explanation")}
            specification.update(measure_command=shlex.split(request.measure_command),
                                 quality_command=shlex.split(request.quality_command))
            settings = prepare_project(root / "frozen", request.protocol.resolve(),
                                       request.instructions.resolve(), specification)
            retain(repo, root / "frozen/baseline", request.include)
            settings["frozen_files"].update({p.relative_to(root / "frozen").as_posix(): sha256(p)
                for p in (root / "frozen/baseline").rglob("*") if p.is_file()})
            candidate = {"task": "project:" + repo.name, "task_source": "project",
                         "candidate_kind": "directory", "candidate_name": "candidate",
                         "candidate_includes": request.include, "baseline_path": "frozen/baseline",
                         "working_candidate": str(repo),
                         "selection": (
                             # Paired mode ranks by the speedup its decision reads.
                             {"direction": "maximize", "initial_score": 1.0,
                              "metric": "paired_median_speedup"}
                             if request.decision == "paired" else
                             {"direction": request.direction, "initial_score": None,
                              "metric": request.metric_key})}
        else:
            if task_source is None:
                raise ValueError("A resolved task resource directory is required to start")
            settings = prepare_task_protocol(
                task_source, root / "frozen", shlex.split(request.evaluation_args)
            )
            (root / "work").mkdir()
            (root / "work/candidate.py").write_bytes((root / "frozen/baseline.py").read_bytes())
            candidate = {"task": request.task, "task_source": "benchmark", "candidate_kind": "file",
                         "candidate_name": "candidate.py", "baseline_path": "frozen/baseline.py",
                         "working_candidate": "work/candidate.py",
                         "selection": {"direction": "maximize", "initial_score": 1.0,
                                       "metric": "speedup"}}
        plan = {"schema_version": 2, "condition": request.condition,
                "round_limit": request.rounds, "max_seconds": max_seconds,
                "round_mode": request.round_mode, "final_reserve_seconds": reserve,
                "knowledge_allowed": request.knowledge == "on",
                "ranking_policy": ranking_policy.receipt(),
                "evaluation_timeout_seconds": request.evaluation_timeout_seconds,
                "evaluation_prefix": evaluation_prefix, "python": request.python,
                "runtime_identity": session_runtime_identity(), **candidate, **settings}
        if allow_continuation:
            plan["allow_final_continuation"] = True
        if external_knowledge:
            plan["external_knowledge"] = external_knowledge
            plan["external_knowledge_project"] = external_project
        if report_metadata is not None:
            plan["report_metadata"] = report_metadata
        result = initialize(root, plan)
        operation = "campaign" if project else "benchmarks session"
        result["instructions"] = (
            f"Read the frozen TASK.md. Record the measured bottleneck with {operation} "
            "diagnose first. When knowledge is permitted, use find with --session, "
            "then execute a selected hit's read_args to read and retain its body. "
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
        if getattr(request, "confirm_domain_empty", False):
            raise ValueError("Service-reuse cleanup requires --cleanup-receipt")
        if request.action == "profile":
            try:
                return state.service_command(
                    root, request, ranking_policy_for=ranking_policy_for,
                )
            except (ValueError, OSError) as exc:
                message = "Campaign lock is busy" if isinstance(exc, BlockingIOError) else str(exc)
                return {
                    "exit_code": 2,
                    "round": request.round,
                    "profiling_error": {
                        "status": "failed", "stage": "campaign", "message": message,
                    },
                }
        if request.action == "knowledge-read":
            raise ValueError("External round knowledge requires a benchmark or AB/BA campaign")
        if getattr(request, "mechanism_file", None) is not None:
            raise ValueError("Mechanism checks apply to AB/BA project campaign rounds only")
        if getattr(request, "alternative", None) is not None or getattr(
                request, "selection_reason", None) is not None:
            raise ValueError("Round decision declarations require a benchmark or AB/BA campaign")
        if getattr(request, "knowledge_ref", None) is not None:
            raise ValueError("Round knowledge references require a benchmark or AB/BA campaign")
        return state.service_command(root, request, ranking_policy_for=ranking_policy_for)
    if (
        request.action in ("baseline", "refresh-references", "resume", "profile")
        or getattr(request, "retry_of", None)
        or getattr(request, "repair_reason", None)
        or getattr(request, "cleanup_receipt", None)
        or getattr(request, "repair_protocol", None)
    ):
        raise ValueError("Service lifecycle/retry operations require a service-reuse campaign")
    if plan["runtime_identity"] != session_runtime_identity():
        raise ValueError("Optimization runtime changed, use its frozen runtime to resume")
    indexer.resolve_frozen_ranking(
        plan, ranking_policy_for, read_only=request.action == "status",
    )
    if request.action == "status":
        return state.status(root)
    if request.action == "diagnose":
        return state.record_diagnosis(root, request.bottleneck, request.evidence)
    if request.action == "knowledge-read":
        return state.read_external_context(
            root, external_provider, search_ref=request.search_ref, locator=request.locator,
            page=request.page, external_provider_for=external_provider_for,
        )
    assess = partial(evaluator.assess_ordinary, assess_packaged=assess_packaged)
    if request.action == "recover":
        return state.recover(
            root, assess, confirm_domain_empty=getattr(request, "confirm_domain_empty", False)
        )
    final = request.action == "final"
    mechanism = None
    if not final and getattr(request, "mechanism_file", None) is not None:
        if plan.get("task_source") != "project":
            raise ValueError("Mechanism checks apply to project campaign rounds only")
        from inferrsi.harness.evaluator import CONFIDENCE, min_pairs, validate_mechanism

        mechanism = validate_mechanism(
            json.loads(Path(request.mechanism_file).read_text(encoding="utf-8")))
        settings = plan["evaluation_settings"]
        needed = min_pairs(1 - (1 - CONFIDENCE) / len(mechanism["expect"]))
        if settings.get("require_explanation") and needed > settings["repetitions"]:
            # Reject before execution so an uncheckable declaration spends no round.
            raise ValueError(
                f"{len(mechanism['expect'])} expectations need {needed} repetitions under "
                f"--require-explanation; the campaign froze {settings['repetitions']}. "
                "Declare fewer expectations")
    return state.evaluate_round(
        root, candidate=None if final else request.candidate,
        hypothesis="Independent final of the selected candidate" if final else request.hypothesis,
        usage=request.usage_export, execute=executor.execute_ordinary, assess=assess, final=final,
        reason=getattr(request, "reason", None),
        strategy=getattr(request, "strategy", None),
        alternatives=getattr(request, "alternative", None),
        selection_reason=getattr(request, "selection_reason", None),
        knowledge_refs=getattr(request, "knowledge_ref", None),
        mechanism=mechanism,
        continue_after_final=getattr(request, "continue_after_final", None),
        continuation_reason=getattr(request, "continuation_reason", None),
    )
