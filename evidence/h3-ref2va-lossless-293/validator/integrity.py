"""Coverage and explicit scorer loading for the lossless H3 follow-up.

The historical campaign validator remains frozen. This version never downloads
weights and authenticates the same in-memory bytes that torch.load consumes.
"""

import hashlib
import io
import json
import math
import subprocess
from pathlib import Path


def checked_bytes(path, expected):
    data = Path(path).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"Scorer weight hash mismatch: {actual} != {expected}")
    return data


def load_scorer(alexnet_path, lpips_path, weights):
    # Authenticate before imports/model construction; no download fallback.
    trunk = checked_bytes(alexnet_path, weights["alexnet_sha256"])
    linear = checked_bytes(lpips_path, weights["lpips_sha256"])
    import lpips
    import torch

    scorer = lpips.LPIPS(net="alex", pnet_rand=True, pretrained=False, verbose=False)
    trunk_state = torch.load(io.BytesIO(trunk), map_location="cpu", weights_only=True)
    features = {}
    for name in scorer.net.state_dict():
        _, index, parameter = name.split(".")
        features[name] = trunk_state[f"features.{index}.{parameter}"]
    scorer.net.load_state_dict(features, strict=True)
    linear_state = torch.load(io.BytesIO(linear), map_location="cpu", weights_only=True)
    expected = {f"lin{index}.model.1.weight" for index in range(5)}
    if set(linear_state) != expected:
        raise ValueError("Unexpected LPIPS calibration keys")
    for index in range(5):
        getattr(scorer, f"lin{index}").load_state_dict(
            {"model.1.weight": linear_state[f"lin{index}.model.1.weight"]}, strict=True
        )
    scorer.eval()
    return scorer, dict(weights)


def check_timeline(frames, expected_duration, rate, padding_samples):
    """Reject missing heads/tails, gaps, overlaps, and non-finite timestamps."""
    tolerance = 1.1 / rate  # one sample plus decimal timestamp serialization
    padding = padding_samples / rate
    end = 0.0
    for frame in frames:
        start = float(frame["best_effort_timestamp_time"])
        duration = int(frame["nb_samples"]) / rate
        if not math.isfinite(start) or duration <= 0:
            raise ValueError("Invalid decoded audio timestamp/duration")
        if abs(start - end) > tolerance:
            raise ValueError("Audio has a missing head, timestamp gap, or overlap")
        end = start + duration
    if not frames or end < expected_duration - tolerance or end > expected_duration + padding:
        raise ValueError("Audio does not cover the expected video duration")
    return end


def audio_coverage(path, gates, frames):
    duration = frames / gates["fps"]
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time,nb_samples",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=3600,
    )
    audio_frames = json.loads(probe.stdout)["frames"]
    end = check_timeline(
        audio_frames, duration, gates["sample_rate"], gates["max_audio_padding_samples"]
    )
    return {"expected_duration_s": duration, "decoded_audio_end_s": end}


def check_pcm_samples(samples, gates, frames):
    expected = frames * gates["sample_rate"] / gates["fps"]
    if (
        samples < math.floor(expected)
        or samples > math.ceil(expected) + gates["max_audio_padding_samples"]
    ):
        raise ValueError("Decoded PCM does not cover the expected video duration")
