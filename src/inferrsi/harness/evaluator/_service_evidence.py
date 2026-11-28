"""Validate the retained receipts that underlie service-reuse campaign decisions."""

from pathlib import Path

from ..records import service_io
from . import _service


def service_reference_snapshot(reference):
    """Retain selection evidence. The source attempt owns its optional inline profile."""
    if not reference:
        return reference
    snapshot = dict(reference)
    snapshot.pop("profile", None)
    if snapshot.get("parent_reference_at_acceptance"):
        snapshot["parent_reference_at_acceptance"] = service_reference_snapshot(
            snapshot["parent_reference_at_acceptance"]
        )
    return snapshot


def service_choice(pending, execution):
    return {
        **({k: pending[k] for k in ("stage_id", "stage_protocol", "protocol_id")}
           if "stage_id" in pending else {}),
        "kind": "candidate" if pending["role"] == "candidate" else "baseline",
        "attempt_id": pending["attempt_id"],
        "candidate_id": pending["candidate_id"],
        "path": pending["path"] + "/candidate",
        "revision": pending["revision"],
        "source_repo": pending.get("source_repo"),
        "conditions": pending["conditions"],
        "reference_epoch": pending["reference_epoch"],
        "effective_config_path": pending["path"] + "/effective-config.json",
        "measurements": execution["measurements"],
        "quality_score": execution["quality_score"],
        "protocol_path": pending["protocol_path"],
        "binding": execution["binding"],
        "parent_reference_at_acceptance": (
            {
                key: value
                for key, value in pending["parent"].items()
                if key not in ("profile", "parent_reference_at_acceptance")
            }
            if pending.get("parent")
            else None
        ),
    }


def service_reference_result(root, directory, plan, job, result):
    """Verify cleanup independently of the quality and performance receipts."""
    try:
        binding = result["binding"]
        owner = service_io.read(service_io.safe_path(directory, "service/owner.json"))
        stop = service_io.read(service_io.safe_path(directory, "execution/stop/result.json"))
        cleaned = (
            result["cleanup_verified"] is True
            and owner["domain_empty"] is True
            and all(owner.get(k) == v for k, v in binding.items())
            and stop.get("binding") == binding
            and stop["cleanup_complete"] is True
        )
    except (KeyError, ValueError, OSError, TypeError, AttributeError):
        return False, False
    assessment = result.get("assessment") or {}
    performance_only = job.get("reference_kind") == "final_baseline"
    valid = (
        cleaned
        and result.get("status") == "completed"
        and (performance_only or service_io.finite_number(result.get("quality_score")))
        and isinstance(assessment, dict)
        and assessment.get("verdict") in ("PASS", "FAIL")
        and assessment.get("reason") in (
            ("performance_reference_refreshed",) if performance_only else
            ("fixed_checks_satisfied", "quality_gate_not_met")
        )
        and not evaluation_reason(
            root, plan, {**job, "execution": result, "assessment": assessment}
        )
    )
    return cleaned, valid


def final_baseline_job(plan, final):
    return {
        **final, "role": "baseline", "candidate_id": "baseline", "reference_kind": "final_baseline",
        "attempt_id": final["attempt_id"] + "-baseline", "path": final["path"] + "/baseline",
        "source_repo": plan["working_candidate"], "revision": plan["baseline_revision"],
        "initial": None, "parent": None,
    }


def evaluation_reason(root, plan, record):
    """Recheck the required receipts and gates for a reference, candidate or final run."""
    execution, assessed = record["execution"], record["assessment"]
    try:
        directory = service_io.safe_path(root, record["path"])
        expected = execution["binding"]
        if (
            any(expected[key] != record[key] for key in ("attempt_id", "revision", "conditions"))
            or ("stage_id" in record and any(expected.get(k) != record.get(k) for k in
                ("stage_id", "stage_protocol", "protocol_id", "reference_epoch")))
            or not expected["service_id"]
            or not expected["run_id"]
            or service_io.read(directory / "request.json") != expected
        ):
            return "unverifiable_selected_attempt_binding"
        config = record["conditions"]["effective_config"]
        try:
            actual_config = service_io.read(directory / "effective-config.json")
        except (ValueError, OSError):
            return "unverifiable_selected_configuration"
        if expected["effective_config"] != config or actual_config != config:
            return "unverifiable_selected_configuration"

        def receipt(stage):
            path = service_io.safe_path(directory, "execution/" + stage + "/result.json")
            doc = service_io.read(path)
            if doc.get("binding") != expected:
                raise ValueError("Incompatible stage binding")
            return doc

        if plan.get("stage_parent_only") and record["role"] == "final":
            job = final_baseline_job(plan, record)
            child = service_io.safe_path(root, job["path"])
            run = service_io.read(service_io.safe_path(child, "execution/execution.json"))
            _, valid = service_reference_result(root, child, plan, job, run)
            if not valid or execution.get("final_baseline") != service_choice(job, run):
                return "unverifiable_final_baseline"

        precheck_path = service_io.safe_path(directory, "execution/precheck/result.json")
        precheck = service_io.read(precheck_path)
        if assessed["reason"] == "functional_check_rejected":
            status = precheck.get("status")
            rejected = status == "candidate_failure" or (
                status == "completed" and precheck.get("passed") is False
            )
            retained = next(
                (step.get("result") for step in execution["steps"] if step["id"] == "precheck"),
                None,
            )
            if not rejected or retained != precheck or assessed["verdict"] != "FAIL":
                return "unverifiable_evaluation_evidence"
            return None
        owner = service_io.read(service_io.safe_path(directory, "service/owner.json"))
        ready = receipt("ready")
        if (
            precheck.get("passed") is not True
            or precheck.get("status") != "completed"
            or ready.get("status") != "completed"
            or not _service.service_ready(ready, revision=expected["revision"], pid=owner["pid"])
            or ready.get("loaded_root") != owner["cwd"]
            or any(owner.get(k) != v for k, v in expected.items())
        ):
            return "unverifiable_evaluation_evidence"
        settings = plan["evaluation_settings"]
        role = record["role"]
        sampling = settings["sampling"][role]
        for i in range(sampling["warmups"]):
            if receipt(f"warmup-{i + 1:03d}").get("status") != "completed":
                return "unverifiable_evaluation_evidence"
        docs = [receipt(f"measure-{i + 1:03d}") for i in range(sampling["repetitions"])]
        if any(doc.get("status") != "completed" for doc in docs):
            return "unverifiable_evaluation_evidence"
        measured = _service.aggregate_service_measurements(settings, docs, role)
        if measured != execution["measurements"]:
            return "unverifiable_evaluation_evidence"
        gate = _service.service_trial_gate(
            plan, record, measured, final_baseline=execution.get("final_baseline")
        )
        if gate != assessed["performance"]:
            return "unverifiable_evaluation_evidence"
        # Legacy condition refreshes and the independent final baseline collect performance only.
        if record.get("reference_kind") in ("parent", "final_baseline"):
            if assessed["verdict"] != "PASS" or execution["quality_score"] is not None:
                return "unverifiable_evaluation_evidence"
            return None
        passed = gate["passed"]
        if passed or "stage_id" in record:
            reference_path = (
                settings["quality"].get("reference_path") if role == "baseline" and record.get(
                    "reference_kind") not in ("stage_baseline", "stage_parent") else None
            )
            if reference_path:
                protocol = service_io.safe_path(root, record["protocol_path"])
                quality = service_io.read(service_io.safe_path(protocol, reference_path))
                retained = next((s for s in execution["steps"] if s["id"] == "quality"), {})
                if quality != retained.get("result") or retained.get("path") != reference_path:
                    return "unverifiable_evaluation_evidence"
            else:
                quality = receipt("quality")
            if quality.get("status") == "candidate_failure":
                score, passed = None, False
            elif reference_path or quality.get("status") == "completed":
                score = _service.service_quality_score(settings, quality)
                reference = record.get("initial") or record.get("parent")
                passed = _service.service_quality_passed(
                    settings, score, reference["quality_score"] if reference else score
                )
            else:
                return "unverifiable_evaluation_evidence"
            if score != execution["quality_score"] or passed != assessed["quality_passed"]:
                return "unverifiable_evaluation_evidence"
        if assessed["verdict"] != ("PASS" if passed and gate["passed"] else "FAIL"):
            return "unverifiable_evaluation_evidence"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "unverifiable_evaluation_evidence"
    return None


def _reference_records(state):
    for attempt in state["attempts"]:
        if (
            attempt["reference_epoch"] != state["reference_epoch"]
            or attempt["assessment"]["verdict"] != "PASS"
        ):
            continue
        if attempt["kind"] in ("baseline", "round"):
            yield attempt
        if attempt["kind"] == "refresh":
            # A refresh stores both jobs in a single observation. Identical references share a run.
            execution = attempt["execution"]
            for i, (ref, run) in enumerate(zip(execution["references"], execution["runs"])):
                yield {
                    **ref,
                    "role": "baseline",
                    "path": Path(ref["path"]).parent.as_posix(),
                    "reference_kind": (
                        "stage_parent" if "refresh_initial" not in attempt else
                        ("stage_baseline", "stage_parent")[i] if attempt.get("switch_target") else
                        ("initial", "parent")[i]
                    ),
                    "parent": None,
                    "initial": (execution["references"][0] if i and attempt.get("switch_target")
                                else None),
                    "assessment": run["assessment"],
                    "execution": run,
                }


def service_references_reason(root, plan, state, *references):
    """Check the accepted reference chain once per run, including its original measurements."""
    records = {r["attempt_id"]: r for r in _reference_records(state)}
    remaining = [ref for ref in references if ref is not None]
    verified = set()
    while remaining:
        ref = remaining.pop()
        if not isinstance(ref, dict) or not isinstance(ref.get("attempt_id"), str):
            return "unverifiable_selected_attempt_binding"
        record = records.get(ref["attempt_id"])
        if record is None:
            return "unverifiable_selected_attempt_binding"
        expected = service_choice(record, record["execution"])
        for key, value in expected.items():
            if key != "parent_reference_at_acceptance" and ref.get(key) != value:
                return "unverifiable_selected_attempt_binding"
        # The parent snapshot used by final omits its own ancestry.
        if "parent_reference_at_acceptance" in ref:
            parent = ref["parent_reference_at_acceptance"]
            expected_parent = record["parent"]
            if parent is not None and not isinstance(parent, dict):
                return "unverifiable_selected_attempt_binding"
            if (parent or {}).get("attempt_id") != (expected_parent or {}).get("attempt_id"):
                return "unverifiable_selected_attempt_binding"
            if parent is not None:
                remaining.append(parent)
        if "stage_id" in state and any(
            ref.get(k) != state[k] for k in ("stage_id", "stage_protocol", "protocol_id")
        ):
            return "unverifiable_selected_attempt_binding"
        if ref["conditions"] != state["conditions"]:
            return "incompatible_selected_conditions"
        if ref["attempt_id"] in verified:
            continue
        reason = evaluation_reason(root, plan, record)
        if reason:
            return reason
        verified.add(ref["attempt_id"])
        remaining.extend(r for r in (record["initial"], record["parent"]) if r is not None)
    return None


def service_settlement_reason(root, plan, state, record):
    """Recheck the evidence needed to settle this attempt's verdict."""
    kind = record["kind"]
    assessed = record["assessment"]
    if kind not in ("baseline", "round", "final") or assessed["verdict"] not in ("PASS", "FAIL"):
        return None
    if assessed["reason"] == "functional_check_rejected" and kind != "final":
        return None
    reason = evaluation_reason(root, plan, record)
    if reason:
        return reason
    if kind == "baseline":
        return None
    selected = state["best"] if kind == "final" else None
    return service_references_reason(
        root, plan, state, record["parent"], record["initial"], selected
    )
