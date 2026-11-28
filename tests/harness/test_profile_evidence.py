import gzip
import hashlib
from dataclasses import replace

import pytest

from inferrsi.harness.analyzer import replay_profile
from inferrsi.harness.records import ProfileReceipt, retain_profile

_TRACE = (
    b'{"traceEvents":[{"ph":"X","name":"kernel","pid":1,"tid":1,"ts":100,"dur":20,"cat":"gpu"}]}'
)


@pytest.mark.parametrize("compressed", [False, True])
def test_replay_verified_profile_without_original_source(tmp_path, compressed):
    raw = gzip.compress(_TRACE) if compressed else _TRACE
    source = tmp_path / "capture"
    source.write_bytes(raw)
    receipt = _receipt(raw, "chrome-trace-gzip-v1" if compressed else "chrome-trace-json-v1")
    retain_profile(tmp_path, source, receipt)
    retain_profile(tmp_path, source, receipt)
    source.unlink()

    overview = replay_profile(tmp_path, receipt)
    assert (overview["event_count"], overview["duration_us"]) == (1, 20)
    for changed in (
        replace(receipt, service_id="another-service"),
        replace(receipt, attempt_id="another-attempt"),
    ):
        with pytest.raises(ValueError, match="identity"):
            replay_profile(tmp_path, changed)

    retained = next((tmp_path / "profile-evidence").glob("*.raw"))
    retained.write_bytes(b"altered")
    with pytest.raises(ValueError, match="does not match"):
        replay_profile(tmp_path, receipt)


def test_recapture_retains_earlier_binding(tmp_path):
    source = tmp_path / "capture"
    source.write_bytes(_TRACE)
    original = _receipt(_TRACE)
    recapture = replace(
        original,
        capture_id="capture-2",
        attempt_id="backfill-attempt",
        service_id="new-service",
        capture_started_at="2026-11-28T11:10:00Z",
        capture_ended_at="2026-11-28T11:11:00Z",
        artifact_ready_at="2026-11-28T11:12:00Z",
        supersedes_capture_id=original.capture_id,
        original_attempt_id=original.attempt_id,
    )
    with pytest.raises(FileNotFoundError):
        retain_profile(tmp_path, source, recapture)
    retain_profile(tmp_path, source, original)
    with pytest.raises(ValueError, match="different binding"):
        retain_profile(tmp_path, source, replace(original, service_id="new-service"))
    retain_profile(tmp_path, source, recapture)
    recapture_again = replace(
        recapture,
        capture_id="capture-3",
        attempt_id="another-backfill-attempt",
        service_id="another-backfill-service",
        capture_started_at="2026-11-28T11:20:00Z",
        capture_ended_at="2026-11-28T11:21:00Z",
        artifact_ready_at="2026-11-28T11:22:00Z",
        supersedes_capture_id=recapture.capture_id,
    )
    retain_profile(tmp_path, source, recapture_again)
    assert len(list((tmp_path / "profile-evidence").glob("*.receipt.json"))) == 3
    assert replay_profile(tmp_path, original) == replay_profile(tmp_path, recapture)
    assert replay_profile(tmp_path, original) == replay_profile(tmp_path, recapture_again)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("original_attempt_id", "unrelated-attempt"),
        ("revision", "unrelated-revision"),
        ("metric", "unrelated-metric"),
        ("unit", "ms"),
        ("capture_started_at", "2026-11-28T11:00:30Z"),
    ],
)
def test_recapture_rejects_mismatched_lineage_without_retaining_bytes(tmp_path, field, value):
    source = tmp_path / "capture"
    source.write_bytes(_TRACE)
    original = _receipt(_TRACE)
    retain_profile(tmp_path, source, original)
    directory = tmp_path / "profile-evidence"
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    new_raw = _TRACE + b"\n"
    source.write_bytes(new_raw)
    recapture = replace(
        original,
        capture_id="capture-2",
        attempt_id="new-attempt",
        service_id="new-service",
        capture_started_at="2026-11-28T11:10:00Z",
        capture_ended_at="2026-11-28T11:11:00Z",
        artifact_ready_at="2026-11-28T11:12:00Z",
        supersedes_capture_id=original.capture_id,
        original_attempt_id=original.attempt_id,
        raw_sha256=hashlib.sha256(new_raw).hexdigest(),
    )
    with pytest.raises(ValueError, match="prior capture lineage"):
        retain_profile(tmp_path, source, replace(recapture, **{field: value}))
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


def test_invalid_evidence_fails_closed(tmp_path):
    receipt = _receipt(_TRACE)
    with pytest.raises(ValueError, match="capture window"):
        replace(receipt, artifact_ready_at="2026-11-28T10:00:00Z")
    with pytest.raises(ValueError, match="unknown profile decoder"):
        replace(receipt, decoder_version="future")
    with pytest.raises(ValueError, match="original attempt ID"):
        replace(receipt, capture_id="capture-2", supersedes_capture_id=receipt.capture_id)
    with pytest.raises(ValueError, match="its own attempt"):
        replace(receipt, original_attempt_id="unrelated-attempt")
    source = tmp_path / "capture"
    source.write_bytes(b"wrong bytes")
    with pytest.raises(ValueError, match="does not match"):
        retain_profile(tmp_path, source, receipt)
    assert not (tmp_path / "profile-evidence").exists()


@pytest.mark.parametrize(
    ("raw", "decoder"),
    [
        (b'{"traceEvents":[', "chrome-trace-json-v1"),
        (b"event,duration\nkernel,20\n", "chrome-trace-json-v1"),
        (gzip.compress(_TRACE)[:-8], "chrome-trace-gzip-v1"),
        (_TRACE, "chrome-trace-gzip-v1"),
    ],
)
def test_retention_rejects_undecodable_raw_before_publication(tmp_path, raw, decoder):
    source = tmp_path / "capture"
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        retain_profile(tmp_path, source, _receipt(raw, decoder))
    assert list(tmp_path.iterdir()) == [source]


def _receipt(raw, decoder="chrome-trace-json-v1"):
    return ProfileReceipt(
        capture_id="capture-1",
        attempt_id="attempt-1",
        service_id="service-1",
        revision="revision-1",
        metric="kernel_duration",
        unit="us",
        capture_started_at="2026-11-28T11:00:00Z",
        capture_ended_at="2026-11-28T11:01:00Z",
        artifact_ready_at="2026-11-28T11:02:00Z",
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        decoder_version=decoder,
    )
