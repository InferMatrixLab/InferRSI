"""Validate complete native audio rows; this is not the entire campaign verdict."""
import argparse
import json
import math
import statistics
from pathlib import Path


def number(row, key, *, positive=True):
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Missing numeric {key}")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"Invalid {key}: {value}")
    return value


def percentile(values, p):
    ordered = sorted(values)
    index = (len(ordered) - 1) * p / 100
    low = math.floor(index)
    high = math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def close(actual, expected, name):
    if not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError(f"Raw/aggregate mismatch: {name}")


def summarize(result, expected):
    rows = result.get("audio_request_metrics")
    if not isinstance(rows, list) or len(rows) != expected:
        raise ValueError("Incomplete raw audio rows")
    if result.get("completed") != expected or result.get("failed") != 0:
        raise ValueError("Incomplete or failed requests")
    ttfa, rtfs, frames = [], [], []
    for index, row in enumerate(rows):
        if row.get("request_index") != index or row.get("success") is not True or row.get("error"):
            raise ValueError(f"Invalid request row {index}")
        first = number(row, "audio_ttfp")
        rtf = number(row, "audio_rtf")
        duration = number(row, "audio_duration")
        count = number(row, "audio_frames")
        latency = number(row, "latency")
        number(row, "start_time")
        if first > latency + 1e-6 or rtf * duration > latency + 1e-6:
            raise ValueError(f"Audio timing exceeds request latency: {index}")
        close(count / duration, 24000, "Qwen3-Omni sample rate")
        if int(count) != count:
            raise ValueError("Fractional PCM frame count")
        ttfa.append(first * 1000)
        rtfs.append(rtf)
        frames.append(count)
    summary = {
        "throughput_frames_s": sum(frames) / number(result, "duration"),
        "ttfa_p50_ms": percentile(ttfa, 50),
        "ttfa_p95_ms": percentile(ttfa, 95),
        "rtf_mean": statistics.fmean(rtfs),
        "completed": expected,
    }
    for field, key in (("ttfa_p50_ms", "median_audio_ttfp_ms"),
                       ("ttfa_p95_ms", "p95_audio_ttfp_ms"), ("rtf_mean", "mean_audio_rtf")):
        close(summary[field], number(result, key), key)
    close(sum(frames), number(result, "total_audio_frames"), "total_audio_frames")
    return summary


def quality(result, expected):
    if result.get("seed_tts_content_evaluated") != expected:
        raise ValueError("Incomplete WER coverage")
    for key in ("seed_tts_request_failed", "seed_tts_no_pcm", "seed_tts_asr_failed", "seed_tts_empty_audio"):
        if result.get(key) != 0:
            raise ValueError(f"Missing or failed quality check: {key}")
    items = result.get("seed_tts_wer_eval_items")
    if not isinstance(items, list) or len(items) != expected:
        raise ValueError("Missing per-item WER evidence")
    identities = [(item.get("utterance_id"), item.get("reference_raw")) for item in items]
    if any(not uid or not ref for uid, ref in identities) or len(set(identities)) != expected:
        raise ValueError("Missing/duplicate WER identities")
    for item in items:
        if item.get("error"):
            raise ValueError("Per-item quality error")
        number(item, "wer", positive=False)
    return number(result, "seed_tts_content_error_mean", positive=False), identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--expected", required=True, type=int)
    parser.add_argument("--baseline-quality", type=Path)
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    args = parser.parse_args()
    if args.expected <= 0:
        parser.error("--expected must be positive")
    result = json.loads(args.result.read_text())
    if args.baseline_quality:
        if not args.baseline_manifest or not args.candidate_manifest:
            parser.error("quality comparison requires both scorer manifests")
        manifests = [json.loads(p.read_text()) for p in (args.baseline_manifest, args.candidate_manifest)]
        scorer = manifests[0].get("quality_scorer")
        if not scorer or scorer != manifests[1].get("quality_scorer"):
            raise ValueError("Missing or mismatched scorer identity")
        baseline = json.loads(args.baseline_quality.read_text())
        current_wer, current_ids = quality(result, args.expected)
        baseline_wer, baseline_ids = quality(baseline, args.expected)
        if current_ids != baseline_ids:
            raise ValueError("Quality workload mismatch")
        if current_wer > baseline_wer:
            raise ValueError("WER regression")
        print(json.dumps({"quality_gate": "PASS", "scope": "paired WER only"}))
    else:
        print(json.dumps(summarize(result, args.expected), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
