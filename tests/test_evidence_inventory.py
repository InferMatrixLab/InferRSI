"""Structural and digest checks do not grant campaign acceptance."""

import hashlib
import json
from pathlib import Path

import pytest

from tools.validate_evidence import SEGMENTS, validate_inventory


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "evidence/synthetic"
    for part in SEGMENTS:
        (root / part).mkdir(parents=True)
    payload = root / "validator/check.py"
    payload.write_bytes(b"# synthetic frozen validator\r\n")
    write_json(root / "plan/freeze.json", {
        "validator/check.py": hashlib.sha256(payload.read_bytes()).hexdigest(),
    })
    inventory = {"version": 1, "bundles": {"synthetic": {
        "kind": "campaign",
        "manifests": [{"path": "plan/freeze.json", "schema": "bundle-sha256"}],
    }}}
    write_json(tmp_path / "tools/evidence_inventory.json", inventory)
    return tmp_path, root, inventory


def test_hash_validation_is_read_only(bundle):
    repo, root, _ = bundle
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = validate_inventory(repo)
    assert result["errors"] == []
    assert result["checked_hashes"] == 1
    assert "verdict" not in result
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_missing_segment_fails(bundle):
    repo, root, _ = bundle
    (root / "results").rmdir()
    assert "missing required results" in str(validate_inventory(repo)["errors"])


@pytest.mark.parametrize("manifest", [[], {}, {"validator/check.py": "bad"}])
def test_malformed_manifest_fails(bundle, manifest):
    repo, root, _ = bundle
    write_json(root / "plan/freeze.json", manifest)
    assert validate_inventory(repo)["errors"]


def test_invalid_json_fails(bundle):
    repo, root, _ = bundle
    (root / "plan/freeze.json").write_text("{", encoding="utf-8")
    assert validate_inventory(repo)["errors"]


def test_changed_hashed_file_fails(bundle):
    repo, root, _ = bundle
    (root / "validator/check.py").write_bytes(b"# changed\n")
    assert "SHA-256 mismatch" in str(validate_inventory(repo)["errors"])


@pytest.mark.parametrize("path", ["../outside", "/outside", "C:/outside", "..\\outside", "a/../b"])
def test_unsafe_manifest_path_fails(bundle, path):
    repo, root, _ = bundle
    write_json(root / "plan/freeze.json", {path: "0" * 64})
    assert "unsafe relative path" in str(validate_inventory(repo)["errors"])


def test_escaping_symlink_fails(bundle):
    repo, root, _ = bundle
    outside = repo / "outside"
    outside.write_bytes(b"secret fixture")
    link = root / "validator/check.py"
    link.unlink()
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert "escapes" in str(validate_inventory(repo)["errors"])


def test_unknown_bundle_or_manifest_requires_classification(bundle):
    repo, root, _ = bundle
    (repo / "evidence/new-bundle").mkdir()
    write_json(root / "results/new-manifest.json", {})
    errors = str(validate_inventory(repo)["errors"])
    assert "inventory directories differ" in errors
    assert "unclassified manifest" in errors


def test_historical_mapping_uses_frozen_file_not_current_code(bundle):
    repo, root, inventory = bundle
    digest = hashlib.sha256(b"frozen").hexdigest()
    write_json(root / "plan/freeze.json", {"old.py": digest, "external.py": "0" * 64})
    (repo / "snapshot.py").write_bytes(b"frozen")
    (repo / "old.py").write_bytes(b"current implementation")
    inventory["bundles"]["synthetic"]["manifests"] = [{
        "path": "plan/freeze.json", "schema": "historical-sha256", "files": {
            "old.py": {"local": "snapshot.py"},
            "external.py": {"external": "original source bundle required"},
        },
    }]
    write_json(repo / "tools/evidence_inventory.json", inventory)
    result = validate_inventory(repo)
    assert result["errors"] == []
    assert result["checked_hashes"] == 1
    assert len(result["unavailable"]) == 1
    del inventory["bundles"]["synthetic"]["manifests"][0]["files"]["external.py"]
    write_json(repo / "tools/evidence_inventory.json", inventory)
    assert validate_inventory(repo)["errors"]


def test_external_archive_is_explicit_then_verified_when_available(bundle):
    repo, root, inventory = bundle
    payload = b"archive bytes"
    write_json(root / "plan/freeze.json", {
        "archive": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
    })
    inventory["bundles"]["synthetic"]["manifests"] = [{
        "path": "plan/freeze.json", "schema": "archive-sha256", "field": "archive",
        "artifact": "results/archive.tar.gz",
    }]
    write_json(repo / "tools/evidence_inventory.json", inventory)
    result = validate_inventory(repo)
    assert not result["errors"] and len(result["unavailable"]) == 1
    assert result["checked_hashes"] == 0
    archive = root / "results/archive.tar.gz"
    archive.write_bytes(payload)
    result = validate_inventory(repo)
    assert not result["errors"] and not result["unavailable"]
    assert result["checked_hashes"] == 1
    archive.write_bytes(b"changed")
    assert validate_inventory(repo)["errors"]


def test_metadata_manifest_checks_retained_bytes_not_external_payloads(bundle):
    repo, root, inventory = bundle
    path = root / "plan/freeze.json"
    write_json(path, {
        "model": {"revision": "source revision", "files": [{
            "path": "<PRIVATE_MODEL_ROOT>/weights.bin", "sha256": "0" * 64,
        }]},
        "availability": "External payloads are not included",
    })
    inventory["bundles"]["synthetic"]["manifests"] = [{
        "path": "plan/freeze.json", "schema": "metadata-sha256",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }]
    write_json(repo / "tools/evidence_inventory.json", inventory)
    before = path.read_bytes()
    report = validate_inventory(repo)
    assert report["errors"] == []
    assert report["checked_hashes"] == 1
    assert path.read_bytes() == before
    assert "verdict" not in report
    # Even a formatting-only change invalidates the recorded byte digest.
    path.write_bytes(before + b"\n")
    assert "SHA-256 mismatch" in str(validate_inventory(repo)["errors"])


@pytest.mark.parametrize("value,digest", [([], "0" * 64), ({}, "bad"), ({}, None)])
def test_metadata_manifest_rejects_invalid_structure_or_digest(bundle, value, digest):
    repo, root, inventory = bundle
    write_json(root / "plan/freeze.json", value)
    entry = {"path": "plan/freeze.json", "schema": "metadata-sha256"}
    if digest is not None:
        entry["sha256"] = digest
    inventory["bundles"]["synthetic"]["manifests"] = [entry]
    write_json(repo / "tools/evidence_inventory.json", inventory)
    assert validate_inventory(repo)["errors"]


def test_checked_in_inventory():
    repo = Path(__file__).resolve().parents[1]
    result = validate_inventory(repo)
    assert result["errors"] == []
    assert len(result["bundles"]) == 9
    assert result["checked_hashes"] == 134
    assert result["unavailable"]  # Historical raw artifacts are not in this checkout.
