"""Frozen campaign media gate; CPU only, separate from latency measurement.

SSIM/PSNR use the upstream accuracy helper's FFmpeg filter definitions.
LPIPS and audio metrics are frozen verbatim in upstream_metrics.py.
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from integrity import audio_coverage, check_pcm_samples, load_scorer
from upstream_metrics import _audio_quality_metrics


def run(command):
    return subprocess.run(command, check=True, capture_output=True, timeout=3600)


def probe(path, gates, frames):
    result = json.loads(
        run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(path)]
        ).stdout
    )
    streams = result["streams"]
    video = [s for s in streams if s["codec_type"] == "video"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    if len(video) != 1 or len(audio) != 1:
        raise ValueError("Exactly one video and audio stream required")
    v, a = video[0], audio[0]
    numerator, denominator = map(int, v["avg_frame_rate"].split("/"))
    actual = (
        v["width"],
        v["height"],
        numerator / denominator,
        int(v["nb_read_frames"]),
        int(a["sample_rate"]),
        a["channels"],
    )
    expected = (
        gates["width"],
        gates["height"],
        gates["fps"],
        frames,
        gates["sample_rate"],
        gates["channels"],
    )
    if actual != expected:
        raise ValueError(f"Media contract mismatch: {actual} != {expected}")
    if abs(float(v["start_time"])) > 1 / gates["sample_rate"]:
        raise ValueError("Video does not start at zero")
    if abs(float(v["duration"]) - frames / gates["fps"]) > 1 / gates["sample_rate"]:
        raise ValueError("Video timestamp duration differs from expected frame duration")
    audio_start, audio_duration = float(a["start_time"]), float(a["duration"])
    if not math.isfinite(audio_start) or not math.isfinite(audio_duration):
        raise ValueError("Invalid audio stream timestamps")
    if abs(audio_start) > 1 / gates["sample_rate"]:
        raise ValueError("Audio stream does not start at zero")
    expected_duration = frames / gates["fps"]
    if audio_duration < expected_duration - 1 / gates["sample_rate"]:
        raise ValueError("Audio stream ends before the expected video duration")
    max_duration = expected_duration + gates["max_audio_padding_samples"] / gates["sample_rate"]
    if audio_duration > max_duration:
        raise ValueError("Audio stream exceeds the allowed codec padding")
    return audio_coverage(path, gates, frames)


def compare(baseline, candidate, gates, frames, alexnet_path, lpips_path, weights):
    coverage = [probe(path, gates, frames) for path in (baseline, candidate)]
    loss_fn, scorer_identity = load_scorer(alexnet_path, lpips_path, weights)
    metrics = {}
    for name, pattern in [
        ("ssim", r"All:([0-9.eE+-]+)"),
        ("psnr_db", r"average:([0-9.eE+-]+|inf)"),
    ]:
        filter_name = "ssim" if name == "ssim" else "psnr"
        output = run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-i",
                str(baseline),
                "-i",
                str(candidate),
                "-lavfi",
                f"[0:v][1:v]{filter_name}",
                "-f",
                "null",
                "-",
            ]
        ).stderr.decode()
        found = re.findall(pattern, output)
        if not found:
            raise ValueError(f"Missing {name} metric")
        metrics[name] = float(found[-1])
    with tempfile.TemporaryDirectory() as directory:
        videos, audios = [], []
        for index, path in enumerate((baseline, candidate)):
            raw = Path(directory) / f"{index}.rgb"
            run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-map",
                    "0:v:0",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    str(raw),
                ]
            )
            video = np.memmap(raw, dtype=np.uint8, mode="r")
            shape = (frames, gates["height"], gates["width"], 3)
            if video.size != math.prod(shape):
                raise ValueError("Decoded video length mismatch")
            videos.append(video.reshape(shape))
            pcm = run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-map",
                    "0:a:0",
                    "-f",
                    "f32le",
                    "-acodec",
                    "pcm_f32le",
                    "-",
                ]
            ).stdout
            audio = np.frombuffer(pcm, dtype="<f4").reshape(-1, gates["channels"]).T.copy()
            check_pcm_samples(audio.shape[1], gates, frames)
            audios.append(audio)
        if audios[0].shape != audios[1].shape:
            raise ValueError("Decoded audio length mismatch")
        # Match upstream LPIPS full-resolution normalization, all decoded frames.
        # One frame at a time bounds host memory; retain the model across frames.
        import torch

        exact_video = all(np.array_equal(a, b) for a, b in zip(*videos, strict=True))
        exact_audio = np.array_equal(*audios)
        scores = []
        with torch.no_grad():
            for left, right in zip(*videos, strict=True):
                tensors = [
                    torch.from_numpy(x.copy()).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1
                    for x in (left, right)
                ]
                scores.append(float(loss_fn(*tensors).item()))
        metrics["lpips"] = float(np.mean(scores))
        metrics["audio_spectral_cosine"], metrics["audio_rms_ratio"] = _audio_quality_metrics(
            *audios
        )
        metrics["audio_samples"] = audios[0].shape[1]
    finite = all(math.isfinite(v) for k, v in metrics.items() if k != "psnr_db")
    passed = (
        finite
        and metrics["ssim"] >= gates["min_ssim"]
        and metrics["psnr_db"] >= gates["min_psnr_db"]
        and metrics["lpips"] <= gates["max_lpips"]
        and metrics["audio_spectral_cosine"] >= gates["min_audio_spectral_cosine"]
        and gates["min_audio_rms_ratio"]
        <= metrics["audio_rms_ratio"]
        <= gates["max_audio_rms_ratio"]
    )
    if math.isinf(metrics["psnr_db"]):
        metrics["psnr_db"] = "inf"
    return {
        "verdict": "FAIL"
        if not passed
        else ("PASS" if exact_video and exact_audio else "INCONCLUSIVE"),
        "media_gate_verdict": "PASS" if passed else "FAIL",
        "scope": (
            "decoded media equality; unequal outputs require "
            "separate baseline-repeatability adjudication"
        ),
        "exact_video": exact_video,
        "exact_audio": exact_audio,
        "coverage": coverage,
        "scorer_identity": scorer_identity,
        "metrics": metrics,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alexnet-weights", type=Path, required=True)
    parser.add_argument("--lpips-weights", type=Path, required=True)
    args = parser.parse_args()
    gates_path = Path(__file__).with_name("gates.json")
    gates = json.loads(gates_path.read_text())
    weights = json.loads(Path(__file__).with_name("weights.json").read_text())
    result = compare(
        args.baseline,
        args.candidate,
        gates,
        args.frames,
        args.alexnet_weights,
        args.lpips_weights,
        weights,
    )
    result["inputs"] = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in [
            ("baseline", args.baseline),
            ("candidate", args.candidate),
            ("gates", gates_path),
        ]
    }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    raise SystemExit({"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[result["verdict"]])
