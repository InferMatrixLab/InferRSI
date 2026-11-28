"""Shared, Agent-driven optimization lifecycle for project and packaged tasks."""

import hashlib
import json
import math
import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory

from inferrsi import __version__

from .. import analyzer, evaluator, indexer
from ..executor import TaskProtocolError, candidates
from ..records import knowledge_capture, service_io
from ..records.artifact_primitives import digest, file_lock, sha256
from ..records.atomic_json import atomic_write_json, durable_write_json
from ..records.evidence import bounded_record_bytes, sanitized_text
from ..records.usage import normalize_usage, usage_totals
from . import _attempt_recovery as attempt_recovery


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


def _control(root):
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    manifest_header = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    if (
        plan.get("evaluation_mode") == "service_reuse"
        or plan.get("schema_version") == 3
        or manifest_header.get("evaluation_mode") == "service_reuse"
    ):
        manifest = service_io.read(root / "campaign.json")
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
                or manifest.get("allow_final_continuation") != plan.get("allow_final_continuation")
            )
        ):
            raise ValueError("Incompatible service campaign records")
        if "ranking_policy" in manifest or "ranking_policy" in plan:
            indexer.require_ranking_policy(
                manifest.get("ranking_policy"), plan.get("ranking_policy")
            )
        service_io.no_fingerprints(plan)
        service_io.no_fingerprints(state)
        return plan, state
    if digest(plan) != state["plan_digest"]:
        raise ValueError("Frozen optimization plan changed")
    manifest = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    if manifest.get("plan_digest") != state["plan_digest"]:
        raise ValueError("Campaign and optimization plan disagree")
    return plan, state


class _FrozenInputError(ValueError):
    pass


def _validate_frozen(root, plan, identity):
    frozen = root / "frozen"
    try:
        paths = list(frozen.rglob("*"))
        if frozen.is_symlink() or any(path.is_symlink() for path in paths):
            raise ValueError("Frozen task resources cannot contain symbolic links")
        actual = {p.relative_to(frozen).as_posix(): sha256(p) for p in paths if p.is_file()}
        if actual != plan["frozen_files"]:
            raise ValueError("Frozen task resources changed (content or file set)")
        if identity(root / plan["baseline_path"]) != plan["baseline_sha256"]:
            raise ValueError("Frozen baseline changed")
    except (OSError, ValueError) as error:
        raise _FrozenInputError(str(error)) from error


def _load(root, *, read_only=False):
    plan, state = _control(root)
    if plan.get("evaluation_mode") == "service_reuse":
        return _service_load(root, plan, state, read_only=read_only)
    # The selected path also appears as the baseline or a retained round. Verify
    # its bytes once per load, while comparing every stored digest independently.
    identity = cache(candidates.identity)
    _validate_frozen(root, plan, identity)
    if identity(root / state["best"]["path"]) != state["best"]["sha256"]:
        raise ValueError("Selected candidate changed")
    diagnoses = _diagnosis_index(state)
    contexts = {}
    for context in state["contexts"]:
        retained = knowledge_capture.read_retained(root, context)
        if context.get("kind") not in ("external_search", "external_read"):
            _check_context_diagnosis(plan, diagnoses, context, retained)
            indexer.check_context_ranking(plan, retained)
        contexts[context["path"]] = context
    for record in [*state["rounds"], *state.get("final_attempts", ()),
                   *([state["final"]] if state["final"] else [])]:
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
        if record["kind"] == "round" and (
            plan.get("diagnosis_required") or diagnoses or record.get("diagnosis_id")
        ):
            if observation.get("diagnosis_id") != record.get("diagnosis_id"):
                raise ValueError("Round diagnosis differs from the retained observation")
            _check_activity_diagnosis(plan, diagnoses, observation)
        if identity(directory / plan["candidate_name"]) != record["candidate_sha256"]:
            raise ValueError("Retained round candidate changed")
        if record["assessment"]["status"] == "interrupted":
            if (record["execution"] is not None or observation.get("execution") is not None
                    or observation.get("recovery") != record.get("recovery")):
                raise ValueError("Interrupted attempt differs from its retained observation")
            attempt_recovery.retained(root, record["recovery"], record["path"])
        elif sha256(directory / "execution/execution.json") != record["execution_sha256"]:
            raise ValueError("Retained execution record changed")
        source = record["observations"]["usage_source"]
        if source and sha256(directory / "agent-usage.json") != source["sha256"]:
            raise ValueError("Retained usage export changed")
        for name, expected in record["assessment"].get("evidence_files", {}).items():
            if sha256(directory / name) != expected:
                raise ValueError("Retained task evidence changed")
    if gate := state.get("cleanup_unconfirmed"):
        _recovery_snapshot(root, gate)
    for reference in state.get("recovery_confirmations", ()):
        attempt_recovery.retained(root, reference, reference["attempt"])
    return plan, state


def status(root: Path) -> dict:
    plan, control = _control(root)
    if plan.get("evaluation_mode") == "service_reuse":
        plan, control = _service_load(root, plan, control, read_only=True)
        return _service_status(root, plan, control)
    if control["state"] == "blocked" and control.get("integrity_error"):
        # A diagnostic is still readable after rejected input drift. Never expose
        # a selected score or a usable summary from an invalid evidence tree.
        return _integrity_status(root, control)
    try:
        plan, state = _load(root)
    except _FrozenInputError:
        if control["pending"] is None:
            raise
        with _locked(root):
            plan, control = _control(root)
            try:
                _validate_frozen(root, plan, candidates.identity)
            except _FrozenInputError as error:
                if control["pending"] is not None:
                    return _reject_frozen_attempt(root, plan, control, error)
                if not control.get("integrity_error"):
                    raise
        return status(root)
    return _ordinary_status(root, plan, state)


def inspect_session_status(root: Path) -> dict:
    """Read retained status without acquiring a lock or resolving a pending attempt."""
    from ._runtime import session_runtime_identity

    plan, control = _control(root)
    if plan.get("evaluation_mode") == "service_reuse":
        plan, state = _service_load(root, plan, control, read_only=True)
        result = _service_status_with_rounds(root, plan, state)
        if result["final_block_reason"] not in _SERVICE_RUNTIME_ERRORS:
            return result
        result["can_continue"] = False
    else:
        if control["state"] == "blocked" and control.get("integrity_error"):
            return _integrity_status(root, control)
        plan, state = _load(root, read_only=True)
        result = _ordinary_status(root, plan, state)
        if plan["runtime_identity"] == session_runtime_identity():
            return result
    result.pop("recovery_command", None)
    return {**result, "read_only": True, "can_finalize": False,
            "next_action": "restore_frozen_runtime"}


def _integrity_status(root, control):
    gate = control.get("cleanup_unconfirmed")
    return {"session": str(root), "state": "blocked", "next_action": "blocked",
            "can_finalize": False, "pending": control["pending"],
            "integrity_error": control["integrity_error"], "summary": None,
            **({"cleanup_unconfirmed": gate} if gate is not None else {})}


def _ordinary_status(root, plan, state):
    next_action = (
        "record_bottleneck_diagnosis" if plan.get("diagnosis_required") and not _diagnosis(state)
        else "edit_candidate_and_submit_round"
    )
    final_eligible = bool(state["rounds"]) and (
        plan["round_mode"] == "up_to" or len(state["rounds"]) == plan["round_limit"]
    )
    if len(state["rounds"]) == plan["round_limit"] or (
        state.get("final_attempts") and final_eligible
    ):
        next_action = "independently_retest_selected_candidate_with_final"
    remaining = state["deadline"] - time.time()
    search_remaining = remaining - plan["final_reserve_seconds"]
    if search_remaining <= 0 and state["final"] is None:
        next_action = ("independently_retest_selected_candidate_with_final"
                       if final_eligible
                       else "search_budget_exhausted_incomplete_session")
    if remaining <= 0 and state["final"] is None:
        next_action = "deadline_exhausted_incomplete_session"
    if state["pending"] is not None:
        next_action = "recover_existing_attempt_without_relaunch"
    if state["state"] in ("completed", "blocked"):
        next_action = state["state"]
    gate = state.get("cleanup_unconfirmed")
    if gate is not None:
        next_action = "confirm_interrupted_process_cleanup"
    return {
        "session": str(root), "state": state["state"], "next_action": next_action,
        "completed_rounds": len(state["rounds"]), "round_limit": plan["round_limit"],
        "remaining_seconds": max(0, remaining),
        "remaining_search_seconds": max(0, search_remaining),
        "round_mode": plan["round_mode"],
        "can_finalize": (state["state"] == "active" and state["pending"] is None
                         and remaining > 0 and final_eligible),
        "task_instructions": str(root / "frozen/TASK.md"),
        "working_candidate": str(root / plan["working_candidate"]),
        "best": state["best"], "pending": state["pending"],
        **({"cleanup_unconfirmed": gate, "recovery_command": "recover --confirm-domain-empty"}
           if gate is not None else {}),
        **({"final_attempts": state["final_attempts"]} if state.get("final_attempts") else {}),
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
    draft = analyzer.diagnosis_draft(bottleneck, evidence)
    diagnosis = {"id": "diagnosis-" + uuid.uuid4().hex, **draft,
                 "reference_epoch": state.get("reference_epoch"), "recorded_at": time.time()}
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


# Only portable Find data goes in an immutable capture. The installed launcher and
# session directory belong to this invocation, not the material's identity.
_HIT = (
    "material_ref", "revision", "body_resource", "material_read_args", "id", "authority", "kind",
    "path", "title", "summary", "state", "score", "source", "source_location", "applicability",
    "limitations", "limitations_withheld", "findings", "findings_withheld",
    "next_read_content_bytes", "matched", "unreadable",
    "repo", "backend", "scenario", "tier", "sources", "locally_verified",
)


def _prepare_scoped_knowledge(
    campaign, step, *, context_id, action, request, items, display,
    assemble_context, contexts=(),
):
    binding = step[1] if step else None
    service = campaign.get("evaluation_mode") == "service_reuse"
    captured_by = f"inferrsi {action} {__version__}"
    selection = {"method": request["relevance_method"], "ranking_applied": action == "find",
                 "state": "applied" if action == "find" else "explicit_ids",
                 "ranking_policy": request["ranking_policy"]}
    observation = {"schema_version": 1, "entrypoint": action, "calls": [action],
                   "request": request, "selection": selection, "display": display,
                   "counts": {"matched": display.get("matched"), "returned": len(items)},
                   "items": [{k: row[k] for k in ("ref", "revision") if k in row} for row in items]}
    facts = {
        "request": request, "selection": selection, "items": items, "omissions": [],
        "context_omissions": [], "context_budget": None,
        "context_bytes_used": sum(c["content_bytes"] for c in contexts),
        "contexts": list(contexts), "retrieval": observation,
    }
    kind = "knowledge_search" if action == "find" else (
        "delivered_context" if facts["context_bytes_used"] else "empty_context"
    )
    if kind == "empty_context":
        observation["receipt_kind"] = kind
        facts["context_omissions"] = [{"ref": items[0]["ref"], "reason": "empty_resource"}]
    path = f"knowledge/{context_id}.json"
    reference = {"path": path, "kind": kind}
    if service:
        document = {**facts, "kind": "service_knowledge_context", "context_id": context_id,
                    "captured_by": captured_by, "prepared_not_consumed": True}
        if action == "find":
            document["source_snapshot"] = f"knowledge/sources/{context_id}"
        if binding:
            document["diagnosis_binding"] = binding
    else:
        document = knowledge_capture.prepare_capture(
            campaign_id=campaign["campaign_id"], context_id=context_id,
            captured_by=captured_by, diagnosis_binding=binding,
            assembled_text=assemble_context(list(contexts)),
            **facts,
        )
        reference["sha256"] = hashlib.sha256(knowledge_capture.capture_bytes(document)).hexdigest()
    return {"reference": reference, "context": document}


def _open_knowledge_search(root, campaign, state, step, location):
    path = Path(location)
    if path.parent.as_posix() != "knowledge" or path.suffix != ".json":
        raise ValueError("Supply a search reference from this campaign")
    if state is not None:
        number, binding = step
        ref = next((entry for entry in state["contexts"] if entry["path"] == location
                    and entry["kind"] == "knowledge_search" and entry.get("round") == number
                    and entry.get("diagnosis_id") == (binding or {}).get("diagnosis_id")), None)
        if ref is None:
            raise ValueError("Supply a Find reference from the current round and diagnosis")
        search = (service_io.read(service_io.safe_path(root, location))
                  if campaign.get("evaluation_mode") == "service_reuse" else
                  knowledge_capture.read_retained(root, ref))
    else:
        raw, _ = bounded_record_bytes(root, location, knowledge_capture.MAX_CONTEXT_CAPTURE_BYTES)
        search = knowledge_capture.verify_capture(raw)[0] if raw else None
        if not search or search["campaign_id"] != campaign["campaign_id"]:
            raise ValueError("Supply a verified Find reference from this campaign")
    if search.get("retrieval", {}).get("entrypoint") != "find":
        raise ValueError("The reference must identify a Find result")
    return search


def _find_scoped(reader, campaign, plan, state, step, policy, options, *,
                 assemble_context, external_provider_for, context_id, retained_source):
    query = options["query"]
    backend = options["backend"] or campaign.get("backend")
    settings = plan.get("external_knowledge")
    external_enabled = (
        settings and not options["no_external"]
        and (backend is None or backend == settings["backend"])
    )
    if external_enabled:
        if step[0] is None:
            raise ValueError("Round budget consumed, run independent final evaluation")
        query = sanitized_text(query, "", limit=None)
    result = reader.find(
        query, kinds=tuple(k.strip() for k in options["kinds"].split(",") if k.strip()),
        backend=backend, repo=options["repo"], tier=options["tier"], scenario=options["scenario"],
        revisions=options["revisions"],
        limit=options["limit"], explain=options["explain"], ranking_policy=policy,
        retained_source=retained_source, pin_material=True,
    )
    indexer.check_find_return(plan, result, query=query, limit=options["limit"])
    request = {
        "query": query, "relevance": query, "relevance_method": "find-lexical-v1",
        "ranking_policy": result["ranking_policy"], "backend": backend,
        "scenario": options["scenario"], "limit": options["limit"], "kinds": options["kinds"],
        "repo": options["repo"], "tier": options["tier"], "sources": result["sources"],
    }
    if options["no_external"]:
        request["external_source"] = "none"
    if options["revisions"]:
        request["revisions"] = options["revisions"]
    items = [{key: hit[key] for key in _HIT if key in hit} for hit in result["items"]]
    for item in items:
        item["ref"] = item.get("material_ref") or f"{item['authority']}:{item['id']}"
        argv = list(item.get("material_read_args", ()))
        for flag in ("--skill-root", "--store"):
            if flag in argv:
                argv[argv.index(flag) + 1] = flag[2:].upper().replace("-", "_")
        if argv:
            item["material_read_args"] = argv
    external = None
    if external_enabled:
        remaining = _knowledge_time(plan, state)
        external = (external_provider_for(plan).search(
            query, settings=settings, limit=options["limit"], timeout=remaining,
        ) if remaining > 0 else {"state": "timeout", "items": [], "count": 0})
        result["no_match"] = (
            False if result["matched"] or external["items"]
            else (True if external["state"] == "ok" else None)
        )
    display = {key: value for key, value in result.items()
               if key not in ("items", "external", "searchspace_source")}
    display["context_bytes_used"] = 0
    delivery = _prepare_scoped_knowledge(
        campaign, step, context_id=context_id, action="find", request=request,
        items=items, display=display, assemble_context=assemble_context,
    )
    return delivery, ({**external, **settings} if external is not None else None)


def _read_scoped(root, reader, campaign, plan, state, step, options, *,
                 assemble_context, context_id):
    location = options["search_ref"]
    search = _open_knowledge_search(root, campaign, state, step, location)
    hit = next((row for row in search["items"] if row.get("material_ref") == options["ref"]), None)
    if not hit or not hit.get("revision") or hit["revision"] != options["revision"]:
        raise ValueError("Read requires a hit and revision returned by this Find")
    material_args = hit["material_read_args"]
    for flag in ("--skill-root", "--store", "--installed-library"):
        if (flag in material_args) != (flag in options["source_flags"]):
            raise ValueError("Use the source arguments returned by the original Find")
    retained_source = None
    if campaign.get("evaluation_mode") == "service_reuse":
        snapshot = f"knowledge/sources/{search['context_id']}"
        if search.get("source_snapshot") != snapshot:
            raise ValueError("This Find has no retained source bytes; run Find again "
                             "before reading")
        retained_source = service_io.safe_path(root, snapshot + "/" + hit["id"])
    resource = options.get("resource")
    byte_range = options.get("byte_range")
    view, context = reader.read_hit(
        hit, resource=resource, byte_range=byte_range, retained_source=retained_source,
    )
    delivered, = context["resources"]
    if (context["ref"] != hit["ref"] or context["revision"] != hit["revision"]
            or delivered["path"] != view["content_resource"]
            or delivered["content"] != view["content"]
            or context["content_bytes"] != len(delivered["content"].encode("utf-8"))):
        raise ValueError("Read did not deliver the pinned resource bytes")
    request = {**search["request"], "search_ref": location, "resource": view["content_resource"]}
    if byte_range is not None:
        request["byte_range"] = byte_range
    request.pop("context_bytes", None)  # An earlier manual Find may carry a packing budget.
    indexer.check_context_ranking(plan, {"request": request})
    display = {key: value for key, value in view.items() if key in (
        "id", "ref", "revision", "kind", "title", "entrypoint", "content_resource",
        "body_resource", "content_view", "content_range", "next_byte_range",
        "sources", "limitations", "applicability",
    )}
    if "next_byte_range" in view:
        argv = list(material_args)
        if resource is not None:
            argv.extend(("--resource", resource))
        display["next_read_args"] = [
            *argv, "--session", ".", "--search-ref", location,
            "--byte-range", *map(str, view["next_byte_range"]),
        ]
    item = {key: hit[key] for key in ("ref", "revision", "title", "kind") if key in hit}
    return _prepare_scoped_knowledge(
        campaign, step, context_id=context_id,
        action="read", request=request, items=[item], display=display,
        contexts=[context], assemble_context=assemble_context,
    )


def knowledge_operation(root: Path, reader, action: str, options: dict, *,
                        default_policy, ranking_policy_for, assemble_context,
                        external_provider_for) -> dict:
    """Run a Find or pinned Read and register its actual receipts under the session lock."""
    from ._runtime import session_runtime_identity

    root = root.resolve()
    context_id = f"{action}-{uuid.uuid4().hex}"
    campaign = knowledge_capture.capture_campaign(root, context_id)
    if campaign.get("managed_optimization") and campaign.get("evaluation_mode") == "service_reuse":
        plan, _ = _control(root)
        _require_service_runtime(plan)
    with _locked(root), ExitStack() as scratch:
        plan, state, step, policy = {}, None, None, default_policy
        retained_source = None
        if campaign.get("managed_optimization"):
            plan, state = _load(root)
            service = plan.get("evaluation_mode") == "service_reuse"
            active = state if not service else {
                **state, "deadline": _service_deadline(state),
                "state": "active" if state["state"] == "needs_baseline" else state["state"],
            }
            number = _knowledge_round(plan, active)
            ticket = _knowledge_request(plan, state, action=action, round_number=number)
            step, context_id = (number, ticket.binding), ticket.context_id
            if not service and plan["runtime_identity"] != session_runtime_identity():
                raise ValueError("Optimization runtime changed, use its frozen runtime to resume")
            policy = indexer.resolve_frozen_ranking(plan, ranking_policy_for)
            if action == "find" and (
                reader.skill_root is not None or reader.store is not None
                or options.get("revisions")
            ):
                raise ValueError("Managed Find uses the session's installed corpus")
            if service and action == "find":
                retained_source = Path(scratch.enter_context(
                    TemporaryDirectory(prefix=".find-", dir=root)
                )) / context_id
        external = None
        if action == "find":
            delivery, external = _find_scoped(
                reader, campaign, plan, state, step, policy, options, context_id=context_id,
                assemble_context=assemble_context, external_provider_for=external_provider_for,
                retained_source=retained_source,
            )
        else:
            delivery = _read_scoped(
                root, reader, campaign, plan, state, step, options,
                assemble_context=assemble_context, context_id=context_id,
            )
        if state is None:
            knowledge_capture.store_capture(root, delivery["context"])
            return delivery
        _active(active, reserve=plan["final_reserve_seconds"])
        return _commit_knowledge(
            root, ticket, delivery, external_search=external, retained_source=retained_source,
        )


def _store_knowledge(root, kind, number, record, *, request_id=None):
    directory = root / "knowledge"
    if directory.is_symlink():
        raise ValueError("Knowledge directory must not be a symbolic link")
    directory.mkdir(exist_ok=True)
    path = directory / f"{kind}-{request_id or uuid.uuid4().hex}.json"
    atomic_write_json(path, record)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path),
            "kind": kind, "round": number}


@dataclass(frozen=True)
class _KnowledgeRequest:
    context_id: str
    diagnosis_id: str | None
    reference_epoch: int | None
    started_at: float
    round_number: int | None

    @property
    def binding(self):
        if self.diagnosis_id is None:
            return None
        return {"diagnosis_id": self.diagnosis_id, "reference_epoch": self.reference_epoch,
                "started_at": self.started_at}


def _knowledge_request(plan, state, *, action, round_number=None):
    diagnosis_id = _diagnosis_reference(plan, state).get("diagnosis_id")
    return _KnowledgeRequest(f"{action}-{uuid.uuid4().hex}", diagnosis_id,
                             state.get("reference_epoch"), time.time(), round_number)


def _commit_knowledge(root, ticket, delivery, *, external_search=None, retained_source=None):
    """Register a checked delivery while the caller holds the session lock."""
    plan, state = _control(root)
    diagnosis = _diagnosis(state)
    reference, context = delivery["reference"], delivery["context"]
    if (ticket.reference_epoch != state.get("reference_epoch")
            or ticket.diagnosis_id != (diagnosis["id"] if diagnosis else None)
            or context.get("diagnosis_binding") != ticket.binding):
        raise ValueError("Knowledge delivery belongs to a different diagnosis or condition epoch")
    if (reference["path"] != f"knowledge/{ticket.context_id}.json"
            or context.get("context_id") != ticket.context_id):
        raise ValueError("Knowledge capture differs from its dispatched request")
    retained = {**reference, "round": ticket.round_number}
    if ticket.diagnosis_id is not None:
        retained["diagnosis_id"] = ticket.diagnosis_id
    if context["retrieval"]["entrypoint"] == "read":
        retained["search_ref"] = context["request"]["search_ref"]
    service_mode = plan.get("evaluation_mode") == "service_reuse"
    if service_mode:
        service_io.no_fingerprints(context)
        path = service_io.safe_path(root, reference["path"])
    previous = next((item for item in state["contexts"] if item["path"] == reference["path"]), None)
    if previous is not None:
        recorded = (service_io.read(path) if service_mode
                    else knowledge_capture.read_retained(root, previous))
        if previous != retained or recorded != context:
            raise ValueError("Conflicting knowledge delivery for a registered request")
        if external_search is not None:
            for item in state["contexts"]:
                if item.get("kind") == "external_search" and item["round"] == ticket.round_number:
                    search = knowledge_capture.read_retained(root, item)
                    if search["context_ref"] == reference["path"]:
                        return {**delivery, "external": {**search, "reference": item},
                                "task_source": plan["task_source"]}
        return delivery
    if ticket.round_number is not None and ticket.round_number != len(state["rounds"]) + 1:
        raise ValueError("Knowledge delivery belongs to an earlier round")
    if service_mode:
        if snapshot := context.get("source_snapshot"):
            target = service_io.safe_path(root, snapshot)
            if not target.is_dir():
                if retained_source is None:
                    raise ValueError("Find is missing its retained sources")
                target.parent.mkdir(parents=True, exist_ok=True)
                retained_source.rename(target)
        path.parent.mkdir(exist_ok=True)
        atomic_write_json(path, context)
    else:
        knowledge_capture.store_capture(root, context, expected_sha256=reference["sha256"])
    state["contexts"].append(retained)
    if external_search is not None:
        search = {**external_search, "context_ref": reference["path"]}
        search_ref = _store_knowledge(
            root, "external_search", ticket.round_number, search,
            request_id=ticket.context_id.removeprefix("find-"),
        )
        state["contexts"].append(search_ref)
        delivery = {**delivery, "external": {**search, "reference": search_ref},
                    "task_source": plan["task_source"]}
    atomic_write_json(root / "state.json", state)
    return delivery


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
        search = knowledge_capture.read_retained(root, reference)
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
                 if entry["kind"] in ("delivered_context", "external_read")}
    for ref in refs:
        path, separator, item = ref.partition("#")
        reference = delivered.get(path)
        if reference is None or (separator and reference["kind"] != "delivered_context"):
            raise ValueError("Cite a delivered context or CANNBot read receipt from this session")
        if reference["kind"] == "delivered_context":
            capture = knowledge_capture.read_retained(root, reference)
            if not any(not separator or entry["ref"] == item
                       for entry in knowledge_capture.delivered_contexts(capture)):
                raise ValueError("Cite an item with delivered resources from this context")
            if (
                capture.get("retrieval", {}).get("entrypoint") != "read"
                or not reference.get("search_ref")
                or capture["request"].get("search_ref") != reference["search_ref"]
            ):
                raise ValueError("Cite a scoped Read receipt; legacy captures are audit-only")


def _usage_record(source, *, fingerprint=True):
    if source is None:
        return {"usage": None, "tool_calls": None, "usage_source": None}, None
    raw = Path(source).read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Usage export must be a JSON object")
    if not fingerprint:
        service_io.no_fingerprints(payload)
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


def _knowledge_summary(contexts, read_capture):
    """Summarize search and read receipts without altering historical records."""
    summary = []
    for ref in contexts:
        if ref["kind"] == "knowledge_search":
            capture = read_capture(ref)
            summary.append({**ref, "hits": len(capture["items"]), "context_bytes_used": 0})
        elif ref["kind"] == "empty_context":
            summary.append({**ref, "context_bytes_used": 0})
        elif (ref["kind"] == "delivered_context" and ref.get("search_ref") is None
              and not any(knowledge_capture.delivered_contexts(read_capture(ref)))):
            summary.append({**ref, "kind": "empty_context"})
        else:
            summary.append(ref)
    return summary


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
        "knowledge_deliveries": _knowledge_summary(
            state["contexts"], lambda ref: knowledge_capture.read_retained(root, ref)),
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
            message = execution["coordinator_error"]
            if error_type := execution.get("coordinator_error_type"):
                raise TaskProtocolError("protocol_exception", message, error_type=error_type)
            raise ValueError(message)
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
    except (Exception, SystemExit) as error:
        assessment = _failure(error)
    score = assessment.get("score")
    # Normalized so every record carries the key, even for a scoreless ineligible round.
    assessment["score"] = score if assessment["status"] == "completed" else None
    record = {**pending, "assessment": assessment, "execution": execution,
              "execution_sha256": (sha256(directory / "execution/execution.json")
                                   if execution is not None else None),
              "elapsed_seconds": (execution or {}).get("elapsed_seconds")}
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
    return _publish_attempt(root, plan, state, record)


def _publish_attempt(root, plan, state, record):
    if state["state"] in ("completed", "blocked"):
        state["settled_at"] = time.time()
    state["pending"] = None
    observation = root / record["path"] / "observation.json"
    durable_write_json(observation, record)
    record["observation_sha256"] = sha256(observation)
    durable_write_json(root / "state.json", state)
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
        durable_write_json(root / "state.json", state)
        deadline = state["deadline"] - (0 if final else plan["final_reserve_seconds"])
        try:
            execution = execute(root, directory, plan, deadline)
        except (Exception, SystemExit) as error:
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
                if _type_name(error) == "SystemExit":
                    execution["coordinator_error_type"] = "SystemExit"
                # No receipt does not prove termination. The resulting blocked
                # session cannot launch more work or claim device cleanup.
                path.parent.mkdir(exist_ok=True)
                atomic_write_json(path, execution)
        return _settle(root, plan, state, pending, execution, assess)


def read_session_records(root: Path) -> tuple[dict, dict, dict]:
    """Read one validated state for status, dashboard and reconstructable summaries."""
    plan, state = _load(root, read_only=True)
    summary = _summary(root, plan, state)
    if plan.get("evaluation_mode") == "service_reuse":
        from ..records import service_observations

        state = service_observations.selection_view(state, state["attempts"])
    return plan, state, summary


def observe_service_records(root: Path) -> tuple[dict, dict, dict, dict[str, dict | None]]:
    """Read service records with unavailable knowledge marked for observation."""
    plan, state = _control(root)
    if plan.get("evaluation_mode") != "service_reuse":
        raise ValueError("Expected service-reuse campaign records")
    captures: dict[str, dict | None] = {}
    _service_load(root, plan, state, read_only=True, observed_contexts=captures)
    return plan, state, _service_summary(root, plan, state), captures


def _recovery_snapshot(root, gate):
    return attempt_recovery.retained(
        root, {"path": gate["path"], "sha256": gate["recovery_sha256"]}, gate["attempt"]
    )


def _record_recovery_snapshot(root, state, attempt, launches, blocked, *, receipt_present):
    reference = attempt_recovery.capture(root, attempt, launches, receipt_present)
    if blocked:
        state["state"] = "blocked"
        state["cleanup_unconfirmed"] = {
            "attempt": attempt, "path": reference["path"],
            "recovery_sha256": reference["sha256"],
            "stages": [entry["stage"] for entry in blocked],
        }
    return reference


def _reject_frozen_attempt(root, plan, state, error):
    pending = state["pending"]
    attempt = pending["path"]
    path = root / attempt / "execution/execution.json"
    try:
        execution = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        execution = None
    if not isinstance(execution, dict):
        execution = None
    state["integrity_error"] = str(error)
    if state.get("cleanup_unconfirmed") is None:
        receipt_present = execution is not None
        launches = attempt_recovery.scan(root, attempt, receipt_present=receipt_present)
        blocked = attempt_recovery.unconfirmed(root, state, attempt, launches)
        if blocked:
            _record_recovery_snapshot(
                root, state, attempt, launches, blocked, receipt_present=receipt_present
            )
    return _settle(root, plan, state, pending, execution, None)


def _interrupted(root, plan, state, pending, reference):
    record = {
        **pending, "execution": None, "execution_sha256": None, "elapsed_seconds": None,
        "assessment": {"status": "interrupted", "verdict": "INCONCLUSIVE", "score": None,
                       "reason": "Coordinator stopped before retaining an execution receipt"},
        "recovery": reference,
        "selection": {"outcome": "interrupted", "metric": plan["selection"]["metric"],
                      "score": None, "best_score_before": state["best"]["score"]},
        "best_after": dict(state["best"]),
    }
    if pending["kind"] == "round":
        state["rounds"].append(record)
    else:
        state.setdefault("final_attempts", []).append(record)
    return _publish_attempt(root, plan, state, record)


def _recover_attempt(root, plan, state, assess, *, manual):
    pending = state["pending"]
    gate = state.get("cleanup_unconfirmed")
    attempt = gate["attempt"] if gate else pending["path"]
    path = root / attempt / "execution/execution.json"
    receipt_present = pending is not None and path.is_file()
    earlier = list(_recovery_snapshot(root, gate)["launches"]) if gate else []
    for reference in state.get("recovery_confirmations", ()):
        if reference["attempt"] == attempt:
            earlier.extend(attempt_recovery.retained(root, reference, attempt)["launches"])
    launches = attempt_recovery.scan(
        root, attempt, receipt_present=receipt_present, earlier=earlier,
    )
    blocked = attempt_recovery.unconfirmed(root, state, attempt, launches)
    if gate is None and (blocked or not receipt_present):
        reference = _record_recovery_snapshot(
            root, state, attempt, launches, blocked, receipt_present=receipt_present
        )
        if not receipt_present:
            return _interrupted(root, plan, state, pending, reference)
        durable_write_json(root / "state.json", state)
        return status(root)
    if gate is not None:
        if blocked and not manual:
            return status(root)
        if any(entry["observation"] == "unreadable_directory" for entry in blocked):
            raise ValueError("Cannot confirm cleanup until the launch directory is readable")
        attempt_recovery.confirm(root, state, gate, launches, blocked, manual=manual)
        del state["cleanup_unconfirmed"]
        state.pop("settled_at", None)
        state["state"] = "active"
        # Persist the release before assessment can create a new launch record.
        durable_write_json(root / "state.json", state)
        if pending is None:
            atomic_write_json(root / "summary.json", _summary(root, plan, state))
            return status(root)
        if not receipt_present:
            return _interrupted(root, plan, state, pending, {
                "path": gate["path"], "sha256": gate["recovery_sha256"],
            })
    execution = json.loads(path.read_text(encoding="utf-8"))
    if pending.get("mechanism") is not None or pending.get("mechanism_sha256") is not None:
        # An interrupted attempt cannot prove which declaration was bound to execution.
        pending = {**pending, "mechanism": None, "mechanism_sha256": None,
                   "mechanism_unverified_after_recovery": True}
    return _settle(root, plan, state, pending, execution, assess)


def recover(root: Path, assess, *, confirm_domain_empty=False) -> dict:
    with _locked(root):
        control_plan, control = _control(root)
        if control["state"] == "blocked" and control.get("integrity_error"):
            return status(root)
        try:
            plan, state = _load(root)
        except _FrozenInputError as error:
            if control["pending"] is None:
                raise
            return _reject_frozen_attempt(root, control_plan, control, error)
        if confirm_domain_empty and not state.get("cleanup_unconfirmed"):
            raise ValueError("No interrupted cleanup is awaiting confirmation")
        if state["pending"] is None and not state.get("cleanup_unconfirmed"):
            atomic_write_json(root / "summary.json", _summary(root, plan, state))
            return status(root)
        return _recover_attempt(root, plan, state, assess, manual=confirm_domain_empty)


def _service_initialize(root, plan):
    from .. import executor

    executor.validate_service_settings(plan["evaluation_settings"])
    if (
        type(plan["round_limit"]) is not int
        or plan["round_limit"] < 1
        or (
            plan["round_mode"] not in ("up_to", "exact")
            or not service_io.positive_number(plan["max_seconds"])
            or not service_io.positive_number(plan["evaluation_timeout_seconds"])
            or not service_io.positive_number(plan["final_reserve_seconds"])
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
            **({"allow_final_continuation": True} if plan.get("allow_final_continuation") else {}),
        },
    )
    atomic_write_json(root / "state.json", state)
    return _service_status(root, plan, state)


_SERVICE_RUNTIME_ERRORS = {
    "runtime_version_mismatch": (
        "Runtime package version changed; use the recorded version to resume"
    ),
    "runtime_identity_missing": (
        "Service session has no recorded runtime identity; use its verified original deployment"
    ),
    "runtime_identity_mismatch": "Service runtime build changed; use its frozen runtime to resume",
}


def _service_runtime_reason(plan):
    from inferrsi import __version__

    from ._runtime import session_runtime_digest

    if plan.get("runtime_version") != __version__:
        return "runtime_version_mismatch"
    if "runtime_identity" not in plan:
        return "runtime_identity_missing"
    if plan["runtime_identity"] != session_runtime_digest():
        return "runtime_identity_mismatch"
    return None


def _require_service_runtime(plan):
    reason = _service_runtime_reason(plan)
    if reason is not None:
        raise ValueError(_SERVICE_RUNTIME_ERRORS[reason])


def _service_load(root, plan, state, *, read_only=False, observed_contexts=None):
    from .. import executor
    from ..records import service_observations

    if not read_only:
        _require_service_runtime(plan)
    executor.validate_service_settings(plan["evaluation_settings"])
    if service_io.read(root / "frozen/evaluation.json") != plan["evaluation_settings"]:
        raise ValueError("Retained protocol and plan disagree")
    executor.validate_service_conditions(state["conditions"])
    candidates.members(service_io.safe_path(root, state["protocol_path"]))
    candidates.members(service_io.safe_path(root, plan["baseline_path"]))
    diagnoses = _diagnosis_index(state)
    for attempt in state["attempts"]:
        if not service_observations.matches_control(root, attempt):
            raise ValueError("Retained attempt and control record disagree")
        if attempt["kind"] == "round":
            _check_activity_diagnosis(plan, diagnoses, attempt)
    for context in state["contexts"]:
        path = context["path"]
        try:
            retained = service_io.read(service_io.safe_path(root, path))
            indexer.check_context_ranking(plan, retained)
            _check_context_diagnosis(plan, diagnoses, context, retained)
        except (OSError, ValueError):
            if observed_contexts is None:
                raise
            retained = None
        if observed_contexts is not None:
            observed_contexts[path] = retained
    for event in state["recovery_events"]:
        if event["kind"] == "cleanup_inspection":
            proof = service_io.read(service_io.safe_path(root, event["path"]))
            if (
                proof["attempt_id"] != event["attempt_id"]
                or proof.get("cleanup_complete") is not True
            ):
                raise ValueError("Retained cleanup inspection is incomplete")
    if state["best"] is not None:
        candidates.members(service_io.safe_path(root, state["best"]["path"]))
    return plan, state


def _service_profiling(root, attempt, *, published=None):
    from .. import executor
    from . import _service_backfill as service_backfill

    profile = (
        published
        or service_backfill.latest(root, attempt)
        or executor.read_service_attempt_profile(root, attempt)
    )
    if not profile:
        return {"available": False}
    return {"available": True, "result": profile["result"], "artifacts": profile["artifacts"]}


def _service_round_view(root, attempt, *, profiling=None):
    from ..records import service_observations

    if attempt["kind"] == "round":
        if profiling is None:
            profiling = _service_profiling(root, attempt)
        return {**service_observations.display(root, attempt), "profiling": profiling}
    return attempt


def _service_account_capture(root, state, pending, execution):
    from .. import executor

    capture = execution.get("capture")
    attempt_id = pending["attempt_id"]
    if (
        not isinstance(capture, dict)
        or capture.get("id") != attempt_id
        or not isinstance(execution.get("binding"), dict)
        or execution["binding"].get("attempt_id") != attempt_id
        or not service_io.finite_number(capture.get("started_at"))
    ):
        return
    ledger = state.setdefault("profiling_accounting", {})
    if attempt_id not in ledger:
        ledger[attempt_id] = {
            "started_at": capture["started_at"],
            "elapsed_seconds": executor.service_capture_elapsed(root, pending, execution),
        }


def _service_deadline(state):
    entries = state.get("profiling_accounting", {}).values()
    return state["deadline"] + sum(entry["elapsed_seconds"] for entry in entries)


def _service_continuation_block_reason(root, plan, state, reference_reason, *, budget_time):

    if plan.get("allow_final_continuation") is not True or plan["round_mode"] != "up_to":
        return "continuation_not_enabled"
    if state["pending"] is not None:
        return "unresolved_attempt_or_pause"
    if any(attempt.get("continuation") for attempt in state["attempts"]):
        return "continuation_already_used"
    final = state["final"]
    if (
        state["state"] != "completed"
        or final is None
        or final["kind"] != "final"
        or final["assessment"]["verdict"] != "FAIL"
        or final["execution"].get("status") != "completed"
        or final not in state["attempts"]
    ):
        return "completed_failed_final_required"
    if not _service_cleanup_confirmed(state, final):
        return "failed_final_cleanup_unverified"
    if reference_reason is not None:
        return reference_reason
    if plan.get("diagnosis_required") and not _diagnosis(state):
        return "missing_bottleneck_diagnosis"
    if len(state["rounds"]) >= plan["round_limit"]:
        return "round_budget_exhausted"
    if budget_time >= _service_deadline(state) - plan["final_reserve_seconds"]:
        return "search_time_exhausted"
    return evaluator.service_settlement_reason(root, plan, state, final)


def _service_final_attempts(state):
    return [
        {
            "attempt_id": attempt["attempt_id"],
            "candidate_id": attempt["candidate_id"],
            "revision": attempt["revision"],
            "verdict": attempt["assessment"]["verdict"],
            "reason": attempt["assessment"]["reason"],
            "observation": attempt["path"] + "/observation.json",
        }
        for attempt in state["attempts"] if attempt["kind"] == "final"
    ]


def _service_selected_evidence_reason(root, plan, state, *, starting_epoch=False):

    if (
        state["initial_reference"] is None or state["comparison_parent"] is None
        or state["best"] is None and not starting_epoch
    ):
        return "missing_baseline_reference"
    if state["best"] is not None and "parent_reference_at_acceptance" not in state["best"]:
        return "unverifiable_selected_attempt_binding"
    return evaluator.service_references_reason(
        root, plan, state, state["initial_reference"], state["comparison_parent"], state["best"]
    )


def _service_final_reference_reason(root, plan, state):
    runtime_reason = _service_runtime_reason(plan)
    if runtime_reason is not None:
        return runtime_reason
    if state["requires_current_conditions_acceptance"] or (
        state["reference_epoch"] > 0
        and (
            state["best"] is None
            or state["best"]["attempt_id"] not in state["accepted_attempt_ids"]
            or state["best"]["reference_epoch"] != state["reference_epoch"]
        )
    ):
        return "missing_current_conditions_acceptance"
    return _service_selected_evidence_reason(root, plan, state)


def _service_final_reason(plan, state, reference_reason, *, budget_time=None):
    if reference_reason is not None:
        return reference_reason
    if state["pending"] is not None or state["state"] != "active":
        return "unresolved_attempt_or_pause"
    completed = sum(item["terminal"] for item in state["rounds"])
    if not completed or plan["round_mode"] == "exact" and completed != plan["round_limit"]:
        return "incomplete_round_policy"
    if (time.time() if budget_time is None else budget_time) >= _service_deadline(state):
        return "deadline_exhausted"
    return None


def _service_status(root, plan, state):
    from ..records import service_observations

    reference_reason = _service_final_reference_reason(root, plan, state)
    now = time.time()
    reason = _service_final_reason(plan, state, reference_reason, budget_time=now)
    continuation_reason = _service_continuation_block_reason(
        root, plan, state, reference_reason, budget_time=now,
    )
    remaining = max(0, _service_deadline(state) - now)
    if continuation_reason is None:
        next_action = "continue_search_after_failed_final"
    elif state["state"] == "completed" and not state["pending"]:
        next_action = "completed"
    elif reason == "runtime_version_mismatch":
        next_action = "use_recorded_runtime_version"
    elif reason in _SERVICE_RUNTIME_ERRORS:
        next_action = "restore_frozen_runtime"
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
    finals = _service_final_attempts(state)
    latest = [_service_round_view(root, attempt) for attempt in state["attempts"][-1:]]
    state = service_observations.selection_view(state, latest)
    return {
        "session": str(root),
        "evaluation_mode": "service_reuse",
        "state": state["state"],
        "next_action": next_action,
        "recorded_runtime_version": plan.get("runtime_version"),
        "can_finalize": reason is None,
        "can_continue": continuation_reason is None,
        "continuation_block_reason": continuation_reason,
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
        "final_attempts": finals,
        "latest_observation": state["attempts"][-1] if state["attempts"] else None,
        "diagnosis": _diagnosis(state),
        "summary": str(root / "summary.json"),
    }


def _service_summary(root, plan, state, *, attempts=None, budget_time=None):
    from ..records import service_observations

    if attempts is None:
        attempts = [_service_round_view(root, attempt) for attempt in state["attempts"]]
    reason = (
        None if state["state"] == "completed"
        else _service_final_reason(
            plan, state, _service_final_reference_reason(root, plan, state),
            budget_time=budget_time,
        )
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
        "current_final_attempt_id": state["final"]["attempt_id"] if state["final"] else None,
        "final_attempts": _service_final_attempts(state),
        "final_block_reason": reason,
        "optimization_speedup": None,
        "reference_epoch": state["reference_epoch"],
        "conditions": state["conditions"],
        "initial_reference": state["initial_reference"],
        "comparison_parent": state["comparison_parent"],
        "accepted_attempt_ids": state["accepted_attempt_ids"],
        "attempts": state["attempts"],
        "knowledge_deliveries": _knowledge_summary(
            state["contexts"],
            lambda ref: service_io.read(service_io.safe_path(root, ref["path"])),
        ),
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
    from .. import executor

    directory = service_io.safe_path(root, pending["path"])
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
                and evaluator.service_profile_eligible(checkpoint["assessment"]["reason"])
            ):
                execution["profiling_error"] = executor.service_capture_diagnostic(
                    root,
                    directory,
                    "profile",
                    "interrupted",
                    "Capture interrupted before completion; no further error receipt was recorded",
                )
            atomic_write_json(directory / "execution/execution.json", execution)
    path = directory / "observation.json"
    if path.exists():
        record = service_io.read(path)
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
    reason = evaluator.service_settlement_reason(root, plan, state, record)
    if reason:
        record["assessment_before_settlement"] = record["assessment"]
        record["assessment"] = evaluator.service_assessment(
            "INCONCLUSIVE",
            reason,
            performance=record["assessment"].get("performance"),
            quality_passed=record["assessment"].get("quality_passed"),
        )
    kind = record["kind"]
    verdict = record["assessment"]["verdict"]
    if kind == "round":
        choice = (
            evaluator.service_choice(record, record["execution"]) if verdict == "PASS" else None
        )
        record["profiling"] = _service_profiling(root, record)
        record["selected"] = choice is not None and (
            state["best"] is None
            or evaluator.prefer_service_measurements(
                plan["evaluation_settings"],
                choice["measurements"]["values"],
                state["best"]["measurements"]["values"],
            )
        )
        record["best_after"] = (
            choice if record["selected"] else evaluator.service_reference_snapshot(state["best"])
        )
    atomic_write_json(path, record)
    if kind == "baseline":
        if verdict == "PASS":
            choice = evaluator.service_choice(record, record["execution"])
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
                    "best": evaluator.service_reference_snapshot(state["best"]),
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
        # A later inconclusive attempt stays in history without superseding a conclusive final.
        previous = state["final"]
        if (
            verdict != "INCONCLUSIVE"
            or previous is None
            or previous["assessment"]["verdict"] == "INCONCLUSIVE"
        ):
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
    from .. import executor

    pending = state["pending"]
    if pending["kind"] != "refresh":
        return executor.execute_service_attempt(root, directory, plan, pending, deadline)
    from ..records import service_observations

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
        subdir = service_io.safe_path(root, relative)
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
        result = executor.execute_service_attempt(root, subdir, plan, job, deadline)
        runs.append(result)
        if result["assessment"]["verdict"] != "PASS":
            return {
                "assessment": evaluator.service_assessment(
                    "INCONCLUSIVE", "reference_refresh_incomplete"
                ),
                "runs": runs,
                "cleanup_verified": result["cleanup_verified"],
                "elapsed_seconds": time.monotonic() - started,
            }
        references.append(evaluator.service_choice(job, result))
    parent_profile = service_observations.reference_view(
        pending["refresh_parent"], service_observations.inline_profiles(state["attempts"])
    )["profile"]
    return {
        "assessment": evaluator.service_assessment(
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
    from ..executor import process_group_empty

    latest = state["pending"] or (state["attempts"][-1] if state["attempts"] else None)
    proof = service_io.read(path)
    if (
        latest is None
        or proof.get("attempt_id") != latest["attempt_id"]
        or not proof.get("reason")
        or (
            proof.get("cleanup_complete") is not True
            or not service_io.positive_number(proof.get("observed_at"))
            or not isinstance(proof.get("services"), list)
            or any(not isinstance(item, dict) for item in proof.get("services", []))
        )
    ):
        raise ValueError(
            "Cleanup inspection must identify the attempt, time, reason and all services"
        )
    directory = service_io.safe_path(root, latest["path"])
    owners = [
        service_io.read(service_io.safe_path(directory, name))
        for name in (
            "service/owner.json",
            "baseline/service/owner.json",
            "parent/service/owner.json",
        )
        if service_io.safe_path(directory, name).is_file()
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
            and process_group_empty(owner["process_group_id"]) is not True
        ):
            raise ValueError("Recorded process domain is still live or unobservable")
    relative = "recoveries/cleanup-" + uuid.uuid4().hex + ".json"
    (root / "recoveries").mkdir(exist_ok=True)
    atomic_write_json(service_io.safe_path(root, relative), proof)
    state["recovery_events"].append(
        {"kind": "cleanup_inspection", "attempt_id": latest["attempt_id"], "path": relative}
    )
    atomic_write_json(root / "state.json", state)


def _service_status_with_rounds(root, plan, state):
    result = _service_status(root, plan, state)
    latest_by_round = {
        attempt["round_number"]: attempt
        for attempt in state["attempts"] if attempt["kind"] == "round"
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


def service_command(root, request, *, ranking_policy_for=None):
    """Service-mode operations inside the shared controller's lock and control record."""
    from .. import executor

    action = request.action
    plan, control = _control(root)
    if action == "status":
        if _service_runtime_reason(plan) is not None:
            plan, control = _service_load(root, plan, control, read_only=True)
            return {**_service_status_with_rounds(root, plan, control), "read_only": True}
    else:
        _require_service_runtime(plan)
    with _locked(root):
        if action == "profile":
            from . import _service_backfill as service_backfill

            plan, _ = _control(root)
            indexer.resolve_frozen_ranking(plan, ranking_policy_for)
            return service_backfill.run(root, request)
        plan, state = _load(root, read_only=action == "status")
        indexer.resolve_frozen_ranking(
            plan, ranking_policy_for, read_only=action == "status"
        )
        after_final = getattr(request, "continue_after_final", None)
        continuation_reason = getattr(request, "continuation_reason", None)
        continuation = None
        if after_final is not None or continuation_reason is not None:
            if (
                action != "round" or not after_final or not (continuation_reason or "").strip()
                or any(getattr(request, name, None) is not None for name in (
                    "retry_of", "repair_reason", "repair_protocol", "cleanup_receipt",
                ))
            ):
                raise ValueError("Continuation requires a failed final ID and a separate reason")
            reason = _service_continuation_block_reason(
                root, plan, state, _service_final_reference_reason(root, plan, state),
                budget_time=time.time(),
            )
            if reason is not None:
                raise ValueError(f"Cannot continue campaign ({reason})")
            if after_final != state["final"]["attempt_id"]:
                raise ValueError("Continuation must name the current failed final")
            continuation = {"after_final": after_final, "reason": continuation_reason.strip()}
        if getattr(request, "cleanup_receipt", None) is not None:
            _service_cleanup_receipt(root, state, request.cleanup_receipt)
        if action == "status":
            return _service_status_with_rounds(root, plan, state)
        if action == "diagnose":
            return _retain_diagnosis(root, plan, state, request.bottleneck, request.evidence)
        if action == "recover":
            if state["pending"] and state["pending"]["kind"] == "profile":
                from . import _service_backfill as service_backfill

                return service_backfill.recover(root, plan, state, request)
            if state["pending"] is None:
                atomic_write_json(root / "summary.json", _service_summary(root, plan, state))
                return _service_command_result(
                    root, plan, state, {"profiling_error": state.get("last_profiling_error")}
                )
            pending = state["pending"]
            directory = service_io.safe_path(root, pending["path"])
            observation = directory / "observation.json"
            if observation.exists():
                result = service_io.read(observation)["execution"]
            else:
                try:
                    result = service_io.read(directory / "execution/execution.json")
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
                            assessment=evaluator.service_assessment(
                                "INCONCLUSIVE", "interrupted_execution_requires_full_retry"
                            ),
                        )
            return _service_settle(root, plan, state, pending, result)
        if action == "resume":
            if not request.reason.strip() or state["pending"] is not None:
                raise ValueError(
                    "Record investigation before resume; resolve pending execution first"
                )
            latest = state["attempts"][-1] if state["attempts"] else None
            if (
                state["state"] == "active"
                and state["recovery_events"]
                and (
                    state["recovery_events"][-1].get("kind") == "resume"
                    and state["recovery_events"][-1].get("reason") == request.reason
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
                {"kind": "resume", "reason": request.reason, "attempt_id": latest["attempt_id"]}
            )
            state["state"] = "active"
            atomic_write_json(root / "state.json", state)
            return _service_status(root, plan, state)
        retry = getattr(request, "retry_of", None)
        repair = getattr(request, "repair_reason", None)
        repaired_protocol = getattr(request, "repair_protocol", None)
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
        if state["pending"] is not None or (state["state"] == "completed" and continuation is None):
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
        if kind == "baseline":
            if initial is not None:
                raise ValueError("Initial baseline is already measured")
            source, commit = root / plan["baseline_path"], plan["baseline_revision"]
            candidate_id, number = "baseline", None
        elif kind == "round":
            if continuation is None:
                if initial is None or parent is None:
                    raise ValueError("Complete baseline and compatible reference refresh first")
                reason = _service_selected_evidence_reason(
                    root, plan, state,
                    starting_epoch=state["requires_current_conditions_acceptance"],
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
            if number > plan["round_limit"] or not request.hypothesis.strip():
                raise ValueError("Round budget exhausted or hypothesis missing")
            if request.candidate.is_symlink():
                raise ValueError("Candidate root cannot be symbolic")
            source = request.candidate.resolve()
            commit = executor.service_revision(source, plan["candidate_includes"])
            candidate_id = f"candidate-{number:03d}"
            if not old:
                state["rounds"].append({"number": number, "terminal": False, "attempt_ids": []})
        elif kind == "refresh":
            if initial is None or parent is None or not request.reason.strip():
                raise ValueError("Initial references and a change reason required")
            if len(state["rounds"]) >= plan["round_limit"]:
                raise ValueError("No round budget for current-conditions acceptance")
            conditions = service_io.read(request.conditions)
            executor.validate_service_conditions(conditions)
            if not old:
                if conditions == state["conditions"]:
                    raise ValueError("No changed conditions; reuse compatible retained references")
                if conditions["id"] == state["conditions"]["id"]:
                    raise ValueError("Changed conditions require a new explicit ID")
                state.update(
                    conditions=conditions,
                    reference_epoch=state["reference_epoch"] + 1,
                    requires_current_conditions_acceptance=True,
                    accepted_attempt_ids=[],
                )
                state["stagnation"].update(consecutive=0, notified=False)
            elif conditions != old["conditions"]:
                raise ValueError("Reference retry must retain its declared conditions")
            source, commit = root / plan["baseline_path"], plan["baseline_revision"]
            candidate_id, number = "reference-refresh", None
        else:
            if plan["round_mode"] == "up_to" and not (request.reason or "").strip():
                raise ValueError("Record why search stopped")
            admission = _service_final_reason(
                plan, state, _service_final_reference_reason(root, plan, state),
            )
            selected = state["best"]
            source = (
                service_io.safe_path(root, selected["path"])
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
        directory = service_io.safe_path(root, relative)
        directory.mkdir(parents=True)
        protocol_path = state["protocol_path"]
        if kind == "final" and state["best"] is not None:
            protocol_path = state["best"]["protocol_path"]
        if repaired_protocol:
            candidates.retain(repaired_protocol, directory / "protocol", fingerprint=False)
            protocol_path = relative + "/protocol"
            state["protocol_path"] = protocol_path
        observations, raw = _usage_record(getattr(request, "usage_export", None), fingerprint=False)
        if raw is not None:
            (directory / "agent-usage.json").write_bytes(raw)
        if kind == "round":
            executor.retain_service_revision(
                source, directory / "candidate", plan["candidate_includes"], commit
            )
            if executor.service_revision(source, plan["candidate_includes"]) != commit:
                raise ValueError("Candidate revision changed while retaining inputs")
            source_repo = str(source)
        elif kind == "final" and selected:
            source_repo = selected.get("source_repo")
        else:
            source_repo = plan["working_candidate"]
        initial = evaluator.service_reference_snapshot(initial)
        parent = evaluator.service_reference_snapshot(parent)
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
            "hypothesis": getattr(request, "hypothesis", None)
            or getattr(request, "reason", None)
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
        if continuation is not None:
            pending["continuation"] = continuation
            state["state"] = "active"
        state["pending"] = pending
        atomic_write_json(root / "state.json", state)
        try:
            if admission:
                result = {
                    "assessment": evaluator.service_assessment("INCONCLUSIVE", admission),
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
                result = service_io.read(receipt)
            except (OSError, ValueError):
                result = {"cleanup_verified": None}
            result["assessment"] = evaluator.service_assessment(
                "INCONCLUSIVE",
                f"coordinator: {error}",
                performance=(result.get("assessment") or {}).get("performance"),
                quality_passed=(result.get("assessment") or {}).get("quality_passed"),
            )
        execution_dir = directory / "execution"
        execution_dir.mkdir(exist_ok=True)
        atomic_write_json(execution_dir / "execution.json", result)
        return _service_settle(root, plan, state, pending, result)
