"""Python entry points for assembling and publishing Apps operations."""

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from inferrsi._json_v1 import encode
from inferrsi.harness.errors import PublicError
from inferrsi.harness.run_store import request_digest

from .archive import RunOutput, publish_result, validate_output_id
from .result import execution_result, is_public_error

_EXECUTE_FIELDS = {"schema_version", "prepared_ref", "proposal", "attempt", "output_root"}
_ATTEMPT_FIELDS = {
    "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
    "resources", "budget", "retry_of", "retry_reason",
}
_PROPOSAL_FIELDS = {"candidate", "inputs", "generation_record_ref"}


def _validation_error(code: str, message: str) -> dict:
    return {
        "code": code,
        "stage": "validation",
        "attempt_id": None,
        "started": None,
        "latest_record_ref": None,
        "partial_record": None,
        "retained_refs": [],
        "field_errors": [],
        "message": message,
    }


def _request_fields(request: dict) -> dict:
    if not isinstance(request, dict) or request.keys() != _EXECUTE_FIELDS:
        raise ValueError("expected AppsExecuteRequest fields")
    attempt = request["attempt"]
    proposal = request["proposal"]
    if (
        type(request["schema_version"]) is not int
        or request["schema_version"] != 1
        or not isinstance(attempt, dict)
        or attempt.keys() != _ATTEMPT_FIELDS
        or not isinstance(attempt["attempt_id"], str)
        or not attempt["attempt_id"]
        or attempt["request_id"] != attempt["attempt_id"]
        or not isinstance(proposal, dict)
        or proposal.keys() != _PROPOSAL_FIELDS
        or not isinstance(proposal["inputs"], list)
    ):
        raise ValueError("expected a pre-allocated AttemptContext")
    return {
        **attempt,
        "schema_version": 1,
        "prepared_ref": request["prepared_ref"],
        "output_root": request["output_root"],  # Harness runtime artifacts, per ExecutionSpec.
        "candidate": proposal["candidate"],
        "generation_record_ref": proposal["generation_record_ref"],
    }


def _preserves_request(spec: dict, fields: dict, inputs: list) -> bool:
    if not fields.keys() <= spec.keys() or encode(fields) != encode(
        {field: spec[field] for field in fields}
    ):
        return False
    bound_inputs = spec.get("inputs")
    if not isinstance(bound_inputs, list):
        return False
    # The binder can add inputs from the frozen preparation.
    bound_bytes = {encode(item) for item in bound_inputs}
    return all(encode(item) in bound_bytes for item in inputs)


def _execute_saved(request: dict, fields: dict, bind_execution, execute_harness) -> dict:
    spec = bind_execution(deepcopy(request))
    if is_public_error(spec):
        return execution_result(error=spec)
    if not _preserves_request(spec, fields, request["proposal"]["inputs"]):
        return execution_result(error=_validation_error(
            "InvalidExecutionSpec", "Execution binding changed fields of the saved request."
        ))

    submitted_digest = request_digest(spec)
    response = execute_harness(spec)
    if is_public_error(response):
        return execution_result(error=response)
    if response.get("request_digest") != submitted_digest or any(
        response.get(field) != fields[field]
        for field in ("request_id", "run_id", "attempt_id", "prepared_ref")
    ):
        return execution_result(error=_validation_error(
            "IdentityMismatch", "Harness returned a record for a different request."
        ))
    return execution_result(record=response)


def execute(
    request: dict,
    *,
    workspace: Path,
    bind_execution: Callable[[dict], dict],
    execute_harness: Callable[[dict], dict],
    output_id: str | None = None,
) -> RunOutput:
    """Bind the saved request and submit its original attempt to Harness.

    The trusted host supplies the binder and Harness port. Either may raise
    PublicError or return its wire form. Harness owns the RunStore, request
    identity and replay decisions. Workspace and output_id locate Apps output.
    """
    if output_id is not None:
        validate_output_id(output_id)
    try:
        encode(request)
        fields = _request_fields(request)
    except ValueError:
        result = execution_result(error=_validation_error(
            "InvalidRequest", "Expected a v1 execute request with a pre-allocated attempt."
        ))
        return publish_result(workspace, result, output_id=output_id)

    try:
        result = _execute_saved(request, fields, bind_execution, execute_harness)
    except PublicError as error:
        result = execution_result(error=error.to_json())
    return publish_result(workspace, result, output_id=output_id)
