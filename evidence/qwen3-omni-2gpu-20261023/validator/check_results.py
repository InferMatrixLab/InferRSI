"""Frozen campaign checks for native vLLM-Omni benchmark JSON.

These checks alone do not certify source integrity, repetitions or model quality.
Missing measurements must never become zero-valued successful samples.
"""

import argparse
import json
import math
from pathlib import Path


def positive(result, key):
    value = result.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Missing numeric {key}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Invalid {key}: {value}")
    return value


def summarize(result, expected):
    if result.get("completed") != expected:
        raise ValueError("Incomplete requests")
    for key in ("num_audio_ttfp_samples", "num_audio_rtf_samples"):
        if result.get(key) != expected:
            raise ValueError(f"Incomplete {key}")
    return {
        "throughput_frames_s": positive(result, "total_audio_frames") / positive(result, "duration"),
        "ttfa_p50_ms": positive(result, "median_audio_ttfp_ms"),
        "ttfa_p95_ms": positive(result, "p95_audio_ttfp_ms"),
        "rtf_mean": positive(result, "mean_audio_rtf"),
        "completed": expected,
    }


def quality(result, expected):
    if result.get("seed_tts_content_evaluated") != expected:
        raise ValueError("Incomplete WER coverage")
    for key in ("seed_tts_request_failed", "seed_tts_no_pcm", "seed_tts_asr_failed", "seed_tts_empty_audio"):
        if result.get(key) != 0:
            raise ValueError(f"Missing or failed quality check: {key}")
    value = result.get("seed_tts_content_error_mean")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid WER")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--expected", required=True, type=int)
    parser.add_argument("--baseline-quality", type=Path)
    args = parser.parse_args()
    if args.expected <= 0:
        parser.error("--expected must be positive")
    result = json.loads(args.result.read_text())
    if args.baseline_quality:
        baseline = json.loads(args.baseline_quality.read_text())
        if quality(result, args.expected) > quality(baseline, args.expected):
            raise ValueError("WER regression")
        print(json.dumps({"quality_gate": "PASS", "scope": "paired WER only"}))
    else:
        print(json.dumps(summarize(result, args.expected), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
