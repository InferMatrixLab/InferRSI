"""H's read-only binding projection of a fixed PreparedEvaluation (D021 section 1, V28, V32).

An evaluation-mode ExecutionSpec names its preparation by PreparedRef. Before any
registration, H reads the fixed bytes through the read-only artifact port, verifies them
against the Ref and compares the fields it needs with the spec: ids, digests, operation and
scope, the candidate declaration and the frozen worker code digest. The projection is defined
here. It imports nothing from Benchmark or Apps, and it never interprets task rules, formats
or scores.

Nothing in this module registers an attempt, writes a record or starts a process. Every
refusal is raised before the RunStore sees the request. Verifying the actual entry bytes
against the frozen digest (T37) happens after registration and is not part of this module.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from inferrsi.contracts import json_v1
from inferrsi.harness import run_store
from inferrsi.harness.errors import PublicError

STAGE = "prepared_binding"
PREPARED_MEDIA_TYPE = "application/json"
# The candidate identity rules this H supports (V28). Any other is refused, never downgraded.
CAPTURED_SHA256 = {"name": "captured-sha256", "revision": "1"}
EXPECTED_SHA256 = {"name": "expected-sha256", "revision": "1"}

# Exact v1 field sets of the objects the projection reads. An unknown field is refused and
# never dropped (V01).
_PREPARED_FIELDS = frozenset(
    {
        "schema_version", "prepared_id", "task", "grader", "operation", "validation_scope",
        "protocol", "protocol_digest", "candidate_contract", "expected_candidate",
        "required_evidence", "recipe", "resources", "created_at", "display_notes",
    }
)
_CONTRACT_FIELDS = frozenset(
    {
        "kind", "input_role", "format_schema", "entrypoint", "required_paths",
        "allowed_content", "identity_rule", "modification_receipt_required",
    }
)
_RECIPE_FIELDS = frozenset(
    {
        "recipe_revision", "runtime_role", "entrypoint_kind", "entrypoint",
        "entrypoint_revision", "code_sha256", "args", "input_roles", "outputs",
        "required_capabilities",
    }
)
_EXPECTED_FIELDS = frozenset({"candidate_id", "sha256", "format_schema"})
_DEFINITION_FIELDS = frozenset({"name", "revision"})
_SEMANTIC_ID = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class FixedPreparation:
    """The identity fields H reads from a fixed preparation; nothing else is retained."""

    prepared_id: str
    operation: str
    validation_scope: str
    protocol_digest: str
    candidate_kind: str
    candidate_input_role: str
    candidate_format: dict
    identity_rule: dict
    expected_candidate: dict | None
    code_sha256: str


def _refuse(code: str, message: str, field_errors: list[str] | None = None) -> PublicError:
    return PublicError(code, stage=STAGE, message=message, field_errors=field_errors or [])


def _is_definition(value: object) -> bool:
    return run_store._has_fields(value, _DEFINITION_FIELDS) and all(
        run_store._is_id(value[name]) for name in _DEFINITION_FIELDS
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _is_semantic_id(value: object) -> bool:
    return isinstance(value, str) and _SEMANTIC_ID.fullmatch(value) is not None


def read(ref: Mapping, reader) -> bytes:
    """The fixed bytes of ``ref`` from the read-only port, verified against the Ref.

    The port's own verification is not trusted: size and hash are checked here again
    (V06). At most ``size_bytes + 1`` bytes are read, so a wrong Ref cannot make this
    allocate more than the stream actually holds.
    """
    if reader is None:
        raise _refuse(
            "ArtifactUnavailable", "no read-only artifact reader is configured for the "
            "fixed preparation",
        )
    size = ref["size_bytes"]
    digest = hashlib.sha256()
    parts: list[bytes] = []
    total = 0
    try:
        stream = reader.open(ref)
        with stream:
            while total <= size:
                chunk = stream.read(min(_READ_CHUNK, size + 1 - total))
                if not chunk:
                    break
                digest.update(chunk)
                parts.append(chunk)
                total += len(chunk)
    except PublicError:
        raise
    except OSError as exc:
        raise _refuse(
            "ArtifactUnavailable",
            f"the fixed preparation could not be read: {run_store._describe(exc)}",
        ) from exc
    if total != size or digest.hexdigest() != ref["sha256"]:
        raise _refuse(
            "ArtifactIntegrityError", "the fixed preparation bytes differ from their ArtifactRef"
        )
    return b"".join(parts)


def project(data: bytes) -> FixedPreparation:
    """Parse the identity fields of canonical PreparedEvaluation bytes."""
    try:
        prepared = json_v1.decode(data)
    except json_v1.CanonicalError as exc:
        raise _refuse(
            "ArtifactIntegrityError",
            f"the fixed preparation is not canonical inferrsi-json-v1 ({exc.stage})",
        ) from exc
    version = prepared.get("schema_version") if isinstance(prepared, dict) else None
    if type(version) is int and version != 1:
        raise _refuse("UnsupportedSchema", "only PreparedEvaluation v1 is supported")
    errors: list[str] = []
    if not run_store._has_fields(prepared, _PREPARED_FIELDS):
        raise _refuse(
            "InvalidExecutionSpec", "illegal fixed preparation",
            ["prepared: fields must be exactly the PreparedEvaluation fields"],
        )
    if type(version) is not int:
        errors.append("prepared.schema_version: must be the integer 1")
    if not _is_semantic_id(prepared["prepared_id"]):
        errors.append("prepared.prepared_id: not a SemanticId")
    if not _is_semantic_id(prepared["protocol_digest"]):
        errors.append("prepared.protocol_digest: not a SemanticId")
    for name in ("operation", "validation_scope"):
        if not run_store._is_id(prepared[name]):
            errors.append(f"prepared.{name}: not an Id")
    contract, recipe = prepared["candidate_contract"], prepared["recipe"]
    expected = prepared["expected_candidate"]
    if not run_store._has_fields(contract, _CONTRACT_FIELDS):
        errors.append("prepared.candidate_contract: not the CandidateContract fields")
    else:
        for name in ("kind", "input_role"):
            if not run_store._is_id(contract[name]):
                errors.append(f"prepared.candidate_contract.{name}: not an Id")
        for name in ("format_schema", "identity_rule"):
            if not _is_definition(contract[name]):
                errors.append(f"prepared.candidate_contract.{name}: not a DefinitionRef")
    if not run_store._has_fields(recipe, _RECIPE_FIELDS):
        errors.append("prepared.recipe: not the OperationRecipe fields")
    elif not _is_sha256(recipe["code_sha256"]):
        errors.append("prepared.recipe.code_sha256: not a Sha256")
    if expected is not None:
        if not run_store._has_fields(expected, _EXPECTED_FIELDS):
            errors.append(
                "prepared.expected_candidate: not null or the CandidateExpectation fields"
            )
        else:
            if not run_store._is_id(expected["candidate_id"]):
                errors.append("prepared.expected_candidate.candidate_id: not an Id")
            if not _is_sha256(expected["sha256"]):
                errors.append("prepared.expected_candidate.sha256: not a Sha256")
            if not _is_definition(expected["format_schema"]):
                errors.append("prepared.expected_candidate.format_schema: not a DefinitionRef")
    if errors:
        raise _refuse("InvalidExecutionSpec", "illegal fixed preparation", errors)
    return FixedPreparation(
        prepared_id=prepared["prepared_id"],
        operation=prepared["operation"],
        validation_scope=prepared["validation_scope"],
        protocol_digest=prepared["protocol_digest"],
        candidate_kind=contract["kind"],
        candidate_input_role=contract["input_role"],
        candidate_format=contract["format_schema"],
        identity_rule=contract["identity_rule"],
        expected_candidate=expected,
        code_sha256=recipe["code_sha256"],
    )


def _check_identity(spec: Mapping, fixed: FixedPreparation) -> None:
    """V17: top-level identity fields must agree before any declaration is compared."""
    pairs = (
        ("prepared_ref.prepared_id", spec["prepared_ref"]["prepared_id"], fixed.prepared_id),
        ("protocol_digest", spec["protocol_digest"], fixed.protocol_digest),
        ("operation", spec["operation"], fixed.operation),
        ("validation_scope", spec["validation_scope"], fixed.validation_scope),
    )
    differing = [f"{name}: differs from the fixed preparation" for name, a, b in pairs if a != b]
    if differing:
        raise _refuse(
            "IdentityMismatch", "the execution spec names a different preparation", differing
        )


def _check_declarations(spec: Mapping, fixed: FixedPreparation) -> None:
    """V28 and V32: declaration conflicts are refused before registration, never recorded."""
    errors = [
        f"steps[{index}].expected_code_sha256: must equal the frozen recipe code_sha256 (V32)"
        for index, step in enumerate(spec["steps"])
        if step["expected_code_sha256"] != fixed.code_sha256
    ]
    candidate = spec["candidate"]
    if candidate["input_role"] != fixed.candidate_input_role:
        errors.append("candidate.input_role: differs from the frozen candidate contract")
    if candidate["kind"] != fixed.candidate_kind:
        errors.append("candidate.kind: differs from the frozen candidate contract")
    declared = next(
        (item["expected_sha256"] for item in spec["inputs"]
         if item["role"] == candidate["input_role"]),
        None,
    )
    if fixed.identity_rule == EXPECTED_SHA256 and declared is None:
        errors.append(
            "inputs: the candidate input needs expected_sha256 under expected-sha256@1 (V28)"
        )
    frozen = fixed.expected_candidate
    if frozen is not None:
        if candidate["candidate_id"] != frozen["candidate_id"]:
            errors.append("candidate.candidate_id: differs from the frozen expected candidate")
        if declared != frozen["sha256"]:
            errors.append("inputs: the candidate expected_sha256 differs from the frozen one")
        if fixed.candidate_format != frozen["format_schema"]:
            errors.append("prepared: expected candidate format differs from the candidate contract")
    if errors:
        raise _refuse(
            "InvalidExecutionSpec", "the execution spec conflicts with its fixed preparation",
            errors,
        )


def verify(spec: Mapping, reader) -> FixedPreparation:
    """Check an evaluation-mode spec against its fixed preparation before registration.

    ``spec`` has passed the static ExecutionSpec checks, so its evaluation fields are all
    set and well formed. Raises a PublicError for any malformed or inconsistent binding.
    """
    fixed = project(read(spec["prepared_ref"]["artifact"], reader))
    if fixed.identity_rule not in (CAPTURED_SHA256, EXPECTED_SHA256):
        raise _refuse(
            "UnsupportedRuleVersion", "the frozen candidate identity rule is unsupported"
        )
    _check_identity(spec, fixed)
    _check_declarations(spec, fixed)
    return fixed
