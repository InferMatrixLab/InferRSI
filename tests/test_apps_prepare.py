"""Exercise the Apps side of the D023 prepare closure with a Benchmark test port."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest

from inferrsi._json_v1 import decode, encode
from inferrsi.apps import archive
from inferrsi.apps.api import prepare
from inferrsi.apps.archive import read_archive_artifact, read_prepared, read_result
from inferrsi.harness.errors import PublicError

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _ROOT / "docs/contracts/fixtures/t108-v4"


def _ref(location, data, media_type):
    return {
        "location": location, "sha256": sha256(data).hexdigest(),
        "size_bytes": len(data), "media_type": media_type,
    }


def _identity(value, *, drop, refs):
    projected = deepcopy(value)
    for key in drop:
        del projected[key]
    for ref in refs(projected):
        del ref["location"]
    return "sha256:" + sha256(encode(projected)).hexdigest()


def _prepared_id(prepared):
    return _identity(
        prepared, drop=("prepared_id", "created_at", "display_notes"),
        refs=lambda value: [value["protocol"], *(item["artifact"] for item in value["resources"])],
    )


def _protocol_digest(protocol):
    return _identity(
        protocol, drop=("display_notes",),
        refs=lambda value: [item["artifact"] for item in value["resources"]],
    )


@pytest.fixture
def preparation(tmp_path):
    protocol = decode((_FIXTURES / "protocol.json").read_bytes())
    prepared = decode((_FIXTURES / "prepared.json").read_bytes())
    # The original golden bytes are left untouched. Extend the test fixture in memory
    # so a missing resource and an internal protocol field change are observable.
    resources = {"baseline-data": b"frozen baseline\n", "input-data": b"frozen input\n"}
    protocol["resources"] = [
        {
            "role": role, "artifact": _ref(f"fixtures/{role}", data, "text/plain"),
            "format_schema": {"name": "utf8-text", "revision": "1"}, "required_for": ["prepare"],
        }
        for role, data in resources.items()
    ]
    protocol_bytes = encode(protocol)
    prepared["resources"] = deepcopy(protocol["resources"])
    prepared["protocol"] = _ref("fixtures/protocol.json", protocol_bytes, "application/json")
    prepared["protocol_digest"] = _protocol_digest(protocol)
    prepared["prepared_id"] = _prepared_id(prepared)
    request = {
        "schema_version": 1,
        "request": {
            "schema_version": 1,
            **{key: prepared[key] for key in (
                "task", "operation", "validation_scope", "expected_candidate"
            )},
            "input_pins": deepcopy(protocol["resources"]),
            "task_parameters": deepcopy(protocol["task_parameters"]),
            "comparison_conditions": {}, "budget_policy_refs": [],
        },
    }
    root = tmp_path / "archive"
    root.mkdir()
    config = {
        "schema_version": 1,
        "archive_namespace": "apps",
        "harness_namespace": "demo",
        "mounts": [
            {"prefix": "run-archives/local", "namespace": "apps",
             "root": str(root), "kind": "directory"},
            {"prefix": "stores/demo", "namespace": "demo",
             "root": str(tmp_path / "store"), "kind": "harness_sqlite"},
        ],
    }
    return request, prepared, protocol_bytes, resources, config, root


def _validate_prepared(prepared, protocol_bytes):
    protocol = decode(protocol_bytes)
    if prepared["prepared_id"] != _prepared_id(prepared):
        raise ValueError("wrong prepared identity")
    if prepared["protocol_digest"] != _protocol_digest(protocol):
        raise ValueError("wrong protocol identity")
    if prepared["recipe"] != protocol["worker_recipe"]:
        raise ValueError("wrong recipe")


def _run(tmp_path, preparation, **overrides):
    request, prepared, protocol, resources, config, _ = preparation
    options = {
        "storage_config": config,
        "prepare_benchmark": lambda value: (prepared, protocol, resources.__getitem__),
        "encode_prepared": encode,
        "validate_prepared": _validate_prepared,
    }
    options.update(overrides)
    return prepare(request, workspace=tmp_path, **options)


def test_t36_commit_closure_and_read_from_new_process(tmp_path, preparation):
    request, prepared, protocol, resources, config, root = preparation
    before = encode(prepared)
    opened = []
    checks = []

    def reader(role):
        if role == "input-data" and len(checks) == 1:
            raise FileNotFoundError
        stream = BytesIO(resources[role])
        opened.append(stream)
        return stream

    def benchmark(value):
        assert value == request["request"]
        return prepared, protocol, reader

    def validate(value, data):
        _validate_prepared(value, data)
        assert value["protocol"]["location"].startswith("run-archives/local/")
        assert list(root.iterdir()) == []
        checks.append(True)

    missing = _run(
        tmp_path, preparation, prepare_benchmark=benchmark, validate_prepared=validate,
    )
    assert missing.result["reason_code"] == "ArtifactUnavailable"
    assert missing.result["prepared_ref"] is None
    assert opened[0].closed
    assert list(root.iterdir()) == []
    committed = _run(
        tmp_path, preparation, prepare_benchmark=benchmark, validate_prepared=validate,
    )
    assert checks == [True, True]
    assert len(opened) == 3 and all(stream.closed for stream in opened)
    assert committed.result["exit_code"] == 0
    assert read_result(tmp_path, committed.output_id) == committed
    ref = committed.result["prepared_ref"]
    assert ref["prepared_id"] == prepared["prepared_id"]
    assert ref["artifact"]["sha256"] != sha256(before).hexdigest()
    assert encode(prepared) == before

    script = """
import json
import sys
from inferrsi._json_v1 import encode
from inferrsi.apps.archive import read_archive_artifact, read_prepared

config, ref = json.load(sys.stdin)
prepared = read_prepared(config, ref)
print(json.dumps({
    "prepared": encode(prepared).hex(),
    "protocol": read_archive_artifact(config, prepared["protocol"]).hex(),
    "resources": {
        item["role"]: read_archive_artifact(config, item["artifact"]).hex()
        for item in prepared["resources"]
    },
}))
"""
    child = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src")},
        input=json.dumps([config, ref]), text=True, capture_output=True, check=True,
    )
    observed = json.loads(child.stdout)
    data = bytes.fromhex(observed["prepared"])
    assert sha256(data).hexdigest() == ref["artifact"]["sha256"]
    assert decode(data)["prepared_id"] == ref["prepared_id"]
    assert bytes.fromhex(observed["protocol"]) == protocol
    assert observed["resources"] == {key: value.hex() for key, value in resources.items()}


def test_changed_internal_protocol_location_gets_new_prepared_identity(tmp_path, preparation):
    _, prepared, raw, _, _, _ = preparation
    original = _run(tmp_path, preparation).result["prepared_ref"]
    protocol = decode(raw)
    protocol["resources"][0]["artifact"]["location"] = "other-internal/baseline"
    changed = encode(protocol)
    assert _protocol_digest(protocol) == prepared["protocol_digest"]
    prepared["protocol"] = _ref("fixtures/protocol.json", changed, "application/json")
    stale = _run(
        tmp_path, preparation, prepare_benchmark=lambda _: (prepared, changed, preparation[3].get)
    )
    assert stale.result["prepared_ref"] is None
    prepared["prepared_id"] = _prepared_id(prepared)
    rebuilt = _run(
        tmp_path, preparation, prepare_benchmark=lambda _: (prepared, changed, preparation[3].get)
    ).result["prepared_ref"]
    assert rebuilt["prepared_id"] != original["prepared_id"]


@pytest.mark.parametrize(
    ("fault", "code", "stage"),
    [
        ("prefix_overlap", "InvalidRequest", "storage_config"),
        ("protocol_bytes", "ArtifactIntegrityError", "prepared_archive"),
        ("resource_bytes", "ArtifactIntegrityError", "prepared_archive"),
        ("different_request", "IdentityMismatch", "benchmark_response_validation"),
        ("different_encoding", "InvalidRequest", "benchmark_response_validation"),
    ],
)
def test_prepare_rejects_invalid_closure_without_committing(
    tmp_path, preparation, fault, code, stage,
):
    _, prepared, protocol, resources, config, root = preparation
    options = {}
    if fault == "prefix_overlap":
        config["mounts"][1]["prefix"] = "run-archives/local/demo"
        options["prepare_benchmark"] = lambda _: pytest.fail("called with overlapping mounts")
    elif fault == "protocol_bytes":
        options["prepare_benchmark"] = lambda _: (prepared, encode({}), resources.get)
    elif fault == "resource_bytes":
        options["prepare_benchmark"] = lambda _: (prepared, protocol, lambda role: b"wrong")
    elif fault == "different_request":
        options["prepare_benchmark"] = lambda _: (
            {**prepared, "operation": "different"}, protocol, resources.get,
        )
    else:
        options["encode_prepared"] = lambda value: encode({**value, "display_notes": "rewritten"})
    result = _run(tmp_path, preparation, **options).result
    assert result["prepared_ref"] is None
    assert result["reason_code"] == code
    assert result["error"]["stage"] == stage
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("after_commit", [False, True])
def test_prepare_keeps_reference_only_after_commit(
    tmp_path, preparation, monkeypatch, after_commit,
):
    _, _, _, _, config, root = preparation
    real_publish = archive._publish_directory

    def publish(staging, destination):
        if destination.parent == (tmp_path / "output" if after_commit else root):
            raise OSError("private path")
        real_publish(staging, destination)

    monkeypatch.setattr(archive, "_publish_directory", publish)
    run = _run(tmp_path, preparation)
    assert run.result["exit_code"] == 6
    assert run.result["reason_code"] == "ArchivePersistenceError"
    assert "private path" not in run.result["error"]["message"]
    ref = run.result["prepared_ref"]
    if after_commit:
        assert run.directory is None
        assert read_prepared(config, ref)["prepared_id"] == ref["prepared_id"]
    else:
        assert ref is None
        assert list(root.iterdir()) == []


def test_prepare_returns_no_ref_if_parent_sync_fails_after_rename(
    tmp_path, preparation, monkeypatch,
):
    _, _, _, _, _, root = preparation
    real_sync = archive._sync_directory

    def sync(path):
        if path == root:
            assert len(list(root.glob("*/prepared.json"))) == 1
            raise OSError("private path")
        real_sync(path)

    monkeypatch.setattr(archive, "_sync_directory", sync)
    run = _run(tmp_path, preparation)
    assert run.result["prepared_ref"] is None
    assert run.result["exit_code"] == 6
    assert run.result["error"]["code"] == "ArchivePersistenceError"
    assert run.result["error"]["stage"] == "prepared_archive"
    assert "confirm the durability" in run.result["error"]["message"]
    assert "private path" not in run.result["error"]["message"]
    assert read_result(tmp_path, run.output_id) == run


@pytest.mark.parametrize("port", ["encode_prepared", "validate_prepared"])
@pytest.mark.parametrize("structured", [False, True])
def test_prepare_publishes_codec_rejection(tmp_path, preparation, port, structured):
    _, _, _, _, _, root = preparation

    def reject(*_):
        if structured:
            raise PublicError(
                "UnsupportedRuleVersion", stage="benchmark_codec", message="Unknown rule."
            )
        raise ValueError("private content")

    run = _run(tmp_path, preparation, **{port: reject})
    code, stage = (
        ("UnsupportedRuleVersion", "benchmark_codec")
        if structured else ("InvalidRequest", "benchmark_response_validation")
    )
    assert run.result["exit_code"] == 2
    assert run.result["error"]["code"] == code
    assert run.result["error"]["stage"] == stage
    assert "private content" not in run.result["error"]["message"]
    assert run.result["prepared_ref"] is None
    assert list(root.iterdir()) == []
    assert read_result(tmp_path, run.output_id) == run


@pytest.mark.parametrize(
    "port", ["wire_prepare", "prepare_benchmark", "encode_prepared", "validate_prepared"],
)
def test_prepare_rejects_port_error_with_execution_facts(tmp_path, preparation, port):
    _, _, _, _, _, root = preparation
    error = PublicError(
        "InvalidRequest", stage="benchmark", message="private content",
        attempt_id="foreign-attempt", started=True,
    )

    def reject(*_):
        if port == "wire_prepare":
            return error.to_json()
        raise error

    option = "prepare_benchmark" if port == "wire_prepare" else port
    run = _run(tmp_path, preparation, **{option: reject})
    assert run.result["exit_code"] == 2
    assert run.result["prepared_ref"] is None
    actual = run.result["error"]
    assert actual["code"] == "InvalidRequest"
    assert actual["stage"] == "benchmark_response_validation"
    assert actual["attempt_id"] is actual["started"] is None
    assert "private content" not in actual["message"]
    assert list(root.iterdir()) == []
    assert read_result(tmp_path, run.output_id) == run


@pytest.mark.parametrize("root_is_file", [False, True])
def test_prepare_rejects_unusable_archive_root_before_benchmark(
    tmp_path, preparation, root_is_file,
):
    _, _, _, _, _, root = preparation
    root.rmdir()
    if root_is_file:
        root.write_bytes(b"unchanged")

    def benchmark(_):
        pytest.fail("called with an invalid archive root")

    run = _run(tmp_path, preparation, prepare_benchmark=benchmark)
    assert run.result["exit_code"] == 2
    assert run.result["error"]["code"] == "InvalidRequest"
    assert run.result["error"]["stage"] == "storage_config"
    assert run.result["prepared_ref"] is None
    assert str(root) not in run.result["error"]["message"]
    assert read_result(tmp_path, run.output_id) == run


def test_read_rejects_wrong_mount_tampering_and_wrong_prepared_id(tmp_path, preparation):
    _, _, _, _, config, root = preparation
    ref = _run(tmp_path, preparation).result["prepared_ref"]
    for location in ("run-archives/local-other/a", "run-archives/local/../secret",
                     "run-archives/local/.pending-123/prepared.json"):
        with pytest.raises(PublicError, match="UnsafeArtifactPath"):
            read_archive_artifact(config, {**ref["artifact"], "location": location})
    with pytest.raises(PublicError, match="IdentityMismatch"):
        read_prepared(config, {**ref, "prepared_id": "sha256:" + "0" * 64})
    file = next(root.glob("*/prepared.json"))
    file.write_bytes(b"tampered")
    with pytest.raises(PublicError, match="ArtifactIntegrityError"):
        read_prepared(config, ref)


def test_read_rejects_link_to_file_outside_archive(tmp_path, preparation):
    _, _, _, _, config, root = preparation
    data = b"outside"
    outside = tmp_path / "outside"
    outside.write_bytes(data)
    try:
        (root / "link").symlink_to(outside)
    except OSError as error:
        if os.name == "nt" and error.winerror == 1314:
            pytest.skip("creating symlinks requires Windows developer mode or privileges")
        raise
    with pytest.raises(PublicError, match="UnsafeArtifactPath"):
        read_archive_artifact(config, _ref("run-archives/local/link", data, "text/plain"))


@pytest.mark.parametrize("source", ["envelope", "benchmark"])
def test_prepare_publishes_unsupported_versions(tmp_path, preparation, source):
    request, _, _, _, _, root = preparation

    def benchmark(_):
        if source == "envelope":
            pytest.fail("called with unsupported request version")
        raise PublicError(
            "UnsupportedRuleVersion", stage="prepare", message="Unknown task version."
        )

    if source == "envelope":
        request["schema_version"] = 2
    run = _run(tmp_path, preparation, prepare_benchmark=benchmark)
    code = "UnsupportedSchema" if source == "envelope" else "UnsupportedRuleVersion"
    assert run.result["reason_code"] == code
    assert run.result["prepared_ref"] is None
    assert list(root.iterdir()) == []
