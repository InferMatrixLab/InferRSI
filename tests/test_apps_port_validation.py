"""Malformed port replies do not become trusted execution facts."""

from copy import deepcopy
from dataclasses import fields

import pytest

from inferrsi.apps.api import execute
from inferrsi.apps.archive import read_result
from inferrsi.harness.errors import PartialExecutionFacts, PublicError
from inferrsi.harness.execution_spec import request_digest
from inferrsi.harness.run_store import request_digest as legacy_digest
from tests.test_apps_output import _bind, _fixture, _request, _submit_to_run_store


def _run(tmp_path, reply):
    return execute(_request(), workspace=tmp_path, bind_execution=_bind,
                   execute_harness=lambda spec: reply)


@pytest.mark.parametrize("reply", [None, [], {"code": "FutureUnknownError"}])
def test_malformed_reply_has_a_published_validation_error(tmp_path, reply):
    output = _run(tmp_path, reply)
    assert output.result["reason_code"] == "InvalidExecutionSpec"
    assert output.result["exit_code"] == 2
    assert read_result(tmp_path, output.output_id) == output


@pytest.mark.parametrize("location", ["attempt", "latest"])
def test_error_identity_must_match_saved_request(tmp_path, location):
    error = PublicError("RecoveryRequired", stage="claim", message="unknown").to_json()
    if location == "attempt":
        error["attempt_id"] = "other"
    else:
        error["latest_record_ref"] = deepcopy(_fixture("record-api-envelope")["record_ref"])
        error["latest_record_ref"]["attempt_id"] = "other"
    output = _run(tmp_path, error)
    assert output.result["reason_code"] == "IdentityMismatch"
    assert output.result["error"]["latest_record_ref"] is None
    assert read_result(tmp_path, output.output_id) == output


def test_partial_values_are_checked_not_just_keys(tmp_path):
    error = PublicError("ExecutionPersistenceError", stage="commit", message="failed").to_json()
    error["partial_record"] = {field.name: 12345 for field in fields(PartialExecutionFacts)}
    output = _run(tmp_path, error)
    assert output.result["reason_code"] == "InvalidExecutionSpec"
    assert output.result["error"]["partial_record"] is None


def test_nonterminal_record_is_a_port_violation(tmp_path):
    reply = _submit_to_run_store(tmp_path, _bind(_request()))
    reply["phase"] = "running"
    output = _run(tmp_path, reply)
    assert output.result["reason_code"] == "InvalidExecutionSpec"
    assert read_result(tmp_path, output.output_id) == output


def test_host_programming_exception_is_not_misrepresented_as_port_result(tmp_path):
    def broken(request):
        raise RuntimeError("host bug")
    with pytest.raises(RuntimeError, match="host bug"):
        execute(_request(), workspace=tmp_path, bind_execution=broken,
                execute_harness=lambda spec: None)
    assert not (tmp_path / "output").exists()


def test_pure_digest_surface_preserves_legacy_function_and_bytes():
    assert request_digest is legacy_digest
    assert request_digest(_bind(_request())) == legacy_digest(_bind(_request()))


@pytest.mark.parametrize("key,value", [("started", 1), ("side_effect_unknown", 0),
                                      ("steps", 12345), ("budget_admission", []),
                                      ("request_digest", "bad"), ("phase", "unknown")])
def test_each_partial_value_type_is_validated(tmp_path, key, value):
    partial = PartialExecutionFacts.from_payload(_fixture("record-payload")).to_json()
    partial["request_digest"] = request_digest(_bind(_request()))
    partial[key] = value
    error = PublicError("ExecutionPersistenceError", stage="commit", message="failed").to_json()
    error["partial_record"] = partial
    assert _run(tmp_path, error).result["reason_code"] == "InvalidExecutionSpec"


def test_partial_identity_is_bound_to_request(tmp_path):
    partial = PartialExecutionFacts.from_payload(_fixture("record-payload")).to_json()
    partial["attempt_id"] = "another"
    error = PublicError("ExecutionPersistenceError", stage="commit", message="failed").to_json()
    error["partial_record"] = partial
    assert _run(tmp_path, error).result["reason_code"] == "IdentityMismatch"
