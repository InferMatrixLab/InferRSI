"""Python entry points for assembling and publishing Apps operations."""

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from inferrsi._json_v1 import encode
from inferrsi.harness.errors import PublicError
from inferrsi.harness.execution_spec import request_digest

from .archive import (
    ResourceReader,
    RunOutput,
    archive_mount,
    archive_prepared,
    publish_result,
    validate_output_id,
)
from .result import execution_result, is_public_error, preparation_result, validate_result

_PREPARE_FIELDS = {"schema_version", "request"}
_BENCHMARK_REQUEST_FIELDS = {
    "schema_version", "task", "operation", "validation_scope", "input_pins", "task_parameters",
    "comparison_conditions", "expected_candidate", "budget_policy_refs",
}
_EXECUTE_FIELDS = {"schema_version", "prepared_ref", "proposal", "attempt", "output_root"}
_ATTEMPT_FIELDS = {
    "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
    "resources", "budget", "retry_of", "retry_reason",
}
_PROPOSAL_FIELDS = {"candidate", "inputs", "generation_record_ref"}


def _validation_error(code: str, message: str, *, stage: str = "validation") -> dict:
    return {
        "code": code,
        "stage": stage,
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


def _port_call(port: Callable[[dict], object], value: dict) -> object:
    # Programming/host exceptions are not port replies: do not silently swallow them.
    try:
        return port(value)
    except PublicError as error:
        return error.to_json()


def _port_error(
    error: dict, fields: dict, digest: str | None = None, *, stage: str
) -> dict:
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
            "IdentityMismatch", "Port error facts belong to a different execution request.",
            stage=stage,
        ))
    return result


def _invalid_port_result(stage: str) -> dict:
    return execution_result(error=_validation_error(
        "InvalidExecutionSpec", "The execution port returned a malformed response.", stage=stage
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
            return _port_error(spec, fields, stage="binder_validation")
        if not isinstance(spec, dict) or not _preserves_request(
            spec, fields, request["proposal"]["inputs"]
        ):
            return _invalid_port_result("binder_validation")
        submitted_digest = request_digest(spec)
    except (ValueError, TypeError, KeyError):
        return _invalid_port_result("binder_validation")

    response = _port_call(execute_harness, spec)
    try:
        if is_public_error(response):
            return _port_error(
                response, fields, submitted_digest, stage="harness_response_validation"
            )
        if not isinstance(response, dict) or "request_digest" not in response:
            return _invalid_port_result("harness_response_validation")
        if response["request_digest"] != submitted_digest or any(
            response.get(field) != fields[field]
            for field in ("request_id", "run_id", "attempt_id", "prepared_ref")
        ):
            return execution_result(error=_validation_error(
                "IdentityMismatch", "Harness returned a record for a different request.",
                stage="harness_response_validation",
            ))
        result = execution_result(record=response)
        validate_result(result)
        return result
    except (ValueError, TypeError, KeyError):
        return _invalid_port_result("harness_response_validation")


def _prepare_request(request: dict) -> dict:
    encode(request)
    benchmark_request = request.get("request") if isinstance(request, dict) else None
    envelopes = (request, _PREPARE_FIELDS), (benchmark_request, _BENCHMARK_REQUEST_FIELDS)
    for value, fields in envelopes:
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
            raise ValueError("expected a numeric schema version")
        if value["schema_version"] != 1:
            raise PublicError(
                "UnsupportedSchema", stage="validation",
                message="Unsupported prepare request version.",
            )
        if value.keys() != fields:
            raise ValueError("unexpected prepare request fields")
    return benchmark_request


def _prepare_port_error(error: dict) -> dict:
    try:
        result = preparation_result(error=error)
        validate_result(result)
    except (ValueError, TypeError, KeyError):
        return preparation_result(error=_validation_error(
            "InvalidRequest", "Benchmark returned a malformed prepare error.",
            stage="benchmark_response_validation",
        ))
    return result


def prepare(
    request: dict,
    *,
    workspace: Path,
    storage_config: dict,
    prepare_benchmark: Callable[[dict], tuple[dict, bytes, ResourceReader] | dict],
    encode_prepared: Callable[[dict], bytes],
    validate_prepared: Callable[[dict, bytes], None],
    output_id: str | None = None,
) -> RunOutput:
    """Freeze a Benchmark request, archive its closure, and publish the Apps result.

    The host adapts the Benchmark prepare port to return the prepared object,
    protocol bytes and a role-keyed reader. Each stream returned by the reader
    is owned by Apps for that read. The pure encoder and validator raise
    ValueError for invalid content or PublicError for a structured rejection.
    The host adapts any Benchmark-specific rejection exception to those types.
    No Harness port is called during preparation.
    """
    if output_id is not None:
        validate_output_id(output_id)
    try:
        benchmark_request = _prepare_request(request)
        mount = archive_mount(storage_config, for_write=True)
    except ValueError:
        result = preparation_result(error=_validation_error(
            "InvalidRequest", "Expected a v1 Apps prepare request."
        ))
    except PublicError as error:
        result = preparation_result(error=error.to_json())
    else:
        response = _port_call(prepare_benchmark, deepcopy(benchmark_request))
        try:
            if is_public_error(response):
                result = _prepare_port_error(response)
            else:
                if not isinstance(response, tuple) or len(response) != 3:
                    raise ValueError("expected a prepared closure")
                prepared, protocol, read_resource = response
                if not isinstance(prepared, dict) or not callable(read_resource):
                    raise ValueError("expected a prepared object and resource reader")
                if any(encode(prepared[key]) != encode(benchmark_request[key]) for key in (
                    "task", "operation", "validation_scope", "expected_candidate"
                )):
                    raise PublicError(
                        "IdentityMismatch", stage="benchmark_response_validation",
                        message="Benchmark prepared a different request.",
                    )
                prepared_ref = archive_prepared(
                    prepared, protocol, read_resource, mount=mount,
                    encode_prepared=encode_prepared, validate_prepared=validate_prepared,
                )
                result = preparation_result(prepared_ref=prepared_ref)
        except PublicError as error:
            result = _prepare_port_error(error.to_json())
        except (ValueError, TypeError, KeyError):
            result = preparation_result(error=_validation_error(
                "InvalidRequest", "Benchmark returned a malformed prepared closure.",
                stage="benchmark_response_validation",
            ))
    return publish_result(workspace, result, output_id=output_id)


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
