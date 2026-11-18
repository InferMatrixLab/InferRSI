"""Plan candidate generation and collect the outputs retained by Harness."""

from collections.abc import Callable
from copy import deepcopy
from hashlib import sha256

from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness.errors import PublicError

from .bridge import (
    _ATTEMPT_FIELDS,
    _CANDIDATE_FIELDS,
    _definition,
    _digest,
    _id,
    _input_paths,
    _output_paths,
    _require_disjoint_paths,
)
from .storage.archive import _logical_path
from .storage.artifact_reader import ArtifactReader
from .storage.result import _RECORD_OBSERVATIONS, _check_ref, validate_artifact_ref

_CONTEXT_FIELDS = {
    "campaign_id", "generation_id", "candidate", "parent", "task_materials",
    "delivered_context", "allowed_feedback", "output_contract",
}
_OUTPUT_CONTRACT_FIELDS = {
    "manifest_role", "candidate_role", "format_schema", "required_input_roles", "parser_revision",
}
_MANIFEST_FIELDS = {"schema_version", "provider", "output_contract", "context_refs", "attempt_id"}
_PLAN_ROLE = "generation_plan"


class CandidateProvider:
    """Apps adapter for the generation leg of a Harness loop.

    The configured parser implements the frozen parser revision. Given the worker's
    manifest and candidate bytes, it returns candidate metadata (without context refs)
    and a mapping from evaluation input roles to declared generation output roles.
    """

    def __init__(
        self, *, provider: dict, output_contract: dict, steps: list[dict],
        bind_inputs: Callable[[dict], list[dict]], output_root_for: Callable[[str], str],
        required_capabilities: list[str],
        parse_candidate: Callable[[bytes, bytes], tuple[dict, dict[str, str]]] | None = None,
    ):
        self._provider = deepcopy(provider)
        self._output_contract = deepcopy(output_contract)
        self._steps = deepcopy(steps)
        self._bind_inputs = bind_inputs
        self._output_root_for = output_root_for
        self._required_capabilities = deepcopy(required_capabilities)
        self._parse_candidate = parse_candidate

    def plan_generation(self, context: dict, attempt: dict) -> dict:
        """Bind the authorized context and original attempt to the configured worker."""
        return _plan_generation(
            context, attempt, provider=self._provider, output_contract=self._output_contract,
            steps=self._steps, bind_inputs=self._bind_inputs, output_root_for=self._output_root_for,
            required_capabilities=self._required_capabilities,
        )

    def collect_candidate(self, record: dict, *, artifacts: ArtifactReader) -> dict:
        """Build a proposal from a fixed successful generation record and its outputs."""
        if self._parse_candidate is None:
            raise PublicError(
                "UnsupportedOperation", stage="candidate_collection",
                message="No candidate parser is configured for this provider.",
            )
        try:
            record_ref, payload = _generation_record(record, artifacts)
            manifest = _generation_manifest(
                payload, artifacts, self._provider, self._output_contract,
            )
            outputs = _generation_outputs(payload, self._steps)
            contract = manifest["output_contract"]
            manifest_ref = outputs[contract["manifest_role"]]
            candidate_ref = outputs[contract["candidate_role"]]
            worker_manifest = _read_artifact(artifacts, manifest_ref)
            candidate_bytes = _read_artifact(artifacts, candidate_ref)
            candidate, bindings = self._parse_candidate(worker_manifest, candidate_bytes)
            inputs = _candidate_inputs(candidate, bindings, contract, outputs)
            verified = {encode(manifest_ref), encode(candidate_ref)}
            refs = [item["source_ref"] for item in inputs]
            refs.extend(outputs[output["role"]] for step in self._steps
                        for output in step["outputs"] if output["required"])
            for ref in refs:
                identity = encode(ref)
                if identity not in verified:
                    with artifacts.open(ref):
                        pass
                    verified.add(identity)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise PublicError(
                "InvalidRequest", stage="candidate_collection",
                message="Expected an accepted generation plan and a valid candidate output.",
            ) from exc
        return deepcopy({
            "candidate": {**candidate, "context_refs": manifest["context_refs"]},
            "inputs": inputs,
            "generation_record_ref": record_ref,
        })


def _read_artifact(artifacts: ArtifactReader, ref: dict) -> bytes:
    validate_artifact_ref(ref)
    _logical_path(ref["location"])
    with artifacts.open(ref) as stream:
        return stream.read()


def _generation_record(record: dict, artifacts: ArtifactReader) -> tuple[dict, dict]:
    ref = record["record_ref"]
    _check_ref(ref, "attempt_id", "record_version")
    if ref["artifact"]["media_type"] != "application/json":
        raise ValueError("expected a JSON record")
    data = _read_artifact(artifacts, ref["artifact"])
    payload = decode(data)
    receipt = {key: value for key, value in record.items() if key not in _RECORD_OBSERVATIONS}
    if (
        encode(receipt) != data or payload["attempt_id"] != ref["attempt_id"]
        or payload["request_id"] != ref["attempt_id"]
        or payload["record_version"] != ref["record_version"]
    ):
        raise PublicError(
            "IdentityMismatch", stage="candidate_collection",
            message="The generation receipt differs from the committed record.",
        )
    if (
        payload["phase"] != "finished" or payload["process_outcome"] != "exited"
        or type(payload["exit_code"]) is not int or payload["exit_code"] != 0
        or payload["side_effect_unknown"] is not False
        or any(payload[field] is not None for field in (
            "candidate", "prepared_ref", "protocol_digest", "operation", "validation_scope",
        ))
    ):
        raise ValueError("incomplete or unsuccessful generation record")
    return ref, payload


def _generation_manifest(
    record: dict, artifacts: ArtifactReader, provider: dict, output_contract: dict,
) -> dict:
    plans = [item for item in record["bound_inputs"] if item["role"] == _PLAN_ROLE]
    if len(plans) != 1:
        raise ValueError("expected one bound generation plan")
    plan = plans[0]
    ref = plan["retained_ref"]
    if (
        plan["attempt_id"] != record["attempt_id"] or plan["identity_status"] != "matched"
        or plan["actual_sha256"] != ref["sha256"] or plan["expected_sha256"] != ref["sha256"]
    ):
        raise ValueError("generation plan identity was not verified")
    manifest = decode(_read_artifact(artifacts, ref))
    if (
        not isinstance(manifest, dict) or manifest.keys() != _MANIFEST_FIELDS
        or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
        or manifest["provider"] != provider or manifest["output_contract"] != output_contract
        or manifest["attempt_id"] != record["attempt_id"]
        or not isinstance(manifest["context_refs"], list) or not manifest["context_refs"]
    ):
        raise ValueError("generation manifest does not match the attempt and configured parser")
    for context in manifest["context_refs"]:
        validate_artifact_ref(context)
        _logical_path(context["location"])
    return manifest


def _generation_outputs(record: dict, steps: list[dict]) -> dict:
    declarations = {output["role"]: (step["step_id"], output)
                    for step in steps for output in step["outputs"]}
    outputs = {}
    for item in record["artifacts"]:
        role = item["role"]
        if role not in declarations:
            continue
        step_id, declaration = declarations[role]
        if (
            role in outputs or item["attempt_id"] != record["attempt_id"]
            or item["step_id"] != step_id or item["format_schema"] != declaration["format_schema"]
        ):
            raise ValueError("generation output must match its unique declared producer")
        outputs[role] = item["artifact"] if item["status"] == "available" else None
    if any(declaration["required"] and outputs.get(role) is None
           for role, (_, declaration) in declarations.items()):
        raise PublicError(
            "ArtifactUnavailable", stage="candidate_collection",
            message="A required generation output was not retained.",
        )
    return outputs


def _candidate_inputs(candidate: dict, bindings: dict, contract: dict, outputs: dict) -> list:
    if (
        not isinstance(candidate, dict) or candidate.keys() != _CANDIDATE_FIELDS - {"context_refs"}
        or not all(_id(candidate[field]) for field in ("candidate_id", "input_role", "kind"))
        or (candidate["parent_id"] is None) != (candidate["parent_digest"] is None)
        or (candidate["parent_id"] is not None and (
            not _id(candidate["parent_id"]) or not _digest(candidate["parent_digest"])
        ))
        or not isinstance(bindings, dict)
        or bindings.keys() != {*contract["required_input_roles"], candidate["input_role"]}
        or bindings[candidate["input_role"]] != contract["candidate_role"]
    ):
        raise ValueError("candidate metadata and input roles must match the frozen output contract")
    inputs = []
    for role, output_role in sorted(bindings.items()):
        ref = outputs.get(output_role)
        if ref is None:
            raise PublicError(
                "ArtifactUnavailable", stage="candidate_collection",
                message="A candidate input does not name a retained output.",
            )
        validate_artifact_ref(ref)
        inputs.append({
            "role": role, "source": ref["location"], "source_namespace": "artifact",
            "source_ref": ref, "snapshot_format": "file-v1", "expected_sha256": ref["sha256"],
            "materialized_path": f"inputs/{sha256(role.encode('ascii')).hexdigest()}",
        })
    _input_paths(inputs)
    return inputs


def _plan_generation(
    context: dict, attempt: dict, *, provider: dict, output_contract: dict,
    steps: list[dict], bind_inputs: Callable[[dict], list[dict]],
    output_root_for: Callable[[str], str], required_capabilities: list[str],
) -> dict:
    """Build the fixed-input plan for Harness to seal and execute."""
    try:
        if (
            not isinstance(context, dict) or context.keys() != _CONTEXT_FIELDS
            or not _id(context["campaign_id"]) or not _id(context["generation_id"])
            or not isinstance(attempt, dict) or attempt.keys() != _ATTEMPT_FIELDS
            or not _id(attempt["attempt_id"]) or attempt["request_id"] != attempt["attempt_id"]
            or not _definition(provider)
        ):
            raise ValueError("expected a candidate context, provider and allocated attempt")
        if (
            not isinstance(output_contract, dict)
            or output_contract.keys() != _OUTPUT_CONTRACT_FIELDS
            or not all(_id(output_contract[key])
                       for key in ("manifest_role", "candidate_role", "parser_revision"))
            or not _definition(output_contract["format_schema"])
            or output_contract["format_schema"] != context["output_contract"]["format_schema"]
        ):
            raise ValueError("invalid generation output contract")
        roles = output_contract["required_input_roles"]
        if not isinstance(roles, list) or not all(_id(role) for role in roles):
            raise ValueError("invalid required input roles")
        if len(set(roles)) != len(roles):
            raise ValueError("duplicate required input role")
        delivery = context["delivered_context"]["artifact"]
        for key in ("task_materials", "allowed_feedback"):
            if not isinstance(context[key], list):
                raise ValueError("expected lists of authorized generation artifacts")
        allowed = set()
        for ref in [delivery, *context["task_materials"], *context["allowed_feedback"]]:
            validate_artifact_ref(ref)
            _logical_path(ref["location"])
            allowed.add(encode(ref))
        inputs = bind_inputs(deepcopy(context))
        if not isinstance(inputs, list):
            raise ValueError("expected generation inputs")
        by_role = _input_paths(inputs)
        if _PLAN_ROLE in by_role:
            raise ValueError("the generation_plan input role is reserved for Harness sealing")
        used = set()
        for item in by_role.values():
            if item["source_namespace"] != "artifact":
                raise ValueError("generation inputs must use fixed artifacts")
            used.add(encode(item["source_ref"]))
        if not used <= allowed or encode(delivery) not in used:
            raise ValueError("expected the delivered context and only authorized fixed inputs")

        if not isinstance(steps, list) or not steps:
            raise ValueError("expected generation command steps")
        outputs = []
        for step in steps:
            if step["expected_code_sha256"] is not None or not isinstance(step["outputs"], list):
                raise ValueError("expected ordinary generation command steps")
            outputs.extend(step["outputs"])
        paths = _output_paths(outputs)
        manifest_role = output_contract["manifest_role"]
        candidate_role = output_contract["candidate_role"]
        required = {output["role"]: output for output in outputs if output["required"]}
        if (
            manifest_role == candidate_role or manifest_role not in required
            or candidate_role not in required
            or required[candidate_role]["format_schema"] != output_contract["format_schema"]
        ):
            raise ValueError("expected distinct required manifest and candidate outputs")
        _require_disjoint_paths([*paths.values(), *(item["materialized_path"] for item in inputs)])
        output_root = output_root_for(attempt["attempt_id"])
        _logical_path(output_root)
        if not isinstance(required_capabilities, list) or not all(
            _id(capability) for capability in required_capabilities
        ):
            raise ValueError("invalid generation capabilities")
        plan = {
            "spec": {
                **attempt, "schema_version": 1, "generation_record_ref": None,
                "prepared_ref": None, "protocol_digest": None, "operation": None,
                "validation_scope": None, "candidate": None, "inputs": inputs,
                "steps": steps, "output_root": output_root,
                "required_capabilities": required_capabilities,
            },
            "manifest": {
                "schema_version": 1, "provider": provider, "output_contract": output_contract,
                "context_refs": [delivery], "attempt_id": attempt["attempt_id"],
            },
        }
        encode(plan)
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicError(
            "InvalidExecutionSpec", stage="generation_plan",
            message="The generation plan could not be bound to the supplied context and attempt.",
        ) from exc
    return deepcopy(plan)
