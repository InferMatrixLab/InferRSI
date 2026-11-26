"""Bind the user's final brief to the same frozen inputs used by campaign start."""

import copy
import shlex
import shutil
import tempfile
from pathlib import Path

from ...harness import candidates, optimization, project_service
from ..storage.artifacts import file_lock
from . import task_intake


def _blocked(reason, **details):
    return {"status": "blocked", "execution": "not started", "reason": reason, **details}


def _execution(plan, args, staged):
    # Retain the settings actually produced by Harness (including defaulted options).
    # Implementation version fingerprints do not describe the user's execution choices.
    launch = {
        key: value
        for key, value in plan.items()
        if key not in ("runtime_identity", "runtime_version")
    }
    launch.update(
        protocol=str(args.protocol.resolve()), instructions=str(args.instructions.resolve())
    )
    settings = plan["evaluation_settings"]
    fields = {
        "optimization.repository": plan["working_candidate"],
        "protocol.comparison": args.evaluation_mode,
        "environment.max_minutes": plan["max_seconds"] / 60,
        "environment.rounds": plan["round_limit"],
        "protocol.quality_failure_policy": "revert_candidate",
    }
    if args.evaluation_mode == "service_reuse":
        primary = next(obj for obj in settings["objectives"] if obj["id"] == settings["ranking"][0])
        quality = settings["quality"]
        comparison = "at_least" if quality["direction"] == "maximize" else "at_most"
        relative = quality["mode"] == "baseline_comparison"
        fields.update(
            {
                "acceptance.baseline_revision": plan["baseline_revision"],
                "acceptance.metric_key": primary["key"],
                "acceptance.metric_unit": primary["unit"],
                "acceptance.direction": primary["direction"],
                "protocol.quality_metric": quality["key"],
                "protocol.quality_benchmark": quality["dataset"],
                "protocol.quality_comparator": "at_most" if relative else comparison,
                "protocol.quality_limit": quality["tolerance" if relative else "threshold"],
                "protocol.timing_boundary": settings["conditions"]["timing_scope"],
                "optimization.workload": settings["conditions"]["workload"],
                "optimization.model": settings["conditions"]["model"],
                "environment.repetitions": settings["sampling"]["baseline"]["repetitions"],
            }
        )
        if primary["threshold_type"] == "relative_percent":
            fields["acceptance.min_improvement_pct"] = primary["gain_threshold"]
        measure, quality_command = settings["commands"]["measure"], settings["commands"]["quality"]
    else:
        baseline = candidates.identity(staged / plan["baseline_path"])
        launch["baseline_identity"] = baseline
        fields.update(
            {
                "acceptance.baseline_revision": baseline,
                "acceptance.metric_key": settings["metric_key"],
                "acceptance.metric_unit": settings["metric_unit"],
                "acceptance.direction": settings["direction"],
                "acceptance.min_improvement_pct": settings["min_improvement_pct"],
                "protocol.timing_boundary": settings["scope"],
                "environment.repetitions": settings["repetitions"],
            }
        )
        measure, quality_command = settings["measure_command"], settings["quality_command"]
    fields.update(
        {
            "environment.baseline_command": measure,
            "environment.candidate_command": measure,
            "environment.quality_command": quality_command,
        }
    )
    return launch, fields


def _conflicts(conditions, expected, args):
    conflicts = []
    for key, actual in expected.items():
        approved = conditions[key]
        if key == "optimization.repository":
            approved = str(Path(approved).expanduser().resolve())
        elif key.endswith("_command"):
            approved = shlex.split(approved)
        elif (
            key == "acceptance.baseline_revision"
            and args.evaluation_mode == "abba"
            and approved != actual
            and (args.repo / ".git").exists()
        ):
            # A Git pin also requires that the retained inputs belong to that commit.
            if actual == candidates.identity(args.repo, args.include):
                actual = project_service.revision(args.repo, args.include)
        if approved != actual:
            conflicts.append({"field": key, "approved": approved, "actual": actual})
    return conflicts


def start(args, run_session):
    if args.intake is None:
        return _blocked(
            "missing_intake", message="Supply --intake with an approved performance brief."
        )
    path = args.intake.resolve()
    if not path.is_file():
        return _blocked("missing_intake", message="Collect task intake before campaign start.")
    destination = args.session.resolve()
    if destination.exists() or any(
        destination.is_relative_to(p.resolve()) for p in (args.repo, args.protocol)
    ):
        raise ValueError("Use a new campaign directory outside project/protocol")
    try:
        with file_lock(path.with_name(path.name + ".lock")):
            gate, record = task_intake.campaign_gate(path)
            if not gate["task_brief"] or (not args.prepare_intake and not gate["complete"]):
                return gate
            if not args.prepare_intake and "campaign_launch" not in record:
                return _blocked(
                    "unbound_brief", message="Use --prepare-intake and review the executable brief."
                )
            with tempfile.TemporaryDirectory(prefix="inferrsi-intake-") as tmp:
                staged_args = copy.copy(args)
                staged_args.session = Path(tmp) / "campaign"
                frozen = run_session(staged_args, initialize=lambda _, plan: {"plan": plan})
                plan = frozen["plan"]
                launch, expected = _execution(plan, args, staged_args.session)
                brief = gate["task_brief"]
                conflicts = _conflicts(brief["conditions"], expected, args)
                if conflicts:
                    return _blocked("launch_conflict", conflicts=conflicts)
                if args.prepare_intake:
                    return task_intake.prepare_launch(path, record, launch)
                if launch != brief["campaign_launch"]:
                    return _blocked("launch_changed",
                                    message="Prepare and review the changed launch.")
                result = _initialize(staged_args.session, destination, plan, record, gate)
                return {**result, "instructions": frozen["instructions"]}
    except BlockingIOError:
        return _blocked("record_busy", message="Retry when the intake update finishes.")


def _initialize(staged, destination, plan, record, gate):
    conditions = gate["task_brief"]["conditions"]
    plan["performance_target"] = {
        name: conditions["protocol." + name] for name in ("target_kind", "target_value")
    }
    if plan.get("evaluation_mode") == "service_reuse":
        settings = plan["evaluation_settings"]
        primary = next(obj for obj in settings["objectives"] if obj["id"] == settings["ranking"][0])
        if primary["threshold_type"] != "relative_percent":
            # A native absolute/point gain cannot stand in for the reviewed percentage gate.
            plan["candidate_min_improvement_pct"] = conditions["acceptance.min_improvement_pct"]
    else:
        plan["evaluation_settings"]["quality_bound"] = {
            name: conditions["protocol.quality_" + name]
            for name in ("metric", "comparator", "limit")
        }
    receipt = task_intake.attach_record(staged, record, gate)["intake"]
    relative = "plan/intake-" + receipt["sha256"] + ".json"
    task_intake.write_record(staged / relative, receipt)
    plan["intake_receipt"] = relative
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for path in staged.iterdir():
            shutil.move(str(path), destination / path.name)
        result = optimization.initialize(destination, plan)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {**result, "intake": receipt}
