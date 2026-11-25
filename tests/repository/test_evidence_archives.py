"""Offline adversarial archives and compatibility with both frozen pilots."""

import copy
import gzip
import hashlib
import io
import json
import tarfile
import urllib.error
from pathlib import Path

import pytest

from tools import evidence_archives as archive
from tools.validate_evidence import budget_assets, validate_inventory
from tools.verify_evidence_archive import main

ROOT = Path(__file__).resolve().parents[2]


def make_tar(path, entries):
    with tarfile.open(path, "w:gz") as target:
        for name, payload, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(payload) if kind == tarfile.REGTYPE else 0
            member.linkname = "../escape" if kind != tarfile.REGTYPE else ""
            target.addfile(member, io.BytesIO(payload))


def identity(path, manifest):
    manifest["archive"]["bytes"] = path.stat().st_size
    manifest["archive"]["sha256"] = archive.sha256(path)


@pytest.fixture
def bundle(tmp_path):
    files = {
        "sample/control.jsonl": b'{"id":"failed","status":"failed"}\n',
        "sample/config.json": b'{"samples":3}\n',
        "sample/recompute.py": b'raise RuntimeError("must never execute")\n',
    }
    path = tmp_path / "sample-v1.tar.gz"
    make_tar(path, [(name, data, tarfile.REGTYPE) for name, data in files.items()])
    manifest = {
        "schema_version": 2,
        "archive": {
            "id": "sample-v1",
            "file": path.name,
            "url": "https://github.com/example/example/releases/download/v1/" + path.name,
            "sha256": "0" * 64,
            "bytes": 1,
            "format": "tar+gzip",
            "retention_owner": "fixture-owner",
            "source_revision": "a" * 40,
            "root": "sample",
            "files": len(files),
            "uncompressed_bytes": sum(map(len, files.values())),
            "key_files": {"control": "sample/control.jsonl", "code": "sample/recompute.py"},
        },
        "verification": {
            "trials": "results/trials.jsonl",
            "summary": "results/summary.json",
            "command": ["python", "validator/recompute.py", "--output", "<new-output>"],
            "absolute_tolerance": 1e-12,
            "relative_tolerance": 0,
            "inputs": [
                {"role": role, "path": name, "sha256": hashlib.sha256(files[name]).hexdigest()}
                for role, name in zip(("control", "configuration", "validator"), files)
            ],
        },
    }
    identity(path, manifest)
    return path, manifest


@pytest.mark.parametrize("campaign,files", [("minicpm-vllm-seedtts", 56), ("h3-image-ascend", 156)])
def test_same_reader_normalizes_frozen_pilots(campaign, files):
    path = ROOT / "evidence" / campaign / "results/artifacts.json"
    original = path.read_bytes()
    normalized = archive.normalize_manifest(archive.read_json(path))
    assert normalized["archive"]["files"] == files
    assert normalized["archive"]["format"] == "tar+gzip"
    assert normalized["archive"]["root"] == campaign
    assert normalized["verification"] is None  # Frozen replay is campaign-specific.
    assert path.read_bytes() == original


def test_conflicting_legacy_aliases_are_rejected():
    manifest = archive.read_json(ROOT / "evidence/h3-image-ascend/results/artifacts.json")
    manifest["archive"]["files"] = manifest["archive"]["original_files"] + 1
    with pytest.raises(archive.VerificationError, match="conflicting files"):
        archive.normalize_manifest(manifest)


@pytest.mark.parametrize(
    "key,value",
    [
        ("bytes", True),
        ("bytes", 0),
        ("sha256", "z" * 64),
        ("retention_owner", " "),
        ("format", "zip"),
        ("file", "../archive.tar.gz"),
        ("source_revision", "main"),
        ("url", "https://user:fake@example.invalid/sample-v1.tar.gz"),
        ("url", "https://example.invalid/sample-v1.tar.gz?fake=secret"),
        ("url", "file:///sample-v1.tar.gz"),
        ("key_files", {}),
    ],
)
def test_bad_metadata_is_rejected(bundle, key, value):
    _, manifest = bundle
    manifest["archive"][key] = value
    with pytest.raises(archive.VerificationError):
        archive.normalize_manifest(manifest)


def test_unknown_version_and_missing_pins_fail(bundle):
    _, manifest = bundle
    manifest["schema_version"] = 3
    with pytest.raises(archive.VerificationError):
        archive.normalize_manifest(manifest)
    manifest["schema_version"] = 2
    manifest["verification"]["inputs"].pop()
    with pytest.raises(archive.VerificationError, match="Pin control"):
        archive.normalize_manifest(manifest)


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version":1,"schema_version":2}')
    with pytest.raises(archive.VerificationError, match="Duplicate JSON"):
        archive.read_json(path)


def test_malformed_gzip_is_a_named_failure(bundle):
    path, manifest = bundle
    path.write_bytes(b"not a gzip stream")
    identity(path, manifest)
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == "invalid_archive"


def test_verified_content_never_executes_or_extracts(bundle, tmp_path):
    path, manifest = bundle
    before = list(tmp_path.iterdir())
    result = archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert result["content"] == "verified"
    assert result["recomputation"] == "not_checked"
    assert result["campaign_verdict"] == "unchanged"
    assert list(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "key,value,code", [("bytes", 1, "bad_bytes"), ("sha256", "0" * 64, "bad_hash")]
)
def test_authenticates_before_parsing(bundle, monkeypatch, key, value, code):
    path, manifest = bundle
    manifest["archive"][key] = value
    monkeypatch.setattr(archive.tarfile, "open", lambda **kw: pytest.fail("parsed before hash"))
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == code


@pytest.mark.parametrize("name", ["/outside", "../outside", "a/../b", "a//b", "a\\b", "C:/file"])
def test_unsafe_paths_rejected(bundle, name):
    path, manifest = bundle
    make_tar(path, [(name, b"x", tarfile.REGTYPE)])
    identity(path, manifest)
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == "unsafe_path"


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE]
)
def test_nonregular_members_rejected(bundle, kind):
    path, manifest = bundle
    make_tar(path, [("sample/link", b"", kind)])
    identity(path, manifest)
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == "unsafe_member"


def test_duplicate_members_rejected(bundle):
    path, manifest = bundle
    make_tar(path, [("sample/a", b"x", tarfile.REGTYPE)] * 2)
    identity(path, manifest)
    with pytest.raises(archive.VerificationError, match="Duplicate archive"):
        archive.verify_archive(path, archive.normalize_manifest(manifest))


@pytest.mark.parametrize(
    "limits",
    [
        archive.Limits(compressed_bytes=1),
        archive.Limits(expanded_bytes=64),
        archive.Limits(members=1),
        archive.Limits(seconds=-1),
    ],
)
def test_resource_limits(bundle, limits):
    path, manifest = bundle
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest), limits)
    assert caught.value.code == "resource_limit"


def test_hidden_tar_metadata_is_bounded(bundle):
    path, manifest = bundle
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as target:
        member = tarfile.TarInfo("sample/a")
        member.pax_headers = {"comment": "x" * 100000}
        target.addfile(member, io.BytesIO(b""))
    identity(path, manifest)
    with pytest.raises(archive.VerificationError, match="Expanded archive limit"):
        archive.verify_archive(
            path, archive.normalize_manifest(manifest), archive.Limits(expanded_bytes=2048)
        )


def test_trailing_compressed_padding_is_bounded(bundle):
    path, manifest = bundle
    path.write_bytes(path.read_bytes() + gzip.compress(b"\0" * 100000))
    identity(path, manifest)
    with pytest.raises(archive.VerificationError, match="Expanded archive limit"):
        archive.verify_archive(
            path, archive.normalize_manifest(manifest), archive.Limits(expanded_bytes=20000)
        )


def test_missing_key_file_and_wrong_input_are_distinct(bundle):
    path, manifest = bundle
    manifest["archive"]["key_files"]["missing"] = "sample/missing"
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == "missing_file"
    del manifest["archive"]["key_files"]["missing"]
    manifest["verification"]["inputs"][0]["sha256"] = "0" * 64
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == "bad_hash"


def test_local_missing_archive_is_unavailable(bundle):
    path, manifest = bundle
    path.unlink()
    with pytest.raises(archive.VerificationError) as caught:
        archive.verify_archive(path, archive.normalize_manifest(manifest))
    assert caught.value.code == "unavailable"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a",
        "https://example.invalid/a",
        "https://user:fake@github.com/a",
        "https://github.com:123/a",
    ],
)
def test_redirects_reject_unsupported_destinations(url):
    with pytest.raises(archive.VerificationError) as caught:
        archive.ReleaseRedirect().redirect_request(None, None, 302, "", {}, url)
    assert caught.value.code == "unsafe_redirect"


@pytest.mark.parametrize(
    "status,code", [(401, "restricted_access"), (403, "restricted_access"), (404, "unavailable")]
)
def test_download_failure_classes(bundle, monkeypatch, tmp_path, status, code):
    _, manifest = bundle

    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError("fixture", status, "fake private details", {}, None)

    monkeypatch.setattr(archive.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(archive.VerificationError) as caught:
        archive.download_archive(archive.normalize_manifest(manifest), tmp_path / "download")
    assert caught.value.code == code
    assert "private details" not in str(caught.value)


def test_controlled_storage_metadata_is_valid_but_never_auto_fetched(bundle, monkeypatch):
    path, manifest = bundle
    manifest["archive"]["url"] = "https://storage.example.invalid/" + path.name
    normalized = archive.normalize_manifest(manifest)
    monkeypatch.setattr(
        archive.urllib.request, "build_opener", lambda *args: pytest.fail("network")
    )
    assert archive.verify_archive(path, normalized)["content"] == "verified"
    with pytest.raises(archive.VerificationError) as caught:
        archive.download_archive(normalized, path.parent / "download")
    assert caught.value.code == "restricted_access"


def trial_rows():
    return [
        {
            "id": str(i),
            "configuration": {"batch": 1},
            "status": status,
            "conclusion": "INCONCLUSIVE",
            "artifact_id": "sample-v1",
            "source_record": "control.jsonl#" + str(i),
        }
        for i, status in enumerate(("failed", "interrupted", "measured"))
    ]


def results(root, rows=None, summary=None):
    (root / "results").mkdir(parents=True)
    (root / "results/trials.jsonl").write_text(
        "\n".join(json.dumps(row) for row in (rows if rows is not None else trial_rows())) + "\n"
    )
    (root / "results/summary.json").write_text(json.dumps(summary or {"n": 3, "median": 1.0}))


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("omit", "trial_mismatch"),
        ("duplicate", "trial_mismatch"),
        ("status", "trial_mismatch"),
        ("summary", "recompute_mismatch"),
    ],
)
def test_replay_catches_missing_failed_trials_and_wrong_summary(bundle, tmp_path, mutation, code):
    _, manifest = bundle
    retained, generated = tmp_path / "retained", tmp_path / "generated"
    rows = trial_rows()
    if mutation == "omit":
        rows.pop(0)
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "status":
        rows[0]["status"] = "measured"
    results(retained)
    results(generated, rows, {"n": 3, "median": 2.0} if mutation == "summary" else None)
    with pytest.raises(archive.VerificationError) as caught:
        archive.compare_results(archive.normalize_manifest(manifest), retained, generated)
    assert caught.value.code == code


def test_replay_ignores_row_order_and_allows_only_frozen_float_tolerance(bundle, tmp_path):
    _, manifest = bundle
    retained, generated = tmp_path / "retained", tmp_path / "generated"
    results(retained)
    results(generated, list(reversed(trial_rows())), {"n": 3, "median": 1.0 + 1e-13})
    result = archive.compare_results(archive.normalize_manifest(manifest), retained, generated)
    assert result == {"recomputation": "outputs_match", "trials": 3}
    for a, b in [(1, 1.0), (True, 1), (float("nan"), float("nan")), (1, 2)]:
        assert not archive.compare_values(a, b, 10, 10)


def test_cli_default_is_offline_and_local_verification_reports_scope(bundle, monkeypatch, capsys):
    path, manifest = bundle
    source = path.parent / "artifacts.json"
    source.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        archive.urllib.request, "build_opener", lambda *args: pytest.fail("network")
    )
    assert main([str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["content"] == "not_checked"
    assert main([str(source), "--archive", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["recomputation"] == "not_checked"
    path.write_bytes(b"tampered")
    assert main([str(source), "--archive", str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "bad_bytes"


def test_cli_compares_replay_and_classifies_missing_output(bundle, tmp_path, capsys):
    path, manifest = bundle
    retained, generated = tmp_path / "retained", tmp_path / "generated"
    results(retained)
    results(generated)
    source = retained / "results/artifacts.json"
    source.write_text(json.dumps(manifest))
    args = [str(source), "--archive", str(path), "--recomputed", str(generated)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["recomputation"] == "outputs_match"
    (generated / "results/summary.json").unlink()
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "missing_file"


def test_replay_rejects_output_symlink_escape(bundle, tmp_path):
    _, manifest = bundle
    retained, generated = tmp_path / "retained", tmp_path / "generated"
    results(retained)
    results(generated)
    target = generated / "results/summary.json"
    target.unlink()
    try:
        target.symlink_to(retained / "results/summary.json")
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(archive.VerificationError) as caught:
        archive.compare_results(archive.normalize_manifest(manifest), retained, generated)
    assert caught.value.code == "unsafe_path"


def test_inventory_format_validation_and_budget_projection_are_offline(monkeypatch):
    monkeypatch.setattr(
        archive.urllib.request, "build_opener", lambda *args: pytest.fail("network")
    )
    report = validate_inventory(ROOT)
    assert not report["errors"]
    assert report["unavailable"]
    view = budget_assets(ROOT)
    assert set(view["bundles"]) == {
        "minicpm-vllm-seedtts", "h3-image-ascend",
        "h3-ref2va-910c-4logical-20261101-297", "qwen38-h20-fp8-single-request-vllm032",
    }
    for campaign, value in view["bundles"].items():
        original = archive.read_json(ROOT / "evidence" / campaign / "results/artifacts.json")
        (asset,) = value["external_assets"]
        assert asset == {key: original["archive"][key] for key in asset}


def test_inventory_rejects_duplicate_archive_authority(bundle, tmp_path):
    _, manifest = bundle
    campaign = tmp_path / "evidence/synthetic"
    for segment in ("plan", "results", "patch", "validator"):
        (campaign / segment).mkdir(parents=True)
    (campaign / "results/artifacts.json").write_text(json.dumps(manifest))
    entry = {
        "kind": "campaign",
        "manifests": [
            {
                "path": "results/artifacts.json",
                "schema": "archive-sha256",
                "field": "archive",
                "artifact": "results/sample-v1.tar.gz",
            }
        ],
    }
    inventory = tmp_path / "tools/evidence_inventory.json"
    inventory.parent.mkdir()
    inventory.write_text(json.dumps({"version": 1, "bundles": {"synthetic": entry}}))
    assert not validate_inventory(tmp_path)["errors"]
    entry["external_assets"] = [copy.deepcopy(manifest["archive"])]
    inventory.write_text(json.dumps({"version": 1, "bundles": {"synthetic": entry}}))
    assert "duplicates authoritative" in str(validate_inventory(tmp_path)["errors"])
