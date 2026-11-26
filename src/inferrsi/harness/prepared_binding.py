"""H's read-only binding projection of a fixed PreparedEvaluation (D021 section 1, V28, V32).

An evaluation-mode ExecutionSpec names its preparation by PreparedRef. Before any
registration, H reads the fixed bytes through the read-only artifact port, verifies them
against the Ref and compares the fields it needs with the spec: ids, digests, operation and
scope, the candidate declaration and the frozen worker declarations. The projection is defined
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
from inferrsi.contracts._harness_errors import PublicError
from inferrsi.harness import input_binding
from inferrsi.harness.records import _run_store as run_store

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
_OUTPUT_FIELDS = frozenset({"role", "path", "required", "media_type", "format_schema"})
_ARTIFACT_FIELDS = frozenset({"location", "sha256", "size_bytes", "media_type"})
_PLACEHOLDER = re.compile(r"\{(input|output):([^{}]+)\}")
_SEMANTIC_ID = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class FixedPreparation:
    """H's mechanical identity/binding projection; task rules and scores are not retained."""

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
    recipe: dict


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


def _is_ids(value: object) -> bool:
    return (isinstance(value, list) and all(run_store._is_id(item) for item in value)
            and len(set(value)) == len(value))


def _is_path(value: object) -> bool:
    return isinstance(value, str) and input_binding.RELATIVE_PATH.fullmatch(value) is not None


def _recipe_errors(recipe: object) -> list[str]:
    """Validate only mechanical worker declarations, without interpreting formats or rules."""
    if not run_store._has_fields(recipe, _RECIPE_FIELDS):
        return ["prepared.recipe: not the OperationRecipe fields"]
    errors = []
    for name in ("recipe_revision", "runtime_role", "entrypoint_revision"):
        if not run_store._is_id(recipe[name]):
            errors.append(f"prepared.recipe.{name}: not an Id")
    if recipe["entrypoint_kind"] not in ("python_module", "executable"):
        errors.append("prepared.recipe.entrypoint_kind: not a supported entry kind")
    if not isinstance(recipe["entrypoint"], str) or not recipe["entrypoint"]:
        errors.append("prepared.recipe.entrypoint: not a non-empty Text")
    if not _is_sha256(recipe["code_sha256"]):
        errors.append("prepared.recipe.code_sha256: not a Sha256")
    for name in ("input_roles", "required_capabilities"):
        if not _is_ids(recipe[name]):
            errors.append(f"prepared.recipe.{name}: not a list of unique Ids")
    outputs = recipe["outputs"]
    if not isinstance(outputs, list) or not all(
        run_store._has_fields(item, _OUTPUT_FIELDS)
        and run_store._is_id(item["role"]) and _is_path(item["path"])
        and type(item["required"]) is bool
        and isinstance(item["media_type"], str) and bool(item["media_type"])
        and _is_definition(item["format_schema"]) for item in outputs
    ):
        errors.append("prepared.recipe.outputs: not a list of OutputSpec")
    elif (len({item["role"] for item in outputs}) != len(outputs)
          or len({item["path"] for item in outputs}) != len(outputs)):
        errors.append("prepared.recipe.outputs: roles and paths must be unique")
    args = recipe["args"]
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        errors.append("prepared.recipe.args: not a list of Text")
    elif not errors:
        roles = {"input": set(recipe["input_roles"]),
                 "output": {item["role"] for item in outputs}}
        for arg in args:
            match = _PLACEHOLDER.fullmatch(arg)
            if match:
                if match[2] not in roles[match[1]]:
                    errors.append("prepared.recipe.args: unknown placeholder role")
            elif "{input:" in arg or "{output:" in arg:
                errors.append("prepared.recipe.args: placeholders must occupy a whole argument")
    return errors


def read(ref: Mapping, reader) -> bytes:
    """The fixed bytes of ``ref`` from the read-only port, verified against the Ref.

    The port's own verification is not trusted: size and hash are checked here again
    (V06). At most ``size_bytes + 1`` bytes are read, so a wrong Ref cannot make this
    allocate more than the stream actually holds.
    """
    if not (run_store._has_fields(ref, _ARTIFACT_FIELDS) and _is_path(ref["location"])
            and _is_sha256(ref["sha256"]) and type(ref["size_bytes"]) is int
            and 0 <= ref["size_bytes"] <= json_v1.MAX_SAFE_INTEGER
            and ref["media_type"] == PREPARED_MEDIA_TYPE):
        raise _refuse("InvalidExecutionSpec", "illegal fixed preparation ArtifactRef")
    if reader is None:
        raise _refuse(
            "ArtifactUnavailable", "no read-only artifact reader is configured for the "
            "fixed preparation",
        )
    size = ref["size_bytes"]
    expected_sha256 = ref["sha256"]
    digest = hashlib.sha256()
    parts: list[bytes] = []
    total = 0
    try:
        stream = reader.open(dict(ref))
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
    if total != size or digest.hexdigest() != expected_sha256:
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
    errors.extend(_recipe_errors(recipe))
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
        recipe=recipe,
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
    errors.extend(_worker_errors(spec, fixed.recipe))
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


def _worker_errors(spec: Mapping, recipe: dict) -> list[str]:
    """Preserve the frozen worker's entry, paths and placeholder-expanded arguments."""
    errors = []
    if len(spec["steps"]) != 1:
        return ["steps: the frozen recipe binds exactly one worker step"]
    step = spec["steps"][0]
    for name in ("runtime_role", "entrypoint_kind", "entrypoint", "entrypoint_revision", "outputs"):
        if step[name] != recipe[name]:
            errors.append(f"steps[0].{name}: differs from the frozen worker declaration")
    if step["cwd"] != ".":
        errors.append("steps[0].cwd: frozen recipe paths are relative to the attempt directory")
    if not set(recipe["required_capabilities"]) <= set(spec["required_capabilities"]):
        errors.append("required_capabilities: missing a frozen worker requirement")
    inputs = {item["role"]: item["materialized_path"] for item in spec["inputs"]}
    if not set(recipe["input_roles"]) <= inputs.keys():
        errors.append("inputs: missing a frozen worker input role")
    else:
        outputs = {item["role"]: item["path"] for item in recipe["outputs"]}
        paths = {"input": inputs, "output": outputs}
        args = []
        for arg in recipe["args"]:
            match = _PLACEHOLDER.fullmatch(arg)
            args.append(paths[match[1]][match[2]] if match else arg)
        if step["args"] != args:
            errors.append("steps[0].args: differs from the frozen recipe binding")
        ordered = sorted(tuple(path.split("/")) for path in [*inputs.values(), *outputs.values()])
        if any(b[:len(a)] == a for a, b in zip(ordered, ordered[1:])):
            errors.append("inputs/outputs: materialized paths must not overlap")
    return errors


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
