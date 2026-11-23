"""Pure P1 worker-report codecs and drafts for a host-owned capture lifecycle.

Drafts are not observations or committed references. Harness must authenticate
their source, retain the bytes and seal producer/attempt fields before commit.
This module neither runs a grader nor manufactures measurement samples.
"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from ..contracts.json_v1 import CanonicalError
from ..contracts.json_v1 import decode as canonical_decode
from ..contracts.json_v1 import encode as canonical_encode
from . import assessment, preparation

CONTEXT_FIELDS = frozenset(
    "schema_version request_id run_id attempt_id request_digest prepared_ref protocol_digest "
    "operation validation_scope candidate bound_inputs target_binding steps started "
    "process_outcome exit_code cleanup resource_leases".split()
)
_ORDER = (("A1", "baseline", 1), ("B1", "candidate", 1),
          ("B2", "candidate", 2), ("A2", "baseline", 2))


class ProofError(ValueError):
    """A declared codec/configuration rejection; no dependency on Harness types."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require(condition, message="Invalid proof projection input.", code="InvalidRequest"):
    if not condition:
        raise ProofError(code, message)


def _object(value, fields):
    _require(isinstance(value, dict) and value.keys() == fields)


def _snapshot(value):
    try:
        return canonical_decode(canonical_encode(value))
    except CanonicalError:
        raise ProofError("InvalidRequest", "Invalid canonical projection input.") from None


def _report_envelope(data):
    if not isinstance(data, bytes):
        raise TypeError("A worker report must be bytes.")
    try:
        value = assessment._proof_json(data)
    except (CanonicalError, assessment.AssessmentError) as error:
        raise ProofError("InvalidRequest", "Invalid worker report JSON.") from error
    _object(value, {"schema_version", "grader", "samples"})
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1,
             "Unsupported worker report version.", "UnsupportedSchema")
    return value


def _grader(value):
    _object(value, {"status", "reasons"})
    _require(value["status"] in ("passed", "failed")
             and isinstance(value["reasons"], list)
             and all(preparation._id(reason) for reason in value["reasons"]))


def _samples(values):
    _require(isinstance(values, list) and len(values) == len(_ORDER))
    for item, identity in zip(values, _ORDER):
        _object(item, {"sample_id", "role", "round", "value", "unit"})
        _require(type(item["round"]) is int
                 and (item["sample_id"], item["role"], item["round"]) == identity
                 and item["unit"] == "ms" and isinstance(item["value"], str)
                 and preparation._DECIMAL.fullmatch(item["value"]) is not None
                 and Decimal(item["value"]) > 0)


def validate_report(value: dict) -> None:
    """Validate the complete closed fixture-grader@1 report without I/O."""
    value = _report_envelope(canonical_encode(_snapshot(value)))
    if value["grader"] is not None:
        _grader(value["grader"])
    if value["samples"] is not None:
        _samples(value["samples"])


def encode_report(value: dict) -> bytes:
    validate_report(value)
    return canonical_encode(value)


def decode_report(data: bytes) -> dict:
    """Raw report whitespace is allowed; strict v1 JSON and family rules apply."""
    value = _report_envelope(data)
    validate_report(value)
    return value


def _context(facts, prepared):
    _object(facts, CONTEXT_FIELDS)
    _require(type(facts["schema_version"]) is int and facts["schema_version"] == 1,
             "Unsupported capture context.", "UnsupportedSchema")
    _require(all(preparation._id(facts[key]) for key in ("request_id", "run_id", "attempt_id"))
             and facts["request_id"] == facts["attempt_id"])
    digest = facts["request_digest"]
    _require(isinstance(digest, str) and digest.startswith("sha256:")
             and preparation._SHA.fullmatch(digest[7:]) is not None)
    ref = facts["prepared_ref"]
    _object(ref, {"schema_version", "prepared_id", "artifact"})
    try:
        preparation._artifact(ref["artifact"])
    except preparation.PreparationError as error:
        raise ProofError(error.code, str(error)) from error
    _require(type(ref["schema_version"]) is int and ref["schema_version"] == 1
             and ref["prepared_id"] == prepared["prepared_id"]
             and all(facts[key] == prepared[key]
                     for key in ("protocol_digest", "operation", "validation_scope")),
             "Capture context differs from the preparation.", "IdentityMismatch")
    candidate = facts["candidate"]
    _require(isinstance(candidate, dict) and preparation._id(candidate.get("candidate_id"))
             and all(candidate.get(key) == prepared["candidate_contract"][key]
                     for key in ("kind", "input_role")),
             "Candidate contract differs.", "IdentityMismatch")
    expected = prepared["expected_candidate"]
    _require(expected is None or candidate["candidate_id"] == expected["candidate_id"],
             "Candidate declaration differs.", "IdentityMismatch")
    _require(isinstance(facts["bound_inputs"], list) and isinstance(facts["steps"], list)
             and type(facts["started"]) is bool and isinstance(facts["target_binding"], dict))


def _candidate_digest(facts, data, prepared):
    if data is None:
        return None
    if not isinstance(data, bytes):
        raise TypeError("Captured candidate content must be bytes or None.")
    matches = [item for item in facts["bound_inputs"] if isinstance(item, dict)
               and item.get("role") == facts["candidate"]["input_role"]
               and item.get("attempt_id") == facts["attempt_id"]]
    _require(len(matches) == 1, "Candidate capture is ambiguous.", "IdentityMismatch")
    item = matches[0]
    digest, ref = sha256(data).hexdigest(), item.get("retained_ref")
    _require(isinstance(ref, dict) and item.get("actual_sha256") == ref.get("sha256") == digest
             and type(ref.get("size_bytes")) is int and ref["size_bytes"] == len(data)
             and item.get("captured_at") is not None and item.get("snapshot_format") == "file-v1",
             "Candidate bytes differ from the actual capture.", "IdentityMismatch")
    try:
        preparation._artifact(ref)
        assessment._timestamp(item["captured_at"])
    except (preparation.PreparationError, assessment.AssessmentError) as error:
        raise ProofError("IdentityMismatch", "Invalid actual candidate capture.") from error
    expected = prepared["expected_candidate"]
    _require(expected is None or expected["sha256"] == digest,
             "Actual candidate differs from its frozen expectation.", "IdentityMismatch")
    return digest


def _worker_bound(facts, prepared):
    if facts["started"] is not True:
        return False
    runtimes = facts["target_binding"].get("runtime_bindings_by_step")
    if not isinstance(runtimes, list):
        return False
    started = {step.get("step_id") for step in facts["steps"] if isinstance(step, dict)
               and step.get("status") != "not_started" and step.get("started_at") is not None
               and preparation._id(step.get("step_id"))}
    inputs = {step for item in facts["bound_inputs"] if isinstance(item, dict)
              and item.get("role") == facts["candidate"]["input_role"]
              and item.get("attempt_id") == facts["attempt_id"]
              and isinstance(item.get("step_ids"), list)
              for step in item["step_ids"] if preparation._id(step)}
    recipe = prepared["recipe"]
    return any(isinstance(runtime, dict) and preparation._id(runtime.get("step_id"))
               and runtime.get("step_id") in started & inputs
               and all(runtime.get(key) == recipe[key] for key in
                       ("runtime_role", "entrypoint", "entrypoint_revision", "code_sha256"))
               for runtime in runtimes)


class ProofProjector:
    """Freeze supported configuration before execution; project supplied bytes only."""

    def __init__(self, prepared: dict, protocol_bytes: bytes):
        self._prepared = _snapshot(prepared)
        try:
            preparation.validate_prepared(self._prepared, protocol_bytes)
        except (CanonicalError, preparation.PreparationError) as error:
            raise ProofError(getattr(error, "code", "InvalidRequest"), str(error)) from error

    def project(self, phase, facts, *, candidate_bytes, report_bytes):
        """Return (draft wire, proof bytes), never producer identities or valid Refs."""
        _require(phase in ("preparing", "finalizing"), "Unsupported capture phase.")
        if report_bytes is not None and not isinstance(report_bytes, bytes):
            raise TypeError("A worker report must be bytes or None.")
        prepared, facts = self._prepared, _snapshot(facts)
        _context(facts, prepared)
        if phase == "preparing":
            _require(facts["started"] is False
                     and all(facts[key] is None for key in
                             ("process_outcome", "exit_code", "cleanup", "resource_leases")),
                     "Preparing capture must precede worker and terminal observations.",
                     "IdentityMismatch")
        actual = _candidate_digest(facts, candidate_bytes, prepared)
        required = {item["check_id"]: item for item in prepared["required_evidence"]}
        draft, blobs = {"schema_version": 1, "checks": [], "errors": []}, {}
        common = {"schema_version": 1, "attempt_id": facts["attempt_id"],
                  "operation": facts["operation"], "validation_scope": facts["validation_scope"]}
        candidate = {**common, "candidate_id": facts["candidate"]["candidate_id"],
                     "actual_sha256": actual}

        def emit(key, source, status, proof=None, reasons=(), error=None):
            rule = required[key]
            allowed = (facts["target_binding"].get("control_domain")
                       in rule["allowed_control_domains"])
            if not allowed:
                status, proof, reasons, error = (
                    "not_performed", None, ["control_domain_mismatch"], "IdentityMismatch",
                )
            proof_key = key if proof is not None else None
            draft["checks"].append({
                **{field: rule[field] for field in
                   ("check_id", "checker_revision", "subject", "phase", "artifact_schema")},
                "status": status, "reasons": list(reasons), "proof_key": proof_key,
                "source": source,
            })
            if proof is not None:
                blobs[key] = canonical_encode(proof)
            if error:
                draft["errors"].append({"code": error, "check_ids": [key],
                                        "reason": reasons[0]})

        if phase == "preparing":
            if actual is None:
                emit("format", "candidate_capture", "not_performed",
                     reasons=["candidate_bytes_unavailable"], error="ArtifactUnavailable")
            else:
                try:
                    candidate_bytes.decode("utf-8")
                    status, reasons = "passed", []
                except UnicodeError:
                    status, reasons = "failed", ["invalid_utf8"]
                emit("format", "candidate_capture", status, {
                    **candidate, "claim_id": "F", "checker_revision": "1",
                    "status": status, "reasons": reasons,
                }, reasons)
            return _snapshot(draft), dict(blobs)

        report, report_error, report_reason = None, None, None
        if report_bytes is None:
            report_error, report_reason = "ArtifactUnavailable", "worker_report_unavailable"
        elif actual is None:
            report_error, report_reason = "ArtifactUnavailable", "candidate_bytes_unavailable"
        elif not _worker_bound(facts, prepared):
            report_error, report_reason = "IdentityMismatch", "worker_not_bound"
        else:
            try:
                report = _report_envelope(report_bytes)
            except ProofError as error:
                report_error, report_reason = error.code, "invalid_worker_report"

        for key, field, validate in (("grader", "grader", _grader),
                                     ("samples", "samples", _samples)):
            if report is None:
                emit(key, "worker_report", "not_performed", reasons=[report_reason],
                     error=report_error)
                continue
            family = report[field]
            if family is None:
                emit(key, "worker_report", "not_performed", reasons=["report_family_incomplete"],
                     error="InvalidRequest")
                continue
            try:
                validate(family)
            except ProofError as error:
                emit(key, "worker_report", "not_performed", reasons=["invalid_report_family"],
                     error=error.code)
                continue
            status, reasons = (family["status"], family["reasons"]) if key == "grader" else (
                "passed", [],
            )
            payload = ({"claim_id": "C", "checker_revision": "1", **family}
                       if key == "grader" else {"samples": family})
            emit(key, "worker_report", status, {**candidate, **payload}, reasons)

        if facts["cleanup"] is None or facts["resource_leases"] is None:
            emit("cleanup", "cleanup_capture", "not_performed", reasons=["cleanup_unobserved"])
        else:
            confirmed = assessment._cleanup_confirmed(facts)
            emit("cleanup", "cleanup_capture", "passed" if confirmed else "failed",
                 {**common, "confirmed": confirmed}, [] if confirmed else ["cleanup_unconfirmed"])
        return _snapshot(draft), dict(blobs)


def project(prepared, protocol_bytes, phase, facts, *, candidate_bytes, report_bytes):
    """One-shot pure projection; hosts may cache ProofProjector for frozen config."""
    return ProofProjector(prepared, protocol_bytes).project(
        phase, facts, candidate_bytes=candidate_bytes, report_bytes=report_bytes,
    )
