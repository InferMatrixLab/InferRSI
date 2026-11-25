"""Read attempt sources by configured role and invoke a host-supplied pure projector."""

from collections.abc import Callable
from contextlib import closing
from copy import deepcopy
from hashlib import sha256

from inferrsi.harness.errors import PublicError

from ..storage.result import validate_artifact_ref


def _one(values):
    if len(values) > 1:
        raise PublicError("IdentityMismatch", stage="evidence_capture",
                          message="The configured capture role has multiple sources.")
    return values[0] if values else None


def _read(ref, artifacts):
    if ref is None:
        return None
    validate_artifact_ref(ref)
    fixed = deepcopy(ref)
    opened = artifacts.open(deepcopy(fixed))
    if isinstance(opened, bytes):
        data = opened
    else:
        chunks, remaining = [], fixed["size_bytes"] + 1
        with closing(opened):
            while remaining:
                chunk = opened.read(min(remaining, 1024 * 1024))
                if not isinstance(chunk, bytes):
                    raise TypeError("A capture capability must supply binary bytes or streams.")
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        data = b"".join(chunks)
    if len(data) != fixed["size_bytes"] or sha256(data).hexdigest() != fixed["sha256"]:
        raise PublicError("ArtifactIntegrityError", stage="evidence_capture",
                          message="Capture bytes do not match their retained reference.")
    return data


class EvidenceCapture:
    """Apps host adapter; roles and pure projection are configured from frozen B metadata.

    This object performs no grading, producer sealing, archive/store write or
    execution. H owns invocation, identity, read authority and failure handling.
    """

    def __init__(self, project: Callable, *, candidate_role: str, report_role: str):
        if not callable(project) or any(not isinstance(role, str) or not role
                                        for role in (candidate_role, report_role)):
            raise ValueError("Expected a pure projector and nonempty configured roles.")
        self._project = project
        self._candidate_role = candidate_role
        self._report_role = report_role

    def capture(self, phase, facts, *, artifacts):
        if phase not in ("preparing", "finalizing"):
            raise ValueError("Unknown evidence capture phase.")
        saved = deepcopy(facts)
        if saved["candidate"]["input_role"] != self._candidate_role:
            raise PublicError("IdentityMismatch", stage="evidence_capture",
                              message="The actual candidate role differs from host configuration.")
        candidate = _one([item["retained_ref"] for item in saved["bound_inputs"]
                          if item["role"] == self._candidate_role
                          and item["attempt_id"] == saved["attempt_id"]])
        report = None
        if phase == "finalizing":
            report = _one([item["artifact"] for step in saved["steps"]
                           for item in step["artifacts"] if item["role"] == self._report_role
                           and item["status"] == "available"
                           and item["attempt_id"] == saved["attempt_id"]
                           and item["step_id"] == step["step_id"]])
        return self._project(
            phase, saved, candidate_bytes=_read(candidate, artifacts),
            report_bytes=_read(report, artifacts),
        )
