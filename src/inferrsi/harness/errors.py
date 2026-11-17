from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields

# H public errors. Exact spellings from PublicErrorCode (D021 section 5); aliases are not accepted.
PUBLIC_ERROR_CODES = frozenset(
    {
        "InvalidRequest",
        "InvalidExecutionSpec",
        "UnsupportedOperation",
        "UnsupportedSchema",
        "UnsupportedRuleVersion",
        "IdentityMismatch",
        "RevisionConflict",
        "RequestConflict",
        "AttemptInProgress",
        "RecoveryRequired",
        "ExecutionPersistenceError",
        "ArchivePersistenceError",
        "NoCommittedRecord",
        "RecordNotFound",
        "RecordIntegrityError",
        "ArtifactUnavailable",
        "ArtifactIntegrityError",
        "UnsafeArtifactPath",
        "AssessorError",
    }
)


@dataclass(frozen=True)
class PartialExecutionFacts:
    """Facts known when a record commit failed; never a committed payload or a Ref."""

    request_id: str
    run_id: str
    attempt_id: str
    request_digest: str | None
    proposed_record_version: int | None
    phase: str | None
    started: bool | None
    side_effect_unknown: bool
    steps: list
    checks: list
    artifacts: list
    budget_admission: dict | None
    usage: list
    resource_leases: dict | None
    errors: list

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> PartialExecutionFacts:
        # The proposed payload's facts are kept; its record_version was never committed.
        values = {
            field.name: copy.deepcopy(payload[field.name])
            for field in fields(cls)
            if field.name != "proposed_record_version"
        }
        return cls(proposed_record_version=payload["record_version"], **values)

    def to_json(self) -> dict:
        return {field.name: copy.deepcopy(getattr(self, field.name)) for field in fields(self)}


class PublicError(Exception):
    """A stable H port error; ``to_json`` is the schema ``PublicError`` object."""

    def __init__(
        self,
        code: str,
        *,
        stage: str,
        message: str,
        attempt_id: str | None = None,
        started: bool | None = None,
        latest_record_ref: dict | None = None,
        partial_record: PartialExecutionFacts | None = None,
        retained_refs: Iterable[dict] = (),
        field_errors: Iterable[str] = (),
    ):
        if code not in PUBLIC_ERROR_CODES:
            raise ValueError(f"Unknown PublicError code: {code!r}")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.stage = stage
        self.message = message
        self.attempt_id = attempt_id
        self.started = started
        self.latest_record_ref = latest_record_ref
        self.partial_record = partial_record
        self.retained_refs = list(retained_refs)
        self.field_errors = list(field_errors)

    def to_json(self) -> dict:
        return {
            "code": self.code,
            "stage": self.stage,
            "attempt_id": self.attempt_id,
            "started": self.started,
            "latest_record_ref": copy.deepcopy(self.latest_record_ref),
            "partial_record": (
                None if self.partial_record is None else self.partial_record.to_json()
            ),
            "retained_refs": copy.deepcopy(self.retained_refs),
            "field_errors": list(self.field_errors),
            "message": self.message,
        }
