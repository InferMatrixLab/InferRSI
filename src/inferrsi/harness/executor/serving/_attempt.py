"""Execute the service stages and persist the candidate checkpoint before cleanup."""

import os
import time
import uuid

from ... import evaluator
from ...records import service_io
from ...records.atomic_json import atomic_write_json
from ..candidates import members, retain
from ._plan import retain_service_revision
from ._profile import service_capture_diagnostic, validated_profile


def execute_service_attempt(root, directory, plan, pending, deadline):
    """One retained attempt, one owned service, ordered client stages, no silent retry."""
    from .. import runtime_environment
    from ..local_process import supervised_service
    from ..trials.external import execute_trial

    settings = plan["evaluation_settings"]
    conditions = pending["conditions"]
    config = conditions["effective_config"]
    source = directory / "candidate"
    workspace = directory / "workspace"
    expected = {
        "attempt_id": pending["attempt_id"],
        "service_id": uuid.uuid4().hex,
        "run_id": uuid.uuid4().hex,
        "revision": pending["revision"],
        "conditions": conditions,
        "effective_config": config,
    }
    atomic_write_json(directory / "request.json", expected)
    atomic_write_json(directory / "effective-config.json", config)
    receipt = directory / "service.json"
    values = {
        "python": plan["python"],
        "candidate": str(workspace),
        "baseline": str(root / plan["baseline_path"]),
        "service_receipt": str(receipt),
        "effective_config": str(directory / "effective-config.json"),
        "attempt_dir": str(directory),
    }
    environment = runtime_environment()
    environment.update(
        INFERRSI_ATTEMPT_REQUEST=str(directory / "request.json"), PYTHONDONTWRITEBYTECODE="1"
    )
    environment["PYTHONPATH"] = str(workspace) + os.pathsep + environment["PYTHONPATH"]
    end = time.monotonic() + min(plan["evaluation_timeout_seconds"], max(0, deadline - time.time()))
    record = {
        "status": "running",
        "steps": [],
        "cleanup_verified": None,
        "binding": expected,
        "assessment": None,
        "cleanup_timeout_seconds": settings["sampling"]["stage_timeout_seconds"],
        "cleanup_budget_scope": "separate_from_evaluation",
    }
    output = directory / "execution"
    output.mkdir()
    started, process, owner = time.monotonic(), None, None
    standalone = pending.get("kind") == "profile"
    sampling = settings["sampling"]
    profile_timeout = sampling.get("profile_timeout_seconds", sampling["stage_timeout_seconds"])
    capture_started = None

    def save():
        atomic_write_json(output / "execution.json", record)

    def begin_capture():
        nonlocal capture_started
        capture_started = time.monotonic()
        record["capture"] = {
            "id": pending["attempt_id"], "started_at": time.time(), "elapsed_seconds": 0.0,
        }
        save()

    def finish_capture():
        nonlocal capture_started
        record["capture"].update(
            elapsed_seconds=time.monotonic() - capture_started, ended_at=time.time()
        )
        capture_started = None
        save()

    def command(argv):
        for key, val in values.items():
            argv = [arg.replace("{" + key + "}", val) for arg in argv]
        return argv

    def binding(document):
        if document.get("binding") != expected:
            raise ValueError("Service/revision/configuration binding mismatch")

    def stage(name, *, bound=True, argv=None):
        definition = {
            "id": name,
            "status": "running",
            "started_at": time.time(),
            "execution_status": "not_started",
        }
        if capture_started is not None:
            offset = time.monotonic() - capture_started
            definition["capture_offset_seconds"] = offset
            record["capture"]["elapsed_seconds"] = offset
        record["steps"].append(definition)
        save()
        if bound and (process is None or process.poll() is not None):
            raise ValueError(f"Service unavailable before {name}")
        stage_end = time.monotonic() + sampling["stage_timeout_seconds"]
        if name != "stop":
            if capture_started is None:
                stage_end = min(end, stage_end)
            else:
                capture_end = capture_started + profile_timeout
                stage_end = capture_end if name == "profile" else min(stage_end, capture_end)
        executed = execute_trial(
            tuple(command(argv or settings["commands"][name.split("-")[0]])),
            workspace,
            output / name,
            stage_end,
            None,
            environment=environment,
        )
        definition.update(executed, execution_status=executed["status"], ended_at=time.time())
        if isinstance(definition.get("error"), str):
            definition["error"] = service_io.error_excerpt(definition["error"])
        if capture_started is not None:
            record["capture"]["elapsed_seconds"] = time.monotonic() - capture_started
        save()
        if executed["status"] != "completed":
            detail = definition.get("error") or f"exit {executed.get('returncode')}"
            if executed["status"] == "cancelled":
                raise KeyboardInterrupt(service_io.error_excerpt(f"{name}: {detail}"))
            raise ValueError(service_io.error_excerpt(f"{name}: {executed['status']}: {detail}"))
        document = service_io.read(output / name / "result.json")
        if bound:
            binding(document)
            if process.poll() is not None:
                raise ValueError(f"Service exited during {name}")
        candidate_failure = document.get("status") == "candidate_failure" and name.startswith(
            ("precheck", "quality")
        )
        if not candidate_failure and document.get("status") != "completed":
            detail = document.get("error") or document.get("message")
            if not detail:
                detail = f"expected completed stage evidence, got {document.get('status')!r}"
            raise ValueError(service_io.error_excerpt(f"{name}: {detail}"))
        if name != "profile" and not standalone:
            definition["result"] = document
            save()
        return document

    def skipped(names, reason):
        record["steps"].extend(
            {"id": name, "status": "skipped", "reason": reason} for name in names
        )
        save()

    measured, gate, score, profile, quality_ok = None, None, None, None, None

    def evaluate(role):
        nonlocal measured, gate, score, quality_ok
        parent, initial = pending.get("parent"), pending.get("initial")
        screen = settings.get("screening")
        if role == "candidate" and screen:
            try:
                docs = [
                    stage(f"screening-{i + 1:03d}", argv=screen["command"])
                    for i in range(settings["sampling"][role]["repetitions"])
                ]
                preview = evaluator.aggregate_service_measurements(settings, docs, role)
                record["screening"] = evaluator.assess_service_performance(
                    settings,
                    preview,
                    parent["measurements"],
                    initial["measurements"],
                    screening=True,
                )
                record["screening"].update(
                    measurements=preview, estimated_gain=screen["estimated_gain"]
                )
            except Exception as error:
                # A malformed screening receipt is diagnostic; formal measurements follow.
                record["screening"] = {"error": str(error)}
                record["steps"][-1].update(status="failed", reason=str(error))
                save()
        docs = []
        first_failure = None
        for i in range(sampling[role]["repetitions"]):
            name = f"measure-{i + 1:03d}"
            try:
                docs.append(stage(name))
            except (ValueError, TypeError, KeyError, OSError) as error:
                if first_failure is None:
                    first_failure = (name, error)
                step = record["steps"][-1]
                if step["status"] in ("running", "completed"):
                    step["status"] = "failed"
                step["reason"] = str(error)
                save()
                if process.poll() is not None or time.monotonic() >= end:
                    break
        if first_failure is not None:
            record["failed_stage"], error = first_failure
            raise error
        measured = evaluator.aggregate_service_measurements(settings, docs, role)
        target = None
        target_failure = "performance_gate_not_met"
        if role == "candidate" and "candidate_min_improvement_pct" in plan:
            target = {"target_kind": "relative_improvement_pct",
                      "target_value": plan["candidate_min_improvement_pct"]}
        elif role == "final":
            target = plan.get("performance_target")
            target_failure = "final_performance_target_not_met"
        gate = (
            evaluator.assess_service_performance(
                settings, measured, parent["measurements"] if parent is not None else None,
                initial["measurements"], target=target, target_failure=target_failure,
            )
            if parent is not None or target is not None
            else {"passed": True, "metrics": {}}
        )
        decision = evaluator.service_measurement_decision(
            role, pending.get("reference_kind"), gate, settings["quality"],
        )
        if decision.assessment is None:
            if decision.quality_reference:
                reference_step = {
                    "id": "quality",
                    "status": "running",
                    "source": "retained_baseline_reference",
                    "path": decision.quality_reference,
                    "started_at": time.time(),
                }
                record["steps"].append(reference_step)
                save()
                quality = service_io.read(
                    service_io.safe_path(
                        service_io.safe_path(
                            root, pending.get("protocol_path", "frozen/protocol")
                        ),
                        decision.quality_reference,
                    )
                )
                evaluator.check_service_quality_reference(
                    settings, quality, pending["revision"], conditions
                )
                reference_step.update(
                    status="completed", ended_at=time.time(), result=quality
                )
                save()
            else:
                quality = stage("quality")
            if quality.get("status") == "candidate_failure":
                quality_ok = False
            else:
                score = evaluator.service_quality_score(settings, quality)
                quality_ok = evaluator.service_quality_passed(
                    settings,
                    score,
                    (initial.get("quality_score") if initial else score),
                )
            decision = evaluator.service_quality_decision(role, gate, quality_ok)
        for stages, reason in decision.skipped:
            skipped(stages, reason)
        record["assessment"] = decision.assessment

    def checkpoint_candidate():
        quality_step = next(step for step in record["steps"] if step["id"] == "quality")
        record["checkpoint"] = {
            "assessment": record["assessment"],
            "binding": expected,
            "measurements": measured,
            "measurement_results": [
                (output / step["id"] / "result.json").relative_to(root).as_posix()
                for step in record["steps"] if step["id"].startswith("measure-")
            ],
            "quality": quality_step,
            "quality_score": score,
        }
        save()

    def profile_error(name, error):
        step = next((s for s in reversed(record["steps"]) if s["id"] == name), {})
        execution_status = step.get("execution_status")
        if isinstance(error, KeyboardInterrupt) or execution_status == "cancelled":
            status = "interrupted"
        elif isinstance(error, TimeoutError) or execution_status == "timeout":
            status = "timed_out"
        else:
            status = "failed"
        diagnostic = service_capture_diagnostic(
            root, directory, name, status, str(error) or status,
            process_failed=execution_status not in (None, "not_started", "completed"),
        )
        record["profiling_error"] = diagnostic
        step.pop("result", None)
        if step.get("status") in ("running", "completed"):
            step.update(status="failed", reason=diagnostic["message"])
        save()

    def capture_profile():
        nonlocal profile
        if "profile" not in settings["commands"]:
            skipped(("profile",), "not_configured")
            return
        try:
            if not standalone:
                begin_capture()
            trace = stage("profile")
            validated = validated_profile(
                root, directory, pending["attempt_id"], conditions, expected, record["steps"][-1],
                captured=trace,
            )
            if time.monotonic() >= capture_started + profile_timeout:
                raise TimeoutError("Profiling timeout during capture validation")
            profile = validated
            record["profile"] = profile
        except (Exception, KeyboardInterrupt) as error:
            profile_error("profile", error)
        finally:
            if not standalone and capture_started is not None:
                finish_capture()

    try:
        if standalone:
            begin_capture()
        protocol = service_io.safe_path(root, pending.get("protocol_path", "frozen/protocol"))
        values["protocol"] = str(protocol)
        if standalone:
            members(protocol)
            if "profile" not in settings["commands"]:
                raise ValueError("No profiler configured in the retained protocol")
        # Rebuild from Git objects; retained directories can be replaced after acceptance.
        repository = pending.get("source_repo")
        if not repository:
            raise ValueError("Authoritative source repository is unavailable")
        retain_service_revision(
            repository, workspace, plan["candidate_includes"], pending["revision"],
            deadline=capture_started + profile_timeout if standalone else None,
        )
        if not standalone and not source.exists():
            retain(workspace, source, fingerprint=False)
        precheck = stage("precheck", bound=False)
        if not evaluator.service_precheck_passed(precheck):
            skipped(("service", "measurement", "quality", "profile"), "precheck_rejected")
            record["assessment"] = evaluator.service_assessment("FAIL", "functional_check_rejected")
            if standalone:
                detail = precheck.get("error") or precheck.get("message")
                profile_error("precheck", ValueError(service_io.error_excerpt(
                    str(detail or "Functional check rejected")
                )))
            record["cleanup_verified"] = True
        else:
            if standalone and time.monotonic() >= capture_started + profile_timeout:
                record["failed_stage"] = "service"
                raise TimeoutError("Profiling timeout before service startup")
            service_step = {"id": "service", "status": "running", "started_at": time.time()}
            record["steps"].append(service_step)
            save()
            with supervised_service(
                [*plan["evaluation_prefix"], *command(settings["commands"]["service"])],
                workspace,
                environment,
                directory / "service",
                expected,
            ) as (process, owner):
                service_step.update(pid=process.pid, owner_path="service/owner.json")
                save()
                try:
                    ready = stage("ready")
                    if (
                        not evaluator.service_ready(
                            ready, revision=expected["revision"], pid=process.pid
                        )
                        or ready.get("loaded_root") != str(workspace.resolve())
                    ):
                        raise ValueError("Service readiness/ownership unverified")
                    role = pending["role"]
                    for index in range(sampling[role]["warmups"]):
                        stage(f"warmup-{index + 1:03d}")
                    if standalone:
                        capture_profile()
                        record["assessment"] = evaluator.service_assessment(
                            "PASS" if profile else "INCONCLUSIVE", "profile_only", eligible=False
                        )
                    else:
                        evaluate(role)
                        if role == "candidate":
                            checkpoint_candidate()
                            if evaluator.service_profile_eligible(record["assessment"]["reason"]):
                                capture_profile()
                except BaseException:
                    record.setdefault("failed_stage", record["steps"][-1]["id"])
                    raise
                finally:
                    try:
                        cleanup = stage("stop", bound=False)
                        binding(cleanup)
                        record["external_cleanup_verified"] = (
                            cleanup.get("cleanup_complete") is True
                        )
                    except (OSError, ValueError, KeyError) as error:
                        record["external_cleanup_verified"] = False
                        record["cleanup_error"] = service_io.error_excerpt(str(error))
            record["cleanup_verified"] = (
                owner["domain_empty"] is True and record.get("external_cleanup_verified") is True
            )
            if not record["cleanup_verified"]:
                raise ValueError(record.get("cleanup_error") or "Service cleanup is unverified")
    except (Exception, KeyboardInterrupt) as error:
        failed = record.get(
            "failed_stage", record["steps"][-1]["id"] if record["steps"] else "startup"
        )
        record["assessment"] = evaluator.service_assessment(
            "INCONCLUSIVE",
            service_io.error_excerpt(f"{failed}: {type(error).__name__}: {error}"),
            performance=gate,
            quality_passed=quality_ok,
        )
        if standalone and ("profiling_error" not in record or isinstance(error, KeyboardInterrupt)):
            profile_error(failed, error)
        for definition in record["steps"]:
            if definition["id"] == failed:
                definition.setdefault("execution_status", definition["status"])
                if definition["status"] in ("running", "completed"):
                    definition["status"] = "failed"
                definition["reason"] = service_io.error_excerpt(str(error))
        if owner is not None:
            record["cleanup_verified"] = (
                owner["domain_empty"] is True and record.get("external_cleanup_verified") is True
            )
        elif standalone and not any(step["id"] == "service" for step in record["steps"]):
            record["cleanup_verified"] = True
        for name in ("quality", "profile"):
            if not any(step["id"] == name for step in record["steps"]):
                skipped((name,), "prerequisite_incomplete")
    if capture_started is not None:
        finish_capture()
    if owner is not None:
        service_step.update(
            status="completed" if owner["domain_empty"] is True else "failed",
            ended_at=time.time(),
            returncode=owner["returncode"],
        )
    record.update(
        status="completed",
        measurements=measured,
        quality_score=score,
        profile=profile,
        elapsed_seconds=time.monotonic() - started,
    )
    save()
    return record
