"""Read-only D023/P1 assessment of one fixed record and its retained evidence."""

from __future__ import annotations

import json
import re
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from ..contracts.json_v1 import CanonicalError
from ..contracts.json_v1 import decode as canonical_decode
from ..contracts.json_v1 import encode as canonical_encode
from . import preparation

_RESULT = set("schema_version assessment_id task grader assessor prepared_ref record_ref "
              "protocol_digest candidate attempt_id claims metrics eligibility comparison "
              "evidence_artifacts assessed_at supersedes derived_from limitations".split())
_CLAIM = set("claim_id validation_scope verdict reasons evidence "
             "missing_evidence limitations".split())
_RECORD = set("schema_version request_id run_id attempt_id request_digest owner target_request "
              "target_binding retry_of retry_reason generation_record_ref prepared_ref "
              "protocol_digest operation validation_scope candidate record_version recorded_at "
              "bound_inputs phase started side_effect_unknown process_outcome exit_code "
              "elapsed_seconds steps cancellation cleanup artifacts checks budget_admission "
              "usage resource_leases errors".split())
_COMMON = {"schema_version", "candidate_id", "actual_sha256", "attempt_id", "operation",
           "validation_scope"}
_ITEM_ERRORS = {"UnsafeArtifactPath", "ArtifactUnavailable", "ArtifactIntegrityError"}


class AssessmentError(ValueError):
    """A declared Benchmark rejection, independent of any Harness exception class."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def to_json(self) -> dict:
        return {
            "code": self.code,
            "stage": "assessment_binding" if self.code == "IdentityMismatch" else "assess",
            "attempt_id": None, "started": None, "latest_record_ref": None,
            "partial_record": None, "retained_refs": [], "field_errors": [],
            "message": str(self),
        }


def _require(condition, message="Invalid P1 assessment.", code="InvalidRequest"):
    if not condition:
        raise AssessmentError(code, message)


def _object(value, fields):
    _require(isinstance(value, dict) and value.keys() == fields)


def _artifact(value):
    preparation._artifact(value)
    _require(all(ord(char) >= 32 and ord(char) != 127 for char in value["location"]),
             "Artifact paths must not contain control characters.")


def _strings(value, *, identifiers=False):
    _require(isinstance(value, list) and all(
        preparation._id(item) if identifiers else isinstance(item, str) for item in value
    ))


def _timestamp(value):
    _require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", value
    ) is not None)
    try:
        datetime.fromisoformat(value[:19])
    except ValueError:
        raise AssessmentError("InvalidRequest", "Invalid assessment timestamp.") from None


def _projection(result):
    """Project only schema-declared ArtifactRefs, including nested candidate refs."""
    # JSON values have no alias identity: callers may reuse the same dict at
    # several typed paths without making the projection depend on object aliasing.
    value = canonical_decode(canonical_encode(result))
    del value["assessment_id"], value["assessed_at"]
    refs = [value["prepared_ref"], value["record_ref"], *value["derived_from"]]
    refs.extend(item["against"] for item in value["comparison"])
    if value["supersedes"] is not None:
        refs.append(value["supersedes"])
    artifacts = [ref["artifact"] for ref in refs]
    artifacts.extend(value["evidence_artifacts"])
    for items, field in ((value["claims"], "evidence"), (value["metrics"], "raw_samples")):
        artifacts.extend(ref for item in items for ref in item[field])
    if value["candidate"] is not None:
        artifacts.extend(value["candidate"]["context_refs"])
    for ref in artifacts:
        _artifact(ref)
        del ref["location"]
    return value


def assessment_id(result: dict) -> str:
    """Pure v1 identity; only assessed_at, the self ID and typed locations are excluded."""
    _object(result, _RESULT)
    try:
        return "sha256:" + sha256(canonical_encode(_projection(result))).hexdigest()
    except (KeyError, TypeError, CanonicalError, preparation.PreparationError):
        raise AssessmentError(
            "InvalidRequest", "Malformed assessment identity projection.",
        ) from None


def validate_assessment(result: dict) -> None:
    """Pure validation of the supported P1 result and its semantic identity."""
    canonical_encode(result)
    _object(result, _RESULT)
    _require(type(result["schema_version"]) is int and result["schema_version"] == 1,
             code="UnsupportedSchema")
    _require(result["task"] == {"name": "p1-fixture", "revision": "1"}
             and result["grader"] == {"name": "p1-rules", "revision": "1"}
             and result["assessor"] == {"name": "fixture-assessor", "revision": "1"},
             code="UnsupportedRuleVersion")
    _timestamp(result["assessed_at"])
    _require(preparation._id(result["attempt_id"]))
    _require(isinstance(result["protocol_digest"], str)
             and re.fullmatch(r"sha256:[a-f0-9]{64}", result["protocol_digest"]) is not None)
    for field, fields in (("prepared_ref", {"schema_version", "prepared_id", "artifact"}),
                          ("record_ref", {"attempt_id", "record_version", "artifact"})):
        _object(result[field], fields)
        _artifact(result[field]["artifact"])
    _require(result["prepared_ref"]["schema_version"] == 1
             and type(result["prepared_ref"]["schema_version"]) is int
             and re.fullmatch(r"sha256:[a-f0-9]{64}",
                              result["prepared_ref"]["prepared_id"]) is not None)
    _require(result["record_ref"]["attempt_id"] == result["attempt_id"]
             and type(result["record_ref"]["record_version"]) is int
             and result["record_ref"]["record_version"] > 0)
    candidate = result["candidate"]
    if candidate is not None:
        _object(candidate, {"candidate_id", "kind", "input_role", "parent_id",
                            "parent_digest", "context_refs"})
        _require(all(preparation._id(candidate[key])
                     for key in ("candidate_id", "kind", "input_role")))
        _require(isinstance(candidate["context_refs"], list))
        for ref in candidate["context_refs"]:
            _artifact(ref)
        _require(candidate["parent_id"] is None or preparation._id(candidate["parent_id"]))
        _require(candidate["parent_digest"] is None or isinstance(candidate["parent_digest"], str)
                 and preparation._SHA.fullmatch(candidate["parent_digest"]) is not None)
    _require(isinstance(result["claims"], list) and len(result["claims"]) == 3)
    keys = []
    for claim in result["claims"]:
        _object(claim, _CLAIM)
        keys.append((claim["claim_id"], claim["validation_scope"]))
        _require(claim["verdict"] in {"PASS", "FAIL", "INCONCLUSIVE"})
        for field in ("reasons", "missing_evidence"):
            _strings(claim[field], identifiers=True)
        _strings(claim["limitations"])
        _require(isinstance(claim["evidence"], list))
        for ref in claim["evidence"]:
            _artifact(ref)
    _require(len(set(keys)) == len(keys) and set(keys) == {("F", "p1"), ("C", "p1"), ("M", "p1")})
    # P1 freezes no metric definitions or assessment comparison target.
    _require(result["metrics"] == [] and result["comparison"] == []
             and result["supersedes"] is None and result["derived_from"] == [])
    _require(isinstance(result["eligibility"], list) and len(result["eligibility"]) == 1)
    eligibility = result["eligibility"][0]
    _object(eligibility, {"validation_scope", "status", "reasons"})
    _require(eligibility["validation_scope"] == "p1"
             and eligibility["status"] in {"eligible", "ineligible", "unknown"})
    _strings(eligibility["reasons"], identifiers=True)
    _strings(result["limitations"])
    _require(isinstance(result["evidence_artifacts"], list))
    for ref in result["evidence_artifacts"]:
        _artifact(ref)
    _require(result["assessment_id"] == assessment_id(result), "Invalid assessment identity.",
             "IdentityMismatch")


def encode(result: dict) -> bytes:
    validate_assessment(result)
    return canonical_encode(result)


def decode(data: bytes) -> dict:
    result = canonical_decode(data)
    _require(canonical_encode(result) == data, "Assessment bytes are not canonical.")
    validate_assessment(result)
    return result


class _RetainedBytes:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.cache = {}
        self.verified = []

    def read(self, ref):
        try:
            _artifact(ref)
        except (preparation.PreparationError, AssessmentError):
            return None, "invalid_artifact_ref"
        key = canonical_encode(ref)
        if key in self.cache:
            return self.cache[key]
        try:
            source = self.artifacts.open(deepcopy(ref))
            if isinstance(source, bytes):
                data = source
            else:
                chunks, remaining = [], ref["size_bytes"] + 1
                with closing(source):
                    while remaining > 0:
                        chunk = source.read(min(remaining, 1024 * 1024))
                        if not isinstance(chunk, bytes):
                            raise TypeError("ArtifactReader must supply binary bytes or streams.")
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                data = b"".join(chunks)
        except Exception as error:
            # Portable error codes are the capability contract; importing an Apps
            # or Harness exception class would invert the module dependency.
            if getattr(error, "code", None) not in _ITEM_ERRORS:
                raise
            self.cache[key] = (None, error.code)
            return self.cache[key]
        if len(data) != ref["size_bytes"] or sha256(data).hexdigest() != ref["sha256"]:
            self.cache[key] = (None, "ArtifactIntegrityError")
        else:
            self.cache[key] = (data, None)
            self.verified.append(deepcopy(ref))
        return self.cache[key]


def _binding(prepared, evidence):
    preparation.encode(prepared)
    _artifact(prepared["protocol"])
    for resource in prepared["resources"]:
        _artifact(resource["artifact"])
    _object(evidence, {"schema_version", "record_ref", "record_digest", "task", "task_source",
                       "record", "artifact_checks"})
    record, ref = evidence["record"], evidence["record_ref"]
    _object(record, _RECORD)
    _object(ref, {"attempt_id", "record_version", "artifact"})
    _object(record["prepared_ref"], {"schema_version", "prepared_id", "artifact"})
    _artifact(ref["artifact"])
    _require(type(evidence["schema_version"]) is int and evidence["schema_version"] == 1
             and type(record["schema_version"]) is int and record["schema_version"] == 1)
    data = canonical_encode(record)
    _require(evidence["task"] == prepared["task"] and evidence["task_source"] == "prepared_ref"
             and evidence["record_digest"] == ref["artifact"]["sha256"]
             and (sha256(data).hexdigest(), len(data))
             == (ref["artifact"]["sha256"], ref["artifact"]["size_bytes"])
             and record["attempt_id"] == ref["attempt_id"]
             and record["record_version"] == ref["record_version"]
             and record["prepared_ref"]["prepared_id"] == prepared["prepared_id"]
             and all(record[key] == prepared[key]
                     for key in ("protocol_digest", "operation", "validation_scope")),
             "Prepared and fixed record identities differ.", "IdentityMismatch")
    for field in ("checks", "bound_inputs", "steps", "artifact_checks"):
        _require(isinstance((evidence if field == "artifact_checks" else record)[field], list))
    if record["candidate"] is not None:
        _require(isinstance(record["candidate"], dict)
                 and all(record["candidate"].get(key) == prepared["candidate_contract"][key]
                         for key in ("kind", "input_role")),
                 "Candidate contract differs from the frozen preparation.", "IdentityMismatch")
    if prepared["expected_candidate"] is not None:
        _require(record["candidate"] is not None
                 and record["candidate"]["candidate_id"]
                 == prepared["expected_candidate"]["candidate_id"],
                 "Declared candidate identity differs.", "IdentityMismatch")
        for item in record["bound_inputs"]:
            if (isinstance(item, dict) and item.get("role") == record["candidate"]["input_role"]
                    and item.get("attempt_id") == record["attempt_id"]
                    and item.get("expected_sha256") is not None):
                _require(item["expected_sha256"] == prepared["expected_candidate"]["sha256"],
                         "Declared candidate expectation differs.", "IdentityMismatch")
    return record


def _captured_candidate(prepared, record, reader):
    candidate = record["candidate"]
    if not isinstance(candidate, dict):
        return None
    matches = [item for item in record["bound_inputs"] if isinstance(item, dict)
               and item.get("role") == candidate.get("input_role")
               and item.get("attempt_id") == record["attempt_id"]]
    if len(matches) != 1 or candidate.get("kind") != prepared["candidate_contract"]["kind"]:
        return None
    item = matches[0]
    ref, digest = item.get("retained_ref"), item.get("actual_sha256")
    if not isinstance(ref, dict) or digest != ref.get("sha256") or item.get("captured_at") is None:
        return None
    try:
        _timestamp(item["captured_at"])
    except AssessmentError:
        return None
    data, _ = reader.read(ref)
    return digest if data is not None else None


def _trusted(check, required, prepared, record):
    fields = {"check_id": required["check_id"], "checker_revision": required["checker_revision"],
              "subject": required["subject"], "phase": required["phase"],
              "artifact_schema": required["artifact_schema"], "operation": record["operation"],
              "validation_scope": record["validation_scope"], "attempt_id": record["attempt_id"]}
    if any(check.get(key) != value for key, value in fields.items()):
        return False
    producer, binding = check.get("producer"), record["target_binding"]
    if not isinstance(producer, dict) or not isinstance(binding, dict):
        return False
    if (producer.get("kind") not in required["allowed_producer_kinds"]
            or producer.get("control_domain") not in required["allowed_control_domains"]
            or producer.get("control_domain") != binding.get("control_domain")
            or not preparation._id(producer.get("capture_route"))):
        return False
    worker = producer["kind"] == "task_worker"
    if worker or required["check_id"] == "samples":
        runtimes = binding.get("runtime_bindings_by_step")
        if (record["started"] is not True or not isinstance(record["candidate"], dict)
                or not isinstance(runtimes, list)):
            return False
        recipe = prepared["recipe"]
        step_ids = {step["step_id"] for step in record["steps"] if isinstance(step, dict)
                    and preparation._id(step.get("step_id"))
                    and step.get("status") != "not_started"
                    and (step.get("started_at") is not None or step.get("status")
                         in {"running", "exited", "timed_out", "cancelled"})}
        input_steps = {step for item in record["bound_inputs"] if isinstance(item, dict)
                       and item.get("role") == record["candidate"]["input_role"]
                       and item.get("attempt_id") == record["attempt_id"]
                       and isinstance(item.get("step_ids"), list)
                       for step in item["step_ids"] if preparation._id(step)}
        if not any(isinstance(runtime, dict)
                   and runtime.get("step_id") in step_ids & input_steps
                   and runtime.get("runtime_role") == recipe["runtime_role"]
                   and runtime.get("entrypoint") == recipe["entrypoint"]
                   and runtime.get("entrypoint_revision") == recipe["entrypoint_revision"]
                   and runtime.get("code_sha256") == recipe["code_sha256"]
                   for runtime in runtimes):
            return False
        if worker:
            return (producer.get("identity") == recipe["entrypoint"]
                    and producer.get("revision") == recipe["entrypoint_revision"])
    return preparation._id(producer.get("identity"))


def _proof_json(data):
    # Raw evidence is hashed as retained, not rewritten into the DTO encoding.
    # JSON whitespace is allowed; duplicate keys, non-finite/floating tokens,
    # invalid Unicode and out-of-range integers must still be refused.
    def pairs(items):
        result = {}
        for key, item in items:
            _require(key not in result, "Duplicate evidence key.")
            result[key] = item
        return result

    def number(_):
        raise AssessmentError("InvalidRequest", "Evidence requires Decimal strings.")

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_float=number, parse_constant=number)
        canonical_encode(value)
    except (ValueError, UnicodeError, RecursionError):
        raise AssessmentError("InvalidRequest", "Invalid P1 evidence JSON.") from None
    return value


def _proof(data, required, record, actual):
    value = _proof_json(data)
    key = required["check_id"]
    common = {"schema_version": 1, "attempt_id": record["attempt_id"],
              "operation": record["operation"], "validation_scope": record["validation_scope"]}
    if key == "cleanup":
        _object(value, set(common) | {"confirmed"})
        _require(type(value["confirmed"]) is bool)
    else:
        common.update(candidate_id=record["candidate"]["candidate_id"], actual_sha256=actual)
        _require(actual is not None)
        if key in ("format", "grader"):
            _object(value, _COMMON | {"claim_id", "checker_revision", "status", "reasons"})
            _require(value["claim_id"] == required["for_claims"][0]
                     and value["checker_revision"] == required["checker_revision"]
                     and value["status"] in {"passed", "failed"})
            _strings(value["reasons"], identifiers=True)
        else:
            _object(value, _COMMON | {"samples"})
            _require(isinstance(value["samples"], list) and len(value["samples"]) == 4)
            for sample, identity in zip(value["samples"], (
                ("A1", "baseline", 1), ("B1", "candidate", 1),
                ("B2", "candidate", 2), ("A2", "baseline", 2),
            )):
                _object(sample, {"sample_id", "role", "round", "value", "unit"})
                _require((sample["sample_id"], sample["role"], sample["round"]) == identity
                         and type(sample["round"]) is int and sample["unit"] == "ms"
                         and isinstance(sample["value"], str)
                         and preparation._DECIMAL.fullmatch(sample["value"]) is not None
                         and Decimal(sample["value"]) > 0)
    _require(type(value["schema_version"]) is int
             and all(value[field] == expected for field, expected in common.items()))
    return value


def _observations(required, prepared, record, actual, reader):
    proofs, refs, problems = [], [], []
    for check in record["checks"]:
        if not isinstance(check, dict) or check.get("check_id") != required["check_id"]:
            continue
        if (not _trusted(check, required, prepared, record)
                or check.get("status") not in {"passed", "failed"}
                or not isinstance(check.get("evidence_refs"), list)
                or not check["evidence_refs"]):
            problems.append("untrusted_or_incomplete_check")
            continue
        for ref in check["evidence_refs"]:
            data, reason = reader.read(ref)
            if data is None:
                problems.append(reason)
                continue
            try:
                proof = _proof(data, required, record, actual)
                if "status" in proof:
                    _require(proof["status"] == check["status"])
            except (CanonicalError, AssessmentError, KeyError, TypeError):
                problems.append("invalid_evidence")
                continue
            proofs.append(proof)
            refs.append(ref)
    key = required["check_id"]
    signatures = {canonical_encode(proof if key == "samples" else proof.get(
        "status", proof.get("confirmed"))) for proof in proofs}
    return proofs, refs, problems, len(signatures) > 1


def _unique(refs):
    return list({canonical_encode(ref): deepcopy(ref) for ref in refs}.values())


def _cleanup_confirmed(record):
    cleanup, resources = record["cleanup"], record["resource_leases"]
    if (not isinstance(cleanup, dict) or not isinstance(resources, dict)
            or not isinstance(resources.get("leases"), list)):
        return False
    if (cleanup.get("status") != "confirmed" or cleanup.get("process_exit_confirmed") is not True
            or resources.get("applicability") not in {"applicable", "not_applicable"}
            or resources.get("applicability") == "not_applicable" and resources["leases"]
            or resources.get("applicability") == "applicable" and not resources["leases"]):
        return False
    for lease in resources["leases"]:
        if not isinstance(lease, dict) or lease.get("release_confirmed") is not True:
            return False
        try:
            _timestamp(lease.get("release_confirmed_at"))
        except AssessmentError:
            return False
    return True


def _claim(definition, protocol, prepared, record, actual, reader):
    missing, reasons, refs, decisions = [], [], [], []
    conflict = False
    for required in protocol["required_evidence"]:
        if definition["claim_id"] not in required["for_claims"]:
            continue
        proofs, used, problems, contradicted = _observations(
            required, prepared, record, actual, reader,
        )
        refs.extend(used)
        conflict |= contradicted
        if not proofs or problems:
            missing.append(required["check_id"])
            reasons.extend(problems)
        elif required["check_id"] == "cleanup" and not all(p["confirmed"] for p in proofs):
            missing.append("cleanup")
        else:
            decisions.extend(p.get("status", "passed") for p in proofs)
            reasons.extend(reason for p in proofs for reason in p.get("reasons", []))
    if definition["requires_completed_measurement"] and not (
        record["phase"] == "finished" and record["started"] is True
        and record["process_outcome"] == "exited" and record["exit_code"] == 0
        and record["side_effect_unknown"] is False
        and record["steps"] and all(isinstance(step, dict) and step.get("status") == "exited"
                                    and step.get("exit_code") == 0 for step in record["steps"])
    ):
        missing.append("completed_measurement")
    if definition["requires_cleanup_confirmed"] and not _cleanup_confirmed(record):
        missing.append("cleanup_confirmation")
    if conflict:
        reasons.append("conflicting_evidence")
    if missing:
        reasons.append("required_evidence_missing")
    verdict = "INCONCLUSIVE" if conflict or missing else (
        "FAIL" if "failed" in decisions else "PASS"
    )
    return {
        "claim_id": definition["claim_id"], "validation_scope": definition["validation_scope"],
        "verdict": verdict, "reasons": list(dict.fromkeys(reasons)), "evidence": _unique(refs),
        "missing_evidence": list(dict.fromkeys(missing)), "limitations": [],
    }


class AssessmentService:
    """The offline P1 port; a clock is injected only for reproducible timestamps."""

    def __init__(self, *, clock=None):
        self._clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )

    def assess(self, prepared: dict, evidence: dict, *, artifacts) -> dict:
        try:
            prepared = canonical_decode(canonical_encode(prepared))
            evidence = canonical_decode(canonical_encode(evidence))
        except CanonicalError:
            return AssessmentError(
                "InvalidRequest", "Malformed canonical assessment input.",
            ).to_json()
        try:
            try:
                record = _binding(prepared, evidence)
            except (KeyError, TypeError):
                raise AssessmentError("InvalidRequest", "Malformed fixed evidence input.") from None
            reader = _RetainedBytes(artifacts)
            data, reason = reader.read(prepared["protocol"])
            _require(data is not None, "Frozen protocol unavailable.",
                     reason if reason in _ITEM_ERRORS else "InvalidRequest")
            try:
                preparation.validate_prepared(prepared, data)
                protocol = canonical_decode(data)
            except CanonicalError:
                raise AssessmentError("InvalidRequest", "Invalid frozen protocol bytes.") from None
            for resource in preparation._closure(protocol):
                _artifact(resource["artifact"])
            actual = _captured_candidate(prepared, record, reader)
            claims = [_claim(item, protocol, prepared, record, actual, reader)
                      for item in protocol["claim_definitions"]]
            verdicts = {claim["verdict"] for claim in claims}
            conflict = any("conflicting_evidence" in claim["reasons"] for claim in claims)
            status = "ineligible" if conflict or "FAIL" in verdicts else (
                "eligible" if verdicts == {"PASS"} else "unknown"
            )
            result = {
                "schema_version": 1, "assessment_id": "", "task": deepcopy(prepared["task"]),
                "grader": deepcopy(prepared["grader"]),
                "assessor": {"name": "fixture-assessor", "revision": "1"},
                "prepared_ref": deepcopy(record["prepared_ref"]),
                "record_ref": deepcopy(evidence["record_ref"]),
                "protocol_digest": record["protocol_digest"],
                "candidate": deepcopy(record["candidate"]), "attempt_id": record["attempt_id"],
                "claims": claims, "metrics": [], "comparison": [],
                "eligibility": [{"validation_scope": "p1", "status": status,
                                 "reasons": ["conflicting_evidence"] if conflict else (
                                     ["claim_failed"] if status == "ineligible" else (
                                         [] if status == "eligible" else ["incomplete_evidence"]
                                     ))}],
                "evidence_artifacts": reader.verified, "assessed_at": self._clock(),
                "supersedes": None, "derived_from": [], "limitations": [],
            }
            result["assessment_id"] = assessment_id(result)
            validate_assessment(result)
            return result
        except (AssessmentError, preparation.PreparationError) as error:
            return AssessmentError(error.code, str(error)).to_json()


def assess(prepared: dict, evidence: dict, *, artifacts) -> dict:
    """Assess the first frozen task using a real UTC assessment clock."""
    return AssessmentService().assess(prepared, evidence, artifacts=artifacts)
