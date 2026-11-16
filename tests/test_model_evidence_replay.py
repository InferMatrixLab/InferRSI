"""Record-preserving compaction: failures, revisions, source identity and replay."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from tools import evidence_archives as archive
from tools import rebuild_model_evidence as replay


def encoded(value):
    return json.dumps(value).encode()


def test_repeated_observations_merge_without_erasing_revisions_or_retries():
    failed = {"trial": "first-attempt", "status": "failed"}
    changed = {**failed, "reason": "missing output"}
    retry = {"trial": "second-attempt", "status": "completed"}
    originals = {
        "results/early.json": encoded({"runs": [failed]}),
        "results/later.json": encoded({"runs": [failed, changed, retry]}),
        "results/anonymous-a.json": encoded({"status": "interrupted"}),
        "results/anonymous-b.json": encoded({"status": "interrupted"}),
    }
    rows, sources = replay.build_index(
        originals, {"campaign": "synthetic", "configuration": [], "integrity_manifests": []},
        "synthetic-v1",
    )
    attempts = [row for row in rows if row["kind"] == "attempt_observation"]
    assert len(attempts) == 3
    repeated = next(row for row in attempts if len(row["source_records"]) == 2)
    assert repeated["status"] == "failed"
    assert repeated["source_records"] == [
        "synthetic/results/early.json#/runs/0", "synthetic/results/later.json#/runs/0",
    ]
    assert sum(row["status"] == "interrupted" for row in rows) == 2
    assert set(sources) == set(originals)


def test_nested_cancelled_and_pending_jobs_remain_explicit():
    data = {"gpu_attempts": [{"job": 1, "state": "CANCELLED"},
                             {"job": 2, "state": "PENDING"},
                             {"status": "failed", "reason": "submission failed"}]}
    rows, _ = replay.build_index(
        {"results/jobs.json": encoded(data)},
        {"campaign": "synthetic", "configuration": [], "integrity_manifests": []}, "v1",
    )
    assert {row["status"] for row in rows} == {"recorded", "CANCELLED", "PENDING", "failed"}
    assert all(row["conclusion"].startswith("INCONCLUSIVE") for row in rows)


@pytest.fixture
def frozen(tmp_path):
    originals = {
        "plan/config.json": encoded({"repetitions": 3}),
        "results/control.json": encoded({"trial": "attempt", "status": "failed",
                                         "campaign_verdict": "INCONCLUSIVE", "samples": [1, 2, 9]}),
        "validator/check.py": b'raise RuntimeError("never execute")\n',
    }
    originals["plan/frozen.json"] = encoded({
        "validator/check.py": hashlib.sha256(originals["validator/check.py"]).hexdigest(),
    })
    projection = {
        "campaign": "synthetic", "configuration": ["plan/config.json"],
        "integrity_manifests": ["plan/frozen.json"],
        "verdict": {"path": "results/control.json", "pointer": "/campaign_verdict"},
        "metrics": [{"name": "latency", "path": "results/control.json", "pointer": "/samples"}],
        "recorded_results": [], "limitations": ["synthetic recorded observations only"],
    }
    snapshot = {"source_revision": "a" * 40,
                "files": {p: hashlib.sha256(data).hexdigest() for p, data in originals.items()}}
    members = {"synthetic/" + p: data for p, data in originals.items()}
    members.update({"snapshot.json": encoded(snapshot),
                    "replay/projection.json": encoded(projection)})
    for module in (archive, replay):
        path = Path(module.__file__)
        members["replay/" + path.name] = path.read_bytes()

    def pack():
        path = tmp_path / "synthetic-v1.tar.gz"
        with tarfile.open(path, "w:gz") as target:
            for name, payload in members.items():
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                target.addfile(member, io.BytesIO(payload))
        original_names = [name for name in members if name.startswith("synthetic/")]
        manifest = {
            "schema_version": 2,
            "archive": {
                "id": "synthetic-v1", "file": path.name,
                "url": "https://example.invalid/" + path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size, "format": "tar+gzip",
                "retention_owner": "fixture", "source_revision": "a" * 40,
                "root": "synthetic", "files": len(original_names),
                "uncompressed_bytes": sum(len(members[n]) for n in original_names),
                "key_files": {"snapshot": "snapshot.json", "projection": "replay/projection.json"},
            },
            "verification": {
                "command": ["python", "rebuild_model_evidence.py"],
                "trials": "results/trials.jsonl", "summary": "results/summary.json",
                "absolute_tolerance": 0, "relative_tolerance": 0,
                "inputs": [{"role": role, "path": name,
                            "sha256": hashlib.sha256(members[name]).hexdigest()}
                           for role, name in [("control", "synthetic/results/control.json"),
                                              ("configuration", "synthetic/plan/config.json"),
                                              ("validator", "synthetic/validator/check.py")]],
            },
        }
        return path, manifest

    return members, pack


def test_replay_recomputes_from_verified_originals_without_executing_them(frozen, tmp_path):
    members, pack = frozen
    path, manifest = pack()
    capture = {}
    archive.verify_archive(path, archive.normalize_manifest(manifest), capture=capture)
    assert capture == members
    summary, rows = replay.replay(archive.normalize_manifest(manifest), path)
    assert summary["campaign_verdict"] == "INCONCLUSIVE"
    assert summary["recomputed_metrics"]["latency"]["distribution"]["median"] == 2
    assert rows[0]["status"] == "failed"
    source = tmp_path / "artifacts.json"
    source.write_text(json.dumps(manifest))
    output = tmp_path / "generated"
    assert replay.main([str(source), "--archive", str(path), "--output", str(output)]) == 0
    original = (output / "results/summary.json").read_bytes()
    assert replay.main([str(source), "--archive", str(path), "--output", str(output)]) == 1
    assert (output / "results/summary.json").read_bytes() == original


@pytest.mark.parametrize("mutation", ["changed_original", "missing_original", "changed_code"])
def test_archive_identity_does_not_replace_original_or_replay_identity(frozen, mutation):
    members, pack = frozen
    if mutation == "changed_original":
        members["synthetic/validator/check.py"] = b"changed"
    elif mutation == "missing_original":
        del members["synthetic/plan/frozen.json"]
    else:
        members["replay/rebuild_model_evidence.py"] = b"changed"
    path, manifest = pack()
    with pytest.raises(archive.VerificationError):
        replay.replay(archive.normalize_manifest(manifest), path)


def test_failed_verification_never_exposes_partially_captured_members(frozen):
    _, pack = frozen
    path, manifest = pack()
    manifest["verification"]["inputs"][0]["sha256"] = "0" * 64
    captured = {}
    with pytest.raises(archive.VerificationError, match="SHA-256"):
        archive.verify_archive(path, archive.normalize_manifest(manifest), capture=captured)
    assert not captured
