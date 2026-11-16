"""Construct the Apps side of a generation plan for Harness to seal."""

from collections.abc import Callable
from copy import deepcopy

from inferrsi.contracts.json_v1 import encode
from inferrsi.harness.errors import PublicError

from .archive import _logical_path
from .bridge import (
    _ATTEMPT_FIELDS,
    _definition,
    _id,
    _input_paths,
    _output_paths,
    _require_disjoint_paths,
)
from .result import validate_artifact_ref

_CONTEXT_FIELDS = {
    "campaign_id", "generation_id", "candidate", "parent", "task_materials",
    "delivered_context", "allowed_feedback", "output_contract",
}
_OUTPUT_CONTRACT_FIELDS = {
    "manifest_role", "candidate_role", "format_schema", "required_input_roles", "parser_revision",
}


class CandidateProvider:
    """Apps adapter for planning the generation leg of a Harness loop."""

    def __init__(
        self, *, provider: dict, output_contract: dict, steps: list[dict],
        bind_inputs: Callable[[dict], list[dict]], output_root_for: Callable[[str], str],
        required_capabilities: list[str],
    ):
        self._provider = deepcopy(provider)
        self._output_contract = deepcopy(output_contract)
        self._steps = deepcopy(steps)
        self._bind_inputs = bind_inputs
        self._output_root_for = output_root_for
        self._required_capabilities = deepcopy(required_capabilities)

    def plan_generation(self, context: dict, attempt: dict) -> dict:
        """Bind the authorized context and original attempt to the configured worker."""
        return _plan_generation(
            context, attempt, provider=self._provider, output_contract=self._output_contract,
            steps=self._steps, bind_inputs=self._bind_inputs, output_root_for=self._output_root_for,
            required_capabilities=self._required_capabilities,
        )


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
        if "generation_plan" in by_role:
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
