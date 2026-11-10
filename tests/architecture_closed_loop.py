"""Test-double handoff for prepare, archive, bind, execute, and offline assess.

This is not the Apps package from #371 and it does not import the Knowledge,
Harness, or Benchmark implementations. Digests are SHA-256 of a test-local
JSON encoding. That encoding is not ``inferrsi-json-v1`` and it does not
change Bundle revision rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class PreparedRef:
    digest: str


@dataclass(frozen=True)
class RecordRef:
    attempt_id: str
    record_version: int
    digest: str


@dataclass(frozen=True)
class AssessmentRef:
    digest: str


@dataclass(frozen=True)
class LoopResult:
    reason: str
    prepared_ref: PreparedRef | None = None
    record_ref: RecordRef | None = None
    assessment_ref: AssessmentRef | None = None
    verdict: str | None = None
    cancelled: bool = False


class MemoryArchive:
    """Byte archive for prepared and assessment payloads. Not a run store."""

    def __init__(self, *, fail_prepared: bool = False, fail_assessment: bool = False):
        self.prepared: dict[str, bytes] = {}
        self.assessments: dict[str, bytes] = {}
        self.fail_prepared = fail_prepared
        self.fail_assessment = fail_assessment

    def save_prepared(self, payload: bytes) -> PreparedRef | None:
        if self.fail_prepared:
            return None
        digest = _digest(payload)
        self.prepared[digest] = payload
        return PreparedRef(digest)

    def read_prepared(self, ref: PreparedRef) -> bytes:
        return self.prepared[ref.digest]

    def save_assessment(self, payload: bytes) -> AssessmentRef | None:
        if self.fail_assessment:
            return None
        digest = _digest(payload)
        self.assessments[digest] = payload
        return AssessmentRef(digest)


def bind_execution(
    *,
    prepared_ref: PreparedRef,
    prepared_bytes: bytes,
    attempt: dict,
) -> dict | None:
    """Return an execution spec, or None. This function has no run store."""
    if _digest(prepared_bytes) != prepared_ref.digest:
        return None
    attempt_id = attempt.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        return None
    return {
        "attempt_id": attempt_id,
        "prepared_digest": prepared_ref.digest,
        "retry_of": attempt.get("retry_of"),
    }


def _record_ref(outcome: dict) -> RecordRef | None:
    record = outcome.get("record_ref")
    if not isinstance(record, dict):
        return None
    attempt_id = record.get("attempt_id")
    version = record.get("record_version")
    digest = record.get("digest")
    if not isinstance(attempt_id, str) or not attempt_id:
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return None
    return RecordRef(attempt_id, version, digest)


def run_loop(*, knowledge, harness, benchmark, archive: MemoryArchive) -> LoopResult:
    """One fake closed loop. Failing a step stops the handoff."""
    delivered = knowledge.deliver()
    prepared = benchmark.prepare(delivered)
    payload = _canonical(prepared)
    prepared_ref = archive.save_prepared(payload)
    if prepared_ref is None:
        return LoopResult("archive_prepared_failed")
    attempt = harness.allocate_attempt()
    spec = bind_execution(
        prepared_ref=prepared_ref,
        prepared_bytes=archive.read_prepared(prepared_ref),
        attempt=attempt,
    )
    if spec is None:
        return LoopResult("bind_rejected", prepared_ref=prepared_ref)
    outcome = harness.execute(spec)
    record_ref = _record_ref(outcome)
    kind = outcome.get("kind")
    if kind == "no_record" or record_ref is None:
        return LoopResult("no_record", prepared_ref=prepared_ref)
    if kind == "recovery_required":
        return LoopResult(
            "recovery_required",
            prepared_ref=prepared_ref,
            record_ref=record_ref,
            cancelled=False,
        )
    if kind == "not_started":
        return LoopResult(
            "not_started",
            prepared_ref=prepared_ref,
            record_ref=record_ref,
        )
    if record_ref.attempt_id != spec["attempt_id"]:
        return LoopResult(
            "record_mismatch",
            prepared_ref=prepared_ref,
            record_ref=record_ref,
        )
    # Only a completed record for this attempt may be assessed.
    if kind != "completed":
        return LoopResult(
            "outcome_rejected",
            prepared_ref=prepared_ref,
            record_ref=record_ref,
        )
    evidence = outcome.get("evidence")
    if not isinstance(evidence, dict):
        return LoopResult(
            "evidence_missing",
            prepared_ref=prepared_ref,
            record_ref=record_ref,
            verdict="INCONCLUSIVE",
        )
    verdict = benchmark.assess(archive.read_prepared(prepared_ref), evidence)
    assessment_payload = _canonical(verdict)
    assessment_ref = archive.save_assessment(assessment_payload)
    if assessment_ref is None:
        return LoopResult(
            "archive_assessment_failed",
            prepared_ref=prepared_ref,
            record_ref=record_ref,
            verdict=verdict.get("verdict"),
        )
    return LoopResult(
        "completed",
        prepared_ref=prepared_ref,
        record_ref=record_ref,
        assessment_ref=assessment_ref,
        verdict=verdict.get("verdict"),
    )
