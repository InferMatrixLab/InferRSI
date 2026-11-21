"""H-owned attempt byte capability and pre-commit evidence provenance sealing."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from inferrsi.contracts import json_v1
from inferrsi.harness import input_binding, run_store
from inferrsi.harness.errors import PublicError

CONTEXT_FIELDS = frozenset(
    "schema_version request_id run_id attempt_id request_digest prepared_ref protocol_digest "
    "operation validation_scope candidate bound_inputs target_binding steps started "
    "process_outcome exit_code cleanup resource_leases".split()
)
_CHECK = frozenset("check_id checker_revision subject phase artifact_schema status reasons "
                   "proof_key source".split())
_ERROR_CODES = frozenset({
    "InvalidRequest", "InvalidExecutionSpec", "UnsupportedSchema", "UnsupportedRuleVersion",
    "IdentityMismatch", "ArtifactUnavailable", "ArtifactIntegrityError", "UnsafeArtifactPath",
})
_FATAL_CONFIG = {"InvalidExecutionSpec", "IdentityMismatch", "UnsupportedSchema",
                 "UnsupportedRuleVersion"}
_SOURCES = {"candidate_capture", "worker_report", "cleanup_capture"}


class _Rejected(ValueError):
    def __init__(self, code="InvalidExecutionSpec"):
        self.code = code
        super().__init__("Invalid capture contract.")


def _require(value, code="InvalidExecutionSpec"):
    if not value:
        raise _Rejected(code)


def _snapshot(value):
    try:
        return json_v1.decode(json_v1.encode(value))
    except json_v1.CanonicalError as error:
        raise _Rejected() from error


def _ids(values):
    return isinstance(values, list) and all(run_store._is_id(value) for value in values)


class _Reader:
    """Whitelist exact attempt Refs; return independently checked immutable bytes."""

    def __init__(self, root, retained):
        self.root = root
        self.sources = {json_v1.encode(ref): source for ref, source in retained}
        self.opened = set()
        self.active = True

    def open(self, ref):
        if not self.active:
            raise PublicError("UnsafeArtifactPath", stage="evidence_capture",
                              message="The capture capability has expired.")
        try:
            key = json_v1.encode(ref)
        except json_v1.CanonicalError:
            key = None
        if key not in self.sources:
            raise PublicError("UnsafeArtifactPath", stage="evidence_capture",
                              message="Artifact is outside this attempt's retained sources.")
        # Read the authorized metadata, not the caller's mutable object.
        fixed = json_v1.decode(key)
        source = self.sources[key]
        try:
            if isinstance(source, bytes):
                data = source
            else:
                relative = Path(source).relative_to(self.root)
                with input_binding.open_regular(self.root, relative.as_posix()) as stream:
                    chunks, remaining = [], fixed["size_bytes"] + 1
                    while remaining:
                        chunk = stream.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    data = b"".join(chunks)
        except input_binding.BindingError as error:
            raise PublicError("UnsafeArtifactPath", stage="evidence_capture",
                              message="Captured source is not a confined regular file.") from error
        except (OSError, ValueError) as error:
            raise PublicError("ArtifactUnavailable", stage="evidence_capture",
                              message="Captured source is unavailable.") from error
        if (len(data) != fixed["size_bytes"]
                or sha256(data).hexdigest() != fixed["sha256"]):
            raise PublicError("ArtifactIntegrityError", stage="evidence_capture",
                              message="Captured source does not match its retained reference.")
        self.opened.add(key)
        return BytesIO(data)


def _read_source(reader, ref):
    return isinstance(ref, dict) and json_v1.encode(ref) in reader.opened


def _candidate(facts):
    candidate = facts["candidate"]
    values = [item for item in facts["bound_inputs"]
              if item["role"] == candidate["input_role"]
              and item["attempt_id"] == facts["attempt_id"]]
    _require(len(values) == 1, "IdentityMismatch")
    return values[0]


def _cleanup_confirmed(facts):
    cleanup, resources = facts["cleanup"], facts["resource_leases"]
    return (isinstance(cleanup, dict) and cleanup.get("status") == "confirmed"
            and cleanup.get("process_exit_confirmed") is True and isinstance(resources, dict)
            and isinstance(resources.get("leases"), list)
            and resources.get("applicability") in {"applicable", "not_applicable"}
            and ((resources["applicability"] == "applicable" and bool(resources["leases"]))
                 or (resources["applicability"] == "not_applicable" and not resources["leases"]))
            and all(item.get("release_confirmed") is True
                    and item.get("release_confirmed_at") is not None
                    for item in resources["leases"]))


def _worker(facts, spec, reader, bound):
    _require(facts["started"] is True, "IdentityMismatch")
    expected = {item["step_id"]: item for item in spec["steps"]}
    runtimes = facts["target_binding"]["runtime_bindings_by_step"]
    for step in facts["steps"]:
        step_id = step["step_id"]
        if step["started_at"] is None or step_id not in bound["step_ids"]:
            continue
        frozen = expected[step_id]
        for runtime in runtimes:
            if runtime["step_id"] != step_id:
                continue
            if not (runtime["code_sha256"] == frozen["expected_code_sha256"]
                    and all(runtime[key] == frozen[key] for key in
                            ("runtime_role", "entrypoint", "entrypoint_revision"))):
                continue
            roles = {item["role"] for item in frozen["outputs"]}
            if any(item["role"] in roles and item["status"] == "available"
                   and _read_source(reader, item["artifact"]) for item in step["artifacts"]):
                return runtime
    raise _Rejected("IdentityMismatch")


def _harness_producer(domain, route):
    return {"kind": "harness_capture", "identity": "inferrsi-harness", "revision": "1",
            "control_domain": domain, "capture_route": route}


def _seal(check, raw, facts, spec, reader):
    common = {"schema_version": 1, "attempt_id": facts["attempt_id"],
              "operation": facts["operation"], "validation_scope": facts["validation_scope"]}
    producer = _harness_producer(facts["target_binding"]["control_domain"],
                                 "evaluation-capture-unavailable@1")
    if raw is not None:
        try:
            proof = json_v1.decode(raw)
            _require(json_v1.encode(proof) == raw)
        except json_v1.CanonicalError as error:
            raise _Rejected() from error
        _require(isinstance(proof, dict))
        _require(type(proof.get("schema_version")) is int and proof["schema_version"] == 1,
                 "UnsupportedSchema")
        _require(not set(proof) & {"producer", "control_domain", "capture_route",
                                  "evidence_refs", "record_ref"}, "IdentityMismatch")
        _require(all(proof.get(key) == value for key, value in common.items()),
                 "IdentityMismatch")
        source = check["source"]
        producer["capture_route"] = "evaluation-" + source + "@1"
        if source == "cleanup_capture":
            _require(type(proof.get("confirmed")) is bool
                     and proof["confirmed"] is bool(_cleanup_confirmed(facts)),
                     "IdentityMismatch")
        else:
            bound = _candidate(facts)
            _require(_read_source(reader, bound["retained_ref"])
                     and proof.get("candidate_id") == facts["candidate"]["candidate_id"]
                     and proof.get("actual_sha256") == bound["actual_sha256"], "IdentityMismatch")
            if source == "worker_report":
                runtime = _worker(facts, spec, reader, bound)
                producer.update(kind="task_worker", identity=runtime["entrypoint"],
                                revision=runtime["entrypoint_revision"])
        if "status" in proof:
            _require(proof["status"] == check["status"], "IdentityMismatch")
    return {
        **{key: deepcopy(check[key]) for key in
           ("check_id", "checker_revision", "subject", "phase", "artifact_schema",
            "status", "reasons")},
        **{key: value for key, value in common.items() if key != "schema_version"},
        "producer": producer, "evidence_refs": [],
    }


def _validate_result(result, phase):
    _require(isinstance(result, tuple) and len(result) == 2)
    draft, blobs = result
    draft = _snapshot(draft)
    _require(isinstance(draft, dict) and draft.keys() == {"schema_version", "checks", "errors"})
    _require(type(draft["schema_version"]) is int and draft["schema_version"] == 1,
             "UnsupportedSchema")
    _require(isinstance(draft["checks"], list) and isinstance(draft["errors"], list)
             and isinstance(blobs, dict) and all(run_store._is_id(key) for key in blobs))
    blobs = dict(blobs)
    _require(all(isinstance(value, bytes) for value in blobs.values()))
    used, ids = set(), set()
    for check in draft["checks"]:
        _require(isinstance(check, dict) and check.keys() == _CHECK)
        _require(all(run_store._is_id(check[key]) for key in
                     ("check_id", "checker_revision", "subject")) and _ids(check["reasons"]))
        definition = check["artifact_schema"]
        _require(isinstance(definition, dict) and definition.keys() == {"name", "revision"}
                 and all(run_store._is_id(value) for value in definition.values()))
        _require(isinstance(check["source"], str) and check["source"] in _SOURCES
                 and check["status"] in
                 ("passed", "failed", "not_performed"))
        if phase == "preparing":
            _require(check["source"] == "candidate_capture" and check["phase"] == "preparing")
        else:
            _require((check["source"] == "worker_report"
                      and check["phase"] in ("running", "finalizing"))
                     or (check["source"] == "cleanup_capture" and check["phase"] == "finalizing"))
        key = check["proof_key"]
        if check["status"] == "not_performed":
            _require(key is None)
        else:
            _require(isinstance(key, str) and key in blobs)
            used.add(key)
        ids.add(check["check_id"])
    _require(used == set(blobs))
    for error in draft["errors"]:
        _require(isinstance(error, dict) and error.keys() == {"code", "check_ids", "reason"}
                 and isinstance(error["code"], str) and error["code"] in _ERROR_CODES
                 and _ids(error["check_ids"])
                 and bool(error["check_ids"]) and set(error["check_ids"]) <= ids
                 and run_store._is_id(error["reason"]))
    return draft, blobs


def _rejection(phase, facts, code):
    return ([{
        "check_id": "evaluation_capture", "checker_revision": "1", "subject": "evaluation",
        "phase": phase, "artifact_schema": {"name": "capture-error", "revision": "1"},
        "status": "not_performed", "reasons": ["capture_contract_rejected"],
        **{key: facts[key] for key in ("attempt_id", "operation", "validation_scope")},
        "producer": _harness_producer(facts["target_binding"]["control_domain"],
                                       "evaluation-capture-rejected@1"), "evidence_refs": [],
    }], [{"code": code, "stage": phase, "message": "capture_contract_rejected",
          "retryable": False}], [], True)


def observe(capability, phase, facts, *, spec, root, namespace, retained):
    """Return checks/errors/tentative byte sources/refusal; H commits all sources once."""
    facts, spec = _snapshot(facts), _snapshot(spec)
    reader = _Reader(root, retained)
    try:
        callback = getattr(capability, "capture", None)
        _require(callable(callback))
        result = callback(phase, deepcopy(facts), artifacts=reader)
        draft, blobs = _validate_result(result, phase)
        checks, sources = [], []
        for item in draft["checks"]:
            raw = blobs.get(item["proof_key"])
            check = _seal(item, raw, facts, spec, reader)
            if raw is not None:
                ref = {"location": run_store.object_location(namespace, sha256(raw).hexdigest()),
                       "sha256": sha256(raw).hexdigest(), "size_bytes": len(raw),
                       "media_type": "application/json"}
                check["evidence_refs"] = [ref]
                sources.append((ref, raw))
            checks.append(check)
        errors = [{"code": item["code"], "stage": phase, "message": item["reason"],
                   "retryable": False} for item in draft["errors"]]
        refused = phase == "preparing" and any(item["code"] in _FATAL_CONFIG for item in errors)
        return checks, errors, sources, refused
    except Exception as error:
        code = getattr(error, "code", None)
        if not isinstance(code, str) or code not in _ERROR_CODES:
            raise
        return _rejection(phase, facts, code)
    finally:
        reader.active = False
