"""Production preparation, fixed resource closure and the real Apps T36 consumer."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from inferrsi.apps.api import prepare as apps_prepare
from inferrsi.apps.handoff.bridge import verify_protocol
from inferrsi.apps.storage.archive import read_archive_artifact, read_prepared
from inferrsi.benchmark import preparation as benchmark
from inferrsi.contracts.json_v1 import CanonicalError, decode, encode

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/contracts/fixtures/t108-v4"


def test_frozen_documentary_ids_and_pure_codec_remain_compatible(monkeypatch):
    prepared_bytes = (GOLDEN / "prepared.json").read_bytes()
    protocol_bytes = (GOLDEN / "protocol.json").read_bytes()
    prepared, protocol = decode(prepared_bytes), decode(protocol_bytes)
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("codec opened a file"))
    assert benchmark.prepared_id(prepared) == prepared["prepared_id"]
    assert benchmark.protocol_digest(protocol) == prepared["protocol_digest"]
    assert benchmark.encode(prepared) == prepared_bytes
    assert benchmark.decode(prepared_bytes) == prepared
    benchmark.validate_prepared(prepared, protocol_bytes)


@pytest.fixture
def preparation(tmp_path):
    protocol = decode((GOLDEN / "protocol.json").read_bytes())
    # Historical vectors stay unchanged. This configured task binds actual code
    # bytes through the production resource capability instead of a dummy digest.
    source = tmp_path / "worker.py"
    source.write_bytes(b"import sys\nprint(sys.version_info.major)\n")
    data = tmp_path / "input.txt"
    data.write_bytes(b"fixed input\n")
    sources = {"worker-code": source, "input-data": data}
    pins = []
    for role, path in sorted(sources.items()):
        payload = path.read_bytes()
        pins.append({
            "role": role,
            "artifact": {"location": "source/" + role, "sha256": sha256(payload).hexdigest(),
                         "size_bytes": len(payload), "media_type": "text/plain"},
            "format_schema": {"name": "utf8-text", "revision": "1"},
            "required_for": ["prepare", "execute"],
        })
    protocol["resources"] = pins
    protocol["worker_recipe"]["code_sha256"] = sha256(source.read_bytes()).hexdigest()
    opened = []

    def resources(role):
        stream = sources[role].open("rb")
        opened.append(stream)
        return stream

    service = benchmark.PreparationService(
        protocol, resources=resources, worker_role="worker-code",
    )
    request = {
        "schema_version": 1, "task": protocol["task"], "operation": "evaluate",
        "validation_scope": "p1", "input_pins": [],
        "task_parameters": deepcopy(protocol["task_parameters"]),
        "comparison_conditions": {}, "expected_candidate": None, "budget_policy_refs": [],
    }
    archive = tmp_path / "archive"
    archive.mkdir()
    config = {
        "schema_version": 1, "archive_namespace": "apps", "harness_namespace": "test",
        "mounts": [{"prefix": "archives/local", "namespace": "apps",
                    "root": str(archive), "kind": "directory"},
                   {"prefix": "stores/test", "namespace": "test",
                    "root": str(tmp_path / "store"), "kind": "harness_sqlite"}],
    }
    return service, request, sources, protocol, opened, config, archive


def _prepare_with_apps(request, workspace, config, producer):
    return apps_prepare(
        {"schema_version": 1, "request": request}, workspace=workspace,
        storage_config=config, prepare_benchmark=producer,
        encode_prepared=benchmark.encode, validate_prepared=benchmark.validate_prepared,
    )


def test_real_prepare_freezes_exact_supplied_bytes_and_isolates_caller_mutations(preparation):
    service, request, sources, protocol, opened, _, _ = preparation
    protocol["task_parameters"]["label"] = "changed after configuration"
    prepared, data, reader = service.prepare(request)
    assert all(stream.closed for stream in opened)
    benchmark.validate_prepared(prepared, data)
    verify_protocol(prepared, data)
    assert decode(data)["task_parameters"] == request["task_parameters"]
    assert prepared["recipe"]["code_sha256"] == sha256(
        sources["worker-code"].read_bytes()
    ).hexdigest()
    with reader("input-data") as stream:
        assert stream.read() == b"fixed input\n"
    with pytest.raises(KeyError):
        reader("not-in-closure")
    original_id = prepared["prepared_id"]
    prepared["recipe"]["args"].append("caller mutation")
    assert service.prepare(request)[0]["prepared_id"] == original_id


def test_two_layer_locations_and_ref_shaped_parameters(preparation):
    service, request, _, _, _, _, _ = preparation
    prepared, data, _ = service.prepare(request)
    moved = deepcopy(prepared)
    moved["protocol"]["location"] = "relocated/protocol.json"
    for resource in moved["resources"]:
        resource["artifact"]["location"] = "relocated/" + resource["role"]
    benchmark.validate_prepared(moved, data)
    assert benchmark.prepared_id(moved) == prepared["prepared_id"]
    assert benchmark.encode(moved) != benchmark.encode(prepared)

    internal = decode(data)
    internal["resources"][0]["artifact"]["location"] = "inside/new-location"
    internal_bytes = encode(internal)
    assert internal_bytes != data
    assert benchmark.protocol_digest(internal) == prepared["protocol_digest"]
    moved["protocol"].update(sha256=sha256(internal_bytes).hexdigest(),
                             size_bytes=len(internal_bytes))
    moved["prepared_id"] = benchmark.prepared_id(moved)
    assert moved["prepared_id"] != prepared["prepared_id"]
    benchmark.validate_prepared(moved, internal_bytes)

    # Identity projection does not recursively strip a location from Parameters.
    projected = decode(data)
    projected["task_parameters"]["ref_shaped"] = deepcopy(prepared["protocol"])
    first = benchmark.protocol_digest(projected)
    projected["task_parameters"]["ref_shaped"]["location"] = "semantic/location"
    assert benchmark.protocol_digest(projected) != first
    changed = decode(data)
    changed["task_parameters"]["label"] = "different frozen condition"
    assert benchmark.protocol_digest(changed) != prepared["protocol_digest"]
    request["task_parameters"]["label"] = changed["task_parameters"]["label"]
    new_prepared, new_data, _ = service.prepare(request)
    assert new_data != data
    for key in ("prepared_id", "protocol_digest"):
        assert new_prepared[key] != prepared[key]
    assert new_prepared["protocol"]["sha256"] != prepared["protocol"]["sha256"]


@pytest.mark.parametrize("change,code", [
    (lambda value: value.update(schema_version=2), "UnsupportedSchema"),
    (lambda value: value["task"].update(revision="unsupported"), "UnsupportedRuleVersion"),
    (lambda value: value.update(operation="other"), "UnsupportedOperation"),
    (lambda value: value.update(unrecognized=True), "InvalidRequest"),
    (lambda value: value["task_parameters"].update(decimal_fixture="1.0"), "InvalidRequest"),
    (lambda value: value.update(expected_candidate={"candidate_id": "incomplete"}),
     "InvalidRequest"),
    (lambda value: value.update(expected_candidate={
        "candidate_id": "candidate", "sha256": "a" * 64,
        "format_schema": {"name": "other", "revision": "1"},
    }), "InvalidRequest"),
])
def test_request_rejections_are_wire_errors_before_any_archive(preparation, change, code):
    service, request, _, _, opened, _, archive = preparation
    change(request)
    response = service.prepare(request)
    assert response["code"] == code and response["stage"] == "prepare"
    assert response["latest_record_ref"] is None and response["retained_refs"] == []
    assert list(archive.iterdir()) == [] and opened == []


@pytest.mark.parametrize("stage", ["prepare", "archive"])
def test_t36_resource_loss_at_each_boundary(preparation, tmp_path, stage):
    service, request, sources, _, _, config, archive = preparation
    if stage == "prepare":
        sources["input-data"].unlink()
        producer = service.prepare
    else:
        response = service.prepare(request)
        sources["input-data"].unlink()
        def producer(value):
            return response
    result = _prepare_with_apps(request, tmp_path, config, producer)
    assert result.result["reason_code"] == "ArtifactUnavailable", result.result
    assert result.result["error"]["stage"] == ("prepare" if stage == "prepare"
                                                else "prepared_archive")
    assert result.result["prepared_ref"] is None
    assert list(archive.iterdir()) == []


def test_wrong_resource_bytes_are_not_frozen_as_a_different_pin(preparation):
    service, request, sources, _, _, _, _ = preparation
    sources["worker-code"].write_bytes(b"unexpected replacement worker")
    assert service.prepare(request)["code"] == "ArtifactIntegrityError"


@pytest.mark.parametrize("close_fails", [False, True], ids=["closes", "close-error"])
def test_t36_oversized_resource_stops_at_the_first_extra_byte(preparation, tmp_path, close_fails):
    _, request, sources, protocol, _, config, archive = preparation
    fixed_bytes = sources["input-data"].read_bytes()
    read_sizes = []

    class OversizedResource(BytesIO):
        def read(self, size=-1):
            read_sizes.append(size)
            if len(read_sizes) > 1:
                raise OSError("resource read failed")
            return super().read(size)

        def close(self):
            super().close()
            if close_fails:
                raise OSError("resource close failed")

    stream = OversizedResource(fixed_bytes + b"x")
    service = benchmark.PreparationService(
        protocol,
        resources=lambda role: stream if role == "input-data" else sources[role].read_bytes(),
        worker_role="worker-code",
    )
    result = _prepare_with_apps(request, tmp_path, config, service.prepare)
    assert result.result["reason_code"] == "ArtifactIntegrityError"
    assert result.result["error"]["stage"] == "prepare"
    assert result.result["prepared_ref"] is None
    assert list(archive.iterdir()) == []
    assert read_sizes == [len(fixed_bytes) + 1]
    assert stream.closed


@pytest.mark.parametrize("change", [
    lambda value: value["candidate_contract"].update(unknown=True),
    lambda value: value["recipe"].update(unrecognized=True),
    lambda value: value["recipe"]["outputs"][0].update(required=1),
    lambda value: value.update(created_at="2026-02-30T00:00:00Z"),
    lambda value: value.update(created_at=True),
    lambda value: value.update(created_at="2026-11-20T00:00:00.1234567890Z"),
    lambda value: value["resources"].append(deepcopy(value["resources"][0])),
    lambda value: value["required_evidence"][0].update(matching_rule_revision="other"),
])
def test_closed_prepared_shape_rejected_even_with_recomputed_identity(preparation, change):
    service, request, _, _, _, _, _ = preparation
    prepared, _, _ = service.prepare(request)
    change(prepared)
    prepared["prepared_id"] = benchmark.prepared_id(prepared)
    with pytest.raises(ValueError):
        benchmark.encode(prepared)


def test_unsafe_location_is_rejected_by_the_encoder_itself(preparation):
    service, request, _, _, _, _, _ = preparation
    prepared, _, _ = service.prepare(request)
    prepared["protocol"]["location"] = "../escape"
    with pytest.raises(benchmark.PreparationError, match="logical artifact location"):
        benchmark.encode(prepared)


def test_source_change_after_preparation_is_rejected_by_independent_apps_verification(
    preparation, tmp_path,
):
    service, request, sources, _, _, config, archive = preparation
    response = service.prepare(request)
    sources["input-data"].write_bytes(b"changed input")
    result = _prepare_with_apps(request, tmp_path, config, lambda value: response)
    assert result.result["reason_code"] == "ArtifactIntegrityError"
    assert result.result["prepared_ref"] is None and list(archive.iterdir()) == []


def test_frozen_task_rules_are_not_request_parameters(preparation):
    _, _, sources, protocol, _, _, _ = preparation
    protocol["claim_definitions"][0]["decision_rule"]["revision"] = "unimplemented"
    with pytest.raises(benchmark.PreparationError) as error:
        benchmark.PreparationService(
            protocol, worker_role="worker-code", resources=lambda role: sources[role].open("rb"),
        )
    assert error.value.code == "UnsupportedRuleVersion"


@pytest.mark.parametrize("failure", [ValueError("host bug"), CanonicalError("host", "host bug")])
def test_programming_error_in_a_host_capability_is_not_a_port_rejection(preparation, failure):
    _, request, _, protocol, _, _, _ = preparation

    def broken(role):
        raise failure

    service = benchmark.PreparationService(protocol, resources=broken, worker_role="worker-code")
    with pytest.raises(ValueError) as error:
        service.prepare(request)
    assert error.value is failure


def test_text_stream_is_a_closed_host_capability_error(preparation):
    _, request, _, protocol, _, _, _ = preparation
    stream = StringIO("a text capability is not a binary resource")
    service = benchmark.PreparationService(
        protocol, resources=lambda role: stream, worker_role="worker-code",
    )
    with pytest.raises(TypeError, match="binary bytes"):
        service.prepare(request)
    assert stream.closed


def test_provisional_locations_do_not_replace_role_authority_or_archive_paths(
    preparation, tmp_path,
):
    service, request, sources, protocol, _, config, _ = preparation
    pin = deepcopy(protocol["resources"][0])
    assert pin["role"] == "input-data"
    pin["artifact"]["location"] = protocol["resources"][1]["artifact"]["location"]
    request["input_pins"] = [pin]
    result = _prepare_with_apps(request, tmp_path, config, service.prepare)
    assert result.result["exit_code"] == 0, result.result
    prepared = read_prepared(config, result.result["prepared_ref"])
    assert len({item["artifact"]["location"] for item in prepared["resources"]}) == 2
    assert {item["role"]: read_archive_artifact(config, item["artifact"])
            for item in prepared["resources"]} == {
                role: path.read_bytes() for role, path in sources.items()
            }
    frozen = decode(read_archive_artifact(config, prepared["protocol"]))
    assert len({item["artifact"]["location"] for item in frozen["resources"]}) == 1


def test_t36_real_port_archive_and_cross_process_fixed_readback(preparation, tmp_path):
    service, request, sources, _, _, config, _ = preparation
    expected, protocol, _ = service.prepare(request)
    result = _prepare_with_apps(request, tmp_path, config, service.prepare)
    assert result.result["exit_code"] == 0, result.result
    ref = result.result["prepared_ref"]
    assert ref["prepared_id"] == expected["prepared_id"]
    archived = read_prepared(config, ref)
    benchmark.validate_prepared(archived, protocol)
    child = """
import json, sys
sys.path.insert(0, sys.argv[1])
from inferrsi.apps.storage.archive import read_prepared, read_archive_artifact
from inferrsi.benchmark.preparation import encode, validate_prepared
config, ref = json.loads(sys.stdin.read())
prepared = read_prepared(config, ref)
protocol = read_archive_artifact(config, prepared['protocol'])
validate_prepared(prepared, protocol)
print(json.dumps({'prepared': encode(prepared).hex(), 'protocol': protocol.hex(),
    'resources': {x['role']: read_archive_artifact(config, x['artifact']).hex()
                  for x in prepared['resources']}}))
"""
    process = subprocess.run(
        [sys.executable, "-I", "-c", child, str(ROOT / "src")], cwd=tmp_path,
        env={**os.environ, "PYTHONUTF8": "1"}, input=json.dumps([config, ref]),
        capture_output=True, text=True, timeout=30,
    )
    assert process.returncode == 0, process.stderr
    observed = json.loads(process.stdout)
    prepared_bytes = bytes.fromhex(observed["prepared"])
    assert sha256(prepared_bytes).hexdigest() == ref["artifact"]["sha256"]
    assert len(prepared_bytes) == ref["artifact"]["size_bytes"]
    assert observed["protocol"] == protocol.hex()
    assert observed["resources"] == {role: path.read_bytes().hex()
                                     for role, path in sources.items()}
