"""Public archive safety and evidence reconstruction, without network or hardware."""

import gzip
import importlib.util
import io
import json
import tarfile
import urllib.error
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "evidence/h3-image-ascend/validator/archive.py"
spec = importlib.util.spec_from_file_location("h3_evidence_archive", MODULE)
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def package(tmp_path, entries, snapshot=None):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(data) if kind == tarfile.REGTYPE else 0
            member.linkname = "../../outside" if kind != tarfile.REGTYPE else ""
            tar.addfile(member, io.BytesIO(data))
    path = tmp_path / "archive.tar.gz"
    payload = gzip.compress(buffer.getvalue(), mtime=0)
    path.write_bytes(payload)
    manifest = {
        "source_revision": "a" * 40,
        "retained_files": "retained.json",
        "archive": {
            "bytes": len(payload),
            "sha256": archive.digest(payload),
            "original_files": 0,
            "original_bytes": 0,
        },
    }
    if snapshot:
        manifest["archive"]["original_files"] = len(snapshot["files"])
        manifest["archive"]["original_bytes"] = sum(x["bytes"] for x in snapshot["files"].values())
    return path, manifest


@pytest.fixture
def frozen(tmp_path):
    files = {
        "results/probe.json": b'[{"tokens": 8, "exact": false}]\n',
        "plan/config.json": b'{"steps": 6}\n',
    }
    files["export-manifest.json"] = json.dumps(
        {k: archive.digest(v) for k, v in files.items()}
    ).encode()
    snapshot = {
        "source_revision": "a" * 40,
        "files": {k: {"bytes": len(v), "sha256": archive.digest(v)} for k, v in files.items()},
    }
    entries = [(archive.PREFIX + k, v, tarfile.REGTYPE) for k, v in files.items()]
    entries.append(("snapshot.json", json.dumps(snapshot).encode(), tarfile.REGTYPE))
    path, manifest = package(tmp_path, entries, snapshot)
    return path, manifest, files


def test_frozen_bytes_verified_without_extracting(frozen, tmp_path):
    path, manifest, files = frozen
    assert archive.read_archive(path, manifest) == files
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("bytes", 1, "byte_count_mismatch"),
        ("sha256", "0" * 64, "sha256_mismatch"),
    ],
)
def test_authenticate_before_tar_parsing(frozen, monkeypatch, field, value, error):
    path, manifest, _ = frozen
    manifest["archive"][field] = value
    monkeypatch.setattr(
        archive.tarfile, "open", lambda **kw: pytest.fail("parsed unauthenticated tar")
    )
    with pytest.raises(archive.VerificationError, match=error):
        archive.read_archive(path, manifest)


@pytest.mark.parametrize("name", ["/outside", "../outside", "a/../b", "a\\b", "C:/outside"])
def test_reject_unsafe_paths(tmp_path, name):
    path, manifest = package(tmp_path, [(name, b"x", tarfile.REGTYPE)])
    with pytest.raises(archive.VerificationError, match="unsafe_archive_path"):
        archive.read_archive(path, manifest)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE])
def test_reject_links_and_devices(tmp_path, kind):
    path, manifest = package(tmp_path, [("link", b"", kind)])
    with pytest.raises(archive.VerificationError, match="unsupported_archive_member"):
        archive.read_archive(path, manifest)


def test_reject_duplicate_members(tmp_path):
    path, manifest = package(tmp_path, [("a", b"x", tarfile.REGTYPE)] * 2)
    with pytest.raises(archive.VerificationError, match="duplicate_archive_member"):
        archive.read_archive(path, manifest)


@pytest.mark.parametrize(
    "limit,value,error",
    [
        ("MAX_MEMBERS", 1, "archive_member_limit"),
        ("MAX_EXPANDED", 64, "archive_expansion_limit"),
        ("MAX_SECONDS", -1, "archive_time_limit"),
    ],
)
def test_resource_limits(frozen, monkeypatch, limit, value, error):
    monkeypatch.setattr(archive, limit, value)
    with pytest.raises(archive.VerificationError, match=error):
        archive.read_archive(*frozen[:2])


def test_missing_original_is_a_gap_even_with_valid_archive_hash(frozen, tmp_path):
    _, _, files = frozen
    snapshot = {
        "source_revision": "a" * 40,
        "files": {k: {"bytes": len(v), "sha256": archive.digest(v)} for k, v in files.items()},
    }
    path, manifest = package(
        tmp_path,
        [
            ("snapshot.json", json.dumps(snapshot).encode(), tarfile.REGTYPE),
        ],
        snapshot,
    )
    with pytest.raises(archive.VerificationError, match="file_coverage_mismatch"):
        archive.read_archive(path, manifest)


def test_repeated_cases_failures_and_omissions_are_distinct(tmp_path):
    files = {
        "results/probes.json": json.dumps(
            {
                "cases": [{"tokens": 8, "exact": False}] * 2,
                "failed_attempts": [{"reason": "synthetic backend failure"}],
            }
        ).encode()
    }
    manifest = {"source_revision": "a" * 40, "retained_files": "retained.json"}
    (tmp_path / "results").mkdir()
    (tmp_path / "retained.json").write_text("{}")
    archive.verify_views(files, manifest, tmp_path, write=True)
    index = tmp_path / "results/trials.jsonl"
    rows = [json.loads(line) for line in index.read_text().splitlines()]
    assert len({row["id"] for row in rows}) == 3
    assert rows[-1]["status"] == "execution_error"
    index.write_text("\n".join(index.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(archive.VerificationError, match="trial_coverage_or_content_mismatch"):
        archive.verify_views(files, manifest, tmp_path)


def test_recompute_summary_rejects_changed_median_and_preserves_spread(tmp_path):
    files = {
        "results/trial.json": json.dumps(
            {
                "latency": {
                    "candidate": {
                        "W1": {
                            "samples_s": [4.0, 1.0, 3.0],
                            "median_s": 3.0,
                            "target_s": 2.0,
                            "target_met": False,
                        }
                    }
                }
            }
        ).encode()
    }
    manifest = {"source_revision": "a" * 40, "retained_files": "retained.json"}
    (tmp_path / "results").mkdir()
    (tmp_path / "retained.json").write_text("{}")
    archive.verify_views(files, manifest, tmp_path, write=True)
    path = tmp_path / "results/summary.json"
    summary = json.loads(path.read_text())
    metric = summary["groups"]["trial"]["http_seconds"]["/latency/candidate/W1"]
    assert (metric["n"], metric["min"], metric["median"], metric["max"]) == (3, 1.0, 3.0, 4.0)
    metric["median"] = 1.0
    path.write_text(json.dumps(summary))
    with pytest.raises(archive.VerificationError, match="summary_recomputation_mismatch"):
        archive.verify_views(files, manifest, tmp_path)


@pytest.mark.parametrize("code,reason", [(403, "restricted_access"), (404, "archive_unavailable")])
def test_download_access_failures_are_not_success(tmp_path, monkeypatch, code, reason):
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError("https://example.com", code, "synthetic", None, None)

    monkeypatch.setattr(archive.urllib.request, "build_opener", lambda *args: Opener())
    manifest = {
        "archive": {
            "url": "https://github.com/InferMatrixLab/InferRSI/releases/download/example/archive.tar.gz",
            "bytes": 10,
        }
    }
    with pytest.raises(archive.VerificationError, match=reason):
        archive.download(manifest, tmp_path / "download")


def test_redirect_cannot_downgrade_tls():
    with pytest.raises(archive.VerificationError, match="non_https_redirect"):
        archive.HTTPSRedirects().redirect_request(None, None, 302, "", {}, "http://example.com")
