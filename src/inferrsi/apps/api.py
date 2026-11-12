"""Python entry points for assembling and publishing Apps operations."""

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from inferrsi._json_v1 import encode
from inferrsi.harness.errors import PublicError
from inferrsi.harness.execution_spec import request_digest

from .archive import RunOutput, publish_result, validate_output_id
from .result import execution_result, is_public_error, validate_result

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


def _port_call(port: Callable[[dict], dict], value: dict) -> object:
    # Programming/host exceptions are not port replies: do not silently swallow them.
    try:
        return port(value)
    except PublicError as error:
        return error.to_json()


def _port_error(error: dict, fields: dict, digest: str | None = None) -> dict:
    result = execution_result(error=error)
    validate_result(result)
    partial = error["partial_record"]
    refs = [error["latest_record_ref"]] if error["latest_record_ref"] is not None else []
    if (error["attempt_id"] is not None and error["attempt_id"] != fields["attempt_id"]) or any(
        ref["attempt_id"] != fields["attempt_id"] for ref in refs
    ) or (partial is not None and (
        any(partial[key] != fields[key] for key in ("request_id", "run_id", "attempt_id"))
        or (digest is not None and partial["request_digest"] is not None
            and partial["request_digest"] != digest)
    )):
        return execution_result(error=_validation_error(
            "IdentityMismatch", "Port error facts belong to a different execution request."
        ))
    return result


def _invalid_port_result() -> dict:
    return execution_result(error=_validation_error(
        "InvalidExecutionSpec", "The execution port returned a malformed response."
    ))


def _execute_saved(
    request: dict,
    fields: dict,
    bind_execution: Callable[[dict], dict],
    execute_harness: Callable[[dict], dict],
) -> dict:
    spec = _port_call(bind_execution, deepcopy(request))
    try:
        if is_public_error(spec):
            return _port_error(spec, fields)
        if not isinstance(spec, dict) or not _preserves_request(
            spec, fields, request["proposal"]["inputs"]
        ):
            return _invalid_port_result()
        submitted_digest = request_digest(spec)
    except (ValueError, TypeError, KeyError):
        return _invalid_port_result()

    response = _port_call(execute_harness, spec)
    try:
        if is_public_error(response):
            return _port_error(response, fields, submitted_digest)
        if not isinstance(response, dict) or "request_digest" not in response:
            return _invalid_port_result()
        if response["request_digest"] != submitted_digest or any(
            response.get(field) != fields[field]
            for field in ("request_id", "run_id", "attempt_id", "prepared_ref")
        ):
            return execution_result(error=_validation_error(
                "IdentityMismatch", "Harness returned a record for a different request."
            ))
        result = execution_result(record=response)
        validate_result(result)
        return result
    except (ValueError, TypeError, KeyError):
        return _invalid_port_result()


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

    result = _execute_saved(request, fields, bind_execution, execute_harness)
    return publish_result(workspace, result, output_id=output_id)
