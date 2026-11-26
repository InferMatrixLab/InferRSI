"""H's opt-in, mechanical frozen-scope/check-to-retained-proof authorization.

The host authorizes the policy Ref. This module neither grades a task nor proves
who approved that Ref, and it does not inspect free-text delivery channels.
"""

from copy import deepcopy
from hashlib import sha256

from inferrsi.contracts import json_v1
from inferrsi.contracts._harness_errors import PublicError
from inferrsi.harness.executor import _prepared_binding as prepared_binding
from inferrsi.harness.records import _run_store as run_store

ROLE = "generation_feedback_policy"
PATH = "inputs/generation-feedback-policy.json"
_ARTIFACT = {"location", "sha256", "size_bytes", "media_type"}
_RECORD = {"attempt_id", "record_version", "artifact"}
_PREPARED_REF = {"prepared_id", "schema_version", "artifact"}
_CANDIDATE = {"candidate_id", "kind", "input_role", "parent_id", "parent_digest", "context_refs"}
_PLAN = set("schema_version campaign_id goal starting_point prepared budget_scope deadline_utc "
            "advance_rule stop_rule allowed_feedback".split())
_PROTOCOL = set("schema_version task grader operation validation_scope candidate_contract "
                "worker_recipe input_requirements claim_definitions metric_definitions "
                "required_evidence task_parameters baseline reference quality_reference "
                "sampling feedback_visibility budget_policy_refs resources display_notes".split())
_REQUIREMENT = set("check_id checker_revision allowed_producer_kinds subject phase artifact_schema "
                   "matching_rule_revision allowed_control_domains for_claims".split())
_CHECK = set("check_id checker_revision subject phase operation validation_scope attempt_id "
             "status producer evidence_refs artifact_schema reasons".split())
_RESOURCE = {"role", "artifact", "format_schema", "required_for"}


def _fail(code, message):
    return PublicError(code, stage="validate", started=False, message=message)


def _require(condition, message, code="InvalidRequest"):
    if not condition:
        raise _fail(code, message)


def _shape(value, fields):
    _require(run_store._has_fields(value, fields), "invalid frozen feedback object fields")


def _version(value):
    version = value.get("schema_version") if isinstance(value, dict) else None
    if type(version) is int and version != 1:
        raise _fail("UnsupportedSchema", "only frozen feedback v1 objects are supported")
    _require(type(version) is int, "schema_version must be integer 1")


def _artifact(ref):
    _shape(ref, _ARTIFACT)
    _require(prepared_binding._is_path(ref["location"])
             and prepared_binding._is_sha256(ref["sha256"])
             and type(ref["size_bytes"]) is int
             and 0 <= ref["size_bytes"] <= json_v1.MAX_SAFE_INTEGER
             and isinstance(ref["media_type"], str) and bool(ref["media_type"]),
             "invalid frozen feedback ArtifactRef")


def _record_ref(ref):
    _shape(ref, _RECORD)
    _artifact(ref["artifact"])
    _require(run_store._is_id(ref["attempt_id"]) and type(ref["record_version"]) is int
             and 1 <= ref["record_version"] <= json_v1.MAX_SAFE_INTEGER,
             "invalid feedback RecordRef")


def request_fields(policy_ref, record_refs, reader):
    """Extra preparation identity only for opt-in calls; legacy has no extra keys."""
    _require(isinstance(record_refs, (tuple, list)), "feedback records must be a sequence")
    if policy_ref is None:
        _require(not record_refs, "feedback records require a frozen policy Ref")
        return {}
    _artifact(policy_ref)
    _require(policy_ref["media_type"] == "application/json", "policy must be JSON")
    _require(reader is not None, "policy requires an artifact reader")
    for ref in record_refs:
        _record_ref(ref)
    _require(len({json_v1.encode(ref) for ref in record_refs}) == len(record_refs),
             "feedback RecordRefs must be unique")
    return {"feedback_policy_ref": deepcopy(policy_ref),
            "feedback_record_refs": deepcopy(list(record_refs))}


def _read(reader, ref):
    _artifact(ref)
    try:
        with reader.open(deepcopy(ref)) as stream:
            parts, total, digest = [], 0, sha256()
            while total <= ref["size_bytes"]:
                chunk = stream.read(min(1024 * 1024, ref["size_bytes"] + 1 - total))
                if not chunk:
                    break
                _require(isinstance(chunk, bytes), "artifact reader must supply bytes")
                total += len(chunk)
                digest.update(chunk)
                parts.append(chunk)
    except PublicError as exc:
        raise _fail(exc.code, exc.message) from exc
    except OSError as exc:
        raise _fail("ArtifactUnavailable", "frozen feedback bytes are not accessible") from exc
    _require(total == ref["size_bytes"] and digest.hexdigest() == ref["sha256"],
             "frozen feedback bytes differ from their Ref", "ArtifactIntegrityError")
    return b"".join(parts)


def _json(data):
    try:
        return json_v1.decode(data)
    except (json_v1.CanonicalError, RecursionError) as exc:
        raise _fail("ArtifactIntegrityError", "feedback metadata is not canonical JSON") from exc


def _resource(value):
    _shape(value, _RESOURCE)
    _artifact(value["artifact"])
    _require(run_store._is_id(value["role"])
             and prepared_binding._is_definition(value["format_schema"])
             and prepared_binding._is_ids(value["required_for"]), "invalid frozen resource")
    return {**value, "artifact": {key: item for key, item in value["artifact"].items()
                                 if key != "location"}}


def _semantic(value):
    # Strip only the contract's typed ArtifactRefs, never ref-shaped Parameters.
    value = deepcopy(value)
    value.pop("display_notes")
    if "prepared_id" in value:
        value.pop("prepared_id")
        value.pop("created_at")
        value["protocol"].pop("location")
    else:
        for key in ("baseline", "reference", "quality_reference"):
            if value[key] is not None:
                value[key] = _resource(value[key])
    value["resources"] = [_resource(item) for item in value["resources"]]
    return "sha256:" + sha256(json_v1.encode(value)).hexdigest()


def _candidate(value):
    _shape(value, _CANDIDATE)
    _require(all(run_store._is_id(value[key]) for key in ("candidate_id", "kind", "input_role"))
             and (value["parent_id"] is None) == (value["parent_digest"] is None)
             and (value["parent_id"] is None or (run_store._is_id(value["parent_id"])
                  and prepared_binding._is_sha256(value["parent_digest"])))
             and isinstance(value["context_refs"], list), "invalid candidate identity")
    for ref in value["context_refs"]:
        _artifact(ref)


def _plan(value, context):
    _version(value)
    _shape(value, _PLAN)
    _require(all(run_store._is_id(value[key]) for key in ("campaign_id", "budget_scope"))
             and isinstance(value["goal"], str) and run_store._is_timestamp(value["deadline_utc"])
             and all(prepared_binding._is_definition(value[key])
                     for key in ("advance_rule", "stop_rule")), "invalid CampaignPlan")
    _require(value["campaign_id"] == context.get("campaign_id"),
             "policy belongs to another campaign", "IdentityMismatch")
    _shape(value["starting_point"], {"candidate", "inputs", "generation_record_ref"})
    _candidate(value["starting_point"]["candidate"])
    from inferrsi.harness.executor._execution import _input_errors

    _require(not _input_errors(value["starting_point"]["inputs"]), "invalid starting inputs")
    _require(sum(item["role"] == value["starting_point"]["candidate"]["input_role"]
                 for item in value["starting_point"]["inputs"]) == 1,
             "starting candidate needs one input role")
    if value["starting_point"]["generation_record_ref"] is not None:
        _record_ref(value["starting_point"]["generation_record_ref"])
    _require(isinstance(value["prepared"], list) and value["prepared"], "missing policy scopes")
    scoped = {}
    for item in value["prepared"]:
        _shape(item, {"validation_scope", "prepared_ref", "protocol_digest"})
        scope, ref = item["validation_scope"], item["prepared_ref"]
        _require(run_store._is_id(scope) and scope not in scoped, "ambiguous policy scope")
        _version(ref)
        _shape(ref, _PREPARED_REF)
        _artifact(ref["artifact"])
        _require(prepared_binding._is_semantic_id(ref["prepared_id"])
                 and prepared_binding._is_semantic_id(item["protocol_digest"]),
                 "invalid scoped preparation identity")
        scoped[scope] = item
    _require(prepared_binding._is_ids(value["allowed_feedback"])
             and set(value["allowed_feedback"]) <= scoped.keys(), "invalid granted scopes")
    return scoped


def _requirements(reader, scoped):
    ref = scoped["prepared_ref"]
    data = _read(reader, ref["artifact"])
    try:
        fixed = prepared_binding.project_prepared_binding(data)
    except PublicError as exc:
        code = "InvalidRequest" if exc.code == "InvalidExecutionSpec" else exc.code
        raise _fail(code, exc.message) from exc
    prepared = _json(data)
    _require((fixed.prepared_id, fixed.protocol_digest, fixed.validation_scope) == (
        ref["prepared_id"], scoped["protocol_digest"], scoped["validation_scope"]),
        "scoped preparation binding differs", "IdentityMismatch")
    _require(_semantic(prepared) == fixed.prepared_id,
             "prepared semantic identity differs", "ArtifactIntegrityError")
    protocol = _json(_read(reader, prepared["protocol"]))
    _version(protocol)
    _shape(protocol, _PROTOCOL)
    _require(_semantic(protocol) == fixed.protocol_digest,
             "protocol semantic identity differs", "ArtifactIntegrityError")
    _require(all(prepared[key] == protocol[key] for key in (
        "task", "grader", "operation", "validation_scope", "candidate_contract",
        "required_evidence")) and prepared["recipe"] == protocol["worker_recipe"],
        "prepared and protocol fields differ", "IdentityMismatch")
    requirements = {}
    _require(isinstance(protocol["required_evidence"], list), "invalid evidence requirements")
    for item in protocol["required_evidence"]:
        _shape(item, _REQUIREMENT)
        key = item["check_id"]
        _require(run_store._is_id(key) and key not in requirements, "ambiguous evidence check")
        _require(all(run_store._is_id(item[field]) for field in (
            "checker_revision", "matching_rule_revision", "subject", "phase",
        )) and prepared_binding._is_ids(item["for_claims"]), "invalid evidence rule identity")
        _require(item["matching_rule_revision"] == "1", "unsupported evidence matching rule",
                 "UnsupportedRuleVersion")
        _require(prepared_binding._is_ids(item["allowed_producer_kinds"])
                 and prepared_binding._is_ids(item["allowed_control_domains"])
                 and prepared_binding._is_definition(item["artifact_schema"]),
                 "invalid evidence authorization")
        requirements[key] = item
    visible = protocol["feedback_visibility"]
    _require(prepared_binding._is_ids(visible), "invalid visible check IDs")
    _require(set(visible) <= requirements.keys(), "unknown visible check ID",
             "UnsupportedRuleVersion")
    return fixed, {key: requirements[key] for key in visible}


def verify(store, attempt, context, policy_ref, record_refs, reader, *, retained=False):
    try:
        return _verify(store, attempt, context, policy_ref, record_refs, reader, retained=retained)
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError) as exc:
        raise _fail("InvalidRequest", "invalid frozen feedback metadata") from exc


def _verify(store, attempt, context, policy_ref, record_refs, reader, *, retained):
    """Validate opt-in inputs before any provider call; return original policy bytes."""
    source = {**policy_ref, "location": run_store.object_location(
        store.namespace, policy_ref["sha256"],
    )} if retained else policy_ref
    data = _read(store if retained else reader, source)
    policy = _json(data)
    scoped = _plan(policy, context)
    wanted = context.get("allowed_feedback")
    _require(isinstance(wanted, list), "feedback must be an ArtifactRef list")
    for ref in wanted:
        _artifact(ref)
    _require(len({json_v1.encode(ref) for ref in wanted}) == len(wanted), "duplicate feedback Ref")
    parent = context.get("parent")
    if record_refs:
        _candidate(parent)
    approved, candidate_digest = set(), None
    for ref in record_refs:
        _require(ref["attempt_id"] != attempt["attempt_id"], "feedback reuses generation attempt",
                 "IdentityMismatch")
        try:
            committed = store.committed(ref["attempt_id"], ref["record_version"])
        except PublicError as exc:
            raise _fail(exc.code, exc.message) from exc
        record = committed.payload
        _require(committed.record_ref == ref and record["run_id"] == attempt["run_id"]
                 and record["owner"] == attempt["owner"] and record["candidate"] == parent,
                 "feedback record/parent/run/owner differs", "IdentityMismatch")
        scope = record["validation_scope"]
        _require(scope in policy["allowed_feedback"], "feedback scope is not granted")
        item = scoped[scope]
        _require(record["prepared_ref"] == item["prepared_ref"]
                 and record["protocol_digest"] == item["protocol_digest"],
                 "record does not match policy preparation", "IdentityMismatch")
        fixed, visible = _requirements(reader, item)
        _require(record["operation"] == fixed.operation
                 and parent["kind"] == fixed.candidate_kind
                 and parent["input_role"] == fixed.candidate_input_role,
                 "record operation differs", "IdentityMismatch")
        bound = [value for value in record["bound_inputs"]
                 if value["role"] == parent["input_role"]]
        _require(len(bound) == 1 and bound[0]["actual_sha256"] is not None
                 and bound[0]["retained_ref"] is not None, "parent input is unavailable",
                 "ArtifactUnavailable")
        _require(bound[0]["snapshot_format"] == "file-v1", "unsupported parent snapshot format",
                 "UnsupportedRuleVersion")
        _require(bound[0]["attempt_id"] == record["attempt_id"],
                 "parent input belongs to another attempt", "IdentityMismatch")
        _read(store, bound[0]["retained_ref"])
        actual = bound[0]["actual_sha256"]
        _require(actual == bound[0]["retained_ref"]["sha256"]
                 and (candidate_digest is None or candidate_digest == actual),
                 "parent captured identity differs", "IdentityMismatch")
        candidate_digest = actual
        if context.get("candidate") is not None:
            _candidate(context["candidate"])
            _require((context["candidate"]["parent_id"], context["candidate"]["parent_digest"])
                     == (parent["candidate_id"], actual), "next candidate parent differs",
                     "IdentityMismatch")
        for check in record["checks"]:
            _require(run_store._has_fields(check, _CHECK), "invalid fixed check fields",
                     "RecordIntegrityError")
            requirement = visible.get(check["check_id"])
            if requirement is None:
                continue
            producer = check["producer"]
            _require(run_store._has_fields(producer, {
                "kind", "identity", "revision", "control_domain", "capture_route",
            }), "invalid fixed producer fields", "RecordIntegrityError")
            _require(all(check[key] == requirement[key] for key in (
                "check_id", "checker_revision", "subject", "phase", "artifact_schema"))
                and check["attempt_id"] == record["attempt_id"]
                and check["operation"] == record["operation"]
                and check["validation_scope"] == scope
                and producer["kind"] in requirement["allowed_producer_kinds"]
                and producer["control_domain"] in requirement["allowed_control_domains"],
                "feedback evidence producer/binding differs", "IdentityMismatch")
            for artifact in check["evidence_refs"]:
                _read(store, artifact)
                approved.add(json_v1.encode(artifact))
    _require(all(json_v1.encode(ref) in approved for ref in wanted),
             "feedback Ref is not an approved original check proof")
    return data


def retain(store, data, attempt_id):
    ref = run_store.artifact_ref(store.namespace, data, "application/json")
    try:
        store._retain(ref, data)
    except (OSError, run_store._StorageFault, run_store._IntegrityFault) as exc:
        raise PublicError("ExecutionPersistenceError", stage="generation-seal",
                          attempt_id=attempt_id, started=False,
                          message="feedback policy retention failed") from exc
    return ref
