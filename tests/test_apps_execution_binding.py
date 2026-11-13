"""Check Apps binding against the D023 spec and a fixed preparation."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi._json_v1 import decode, encode
from inferrsi.apps.api import execute
from inferrsi.apps.bridge import bind_execution, verify_protocol
from inferrsi.harness.errors import PublicError
from inferrsi.harness.execution_spec import request_digest

_FIXTURES = Path(__file__).resolve().parents[1] / "docs/contracts/fixtures"
_ATTEMPT = (
    "request_id", "run_id", "attempt_id", "owner", "target_request", "deadline_utc",
    "resources", "budget", "retry_of", "retry_reason",
)
_PROPOSAL = ("candidate", "inputs", "generation_record_ref")


@pytest.fixture
def binding():
    raw = (_FIXTURES / "execution-spec-d023.json").read_bytes()
    golden = decode(raw)
    prepared = decode((_FIXTURES / "t108-v4/prepared.json").read_bytes())
    request = {
        "schema_version": 1,
        "attempt": {key: golden[key] for key in _ATTEMPT},
        "proposal": {key: golden[key] for key in _PROPOSAL},
        "prepared_ref": golden["prepared_ref"],
        "output_root": golden["output_root"],
    }
    return request, prepared, golden


def _refresh_ref(request, prepared):
    data = encode(prepared)
    request["prepared_ref"]["artifact"].update(
        sha256=sha256(data).hexdigest(), size_bytes=len(data),
    )


def test_bind_matches_d023_golden_with_explicit_timeout_normalized(binding):
    request, prepared, golden = binding
    original = deepcopy((request, prepared))
    spec = bind_execution(request, prepared)
    assert (request, prepared) == original
    assert spec["steps"][0]["timeout_seconds"] is None
    # The golden supplies a step timeout. OperationRecipe carries no such field.
    spec["steps"][0]["timeout_seconds"] = golden["steps"][0]["timeout_seconds"]
    assert encode(spec) == (_FIXTURES / "execution-spec-d023.json").read_bytes()
    manifest = (_FIXTURES / "MANIFEST-d023.json").read_text(encoding="utf-8")
    assert request_digest(spec) in manifest


def test_bind_retains_fixed_execution_resource_by_role(binding):
    request, prepared, _ = binding
    ref = {
        "location": "fixtures/fixed/weights", "sha256": "1" * 64,
        "media_type": "application/octet-stream", "size_bytes": 17,
    }
    prepared["resources"] = [{
        "role": "fixture:weights", "artifact": ref, "required_for": ["execute"],
        "format_schema": {"name": "weights", "revision": "1"},
    }]
    recipe = prepared["recipe"]
    recipe["input_roles"].append("fixture:weights")
    recipe["args"].append("{input:fixture:weights}")
    _refresh_ref(request, prepared)

    spec = bind_execution(request, prepared)
    assert spec == bind_execution(deepcopy(request), deepcopy(prepared))
    candidate, weights = spec["inputs"]
    assert candidate == request["proposal"]["inputs"][0]
    assert weights["source_ref"] == ref
    assert weights["expected_sha256"] == ref["sha256"]
    assert weights["source_namespace"] == "artifact"
    assert spec["steps"][0]["args"][-1] == weights["materialized_path"]
    assert spec["steps"][0]["expected_code_sha256"] == recipe["code_sha256"]
    assert all(spec[key] == request["attempt"][key] for key in _ATTEMPT)
    request["proposal"]["inputs"].append(deepcopy(weights))
    with pytest.raises(PublicError, match="InvalidExecutionSpec"):
        bind_execution(request, prepared)


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("fixed_digest", "IdentityMismatch"),
        ("candidate", "InvalidExecutionSpec"),
        ("worker_digest", "InvalidExecutionSpec"),
        ("unknown_role", "InvalidExecutionSpec"),
        ("embedded_role", "InvalidExecutionSpec"),
        ("path_escape", "InvalidExecutionSpec"),
        ("overlapping_paths", "InvalidExecutionSpec"),
        ("identity_rule", "UnsupportedRuleVersion"),
    ],
)
def test_bind_rejects_inconsistent_declarations(binding, fault, code):
    request, prepared, _ = binding
    if fault == "candidate":
        request["proposal"]["candidate"]["candidate_id"] = "different-candidate"
    elif fault == "worker_digest":
        prepared["recipe"]["code_sha256"] = None
    elif fault == "unknown_role":
        prepared["recipe"]["args"].append("{input:unknown}")
    elif fault == "embedded_role":
        prepared["recipe"]["args"].append("--candidate={input:candidate}")
    elif fault == "path_escape":
        request["proposal"]["inputs"][0]["materialized_path"] = "../candidate"
    elif fault == "overlapping_paths":
        prepared["recipe"]["outputs"][0]["path"] = "inputs"
    elif fault == "identity_rule":
        prepared["candidate_contract"]["identity_rule"]["revision"] = "2"
    if fault == "fixed_digest":
        request["prepared_ref"]["artifact"]["sha256"] = "0" * 64
    else:
        _refresh_ref(request, prepared)
    with pytest.raises(PublicError, match=code):
        bind_execution(request, prepared)


def _write_archive(tmp_path, prepared, protocol):
    root = tmp_path / "archive"
    root.mkdir()
    (root / "prepared.json").write_bytes(encode(prepared))
    (root / "protocol.json").write_bytes(protocol)
    config = decode((_FIXTURES / "t108-v4/storage-config.json").read_bytes())
    config["mounts"][0]["root"] = str(root)
    config["mounts"][1]["root"] = str(tmp_path / "store")
    return root, config


def test_execute_reads_fixed_archive_and_keeps_same_spec_for_replay(tmp_path, binding):
    request, prepared, _ = binding
    protocol = (_FIXTURES / "t108-v4/protocol.json").read_bytes()
    root, config = _write_archive(tmp_path, prepared, protocol)
    submitted = []

    def harness(spec):
        submitted.append(encode(spec))
        raise PublicError(
            "RecoveryRequired", stage="claim", message="Attempt state is unknown.",
            attempt_id=request["attempt"]["attempt_id"],
        )

    saved = encode(request)
    for index in range(2):
        run = execute(
            decode(saved), workspace=tmp_path, storage_config=config,
            execute_harness=harness, output_id=f"run-{index}",
        )
        assert run.result["exit_code"] == 5
    assert submitted == [encode(bind_execution(request, prepared))] * 2

    (root / "protocol.json").unlink()
    run = execute(request, workspace=tmp_path, storage_config=config, execute_harness=harness)
    assert run.result["reason_code"] == "ArtifactUnavailable"
    assert len(submitted) == 2

    (root / "prepared.json").write_bytes(b"tampered")
    run = execute(request, workspace=tmp_path, storage_config=config, execute_harness=harness)
    assert run.result["reason_code"] == "ArtifactIntegrityError"
    assert len(submitted) == 2


@pytest.mark.parametrize("field", ["recipe", "protocol_digest", "validation_scope", "resources"])
def test_execute_rejects_prepare_protocol_disagreement(tmp_path, binding, field):
    request, prepared, _ = binding
    protocol = (_FIXTURES / "t108-v4/protocol.json").read_bytes()
    if field == "recipe":
        prepared["recipe"]["code_sha256"] = "1" * 64
    elif field == "protocol_digest":
        prepared[field] = "sha256:" + "1" * 64
    elif field == "resources":
        prepared[field] = [{
            "role": "extra", "required_for": ["assess"],
            "format_schema": {"name": "fixture-data", "revision": "1"},
            "artifact": prepared["protocol"],
        }]
    else:
        prepared[field] = "another-scope"
    _refresh_ref(request, prepared)
    _, config = _write_archive(tmp_path, prepared, protocol)
    run = execute(
        request, workspace=tmp_path, storage_config=config,
        execute_harness=lambda _: pytest.fail("submitted mismatched preparation"),
    )
    assert run.result["reason_code"] == "IdentityMismatch"
    assert run.result["error"]["stage"] == "binder_validation"


def test_protocol_projection_keeps_ref_shaped_parameters_and_ignores_resource_location(binding):
    _, prepared, _ = binding
    protocol = decode((_FIXTURES / "t108-v4/protocol.json").read_bytes())
    artifact = {
        "location": "fixtures/baseline", "sha256": "1" * 64, "size_bytes": 20,
        "media_type": "application/octet-stream",
    }
    protocol["task_parameters"]["ref_shaped_value"] = deepcopy(artifact)
    protocol["baseline"] = {
        "role": "baseline", "artifact": artifact, "required_for": ["execute"],
        "format_schema": {"name": "fixture-data", "revision": "1"},
    }
    prepared["resources"] = [deepcopy(protocol["baseline"])]
    prepared["resources"][0]["artifact"]["location"] = "archive/relocated-baseline"

    projection = deepcopy(protocol)
    del projection["display_notes"]
    del projection["baseline"]["artifact"]["location"]
    prepared["protocol_digest"] = "sha256:" + sha256(encode(projection)).hexdigest()
    data = encode(protocol)
    prepared["protocol"].update(sha256=sha256(data).hexdigest(), size_bytes=len(data))
    verify_protocol(prepared, data)

    protocol["task_parameters"]["ref_shaped_value"]["location"] = "different/parameter"
    data = encode(protocol)
    prepared["protocol"].update(sha256=sha256(data).hexdigest(), size_bytes=len(data))
    with pytest.raises(PublicError, match="IdentityMismatch"):
        verify_protocol(prepared, data)


def test_protocol_rejects_identical_duplicate_resource_roles(binding):
    _, prepared, _ = binding
    protocol = decode((_FIXTURES / "t108-v4/protocol.json").read_bytes())
    resource = {
        "role": "baseline", "required_for": ["execute"],
        "format_schema": {"name": "fixture-data", "revision": "1"},
        "artifact": prepared["protocol"],
    }
    protocol["resources"] = [deepcopy(resource), deepcopy(resource)]
    prepared["resources"] = [deepcopy(resource)]
    projection = deepcopy(protocol)
    del projection["display_notes"]
    for item in projection["resources"]:
        del item["artifact"]["location"]
    prepared["protocol_digest"] = "sha256:" + sha256(encode(projection)).hexdigest()
    data = encode(protocol)
    prepared["protocol"].update(sha256=sha256(data).hexdigest(), size_bytes=len(data))
    with pytest.raises(PublicError, match="InvalidExecutionSpec"):
        verify_protocol(prepared, data)


@pytest.mark.parametrize("resources", [{}, "", None])
def test_execute_rejects_non_array_protocol_resources(tmp_path, binding, resources):
    request, prepared, _ = binding
    protocol = decode((_FIXTURES / "t108-v4/protocol.json").read_bytes())
    protocol["resources"] = resources
    data = encode(protocol)
    prepared["protocol"].update(sha256=sha256(data).hexdigest(), size_bytes=len(data))
    _refresh_ref(request, prepared)
    _, config = _write_archive(tmp_path, prepared, data)
    run = execute(
        request, workspace=tmp_path, storage_config=config,
        execute_harness=lambda _: pytest.fail("submitted malformed archived protocol"),
    )
    assert run.result["reason_code"] == "InvalidExecutionSpec"
    assert run.result["error"]["stage"] == "binder_validation"
