"""Shared, Agent-driven optimization lifecycle for project and packaged tasks."""

import hashlib
import json
import math
import time
import uuid
from functools import cache
from pathlib import Path

from . import candidates
from .artifact_primitives import digest, file_lock, sha256
from .atomic_json import atomic_write_json
from .records.evidence import bounded_record_bytes, sanitized_text
from .records.knowledge_capture import MAX_CONTEXT_CAPTURE_BYTES
from .task_protocol import TaskProtocolError
from .usage import normalize_usage, usage_totals


def _locked(root):
    return file_lock(root / ".session.lock")


def initialize(root: Path, plan: dict) -> dict:
    plan["diagnosis_required"] = True
    if plan.get("evaluation_mode") == "service_reuse":
        return _service_initialize(root, plan)
    if type(plan["round_limit"]) is not int or plan["round_limit"] < 1:
        raise ValueError("rounds must be a positive integer")
    if (type(plan["max_seconds"]) not in (int, float)
            or not math.isfinite(plan["max_seconds"]) or plan["max_seconds"] <= 0):
        raise ValueError("max-minutes must be finite and positive")
    if (root / "state.json").exists():
        raise ValueError("Session already initialized")
    if plan["round_mode"] not in ("exact", "up_to"):
        raise ValueError("Unknown round policy")
    if plan["selection"]["direction"] not in ("minimize", "maximize"):
        raise ValueError("Unknown selection direction")
    reserve = plan["final_reserve_seconds"]
    if type(reserve) not in (int, float) or not 0 < reserve < plan["max_seconds"]:
        raise ValueError("Final reserve must fit within the total time budget")
    started = time.time()
    plan["baseline_sha256"] = candidates.identity(root / plan["baseline_path"])
    atomic_write_json(root / "plan.json", plan)
    state = {
        "schema_version": 1, "plan_digest": digest(plan), "started_at": started,
        "deadline": started + plan["max_seconds"], "state": "active", "rounds": [],
        "contexts": [], "pending": None, "final": None,
        "best": {"path": plan["baseline_path"],
                 "sha256": plan["baseline_sha256"],
                 "score": plan["selection"]["initial_score"], "kind": "baseline"},
    }
    atomic_write_json(root / "campaign.json", {
        "campaign_id": root.name, "managed_optimization": True,
        "plan_digest": digest(plan), "task": plan["task"],
    })
    atomic_write_json(root / "state.json", state)
    return status(root)


def _require_ranking_policy(recorded, effective):
    if (not isinstance(recorded, dict) or not isinstance(effective, dict)
            or type(recorded.get("version")) is not int
            or not isinstance(recorded.get("weights"), dict)
            or any(type(value) not in (int, float) for value in recorded["weights"].values())
            or recorded != effective):
        raise ValueError("Frozen ranking policy changed or is incomplete, use its original runtime")


def resolve_frozen_ranking(plan, ranking_policy_for, *, read_only=False):
    if read_only and "ranking_policy" not in plan:
        return None
    recorded = plan.get("ranking_policy")
    if not isinstance(recorded, dict) or not isinstance(recorded.get("id"), str):
        raise ValueError("Missing frozen ranking policy, use the original runtime to resume")
    if ranking_policy_for is None:
        raise ValueError("A resolver for the frozen ranking policy is required")
    policy = ranking_policy_for(recorded["id"])
    effective = (policy.configuration() if plan.get("evaluation_mode") == "service_reuse"
                 else policy.receipt())
    _require_ranking_policy(recorded, effective)
    return policy


def _check_context_ranking(plan, context):
    if "ranking_policy" in plan:
        _require_ranking_policy(context.get("request", {}).get("ranking_policy"),
                                plan["ranking_policy"])


def _control(root):
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    manifest_header = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    if (
        plan.get("evaluation_mode") == "service_reuse"
        or plan.get("schema_version") == 3
        or manifest_header.get("evaluation_mode") == "service_reuse"
    ):
        from . import project_service as service

        manifest = service.read(root / "campaign.json")
        if (
            plan.get("evaluation_mode") != "service_reuse"
            or plan.get("schema_version") != 3
            or state.get("schema_version") != 2
            or (
                manifest.get("evaluation_mode") != "service_reuse"
                or manifest.get("protocol_id") != plan["evaluation_settings"]["protocol_id"]
                or state.get("protocol_id") != manifest["protocol_id"]
                or manifest.get("diagnosis_required", False)
                != plan.get("diagnosis_required", False)
            )
        ):
            raise ValueError("Incompatible service campaign records")
        if "ranking_policy" in manifest or "ranking_policy" in plan:
            _require_ranking_policy(manifest.get("ranking_policy"), plan.get("ranking_policy"))
        service.no_fingerprints(plan)
        service.no_fingerprints(state)
        return plan, state
    if digest(plan) != state["plan_digest"]:
        raise ValueError("Frozen optimization plan changed")
    manifest = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    if manifest.get("plan_digest") != state["plan_digest"]:
        raise ValueError("Campaign and optimization plan disagree")
    return plan, state


def _read_context(root, reference):
    raw, state = bounded_record_bytes(root, reference.get("path"), MAX_CONTEXT_CAPTURE_BYTES)
    if raw is None:
        raise ValueError(f"Invalid delivered knowledge context ({state})")
    if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
        raise ValueError("Delivered knowledge context changed")
    try:
        record = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Invalid delivered knowledge context (invalid_format)") from None
    if not isinstance(record, dict):
        raise ValueError("Invalid delivered knowledge context (invalid_format)")
    return record


def _load(root, *, read_only=False):
    plan, state = _control(root)
    if plan.get("evaluation_mode") == "service_reuse":
        return _service_load(root, plan, state, read_only=read_only)
    frozen = root / "frozen"
    paths = list(frozen.rglob("*"))
    if frozen.is_symlink() or any(path.is_symlink() for path in paths):
        raise ValueError("Frozen task resources cannot contain symbolic links")
    actual = {p.relative_to(frozen).as_posix(): sha256(p) for p in paths if p.is_file()}
    if actual != plan["frozen_files"]:
        raise ValueError("Frozen task resources changed (content or file set)")
    # The selected path also appears as the baseline or a retained round. Verify
    # its bytes once per load, while comparing every stored digest independently.
    identity = cache(candidates.identity)
    if identity(root / plan["baseline_path"]) != plan["baseline_sha256"]:
        raise ValueError("Frozen baseline changed")
    if identity(root / state["best"]["path"]) != state["best"]["sha256"]:
        raise ValueError("Selected candidate changed")
    diagnoses = _diagnosis_index(state)
    contexts = {}
    for context in state["contexts"]:
        retained = _read_context(root, context)
        if context.get("kind") not in ("external_search", "external_read"):
            _check_context_diagnosis(plan, diagnoses, context, retained)
            _check_context_ranking(plan, retained)
        contexts[context["path"]] = context
    for record in [*state["rounds"], *([state["final"]] if state["final"] else [])]:
        directory = root / record["path"]
        raw = (directory / "observation.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["observation_sha256"]:
            raise ValueError("Retained assessment record changed")
        observation = json.loads(raw)
        if any(observation.get(key) != record.get(key)
               for key in ("candidate_id", "hypothesis", "strategy", "alternatives",
                           "selection_reason")):
            raise ValueError("Round submission differs from the retained observation")
        if any(observation.get(key) != record.get(key) for key in ("knowledge_refs", "contexts")):
            raise ValueError("Round knowledge attribution differs from the retained observation")
        if observation.get("knowledge_refs"):
            submitted = {ref["path"]: ref for ref in observation["contexts"]}
            for ref in observation["knowledge_refs"]:
                path = ref.partition("#")[0]
                if path not in submitted or submitted[path] != contexts.get(path):
                    raise ValueError("Cited knowledge context differs from the submitted snapshot")
        if record is not state["final"] and (
            plan.get("diagnosis_required") or diagnoses or record.get("diagnosis_id")
        ):
            if observation.get("diagnosis_id") != record.get("diagnosis_id"):
                raise ValueError("Round diagnosis differs from the retained observation")
            _check_activity_diagnosis(plan, diagnoses, observation)
        if identity(directory / plan["candidate_name"]) != record["candidate_sha256"]:
            raise ValueError("Retained round candidate changed")
        if sha256(directory / "execution/execution.json") != record["execution_sha256"]:
            raise ValueError("Retained execution record changed")
        source = record["observations"]["usage_source"]
        if source and sha256(directory / "agent-usage.json") != source["sha256"]:
            raise ValueError("Retained usage export changed")
        for name, expected in record["assessment"].get("evidence_files", {}).items():
            if sha256(directory / name) != expected:
                raise ValueError("Retained task evidence changed")
    return plan, state


def status(root: Path) -> dict:
    plan, control = _control(root)
    if plan.get("evaluation_mode") == "service_reuse":
        plan, control = _service_load(root, plan, control, read_only=True)
        return _service_status(root, plan, control)
    _, control = _control(root)
    if control["state"] == "blocked" and control.get("integrity_error"):
        # A diagnostic is still readable after rejected input drift. Never expose
        # a selected score or a usable summary from an invalid evidence tree.
        return {"session": str(root), "state": "blocked", "next_action": "blocked",
                "can_finalize": False, "pending": control["pending"],
                "integrity_error": control["integrity_error"], "summary": None}
    plan, state = _load(root)
    next_action = (
        "record_bottleneck_diagnosis" if plan.get("diagnosis_required") and not _diagnosis(state)
        else "edit_candidate_and_submit_round"
    )
    if len(state["rounds"]) == plan["round_limit"]:
        next_action = "independently_retest_selected_candidate_with_final"
    search_remaining = state["deadline"] - time.time() - plan["final_reserve_seconds"]
    if search_remaining <= 0 and state["final"] is None:
        next_action = ("independently_retest_selected_candidate_with_final"
                       if state["rounds"] and plan["round_mode"] == "up_to"
                       else "search_budget_exhausted_incomplete_session")
    if time.time() >= state["deadline"] and state["final"] is None:
        next_action = "deadline_exhausted_incomplete_session"
    if state["pending"] is not None:
        next_action = "recover_existing_attempt_without_relaunch"
    if state["state"] in ("completed", "blocked"):
        next_action = state["state"]
    return {
        "session": str(root), "state": state["state"], "next_action": next_action,
        "completed_rounds": len(state["rounds"]), "round_limit": plan["round_limit"],
        "remaining_seconds": max(0, state["deadline"] - time.time()),
        "remaining_search_seconds": max(0, search_remaining),
        "round_mode": plan["round_mode"],
        "can_finalize": (state["state"] == "active" and state["pending"] is None
                         and time.time() < state["deadline"] and bool(state["rounds"])
                         and (plan["round_mode"] == "up_to"
                              or len(state["rounds"]) == plan["round_limit"])),
        "task_instructions": str(root / "frozen/TASK.md"),
        "working_candidate": str(root / plan["working_candidate"]),
        "best": state["best"], "pending": state["pending"],
        **({"external_knowledge": plan["external_knowledge"]} if "external_knowledge" in plan
           else {}),
        "latest_observation": state["rounds"][-1] if state["rounds"] else None,
        "diagnosis": _diagnosis(state),
        "summary": str(root / "summary.json") if state["final"] is not None else None,
    }


def _active(state, *, reserve=0):
    if state["state"] != "active" or state["pending"] is not None:
        raise ValueError("Session is complete, blocked or has an unresolved attempt")
    if time.time() >= state["deadline"] - reserve:
        raise ValueError("Optimization deadline exhausted, final evaluation is incomplete")


def _diagnosis(state):
    records = state.get("diagnoses", [])
    if records and records[-1]["reference_epoch"] == state.get("reference_epoch"):
        return records[-1]
    return None


def _diagnosis_index(state):
    index = {}
    records = state.get("diagnoses", [])
    if not isinstance(records, list):
        raise ValueError("Invalid retained bottleneck diagnoses")
    for record in records:
        if (
            not isinstance(record, dict)
            or any(not isinstance(record.get(key), str) or not record[key].strip()
                   for key in ("id", "bottleneck", "measurement_summary"))
            or record["id"] in index
            or "reference_epoch" not in record
            or type(record.get("recorded_at")) not in (int, float)
            or not 0 <= record["recorded_at"] < math.inf
        ):
            raise ValueError("Incomplete or duplicate retained bottleneck diagnosis")
        index[record["id"]] = record
    return index


def _check_activity_diagnosis(plan, diagnoses, activity):
    reference = activity.get("diagnosis_id")
    if reference is None and not plan.get("diagnosis_required"):
        return
    if not isinstance(reference, str) or reference not in diagnoses:
        raise ValueError("Campaign activity lacks a retained bottleneck diagnosis")
    diagnosis = diagnoses[reference]
    if (
        type(activity.get("started_at")) not in (int, float)
        or not 0 <= activity["started_at"] < math.inf
        or diagnosis["recorded_at"] > activity["started_at"]
        or diagnosis["reference_epoch"] != activity.get("reference_epoch")
    ):
        raise ValueError("Diagnosis must precede the activity under the same conditions")


def _check_context_diagnosis(plan, diagnoses, reference, capture):
    if not isinstance(capture, dict):
        raise ValueError("Invalid retained knowledge capture")
    binding = capture.get("diagnosis_binding")
    if binding is None and not plan.get("diagnosis_required") and not reference.get("diagnosis_id"):
        return
    if (
        not isinstance(binding, dict)
        or not isinstance(binding.get("diagnosis_id"), str)
        or binding["diagnosis_id"] != reference.get("diagnosis_id")
        or "reference_epoch" not in binding
    ):
        raise ValueError("Knowledge diagnosis differs from the retained capture")
    _check_activity_diagnosis(plan, diagnoses, binding)


def _context_diagnosis(plan, state):
    reference = _diagnosis_reference(plan, state)
    if reference:
        return {**reference, "reference_epoch": state.get("reference_epoch"),
                "started_at": time.time()}
    return None


def _diagnosis_reference(plan, state):
    diagnosis = _diagnosis(state)
    if diagnosis:
        return {"diagnosis_id": diagnosis["id"]}
    if plan.get("diagnosis_required"):
        raise ValueError("Record measured bottleneck evidence with diagnose first")
    return {}


def _retain_diagnosis(root, plan, state, bottleneck, evidence):
    deadline = (_service_deadline(state) if plan.get("evaluation_mode") == "service_reuse"
                else state["deadline"])
    _active(
        {**state, "deadline": deadline,
         "state": "active" if state["state"] == "needs_baseline" else state["state"]},
        reserve=plan["final_reserve_seconds"],
    )
    bottleneck = bottleneck.strip()
    if not bottleneck or len(bottleneck) > 4096:
        raise ValueError("Bottleneck must be a nonempty description of at most 4096 characters")
    if evidence.is_symlink() or not evidence.is_file():
        raise ValueError("Diagnosis evidence must be a regular UTF-8 measurement summary")
    with evidence.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Diagnosis evidence exceeds 64 KiB; provide a measurement summary")
    summary = raw.decode("utf-8").strip()
    if not summary or "\x00" in summary:
        raise ValueError("Diagnosis evidence must contain a nonempty UTF-8 measurement summary")
    diagnosis = {"id": "diagnosis-" + uuid.uuid4().hex, "bottleneck": bottleneck,
                 "measurement_summary": summary, "reference_epoch": state.get("reference_epoch"),
                 "recorded_at": time.time()}
    state.setdefault("diagnoses", []).append(diagnosis)
    atomic_write_json(root / "state.json", state)
    return {"diagnosis": diagnosis}


def record_diagnosis(root: Path, bottleneck: str, evidence: Path) -> dict:
    with _locked(root):
        plan, state = _load(root)
        return _retain_diagnosis(root, plan, state, bottleneck, evidence)


def _knowledge_round(plan, state):
    _active(state, reserve=plan["final_reserve_seconds"])
    if plan.get("knowledge_allowed") is False:
        raise ValueError("Knowledge delivery is disabled by the frozen condition")
    number = len(state["rounds"]) + 1
    return number if number <= plan["round_limit"] else None


def _knowledge_time(plan, state):
    return state["deadline"] - time.time() - plan["final_reserve_seconds"]


def _store_knowledge(root, kind, number, record):
    directory = root / "knowledge"
    if directory.is_symlink():
        raise ValueError("Knowledge directory must not be a symbolic link")
    directory.mkdir(exist_ok=True)
    path = directory / f"{kind}-{uuid.uuid4().hex}.json"
    atomic_write_json(path, record)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path),
            "kind": kind, "round": number}


def capture_context(root: Path, reader, *, retain_context, external_provider=None,
                    external_provider_for=None, **request) -> dict:
    with _locked(root):
        plan, state = _load(root)
        number = _knowledge_round(plan, state)
        settings = plan.get("external_knowledge")
        if settings:
            if number is None:
                raise ValueError("Round budget consumed, run independent final evaluation")
            if external_provider is None and external_provider_for is None:
                raise ValueError("The frozen external knowledge provider is unavailable")
            request["relevance"] = sanitized_text(request["relevance"], "", limit=None)
        binding = _context_diagnosis(plan, state)
        path, fingerprint = retain_context(root, context_id="context-" + uuid.uuid4().hex,
                                           reader=reader, diagnosis_binding=binding, **request)
        reference = {"path": path.relative_to(root).as_posix(), "sha256": fingerprint,
                     "kind": "delivered_context"}
        # Keep the local tool response compatible with stored Codex trace verification.
        retained = {**reference, "round": number} if number is not None else reference
        if binding:
            retained = {**retained, "diagnosis_id": binding["diagnosis_id"]}
        state["contexts"].append(retained)
        response = {"reference": reference, "context": _read_context(root, reference)}
        if settings:
            remaining = _knowledge_time(plan, state)
            if remaining > 0:
                if external_provider_for is not None:
                    external_provider = external_provider_for(plan)
                result = external_provider.search(request["relevance"], settings=settings,
                                                  limit=request["limit"], timeout=remaining)
            else:
                result = {"state": "timeout", "items": [], "count": 0}
            search = {**result, **settings, "context_ref": reference["path"]}
            search_ref = _store_knowledge(root, "external_search", number, search)
            state["contexts"].append(search_ref)
            response["external"] = {**search, "reference": search_ref}
        atomic_write_json(root / "state.json", state)
        return response


def read_external_context(root: Path, provider, *, search_ref, locator, page,
                          external_provider_for=None):
    with _locked(root):
        plan, state = _load(root)
        number = _knowledge_round(plan, state)
        if not plan.get("external_knowledge") or (
            provider is None and external_provider_for is None
        ):
            raise ValueError("External knowledge is disabled or unavailable for this session")
        if type(page) is not int or page < 1:
            raise ValueError("CANNBot page must be a positive integer")
        reference = next((entry for entry in state["contexts"]
                          if entry["path"] == search_ref and entry["kind"] == "external_search"
                          and entry["round"] == number), None)
        if reference is None:
            raise ValueError("Supply a CANNBot search reference from the current round")
        search = _read_context(root, reference)
        hit = next((item for item in search["items"] if item["locator"] == locator), None)
        if search["state"] != "ok" or not search["revision"] or hit is None:
            raise ValueError("Supply a versioned CANNBot hit from the recorded search")
        remaining = _knowledge_time(plan, state)
        if remaining <= 0:
            raise ValueError("Optimization deadline exhausted, final evaluation time is reserved")
        revision, card_sha256 = search["revision"], hit["card_sha256"]
        if external_provider_for is not None:
            provider = external_provider_for(plan)
        body = provider.read(locator, revision=revision, card_sha256=card_sha256,
                             page=page, timeout=remaining)
        receipt = {"search_ref": search_ref, "channel": search["channel"], "locator": locator,
                   "revision": revision, "card_sha256": card_sha256, "page": page}
        delivered = _store_knowledge(root, "external_read", number, receipt)
        state["contexts"].append(delivered)
        atomic_write_json(root / "state.json", state)
        return {"reference": delivered, "receipt": receipt, "context": body}


def _validate_knowledge_refs(root, contexts, refs):
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("Knowledge references must be a list of delivered references")
    if len(set(refs)) != len(refs):
        raise ValueError("Cite unique delivered knowledge references")
    delivered = {entry["path"]: entry for entry in contexts
                 if entry["kind"] != "external_search"}
    for ref in refs:
        path, separator, item = ref.partition("#")
        reference = delivered.get(path)
        if reference is None or (separator and reference["kind"] != "delivered_context"):
            raise ValueError("Cite a delivered context or CANNBot read receipt from this session")
        if separator:
            capture = _read_context(root, reference)
            if not any(entry["ref"] == item and entry["resources"]
                       for entry in capture["contexts"]):
                raise ValueError("Cite an item with delivered resources from this context")


def _usage_record(source, *, fingerprint=True):
    if source is None:
        return {"usage": None, "tool_calls": None, "usage_source": None}, None
    raw = Path(source).read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Usage export must be a JSON object")
    if not fingerprint:
        from .project_service import no_fingerprints

        no_fingerprints(payload)
    usage = normalize_usage(payload)
    if not usage or usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        raise ValueError("Usage export requires nonnegative input_tokens and output_tokens")
    return ({"usage": usage, "tool_calls": None,
             "usage_source": {"kind": "caller_export", **(
                 {"sha256": hashlib.sha256(raw).hexdigest()} if fingerprint else {})}},
            raw)


def _token_totals(records):
    totals = usage_totals(records)
    fields = ("input_tokens", "output_tokens", "cached_input_tokens", "total_tokens", "cost")
    return {name: totals[name] for name in fields}


def _summary(root, plan, state):
    if plan.get("evaluation_mode") == "service_reuse":
        return _service_summary(root, plan, state)
    rounds = state["rounds"]
    final = state["final"]
    return {
        "schema_version": 1, "task": plan["task"], "condition": plan["condition"],
        "state": state["state"], "planned_rounds": plan["round_limit"],
        "completed_rounds": len(rounds), "selected_candidate": state["best"],
        "final_assessment": final["assessment"] if final else None,
        "optimization_speedup": (
            1.0 if final and final["assessment"]["status"] == "completed"
            and final["assessment"].get("score") is not None
            and state["best"]["kind"] == "baseline"
            else (final["assessment"].get("speedup")
                  if final["assessment"].get("speedup") is not None
                  else (final["assessment"]["score"] if plan["selection"]["metric"] == "speedup"
                        else None)) if final else None
        ),
        "selection": plan["selection"], "stop_reason": state.get("stop_reason"),
        "wall_elapsed_seconds": state.get("settled_at", time.time()) - state["started_at"],
        "usage": _token_totals(rounds), "usage_scope": "caller_round_exports",
        "session_usage_export": final.get("observations") if final else None,
        "knowledge_deliveries": state["contexts"],
        "curve": [
            {"round": index + 1, "hypothesis": item["hypothesis"],
             "assessment": item["assessment"], "best_score": item["best_after"]["score"],
             "cumulative_usage": _token_totals(rounds[:index + 1])}
            for index, item in enumerate(rounds)
        ],
    }


def _type_name(error):
    # A task protocol that raised is recorded under its own exception type across the
    # child transport (#412 R3); any other error under its own Python type.
    return error.type_name if isinstance(error, TaskProtocolError) else type(error).__name__


def _failure(error):
    return {"status": "infrastructure_failure", "score": None,
            "verdict": "INCONCLUSIVE", "reason": f"{_type_name(error)}: {error}"}


def _settle(root, plan, state, pending, execution, assess):
    directory = root / pending["path"]
    # Re-check integrity before accepting a score. Drift is terminal, but must
    # leave a recorded rejection rather than an attempt permanently in pending.
    try:
        _load(root)
        if candidates.identity(directory / plan["candidate_name"]) != pending["candidate_sha256"]:
            raise ValueError("Submitted candidate changed during evaluation")
        bound = pending.get("mechanism_sha256")
        if bound is not None and not (
            digest(pending.get("mechanism")) == bound
            and (directory / "mechanism.json").is_file()
            and not (directory / "mechanism.json").is_symlink()
            and digest(json.loads((directory / "mechanism.json").read_text(encoding="utf-8")))
            == bound
        ):
            raise ValueError("Declared mechanism changed during evaluation")
    except (OSError, ValueError, TypeError, KeyError) as error:
        state["integrity_error"] = str(error)
    try:
        if state.get("integrity_error"):
            raise ValueError(state["integrity_error"])
        if execution.get("coordinator_error"):
            raise ValueError(execution["coordinator_error"])
        # A task result cannot override an interrupted or unknown execution.
        # A normal nonzero exit may carry a deliberate candidate rejection.
        if (execution.get("status") not in ("completed", "failed")
                or type(execution.get("returncode")) is not int
                or execution["returncode"] < 0):
            raise ValueError(
                "Execution did not finish normally; candidate result cannot resume search")
        # Pass the declaration held in memory since before execution; the candidate
        # can write files during execution, including state.json and attempt copies.
        assessment = (assess(root, directory, plan, execution, mechanism=pending["mechanism"])
                      if pending.get("mechanism") is not None
                      else assess(root, directory, plan, execution))
        if not isinstance(assessment, dict) or assessment.get("status") not in (
            "completed", "candidate_failure", "infrastructure_failure"
        ):
            raise ValueError("Unknown task assessment status")
        score = assessment.get("score")
        if assessment["status"] == "completed":
            if execution["status"] != "completed" or execution["returncode"] != 0:
                raise ValueError("Completed assessment requires successful execution")
            # Only a project's frozen paired decision may leave an ineligible round scoreless
            # (its paired statistics can be unavailable); every other assessor must score.
            scoreless = (score is None and assessment.get("eligible") is False
                         and plan.get("task_source") == "project"
                         and plan["evaluation_settings"].get("decision") == "paired")
            if not scoreless and (
                    type(score) not in (int, float) or not math.isfinite(score) or score <= 0):
                raise ValueError("Completed assessment requires a finite positive score")
            if pending["kind"] == "round" and state["best"]["score"] is None:
                baseline_score = assessment.get("baseline_score")
                if (type(baseline_score) not in (int, float)
                        or not math.isfinite(baseline_score) or baseline_score <= 0):
                    raise ValueError("The task must supply the measured baseline objective")
    except Exception as error:
        assessment = _failure(error)
    score = assessment.get("score")
    # Normalized so every record carries the key, even for a scoreless ineligible round.
    assessment["score"] = score if assessment["status"] == "completed" else None
    record = {**pending, "assessment": assessment, "execution": execution,
              "execution_sha256": sha256(directory / "execution/execution.json"),
              "elapsed_seconds": execution.get("elapsed_seconds")}
    if pending["kind"] == "round":
        best_score = state["best"]["score"]
        if best_score is None and assessment["status"] == "completed":
            best_score = assessment["baseline_score"]
            state["best"]["score"] = best_score
        improved = (score is not None and best_score is not None and (
            score < best_score if plan["selection"]["direction"] == "minimize"
            else score > best_score))
        eligible = assessment["status"] == "completed" and assessment.get("eligible", True)
        outcome = ("not_eligible" if not eligible
                   else "not_better_than_best" if not improved
                   else "baseline_identity" if pending["candidate_sha256"] == candidates.identity(
                       root / plan["baseline_path"])
                   else "adopted")
        if outcome == "adopted":
            state["best"] = {"kind": "candidate",
                             "candidate_id": pending["candidate_id"],
                             "path": pending["path"] + "/" + plan["candidate_name"],
                             "sha256": pending["candidate_sha256"], "score": score}
        # Why this round was or was not selected, compared on the frozen selection metric.
        record["selection"] = {"outcome": outcome, "metric": plan["selection"]["metric"],
                               "score": assessment["score"], "best_score_before": best_score}
        record["best_after"] = dict(state["best"])
        state["rounds"].append(record)
    else:
        state["final"] = record
        state["state"] = "completed" if assessment["status"] == "completed" else "blocked"
    if assessment["status"] == "infrastructure_failure":
        state["state"] = "blocked"
    if state["state"] in ("completed", "blocked"):
        state["settled_at"] = time.time()
    state["pending"] = None
    atomic_write_json(directory / "observation.json", record)
    record["observation_sha256"] = sha256(directory / "observation.json")
    atomic_write_json(root / "state.json", state)
    summary = _summary(root, plan, state)
    if state.get("integrity_error"):
        summary.update(integrity_error=state["integrity_error"], optimization_speedup=None,
                       selected_candidate=None)
    atomic_write_json(root / "summary.json", summary)
    return status(root)


def evaluate_round(root: Path, *, candidate: Path | None, hypothesis: str,
                   usage: Path | None, execute, assess, final=False, reason=None,
                   strategy=None, knowledge_refs=None, alternatives=None, selection_reason=None,
                   mechanism: dict | None = None) -> dict:
    with _locked(root):
        plan, state = _load(root)
        _active(state, reserve=0 if final else plan["final_reserve_seconds"])
        count = len(state["rounds"])
        if final and (not count or (plan["round_mode"] == "exact"
                                   and count != plan["round_limit"])):
            raise ValueError("Finish every planned round before independent final evaluation")
        if final and plan["round_mode"] == "up_to" and not (reason or "").strip():
            raise ValueError("Record why search stopped before final evaluation")
        if not final and count >= plan["round_limit"]:
            raise ValueError("Round budget consumed, run independent final evaluation")
        diagnosis = {} if final else _diagnosis_reference(plan, state)
        if not final and (not isinstance(hypothesis, str) or not hypothesis.strip()):
            raise ValueError("Declare the round hypothesis before execution")
        if strategy is not None and (not isinstance(strategy, str) or not strategy.strip()):
            raise ValueError("Strategy must be a nonempty declaration")
        if alternatives is not None and (
            not isinstance(alternatives, list)
            or any(not isinstance(option, str) or not option.strip() for option in alternatives)
        ):
            raise ValueError("Each round alternative must be a nonempty declaration")
        if selection_reason is not None and (
            not isinstance(selection_reason, str) or not selection_reason.strip()
        ):
            raise ValueError("Selection reason must be a nonempty declaration")
        if knowledge_refs is not None:
            _validate_knowledge_refs(root, state["contexts"], knowledge_refs)
        source = root / state["best"]["path"] if final else Path(candidate)
        if (source.is_symlink() or (plan["candidate_kind"] == "file"
                and (not source.is_file() or source.suffix != ".py"))
                or (plan["candidate_kind"] == "directory" and not source.is_dir())):
            raise ValueError("Candidate does not match the frozen input format")
        observations, usage_bytes = _usage_record(usage)
        parent = "final" if final else f"rounds/round-{count + 1:02d}"
        relative = parent + "/attempt-" + uuid.uuid4().hex
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=False)
        if usage_bytes is not None:
            (directory / "agent-usage.json").write_bytes(usage_bytes)
        fingerprint = candidates.retain(source, directory / plan["candidate_name"],
                                        plan.get("candidate_includes"))
        if final and state["best"]["kind"] == "candidate":
            # The independent final rechecks the mechanism bound to the selected round.
            mechanism = next((r.get("mechanism") for r in state["rounds"]
                              if r["candidate_id"] == state["best"]["candidate_id"]), None)
        mechanism_sha256 = None
        if mechanism is not None:
            atomic_write_json(directory / "mechanism.json", mechanism)
            mechanism_sha256 = digest(mechanism)
        pending = {"kind": "final" if final else "round", "path": relative,
                   "candidate_id": state["best"].get("candidate_id", "baseline") if final
                   else f"candidate-{count + 1:03d}",
                   "hypothesis": hypothesis, "strategy": strategy,
                   "knowledge_refs": knowledge_refs, "observations": observations,
                   **diagnosis,
                   "mechanism": mechanism, "mechanism_sha256": mechanism_sha256,
                   "candidate_sha256": fingerprint,
                   "contexts": list(state["contexts"]), "started_at": time.time()}
        if alternatives:
            pending["alternatives"] = list(alternatives)
        if selection_reason is not None:
            pending["selection_reason"] = selection_reason
        state["pending"] = pending
        if final:
            state["stop_reason"] = reason or "fixed_round_budget_completed"
        atomic_write_json(root / "state.json", state)
        deadline = state["deadline"] - (0 if final else plan["final_reserve_seconds"])
        try:
            execution = execute(root, directory, plan, deadline)
        except Exception as error:
            # A completed child may have persisted its receipt before the caller
            # failed. Collect it without launching the same candidate again.
            path = directory / "execution/execution.json"
            atomic_write_json(directory / "coordinator-error.json", {
                "type": _type_name(error), "error": str(error)})
            if path.is_file():
                execution = json.loads(path.read_text(encoding="utf-8"))
            else:
                execution = {"status": "error", "returncode": None,
                             "coordinator_error": str(error), "cleanup_verified": None}
                # No receipt does not prove termination. The resulting blocked
                # session cannot launch more work or claim device cleanup.
                path.parent.mkdir(exist_ok=True)
                atomic_write_json(path, execution)
        return _settle(root, plan, state, pending, execution, assess)


def read_records(root: Path) -> tuple[dict, dict, dict]:
    """Read one validated state for status, dashboard and reconstructable summaries."""
    plan, state = _load(root, read_only=True)
    summary = _summary(root, plan, state)
    if plan.get("evaluation_mode") == "service_reuse":
        from . import service_observations

        state = service_observations.selection_view(state, state["attempts"])
    return plan, state, summary


def recover(root: Path, assess) -> dict:
    with _locked(root):
        _, control = _control(root)
        if control["state"] == "blocked" and control.get("integrity_error"):
            return status(root)
        plan, state = _load(root)
        pending = state["pending"]
        if pending is None:
            atomic_write_json(root / "summary.json", _summary(root, plan, state))
            return status(root)
        path = root / pending["path"] / "execution/execution.json"
        if not path.is_file():
            raise ValueError("Execution record unavailable, inspect cleanup before recovery")
        execution = json.loads(path.read_text(encoding="utf-8"))
        if pending.get("mechanism") is not None or pending.get("mechanism_sha256") is not None:
            # The candidate ran with write access to every file that could hold the
            # declaration after submission, so an interrupted attempt cannot prove which
            # declaration was bound. Settle it without one: the explanation is reported as
            # not declared and, under require_explanation, the round is not adopted.
            pending = {**pending, "mechanism": None, "mechanism_sha256": None,
                       "mechanism_unverified_after_recovery": True}
        return _settle(root, plan, state, pending, execution, assess)


def _service_initialize(root, plan):
    from . import project_service as service

    service.validate(plan["evaluation_settings"])
    if (
        type(plan["round_limit"]) is not int
        or plan["round_limit"] < 1
        or (
            plan["round_mode"] not in ("up_to", "exact")
            or not service.positive(plan["max_seconds"])
            or not service.positive(plan["evaluation_timeout_seconds"])
            or not service.positive(plan["final_reserve_seconds"])
            or plan["final_reserve_seconds"] >= plan["max_seconds"]
        )
    ):
        raise ValueError("Invalid service campaign round/time budget")
    started = time.time()
    state = {
        "schema_version": 2,
        "protocol_id": plan["evaluation_settings"]["protocol_id"],
        "state": "needs_baseline",
        "started_at": started,
        "deadline": started + plan["max_seconds"],
        "pending": None,
        "rounds": [],
        "attempts": [],
        "contexts": [],
        "recovery_events": [],
        "reference_epoch": 0,
        "protocol_path": "frozen/protocol",
        "conditions": plan["evaluation_settings"]["conditions"],
        "requires_current_conditions_acceptance": False,
        "accepted_attempt_ids": [],
        "initial_reference": None,
        "comparison_parent": None,
        "best": None,
        "final": None,
        "stop_reason": None,
        "stagnation": {"consecutive": 0, "notified": False, "events": []},
    }
    atomic_write_json(root / "plan.json", plan)
    atomic_write_json(
        root / "campaign.json",
        {
            "campaign_id": root.name,
            "managed_optimization": True,
            "evaluation_mode": "service_reuse",
            "protocol_id": state["protocol_id"],
            "diagnosis_required": plan.get("diagnosis_required", False),
            **({"ranking_policy": plan["ranking_policy"]} if "ranking_policy" in plan else {}),
        },
    )
    atomic_write_json(root / "state.json", state)
    return _service_status(root, plan, state)


def _service_runtime_matches(plan):
    from inferrsi import __version__

    return plan.get("runtime_version") == __version__


def _service_load(root, plan, state, *, read_only=False):
    from . import project_service as service
    from . import service_observations

    if not read_only and not _service_runtime_matches(plan):
        raise ValueError("Runtime package version changed; use the recorded version to resume")
    service.validate(plan["evaluation_settings"])
    if service.read(root / "frozen/evaluation.json") != plan["evaluation_settings"]:
        raise ValueError("Retained protocol and plan disagree")
    service.validate_conditions(state["conditions"])
    candidates.members(service.safe_path(root, state["protocol_path"]))
    candidates.members(service.safe_path(root, plan["baseline_path"]))
    diagnoses = _diagnosis_index(state)
    for attempt in state["attempts"]:
        if not service_observations.matches_control(root, attempt):
            raise ValueError("Retained attempt and control record disagree")
        if attempt["kind"] == "round":
            _check_activity_diagnosis(plan, diagnoses, attempt)
    for context in state["contexts"]:
        retained = service.read(service.safe_path(root, context["path"]))
        _check_context_ranking(plan, retained)
        _check_context_diagnosis(plan, diagnoses, context, retained)
    for event in state["recovery_events"]:
        if event["kind"] == "cleanup_inspection":
            proof = service.read(service.safe_path(root, event["path"]))
            if (
                proof["attempt_id"] != event["attempt_id"]
                or proof.get("cleanup_complete") is not True
            ):
                raise ValueError("Retained cleanup inspection is incomplete")
    if state["best"] is not None:
        candidates.members(service.safe_path(root, state["best"]["path"]))
    return plan, state


def _service_profiling(root, attempt, *, published=None):
    from . import project_service as service
    from . import service_backfill

    profile = (
        published
        or service_backfill.latest(root, attempt)
        or service.attempt_profile(root, attempt)
    )
    if not profile:
        return {"available": False}
    return {"available": True, "result": profile["result"], "artifacts": profile["artifacts"]}


def _service_round_view(root, attempt, *, profiling=None):
    from . import service_observations

    if attempt["kind"] == "round":
        if profiling is None:
            profiling = _service_profiling(root, attempt)
        return {**service_observations.display(root, attempt), "profiling": profiling}
    return attempt


def _service_account_capture(root, state, pending, execution):
    from . import project_service as service

    capture = execution.get("capture")
    attempt_id = pending["attempt_id"]
    if (
        not isinstance(capture, dict)
        or capture.get("id") != attempt_id
        or not isinstance(execution.get("binding"), dict)
        or execution["binding"].get("attempt_id") != attempt_id
        or not service.number(capture.get("started_at"))
    ):
        return
    ledger = state.setdefault("profiling_accounting", {})
    if attempt_id not in ledger:
        ledger[attempt_id] = {
            "started_at": capture["started_at"],
            "elapsed_seconds": service.proven_capture_elapsed(root, pending, execution),
        }


def _service_deadline(state):
    entries = state.get("profiling_accounting", {}).values()
    return state["deadline"] + sum(entry["elapsed_seconds"] for entry in entries)


def _service_selected_evidence_reason(root, plan, state, *, starting_epoch=False):
    from . import service_evidence

    if (
        state["initial_reference"] is None or state["comparison_parent"] is None
        or state["best"] is None and not starting_epoch
    ):
        return "missing_baseline_reference"
    if state["best"] is not None and "parent_reference_at_acceptance" not in state["best"]:
        return "unverifiable_selected_attempt_binding"
    return service_evidence.references_reason(
        root, plan, state, state["initial_reference"], state["comparison_parent"], state["best"]
    )


def _service_final_reason(root, plan, state, *, budget_time=None):
    if not _service_runtime_matches(plan):
        return "runtime_version_mismatch"
    if state["requires_current_conditions_acceptance"] or (
        state["reference_epoch"] > 0
        and (
            state["best"] is None
            or state["best"]["attempt_id"] not in state["accepted_attempt_ids"]
            or state["best"]["reference_epoch"] != state["reference_epoch"]
        )
    ):
        return "missing_current_conditions_acceptance"
    reason = _service_selected_evidence_reason(root, plan, state)
    if reason:
        return reason
    if state["pending"] is not None or state["state"] != "active":
        return "unresolved_attempt_or_pause"
    completed = sum(item["terminal"] for item in state["rounds"])
    if not completed or plan["round_mode"] == "exact" and completed != plan["round_limit"]:
        return "incomplete_round_policy"
    if (time.time() if budget_time is None else budget_time) >= _service_deadline(state):
        return "deadline_exhausted"
    return None


def _service_status(root, plan, state):
    from . import service_observations

    reason = _service_final_reason(root, plan, state)
    remaining = max(0, _service_deadline(state) - time.time())
    if state["state"] == "completed" and not state["pending"]:
        next_action = "completed"
    elif reason == "runtime_version_mismatch":
        next_action = "use_recorded_runtime_version"
    elif state["state"] == "needs_baseline":
        next_action = "campaign_baseline"
    elif state["pending"]:
        next_action = "recover_existing_attempt_without_relaunch"
    elif state["state"] == "blocked":
        next_action = "investigate_then_explicit_retry_or_resume"
    elif state["state"] == "paused":
        next_action = "resume_after_recorded_analysis"
    elif (plan.get("diagnosis_required") and not _diagnosis(state)
          and len(state["rounds"]) < plan["round_limit"]):
        next_action = "record_bottleneck_diagnosis"
    elif state["requires_current_conditions_acceptance"]:
        next_action = "submit_current_conditions_candidate"
    elif len(state["rounds"]) >= plan["round_limit"]:
        next_action = "independently_retest_selected_candidate_with_final"
    else:
        next_action = "edit_candidate_and_submit_round"
    latest = [_service_round_view(root, attempt) for attempt in state["attempts"][-1:]]
    state = service_observations.selection_view(state, latest)
    return {
        "session": str(root),
        "evaluation_mode": "service_reuse",
        "state": state["state"],
        "next_action": next_action,
        "recorded_runtime_version": plan.get("runtime_version"),
        "can_finalize": reason is None,
        "final_block_reason": reason,
        "completed_rounds": sum(item["terminal"] for item in state["rounds"]),
        "allocated_rounds": len(state["rounds"]),
        "round_limit": plan["round_limit"],
        "remaining_seconds": remaining,
        "remaining_search_seconds": max(0, remaining - plan["final_reserve_seconds"]),
        "round_mode": plan["round_mode"],
        "working_candidate": plan["working_candidate"],
        "best": state["best"],
        "no_candidate_selected": state["best"] is not None and state["best"]["kind"] == "baseline",
        "pending": state["pending"],
        "reference_epoch": state["reference_epoch"],
        "conditions": state["conditions"],
        "accepted_attempt_ids": state["accepted_attempt_ids"],
        "stagnation": state["stagnation"],
        "final": state["final"],
        "latest_observation": state["attempts"][-1] if state["attempts"] else None,
        "diagnosis": _diagnosis(state),
        "summary": str(root / "summary.json"),
    }


def _service_summary(root, plan, state, *, attempts=None, budget_time=None):
    from . import service_observations

    if attempts is None:
        attempts = [_service_round_view(root, attempt) for attempt in state["attempts"]]
    reason = (
        None if state["state"] == "completed"
        else _service_final_reason(root, plan, state, budget_time=budget_time)
    )
    state = service_observations.selection_view(state, attempts)
    return {
        "schema_version": 2,
        "evaluation_mode": "service_reuse",
        "task": plan["task"],
        "condition": plan["condition"],
        "state": state["state"],
        "planned_rounds": plan["round_limit"],
        "completed_rounds": sum(item["terminal"] for item in state["rounds"]),
        "selected_candidate": state["best"],
        "selection": plan["selection"],
        "final_assessment": state["final"]["assessment"] if state["final"] else None,
        "final_block_reason": reason,
        "optimization_speedup": None,
        "reference_epoch": state["reference_epoch"],
        "conditions": state["conditions"],
        "initial_reference": state["initial_reference"],
        "comparison_parent": state["comparison_parent"],
        "accepted_attempt_ids": state["accepted_attempt_ids"],
        "attempts": state["attempts"],
        "knowledge_deliveries": state["contexts"],
        "stagnation": state["stagnation"],
        "usage": _token_totals([item for item in state["attempts"] if item["kind"] == "round"]),
        "usage_scope": "caller_round_attempt_exports",
        "other_attempt_usage": _token_totals(
            [item for item in state["attempts"] if item["kind"] != "round"]
        ),
        "stop_reason": state["stop_reason"],
        "wall_elapsed_seconds": time.time() - state["started_at"],
    }


def _service_settle(root, plan, state, pending, execution):
    from . import project_service as service
    from . import service_evidence

    directory = service.safe_path(root, pending["path"])
    checkpoint = execution.get("checkpoint")
    if checkpoint:
        if not _service_cleanup_confirmed(state, {**pending, "execution": execution}):
            state["state"] = "blocked"
            atomic_write_json(root / "state.json", state)
            return _service_command_result(root, plan, state, execution)
        if (
            execution.get("status") != "completed"
            or execution.get("assessment") != checkpoint["assessment"]
            or execution.get("cleanup_verified") is not True
        ):
            execution.update(
                assessment=checkpoint["assessment"],
                measurements=checkpoint["measurements"],
                quality_score=checkpoint["quality_score"],
                binding=checkpoint["binding"],
                cleanup_verified=True,
                status="interrupted",
            )
            execution.setdefault("elapsed_seconds", time.time() - pending["started_at"])
            if (
                not execution.get("profile")
                and not execution.get("profiling_error")
                and "profile" in plan["evaluation_settings"]["commands"]
                and checkpoint["assessment"]["reason"] in service.INLINE_PROFILE_REASONS
            ):
                execution["profiling_error"] = service.capture_diagnostic(
                    root,
                    directory,
                    "profile",
                    "interrupted",
                    "Capture interrupted before completion; no further error receipt was recorded",
                )
            atomic_write_json(directory / "execution/execution.json", execution)
    path = directory / "observation.json"
    if path.exists():
        record = service.read(path)
        if record["attempt_id"] != pending["attempt_id"]:
            raise ValueError("Recovery attempt identity mismatch")
    else:
        record = {
            **pending,
            "execution": execution,
            "assessment": execution["assessment"],
            "elapsed_seconds": execution.get("elapsed_seconds"),
        }
    if any(item["attempt_id"] == record["attempt_id"] for item in state["attempts"]):
        state["pending"] = None
        return _service_status(root, plan, state)
    reason = service_evidence.settlement_reason(root, plan, state, record)
    if reason:
        record["assessment_before_settlement"] = record["assessment"]
        record["assessment"] = service.assessment(
            "INCONCLUSIVE",
            reason,
            performance=record["assessment"].get("performance"),
            quality_passed=record["assessment"].get("quality_passed"),
        )
    kind = record["kind"]
    verdict = record["assessment"]["verdict"]
    if kind == "round":
        choice = service_evidence.choice(record, record["execution"]) if verdict == "PASS" else None
        record["profiling"] = _service_profiling(root, record)
        record["selected"] = choice is not None and (
            state["best"] is None
            or service.better(
                plan["evaluation_settings"],
                choice["measurements"]["values"],
                state["best"]["measurements"]["values"],
            )
        )
        record["best_after"] = (
            choice if record["selected"] else service_evidence.reference_snapshot(state["best"])
        )
    atomic_write_json(path, record)
    if kind == "baseline":
        if verdict == "PASS":
            choice = service_evidence.choice(record, record["execution"])
            state.update(
                initial_reference=choice, comparison_parent=choice, best=choice, state="active"
            )
        else:
            state["state"] = "blocked"
    elif kind == "refresh":
        if verdict == "PASS":
            initial, parent = record["execution"]["references"]
            state.update(
                initial_reference=initial, comparison_parent=parent, best=None, state="active"
            )
        else:
            state["state"] = "blocked"
    elif kind == "round":
        round_record = state["rounds"][record["round_number"] - 1]
        round_record["attempt_ids"].append(record["attempt_id"])
        round_record["terminal"] = verdict != "INCONCLUSIVE"
        if verdict == "PASS":
            state["accepted_attempt_ids"].append(record["attempt_id"])
            if record["selected"]:
                state.update(
                    best=choice,
                    comparison_parent=choice,
                    requires_current_conditions_acceptance=False,
                )
        state["state"] = "blocked" if verdict == "INCONCLUSIVE" else "active"
        if verdict == "PASS":
            state["stagnation"].update(consecutive=0, notified=False)
        elif verdict != "INCONCLUSIVE":
            stagnation = state["stagnation"]
            stagnation["consecutive"] += 1
            policy = plan["evaluation_settings"]["stagnation"]
            if (
                not policy.get("disabled")
                and not stagnation["notified"]
                and (stagnation["consecutive"] >= policy["rounds"])
            ):
                event = {
                    "id": record["attempt_id"] + "-stagnation",
                    "round": record["round_number"],
                    "consecutive": stagnation["consecutive"],
                    "best": service_evidence.reference_snapshot(state["best"]),
                    "attempt_path": record["path"],
                    "action": policy["action"],
                    "message": "Reassess system-wide critical paths, compute, communication, "
                    "scheduling and resources across scenarios. Use available profiles; "
                    "record evidence gaps, the next hypothesis and restructuring tradeoffs.",
                }
                stagnation["events"].append(event)
                stagnation["notified"] = True
                if policy["action"] == "pause":
                    state["state"] = "paused"
    elif kind == "final":
        state["final"] = record
        state["stop_reason"] = record["hypothesis"]
        if verdict != "INCONCLUSIVE":
            state["state"] = "completed"
        elif not record.get("admission_failure"):
            state["state"] = "blocked"
    _service_account_capture(root, state, pending, record["execution"])
    state["last_profiling_error"] = record["execution"].get("profiling_error")
    state["attempts"].append(record)
    state["pending"] = None
    atomic_write_json(root / "state.json", state)
    atomic_write_json(root / "summary.json", _service_summary(root, plan, state))
    return _service_command_result(root, plan, state, record["execution"])


def _service_command_result(root, plan, state, execution):
    result = _service_status(root, plan, state)
    error = execution.get("profiling_error")
    if error:
        if state["attempts"] and error == state["attempts"][-1]["execution"].get("profiling_error"):
            error = result["latest_observation"]["execution"]["profiling_error"]
        result["profiling_error"] = error
    return result


def _service_execute(root, directory, plan, state, deadline):
    from . import project_service as service

    pending = state["pending"]
    if pending["kind"] != "refresh":
        return service.execute(root, directory, plan, pending, deadline)
    from . import service_evidence, service_observations

    references, runs = [], []
    started = time.monotonic()
    initial = pending["refresh_initial"]
    for label, reference_kind, source in (
        ("baseline", "initial", initial),
        ("parent", "parent", pending["refresh_parent"]),
    ):
        if (
            reference_kind == "parent"
            and source["revision"] == initial["revision"]
            and (
                source["conditions"]["effective_config"]
                == initial["conditions"]["effective_config"]
            )
        ):
            references.append(references[0])
            continue
        relative = pending["path"] + "/" + label
        subdir = service.safe_path(root, relative)
        subdir.mkdir()
        job = {
            **pending,
            "path": relative,
            "revision": source["revision"],
            "source_repo": source.get("source_repo"),
            "attempt_id": pending["attempt_id"] + "-" + label,
            "candidate_id": source["candidate_id"],
            "role": "baseline",
            "reference_kind": reference_kind,
            "parent": None,
            "initial": None,
        }
        result = service.execute(root, subdir, plan, job, deadline)
        runs.append(result)
        if result["assessment"]["verdict"] != "PASS":
            return {
                "assessment": service.assessment("INCONCLUSIVE", "reference_refresh_incomplete"),
                "runs": runs,
                "cleanup_verified": result["cleanup_verified"],
                "elapsed_seconds": time.monotonic() - started,
            }
        references.append(service_evidence.choice(job, result))
    parent_profile = service_observations.reference_view(
        pending["refresh_parent"], service_observations.inline_profiles(state["attempts"])
    )["profile"]
    return {
        "assessment": service.assessment(
            "PASS", "references_refreshed_not_candidate_acceptance", eligible=False
        ),
        "retained_parent_profile": parent_profile,
        "parent_profile_applicability": "not_applicable" if parent_profile else "not_available",
        "references": references,
        "runs": runs,
        "cleanup_verified": True,
        "elapsed_seconds": time.monotonic() - started,
    }


def _service_cleanup_confirmed(state, attempt):
    return attempt.get("execution", {}).get("cleanup_verified") is True or any(
        event["kind"] == "cleanup_inspection" and event["attempt_id"] == attempt["attempt_id"]
        for event in state["recovery_events"]
    )


def _service_cleanup_receipt(root, state, path):
    from . import project_service as service
    from .local_process import _group_empty

    latest = state["pending"] or (state["attempts"][-1] if state["attempts"] else None)
    proof = service.read(path)
    if (
        latest is None
        or proof.get("attempt_id") != latest["attempt_id"]
        or not proof.get("reason")
        or (
            proof.get("cleanup_complete") is not True
            or not service.positive(proof.get("observed_at"))
            or not isinstance(proof.get("services"), list)
            or any(not isinstance(item, dict) for item in proof.get("services", []))
        )
    ):
        raise ValueError(
            "Cleanup inspection must identify the attempt, time, reason and all services"
        )
    directory = service.safe_path(root, latest["path"])
    owners = [
        service.read(service.safe_path(directory, name))
        for name in (
            "service/owner.json",
            "baseline/service/owner.json",
            "parent/service/owner.json",
        )
        if service.safe_path(directory, name).is_file()
    ]
    if len(owners) != len(proof["services"]):
        raise ValueError("Cleanup inspection must cover every recorded service owner")
    for owner in owners:
        matches = [
            item for item in proof["services"] if item.get("service_id") == owner["service_id"]
        ]
        if (
            len(matches) != 1
            or matches[0].get("pid") != owner["pid"]
            or (matches[0].get("domain_empty") is not True)
        ):
            raise ValueError("Cleanup inspection service owner mismatch")
        if (
            owner.get("process_group_id") is not None
            and _group_empty(owner["process_group_id"]) is not True
        ):
            raise ValueError("Recorded process domain is still live or unobservable")
    relative = "recoveries/cleanup-" + uuid.uuid4().hex + ".json"
    (root / "recoveries").mkdir(exist_ok=True)
    atomic_write_json(service.safe_path(root, relative), proof)
    state["recovery_events"].append(
        {"kind": "cleanup_inspection", "attempt_id": latest["attempt_id"], "path": relative}
    )
    atomic_write_json(root / "state.json", state)


def service_command(root, args, *, ranking_policy_for=None, knowledge_reader=None):
    """Service-mode operations inside the shared controller's lock and control record."""
    from . import project_service as service
    from . import service_evidence

    with _locked(root):
        action = args.session_action
        if action == "profile":
            from . import service_backfill

            plan, _ = _control(root)
            resolve_frozen_ranking(plan, ranking_policy_for)
            return service_backfill.run(root, args)
        plan, state = _load(root, read_only=action == "status")
        ranking_policy = resolve_frozen_ranking(plan, ranking_policy_for,
                                                read_only=action == "status")
        if getattr(args, "cleanup_receipt", None) is not None:
            _service_cleanup_receipt(root, state, args.cleanup_receipt)
        if action == "status":
            result = _service_status(root, plan, state)
            latest_by_round = {
                a["round_number"]: a for a in state["attempts"] if a["kind"] == "round"
            }
            result["rounds"] = [
                {
                    "round_number": number,
                    "attempt_id": attempt["attempt_id"],
                    "verdict": attempt["assessment"]["verdict"],
                    "profiling": _service_profiling(root, attempt),
                }
                for number, attempt in latest_by_round.items()
            ]
            return result
        if action == "diagnose":
            return _retain_diagnosis(root, plan, state, args.bottleneck, args.evidence)
        if action == "recover":
            if state["pending"] and state["pending"]["kind"] == "profile":
                from . import service_backfill

                return service_backfill.recover(root, plan, state, args)
            if state["pending"] is None:
                atomic_write_json(root / "summary.json", _service_summary(root, plan, state))
                return _service_command_result(
                    root, plan, state, {"profiling_error": state.get("last_profiling_error")}
                )
            pending = state["pending"]
            directory = service.safe_path(root, pending["path"])
            observation = directory / "observation.json"
            if observation.exists():
                result = service.read(observation)["execution"]
            else:
                try:
                    result = service.read(directory / "execution/execution.json")
                except (OSError, ValueError):
                    if not _service_cleanup_confirmed(state, pending):
                        raise ValueError(
                            "No execution receipt; inspect cleanup before recovery"
                        ) from None
                    result = {"status": "interrupted", "available_evidence_path": pending["path"]}
                if result.get("status") == "running" or result.get("assessment") is None:
                    if not _service_cleanup_confirmed(state, {**pending, "execution": result}):
                        raise ValueError(
                            "Execution incomplete; inspect cleanup and supply --cleanup-receipt"
                        )
                    if not result.get("checkpoint"):
                        result.update(
                            status="interrupted",
                            cleanup_verified=True,
                            assessment=service.assessment(
                                "INCONCLUSIVE", "interrupted_execution_requires_full_retry"
                            ),
                        )
            return _service_settle(root, plan, state, pending, result)
        if action == "knowledge":
            _active(
                {
                    **state,
                    "state": "active" if state["state"] == "needs_baseline" else state["state"],
                    "deadline": _service_deadline(state),
                },
                reserve=plan["final_reserve_seconds"],
            )
            if not plan["knowledge_allowed"] or knowledge_reader is None:
                raise ValueError("Knowledge delivery is disabled or unavailable")
            binding = _context_diagnosis(plan, state)
            context = knowledge_reader.collect_service_context(
                args.query,
                relevance_method=args.relevance_method,
                limit=args.limit,
                context_bytes=args.context_bytes,
                ranking_policy=ranking_policy,
            )
            _check_context_ranking(plan, context)
            if binding:
                context["diagnosis_binding"] = binding
            service.no_fingerprints(context)
            relative = "knowledge/context-" + uuid.uuid4().hex + ".json"
            (root / "knowledge").mkdir(exist_ok=True)
            atomic_write_json(service.safe_path(root, relative), context)
            reference = {
                "path": relative,
                "kind": "delivered_context",
                "prepared_not_consumed": True,
            }
            state["contexts"].append(
                {**reference, "diagnosis_id": binding["diagnosis_id"]} if binding else reference)
            atomic_write_json(root / "state.json", state)
            return {"reference": reference, "context": context}
        if action == "resume":
            if not args.reason.strip() or state["pending"] is not None:
                raise ValueError(
                    "Record investigation before resume; resolve pending execution first"
                )
            latest = state["attempts"][-1] if state["attempts"] else None
            if (
                state["state"] == "active"
                and state["recovery_events"]
                and (
                    state["recovery_events"][-1].get("kind") == "resume"
                    and state["recovery_events"][-1].get("reason") == args.reason
                )
            ):
                return _service_status(root, plan, state)
            if (
                state["state"] not in ("paused", "blocked")
                or latest is None
                or not _service_cleanup_confirmed(state, latest)
                or latest["kind"] in ("baseline", "refresh")
            ):
                raise ValueError("Cannot resume without verified cleanup and usable references")
            state["recovery_events"].append(
                {"kind": "resume", "reason": args.reason, "attempt_id": latest["attempt_id"]}
            )
            state["state"] = "active"
            atomic_write_json(root / "state.json", state)
            return _service_status(root, plan, state)
        retry = getattr(args, "retry_of", None)
        repair = getattr(args, "repair_reason", None)
        repaired_protocol = getattr(args, "repair_protocol", None)
        if repaired_protocol and not retry:
            raise ValueError("Execution script repairs require an explicit --retry-of")
        old = next((item for item in state["attempts"] if item["attempt_id"] == retry), None)
        if retry or repair:
            if (
                not old
                or not repair
                or not repair.strip()
                or old != state["attempts"][-1]
                or (
                    old["assessment"]["verdict"] != "INCONCLUSIVE"
                    or not _service_cleanup_confirmed(state, old)
                    or old["kind"]
                    != {
                        "round": "round",
                        "baseline": "baseline",
                        "refresh-references": "refresh",
                    }.get(action)
                )
            ):
                raise ValueError(
                    "Retry needs the latest inconclusive attempt, a reason and verified cleanup"
                )
        elif state["state"] in ("blocked", "paused"):
            raise ValueError(
                "Investigate and explicitly retry or resume before launching more work"
            )
        if state["pending"] is not None or state["state"] == "completed":
            raise ValueError("Campaign completed or attempt unresolved")
        reserve = 0 if action == "final" else plan["final_reserve_seconds"]
        if time.time() >= _service_deadline(state) - reserve:
            raise ValueError("Campaign budget exhausted; no automatic retry or reduced sampling")
        kind = {
            "round": "round",
            "baseline": "baseline",
            "final": "final",
            "refresh-references": "refresh",
        }.get(action)
        if kind is None:
            raise ValueError("Unknown service campaign action")
        initial, parent = state["initial_reference"], state["comparison_parent"]
        admission = None
        refresh_review = None
        if kind == "baseline":
            if initial is not None:
                raise ValueError("Initial baseline is already measured")
            source, commit = root / plan["baseline_path"], plan["baseline_revision"]
            candidate_id, number = "baseline", None
        elif kind == "round":
            if initial is None or parent is None:
                raise ValueError("Complete baseline and compatible reference refresh first")
            reason = _service_selected_evidence_reason(
                root, plan, state, starting_epoch=state["requires_current_conditions_acceptance"]
            )
            if reason:
                raise ValueError(f"Cannot establish selected parent: {reason}")
            if (
                initial["conditions"] != state["conditions"]
                or parent["conditions"] != state["conditions"]
            ):
                raise ValueError("Refresh both incompatible performance references first")
            diagnosis = _diagnosis_reference(plan, state)
            number = old["round_number"] if old else len(state["rounds"]) + 1
            if number > plan["round_limit"] or not args.hypothesis.strip():
                raise ValueError("Round budget exhausted or hypothesis missing")
            if args.candidate.is_symlink():
                raise ValueError("Candidate root cannot be symbolic")
            source = args.candidate.resolve()
            commit = service.revision(source, plan["candidate_includes"])
            candidate_id = f"candidate-{number:03d}"
            if not old:
                state["rounds"].append({"number": number, "terminal": False, "attempt_ids": []})
        elif kind == "refresh":
            if initial is None or parent is None or not args.reason.strip():
                raise ValueError("Initial references and a change reason required")
            if len(state["rounds"]) >= plan["round_limit"]:
                raise ValueError("No round budget for current-conditions acceptance")
            conditions = service.read(args.conditions)
            service.validate_conditions(conditions)
            if not old:
                if conditions == state["conditions"]:
                    raise ValueError("No changed conditions; reuse compatible retained references")
                if conditions["id"] == state["conditions"]["id"]:
                    raise ValueError("Changed conditions require a new explicit ID")
                if "target_review" in plan["evaluation_settings"]:
                    refresh_review = service.review_service_targets(
                        args.target_review, conditions, plan["baseline_revision"],
                        plan["evaluation_settings"],
                    )
                state.update(
                    conditions=conditions,
                    reference_epoch=state["reference_epoch"] + 1,
                    requires_current_conditions_acceptance=True,
                    accepted_attempt_ids=[],
                )
                state["stagnation"].update(consecutive=0, notified=False)
            elif conditions != old["conditions"]:
                raise ValueError("Reference retry must retain its declared conditions")
            elif args.target_review:
                raise ValueError("Reference retry reuses the retained target review")
            else:
                refresh_review = old.get("target_review")
            source, commit = root / plan["baseline_path"], plan["baseline_revision"]
            candidate_id, number = "reference-refresh", None
        else:
            if plan["round_mode"] == "up_to" and not (args.reason or "").strip():
                raise ValueError("Record why search stopped")
            admission = _service_final_reason(root, plan, state)
            selected = state["best"]
            source = (
                service.safe_path(root, selected["path"])
                if selected
                else root / plan["baseline_path"]
            )
            commit = selected["revision"] if selected else plan["baseline_revision"]
            candidate_id, number = selected["candidate_id"] if selected else "none", None
            parent = selected.get("parent_reference_at_acceptance") if selected else None
        attempt_id = uuid.uuid4().hex
        prefix = (
            f"rounds/round-{number:02d}"
            if kind == "round"
            else (f"references/epoch-{state['reference_epoch']}" if kind == "refresh" else kind)
        )
        relative = prefix + "/attempt-" + attempt_id
        directory = service.safe_path(root, relative)
        directory.mkdir(parents=True)
        protocol_path = state["protocol_path"]
        if kind == "final" and state["best"] is not None:
            protocol_path = state["best"]["protocol_path"]
        if repaired_protocol:
            candidates.retain(repaired_protocol, directory / "protocol", fingerprint=False)
            protocol_path = relative + "/protocol"
            state["protocol_path"] = protocol_path
        observations, raw = _usage_record(getattr(args, "usage_export", None), fingerprint=False)
        if raw is not None:
            (directory / "agent-usage.json").write_bytes(raw)
        if kind == "round":
            service.retain_revision(
                source, directory / "candidate", plan["candidate_includes"], commit
            )
            if service.revision(source, plan["candidate_includes"]) != commit:
                raise ValueError("Candidate revision changed while retaining inputs")
            source_repo = str(source)
        elif kind == "final" and selected:
            source_repo = selected.get("source_repo")
        else:
            source_repo = plan["working_candidate"]
        initial = service_evidence.reference_snapshot(initial)
        parent = service_evidence.reference_snapshot(parent)
        pending = {
            "attempt_id": attempt_id,
            "protocol_path": protocol_path,
            "kind": kind,
            "path": relative,
            "candidate_id": candidate_id,
            "revision": commit,
            "source_repo": source_repo,
            "round_number": number,
            "started_at": time.time(),
            "hypothesis": getattr(args, "hypothesis", None)
            or getattr(args, "reason", None)
            or "Initial baseline",
            "retry_of": retry,
            "repair_reason": repair,
            "role": "candidate" if kind == "round" else "final" if kind == "final" else "baseline",
            "conditions": state["conditions"],
            "reference_epoch": state["reference_epoch"],
            "observations": observations,
            "parent": parent,
            "initial": initial,
            "contexts": list(state["contexts"]),
            "admission_failure": admission,
        }
        if kind == "refresh":
            pending.update(refresh_initial=initial, refresh_parent=parent)
        if kind == "round":
            pending.update(diagnosis)
        if refresh_review is not None:
            pending["target_review"] = refresh_review
        state["pending"] = pending
        atomic_write_json(root / "state.json", state)
        try:
            if admission:
                result = {
                    "assessment": service.assessment("INCONCLUSIVE", admission),
                    "cleanup_verified": True,
                    "elapsed_seconds": 0,
                }
            else:
                result = _service_execute(
                    root, directory, plan, state, _service_deadline(state) - reserve
                )
        except (Exception, KeyboardInterrupt) as error:
            receipt = directory / "execution/execution.json"
            try:
                result = service.read(receipt)
            except (OSError, ValueError):
                result = {"cleanup_verified": None}
            result["assessment"] = service.assessment(
                "INCONCLUSIVE",
                f"coordinator: {error}",
                performance=(result.get("assessment") or {}).get("performance"),
                quality_passed=(result.get("assessment") or {}).get("quality_passed"),
            )
        execution_dir = directory / "execution"
        execution_dir.mkdir(exist_ok=True)
        atomic_write_json(execution_dir / "execution.json", result)
        return _service_settle(root, plan, state, pending, result)
