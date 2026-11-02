"""CPU regression checks for the new campaign's media integrity contract."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "evidence/h3-ref2va-lossless-293/validator/integrity.py"
SPEC = importlib.util.spec_from_file_location("h3_lossless_integrity", PATH)
assert SPEC is not None and SPEC.loader is not None
integrity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(integrity)


def audio_frame(start, samples=1024):
    return {"best_effort_timestamp_time": str(start), "nb_samples": samples}


def test_accepts_complete_audio_with_codec_padding():
    frames = [audio_frame(i * 1024 / 32000) for i in range(16)]
    assert integrity.check_timeline(frames, 0.5, 32000, 2048) == 0.512


@pytest.mark.parametrize(
    "frames",
    [
        [],
        [audio_frame(0)],  # both arms could have the same truncated tail
        [audio_frame(0.1)],
        [audio_frame(0), audio_frame(0.064)],
        [audio_frame(0), audio_frame(0.016)],
        [audio_frame("nan")],
        [audio_frame("inf")],
        [audio_frame(0, 0)],
        [audio_frame(0, 32000)],
    ],
)
def test_rejects_incomplete_or_invalid_audio(frames):
    with pytest.raises(ValueError):
        integrity.check_timeline(frames, 0.5, 32000, 2048)


def test_pcm_coverage_checks_expected_length_not_just_pair_equality():
    gates = {"fps": 24, "sample_rate": 32000, "max_audio_padding_samples": 2048}
    integrity.check_pcm_samples(165888, gates, 124)
    for samples in (16000, 165888, 999999):
        with pytest.raises(ValueError):
            integrity.check_pcm_samples(samples, gates, 362)


def test_authenticates_actual_bytes_before_loading(tmp_path):
    path = tmp_path / "synthetic-weights"
    data = b"synthetic scorer data"
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    assert integrity.checked_bytes(path, digest) == data
    path.write_bytes(b"different scorer data")
    with pytest.raises(ValueError, match="hash mismatch"):
        integrity.load_scorer(path, path, {"alexnet_sha256": digest, "lpips_sha256": digest})
