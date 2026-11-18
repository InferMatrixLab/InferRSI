"""Read a fixed Harness revision and its optional archived assessment."""

from copy import deepcopy

from inferrsi.contracts.json_v1 import decode
from inferrsi.harness.errors import PublicError

from ..handoff.bridge import check_assessment_identity
from ..storage.archive import read_assessment
from ..storage.artifact_reader import ArtifactReader
from ..storage.result import _check_ref

_EXECUTION_FIELDS = (
    "run_id", "attempt_id", "record_version", "phase", "started", "side_effect_unknown",
    "process_outcome", "exit_code", "recorded_at", "prepared_ref",
)
_CLAIM_FIELDS = ("claim_id", "validation_scope", "verdict", "reasons", "missing_evidence")
_TRACE_FIELDS = {
    "steps": (
        "step_id", "status", "started_at", "ended_at", "elapsed_seconds", "exit_code", "reasons",
    ),
    "checks": ("check_id", "subject", "phase", "status", "reasons"),
    "errors": ("code", "stage", "retryable"),
}


def read_attempt_view(
    record_ref: dict, *, storage_config: dict, assessment_ref: dict | None = None,
    include_trace: bool = False,
) -> dict:
    """Return fixed facts, claim outcomes and optional trace for one record revision."""
    try:
        _check_ref(record_ref, "attempt_id", "record_version")
        if record_ref["artifact"]["media_type"] != "application/json":
            raise ValueError("expected a JSON record")
    except ValueError:
        raise PublicError(
            "InvalidRequest", stage="attempt_view", message="Invalid RecordRef."
        ) from None

    with ArtifactReader(storage_config).open(record_ref["artifact"]) as stream:
        data = stream.read()
    try:
        record = decode(data)
        if (
            not isinstance(record, dict)
            or type(record.get("schema_version")) is not int or record["schema_version"] != 1
            or type(record.get("record_version")) is not int
        ):
            raise ValueError("expected a v1 committed record")
        execution = {field: record[field] for field in _EXECUTION_FIELDS}
        execution["cleanup_status"] = record["cleanup"]["status"]
        candidate = record["candidate"]
        execution["candidate_id"] = candidate["candidate_id"] if candidate is not None else None
        trace = {
            group: [{key: item[key] for key in fields} for item in record[group]]
            for group, fields in _TRACE_FIELDS.items()
        } if include_trace else None
    except (KeyError, TypeError, ValueError):
        raise PublicError(
            "ArtifactIntegrityError", stage="attempt_view",
            message="Invalid committed record bytes.",
        ) from None
    if any(record[field] != record_ref[field] for field in ("attempt_id", "record_version")):
        raise PublicError(
            "IdentityMismatch", stage="attempt_view",
            message="RecordRef identifies a different record revision.",
        )

    evaluation = None
    if assessment_ref is not None:
        assessment = read_assessment(storage_config, assessment_ref)
        expected = {
            "record_ref": record_ref,
            **{key: record.get(key) for key in (
                "attempt_id", "prepared_ref", "protocol_digest", "candidate",
            )},
        }
        if any(assessment.get(key) != value for key, value in expected.items()):
            raise PublicError(
                "IdentityMismatch", stage="attempt_view",
                message="AssessmentRef belongs to a different fixed attempt record.",
            )
        try:
            check_assessment_identity(assessment)
            evaluation = {
                "assessed_at": assessment["assessed_at"],
                "claims": [{key: claim[key] for key in _CLAIM_FIELDS}
                           for claim in assessment["claims"]],
            }
        except (KeyError, TypeError, ValueError):
            raise PublicError(
                "ArtifactIntegrityError", stage="attempt_view",
                message="Invalid archived assessment for this record.",
            ) from None

    view = {
        "record_ref": deepcopy(record_ref), "execution": execution,
        "assessment_ref": deepcopy(assessment_ref), "assessment": evaluation,
    }
    if include_trace:
        view["trace"] = trace
    return view
