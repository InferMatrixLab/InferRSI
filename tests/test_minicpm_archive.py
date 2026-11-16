"""Small synthetic archives exercise the pilot's integrity and extraction boundary."""

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "evidence/minicpm-vllm-seedtts/validator"


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(VALIDATOR))
    spec = importlib.util.spec_from_file_location(
        "minicpm_archive_verifier", VALIDATOR / "verify_archive.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_archive(tmp_path, members):
    path = tmp_path / "fixture.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(content) if kind == tarfile.REGTYPE else 0
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = "../../escape"
            archive.addfile(info, io.BytesIO(content))
    artifact = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "root": "minicpm-vllm-seedtts",
        "files": len(members),
        "uncompressed_bytes": sum(len(data) for _, data, _ in members),
    }
    return path, artifact


def test_regular_archive(verifier, tmp_path):
    path, artifact = make_archive(
        tmp_path, [("minicpm-vllm-seedtts/results/data.json", b"{}", tarfile.REGTYPE)]
    )
    verifier.verify_bytes(path, artifact)
    root = verifier.extract(path, tmp_path / "extract", artifact)
    assert (root / "results/data.json").read_bytes() == b"{}"


@pytest.mark.parametrize(
    "name",
    [
        "/absolute",
        "minicpm-vllm-seedtts/../escape",
        "minicpm-vllm-seedtts/./file",
        "minicpm-vllm-seedtts//file",
        "minicpm-vllm-seedtts/..\\escape",
        "C:/file",
        "wrong/file",
    ],
)
def test_unsafe_paths_rejected(verifier, tmp_path, name):
    path, artifact = make_archive(tmp_path, [(name, b"x", tarfile.REGTYPE)])
    with pytest.raises(ValueError, match="unsafe archive path"):
        verifier.extract(path, tmp_path / "extract", artifact)
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_links_and_special_files_rejected(verifier, tmp_path, kind):
    path, artifact = make_archive(tmp_path, [("minicpm-vllm-seedtts/link", b"", kind)])
    with pytest.raises(ValueError, match="non-regular"):
        verifier.extract(path, tmp_path / "extract", artifact)


def test_duplicate_member_rejected(verifier, tmp_path):
    entry = ("minicpm-vllm-seedtts/file", b"x", tarfile.REGTYPE)
    path, artifact = make_archive(tmp_path, [entry, entry])
    with pytest.raises(ValueError, match="duplicate"):
        verifier.extract(path, tmp_path / "extract", artifact)


@pytest.mark.parametrize("field", ["bytes", "sha256"])
def test_archive_integrity_rejected(verifier, tmp_path, field):
    path, artifact = make_archive(tmp_path, [("minicpm-vllm-seedtts/file", b"x", tarfile.REGTYPE)])
    artifact[field] = 1 if field == "bytes" else "0" * 64
    with pytest.raises(ValueError, match="mismatch"):
        verifier.verify_bytes(path, artifact)


@pytest.mark.parametrize("field", ["files", "uncompressed_bytes"])
def test_declared_expansion_limit_rejected(verifier, tmp_path, field):
    path, artifact = make_archive(tmp_path, [("minicpm-vllm-seedtts/file", b"xx", tarfile.REGTYPE)])
    artifact[field] = 0
    with pytest.raises(ValueError, match="limit exceeded"):
        verifier.extract(path, tmp_path / "extract", artifact)


def test_extraction_time_limit(verifier, tmp_path, monkeypatch):
    path, artifact = make_archive(tmp_path, [("minicpm-vllm-seedtts/file", b"x", tarfile.REGTYPE)])
    ticks = iter([0, 100])
    monkeypatch.setattr(verifier.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ValueError, match="time limit"):
        verifier.extract(path, tmp_path / "extract", artifact)


def test_tar_headers_and_padding_count_toward_limit(verifier, tmp_path, monkeypatch):
    path, artifact = make_archive(tmp_path, [("minicpm-vllm-seedtts/file", b"x", tarfile.REGTYPE)])
    monkeypatch.setattr(verifier, "MAX_TAR_BYTES", 100)
    with pytest.raises(ValueError, match="expanded archive limit"):
        verifier.extract(path, tmp_path / "extract", artifact)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/file",
        "https://example.com/file",
        "https://github.com@example.com/file",
        "file:///tmp/file",
        "https://github.com:8443/file",
    ],
)
def test_unsafe_redirect_rejected(verifier, url):
    assert not verifier.allowed_download(url)
    with pytest.raises(ValueError, match="unsafe download redirect"):
        verifier.ReleaseRedirect().redirect_request(None, None, 302, "", {}, url)


def test_missing_file_detected(verifier, tmp_path):
    root = tmp_path / "snapshot"
    (root / "results").mkdir(parents=True)
    path = root / "results/publication-integrity.json"
    path.write_text(json.dumps({"results/missing.json": "0" * 64}))
    with pytest.raises(ValueError, match="file set mismatch"):
        verifier.verify_snapshot(root, {"publication_integrity_sha256": verifier.sha(path)})


def test_manifest_is_single_authority(verifier):
    data = verifier.metadata(VALIDATOR.parent / "results/artifacts.json")
    inventory = json.loads((ROOT / "tools/evidence_inventory.json").read_text())
    entry = inventory["bundles"]["minicpm-vllm-seedtts"]
    archive = next(x for x in entry["manifests"] if x["schema"] == "archive-sha256")
    assert archive["path"] == "results/artifacts.json" and archive["field"] == "archive"
    assert Path(archive["artifact"]).name == data["archive"]["file"]
    assert "external_assets" not in entry


@pytest.mark.parametrize(
    "actual,expected",
    [
        (1, 2),
        (1.01, 1.0),
        (True, 1),
        ([{"trial_id": "a"}], [{"trial_id": "b"}]),
        ([], [{"trial_id": "a"}]),
        (float("nan"), 1.0),
    ],
)
def test_missing_trials_and_changed_summaries_fail(verifier, actual, expected):
    with pytest.raises(ValueError, match="mismatch"):
        verifier.same(actual, expected)


def test_declared_float_tolerance(verifier):
    verifier.same(1.0 + 1e-13, 1.0)


@pytest.mark.parametrize("status", [403, 404])
def test_unavailable_download_is_reported_separately(verifier, monkeypatch, capsys, status):
    from urllib.error import HTTPError

    def unavailable(*args):
        raise HTTPError("https://github.com/fixture", status, "unavailable", {}, None)

    monkeypatch.setattr(verifier.sys, "argv", ["verify_archive.py", "--download"])
    monkeypatch.setattr(verifier, "download", unavailable)
    assert verifier.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "download" and result["campaign_verdict"] == "unchanged"


def test_size_mismatch_fails_before_extraction(verifier, tmp_path, monkeypatch, capsys):
    path = tmp_path / "wrong.tar.gz"
    path.write_bytes(b"wrong")
    monkeypatch.setattr(verifier.sys, "argv", ["verify_archive.py", "--archive", str(path)])
    assert verifier.main() == 1
    assert json.loads(capsys.readouterr().out)["stage"] == "archive_bytes"
