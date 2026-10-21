"""Offline intake contract checks using synthetic local files and API responses."""

import hashlib
import io
import json

import pytest

from examples.qwen38_text import intake, trial

REVISION = "a" * 40


def sibling(path):
    content = path.read_bytes()
    record = {"rfilename": path.name, "size": len(content)}
    if path.suffix == ".safetensors":
        record["lfs"] = {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    else:
        record["blobId"] = hashlib.sha1(
            f"blob {len(content)}\0".encode() + content,
        ).hexdigest()
    return record


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    root = tmp_path / "model"
    root.mkdir()
    config = {
        "model_type": "qwen3_5",
        "architectures": ["Qwen3_5ForConditionalGeneration"],
        "text_config": {"model_type": "qwen3_5_text", "dtype": "bfloat16"},
    }
    files = {
        "config.json": config,
        "tokenizer.json": {},
        "tokenizer_config.json": {},
        "model.safetensors.index.json": {
            "weight_map": {"a": "part.safetensors", "b": "part.safetensors"}
        },
    }
    for name, value in files.items():
        (root / name).write_text(json.dumps(value))
    (root / "part.safetensors").write_bytes(b"synthetic weights")
    response = {
        "id": trial.MODEL_ID,
        "sha": REVISION,
        "siblings": [sibling(path) for path in sorted(root.iterdir())],
    }
    monkeypatch.setattr(intake, "fetch_metadata", lambda revision: (response, {"source": "test"}))
    return root, response, tmp_path / "manifest.json"


def test_public_identity_manifest_and_single_weight_pass(snapshot, monkeypatch):
    root, _response, output = snapshot
    calls = []
    authenticate = intake.authenticate_file

    def record_call(*args, **kwargs):
        calls.append(args[1])
        return authenticate(*args, **kwargs)

    monkeypatch.setattr(intake, "authenticate_file", record_call)
    result = intake.create_manifest(root, REVISION, output)
    assert result == json.loads(output.read_text())
    assert result["revision"] == REVISION and result["model_id"] == trial.MODEL_ID
    assert calls.count("part.safetensors") == 1
    assert trial.verify_manifest(root, output, REVISION) == trial.sha256_file(output)
    assert str(root) not in output.read_text()


@pytest.mark.parametrize("name", ["part.safetensors", "tokenizer.json"])
def test_same_length_tamper_fails(snapshot, name):
    root, _response, output = snapshot
    path = root / name
    original = path.read_bytes()
    path.write_bytes(b"X" + original[1:])
    with pytest.raises(ValueError, match="differs"):
        intake.create_manifest(root, REVISION, output)
    assert not output.exists()


def test_missing_local_shard_fails(snapshot):
    root, _response, output = snapshot
    (root / "part.safetensors").unlink()
    with pytest.raises(FileNotFoundError):
        intake.create_manifest(root, REVISION, output)
    assert not output.exists()


def test_missing_remote_shard_metadata_fails(snapshot):
    root, response, output = snapshot
    response["siblings"] = [
        r for r in response["siblings"] if not r["rfilename"].endswith("safetensors")
    ]
    with pytest.raises(ValueError, match="missing"):
        intake.create_manifest(root, REVISION, output)


def test_revision_mismatch_fails(snapshot):
    root, response, output = snapshot
    response["sha"] = "b" * 40
    with pytest.raises(ValueError, match="identity"):
        intake.create_manifest(root, REVISION, output)


def test_metadata_available_upstream_must_exist_locally(snapshot):
    root, response, output = snapshot
    extra = root / "added_tokens.json"
    extra.write_text("{}")
    response["siblings"].append(sibling(extra))
    extra.unlink()
    with pytest.raises(FileNotFoundError):
        intake.create_manifest(root, REVISION, output)


def test_output_is_exclusive_and_outside_model(snapshot, tmp_path):
    root, _response, output = snapshot
    with pytest.raises(ValueError, match="outside"):
        intake.create_manifest(root, REVISION, root / "manifest.json")
    output.write_text("keep existing")
    with pytest.raises(ValueError, match="new file"):
        intake.create_manifest(root, REVISION, output)
    assert output.read_text() == "keep existing"
    alias = tmp_path / "model-alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        intake.create_manifest(root, REVISION, alias / "manifest.json")
    output.unlink()
    output.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="new file"):
        intake.create_manifest(root, REVISION, output)


def test_model_symlink_escape_rejected(snapshot, tmp_path):
    root, _response, output = snapshot
    path = root / "part.safetensors"
    outside = tmp_path / "outside.safetensors"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        intake.create_manifest(root, REVISION, output)


def test_authenticated_index_cannot_use_traversal(snapshot):
    root, response, output = snapshot
    index = root / "model.safetensors.index.json"
    index.write_text(json.dumps({"weight_map": {"a": "../part.safetensors"}}))
    response["siblings"] = [
        sibling(index) if r["rfilename"] == index.name else r for r in response["siblings"]
    ]
    response["siblings"].append(
        {"rfilename": "../part.safetensors", "size": 1, "lfs": {"size": 1, "sha256": "b" * 64}}
    )
    with pytest.raises(ValueError, match="relative"):
        intake.create_manifest(root, REVISION, output)


class Response(io.BytesIO):
    def geturl(self):
        return "https://huggingface.co/api/models/Qwen/Qwen3.8-27B"


def test_fetch_immutable_endpoint_and_bounded_response(monkeypatch):
    body = json.dumps({"id": trial.MODEL_ID, "sha": REVISION}).encode()

    def open_response(request, *, timeout):
        assert request.full_url.endswith(f"/revision/{REVISION}?blobs=true")
        assert timeout == 30
        return Response(body)

    monkeypatch.setattr(intake.urllib.request, "urlopen", open_response)
    metadata, provenance = intake.fetch_metadata(REVISION)
    assert metadata["sha"] == REVISION
    assert provenance["response_sha256"] == hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(intake, "MAX_METADATA_BYTES", 2)
    with pytest.raises(ValueError, match="limit"):
        intake.fetch_metadata(REVISION)


@pytest.mark.parametrize("revision", ["main", "a" * 39, "../bad", "A" * 40])
def test_revision_validation_precedes_network(revision, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network must not be called")

    monkeypatch.setattr(intake.urllib.request, "urlopen", forbidden)
    with pytest.raises(ValueError, match="immutable"):
        intake.fetch_metadata(revision)
