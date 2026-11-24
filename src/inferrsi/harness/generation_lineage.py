"""Same-Store generation-to-evaluation admission over H's sealed input facts."""

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256

from inferrsi.contracts import json_v1
from inferrsi.harness import prepared_binding, run_store
from inferrsi.harness.errors import PublicError

_PLAN_FIELDS = {"schema_version", "provider", "output_contract", "context_refs", "attempt_id"}


def _require(condition, message, code="IdentityMismatch"):
    if not condition:
        raise PublicError(code, stage="validate", started=False, message=message)


def _read(store, ref, *, collect=True):
    _require(
        run_store._has_fields(ref, {"location", "sha256", "size_bytes", "media_type"})
        and prepared_binding._is_path(ref["location"])
        and prepared_binding._is_sha256(ref["sha256"])
        and type(ref["size_bytes"]) is int and 0 <= ref["size_bytes"] <= json_v1.MAX_SAFE_INTEGER
        and isinstance(ref["media_type"], str) and bool(ref["media_type"]),
        "invalid retained generation ArtifactRef", "ArtifactIntegrityError",
    )
    chunks, total, digest = [], 0, sha256()
    with store.open(deepcopy(ref)) as stream:
        while total <= ref["size_bytes"]:
            chunk = stream.read(min(1024 * 1024, ref["size_bytes"] + 1 - total))
            if not chunk:
                break
            _require(isinstance(chunk, bytes), "retained source is not bytes",
                     "ArtifactIntegrityError")
            if collect:
                chunks.append(chunk)
            total += len(chunk)
            digest.update(chunk)
    _require(total == ref["size_bytes"] and digest.hexdigest() == ref["sha256"],
             "retained generation bytes differ from their Ref", "ArtifactIntegrityError")
    return b"".join(chunks) if collect else None


def _time(value):
    _require(run_store._is_timestamp(value), "invalid original timestamp", "ArtifactIntegrityError")
    # Timestamp permits nanoseconds; datetime would truncate a sub-microsecond extension.
    fraction = value[20:-1] if value[19] == "." else "0"
    return value[:19], Decimal("0." + fraction)


def _source(store, spec):
    ref = spec["generation_record_ref"]
    _require(ref["artifact"]["location"] == run_store.record_location(
        store.namespace, ref["attempt_id"], ref["record_version"],
    ), "generation must belong to this authorized Store", "UnsupportedOperation")
    _require(ref["attempt_id"] != spec["attempt_id"], "generation and evaluation reuse an attempt")
    committed = store.committed(ref["attempt_id"], ref["record_version"])
    _require(committed.record_ref == ref, "generation RecordRef differs from the fixed record")
    record = committed.payload
    _require(all(record[key] == spec[key] for key in ("run_id", "owner")),
             "generation belongs to another run or owner")
    _require(
        record["phase"] == "finished" and record["process_outcome"] == "exited"
        and type(record["exit_code"]) is int and record["exit_code"] == 0
        and record["side_effect_unknown"] is False
        and all(record[key] is None for key in (
            "candidate", "prepared_ref", "protocol_digest", "operation", "validation_scope",
            "generation_record_ref",
        )), "lineage requires a successful ordinary generation", "UnsupportedOperation",
    )
    bounds = store._read_generation_bounds(ref["attempt_id"])
    _require(bounds is not None, "generation has no original-bounds snapshot",
             "UnsupportedOperation")
    _require(bounds["request_digest"] == record["request_digest"]
             and all(bounds[key] == record[key] for key in ("attempt_id", "run_id", "owner")),
             "generation differs from its original sealed binding")
    from inferrsi.harness.execution_service import _request_errors

    _require(not _request_errors({**spec, "budget": bounds["budget"]}),
             "invalid original budget snapshot", "ArtifactIntegrityError")
    _require(_time(bounds["deadline_utc"]) > _time(run_store.utc_now()),
             "original generation deadline has expired", "UnsupportedOperation")
    _require(_time(spec["deadline_utc"]) <= _time(bounds["deadline_utc"]),
             "evaluation extends the original generation deadline")
    _require(all(spec["budget"][key] == bounds["budget"][key]
                 for key in ("scope_id", "policy_ref")),
             "evaluation changes the original budget scope or policy")

    data = _read(store, bounds["generation_plan"])
    manifest = json_v1.decode(data)
    _require(run_store._has_fields(manifest, _PLAN_FIELDS),
             "invalid pre-sealed generation plan", "ArtifactIntegrityError")
    _require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
             "unsupported generation plan version", "UnsupportedSchema")
    _require(manifest["attempt_id"] == record["attempt_id"],
             "generation plan names another attempt")
    plans = [item for item in record["bound_inputs"] if item["role"] == "generation_plan"]
    _require(len(plans) == 1, "generation must have one captured pre-sealed plan")
    plan = plans[0]
    _require(plan["attempt_id"] == record["attempt_id"]
             and plan["snapshot_format"] == "file-v1" and plan["identity_status"] == "matched"
             and plan["expected_sha256"] == plan["actual_sha256"]
             == bounds["generation_plan"]["sha256"]
             and plan["retained_ref"] is not None,
             "generation plan capture differs from its original binding")
    _require(_read(store, plan["retained_ref"]) == data,
             "captured generation plan differs from its sealed bytes", "ArtifactIntegrityError")
    contract = manifest["output_contract"]
    _require(isinstance(contract, dict) and run_store._is_id(contract.get("candidate_role"))
             and prepared_binding._is_definition(contract.get("format_schema")),
             "generation plan has no supported candidate role", "ArtifactIntegrityError")
    outputs = [item for item in record["artifacts"]
               if item["role"] == contract["candidate_role"]]
    _require(len(outputs) == 1, "generation candidate role is absent or ambiguous")
    output = outputs[0]
    _require(output["attempt_id"] == record["attempt_id"]
             and output["step_id"] in {step["step_id"] for step in record["steps"]}
             and output["format_schema"] == contract["format_schema"],
             "generation candidate producer or format differs")
    _require(output["status"] == "available" and output["artifact"] is not None,
             "generation candidate is not retained", "ArtifactUnavailable")
    candidate = output["artifact"]
    inputs = [item for item in spec["inputs"] if item["role"] == spec["candidate"]["input_role"]]
    _require(len(inputs) == 1, "evaluation needs one candidate input")
    item = inputs[0]
    _require(item["source_namespace"] == "artifact" and item["source_ref"] == candidate
             and item["source"] == candidate["location"]
             and item["expected_sha256"] == candidate["sha256"],
             "evaluation does not use the original retained candidate")
    _require(item["snapshot_format"] == "file-v1", "unsupported generated candidate snapshot",
             "UnsupportedRuleVersion")
    _read(store, candidate, collect=False)
    return deepcopy(candidate)


class _CaptureReader:
    """Read the authorized candidate again through H; delegate unrelated artifacts."""

    def __init__(self, store, delegate, candidate):
        self._store, self._delegate, self._candidate = store, delegate, deepcopy(candidate)

    def open(self, ref):
        if ref == self._candidate:
            return self._store.open(deepcopy(ref))
        if self._delegate is None:
            raise PublicError("ArtifactUnavailable", stage="bind", started=False,
                              message="no reader for an unrelated input artifact")
        return self._delegate.open(ref)


def authorize(store, spec, reader):
    """Authorize only a fresh request, then return its read-only capture router."""
    try:
        ref = spec["generation_record_ref"]
        _require(run_store._has_fields(ref, {"attempt_id", "record_version", "artifact"})
                 and run_store._is_id(ref["attempt_id"])
                 and type(ref["record_version"]) is int
                 and 1 <= ref["record_version"] <= json_v1.MAX_SAFE_INTEGER
                 and run_store._has_fields(ref["artifact"], {
                     "location", "sha256", "size_bytes", "media_type",
                 })
                 and prepared_binding._is_path(ref["artifact"]["location"])
                 and prepared_binding._is_sha256(ref["artifact"]["sha256"])
                 and type(ref["artifact"]["size_bytes"]) is int
                 and 0 <= ref["artifact"]["size_bytes"] <= json_v1.MAX_SAFE_INTEGER
                 and ref["artifact"]["media_type"] == "application/json",
                 "generation_record_ref must be a fixed RecordRef", "InvalidExecutionSpec")
        return _CaptureReader(store, reader, _source(store, spec))
    except PublicError as exc:
        raise PublicError(
            exc.code, stage="validate", attempt_id=spec["attempt_id"], started=False,
            retained_refs=exc.retained_refs,
            field_errors=exc.field_errors, message=exc.message,
        ) from exc
    except OSError as exc:
        raise PublicError("ArtifactUnavailable", stage="validate", started=False,
                          attempt_id=spec["attempt_id"],
                          message="generation lineage bytes are not accessible") from exc
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError) as exc:
        raise PublicError("ArtifactIntegrityError", stage="validate", started=False,
                          attempt_id=spec["attempt_id"],
                          message="invalid retained generation lineage metadata") from exc
