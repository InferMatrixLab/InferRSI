"""Versioned successor of frozen check_results_v3.py for the paired WER gate.

Historical protocol v3/v4/v5 bytes and recorded verdicts stay unchanged. This
successor only replaces aggregate trust: the paired mean is the arithmetic mean
of validated per-item WER values, and a supplied seed_tts_content_error_mean
that disagrees is rejected. See plan/wer-aggregate-protocol-v6.json.
"""

import argparse
import importlib.util
import json
import statistics
from pathlib import Path

_V3_PATH = Path(__file__).with_name("check_results_v3.py")
_SPEC = importlib.util.spec_from_file_location("qwen3_omni_check_results_v3", _V3_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Cannot load frozen validator {_V3_PATH}")
v3 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3)


def quality(result, expected):
    if result.get("seed_tts_content_evaluated") != expected:
        raise ValueError("Incomplete WER coverage")
    for key in (
        "seed_tts_request_failed",
        "seed_tts_no_pcm",
        "seed_tts_asr_failed",
        "seed_tts_empty_audio",
    ):
        if result.get(key) != 0:
            raise ValueError(f"Missing or failed quality check: {key}")
    items = result.get("seed_tts_wer_eval_items")
    if not isinstance(items, list) or len(items) != expected:
        raise ValueError("Missing per-item WER evidence")
    identities = [(item.get("utterance_id"), item.get("reference_raw")) for item in items]
    if any(not uid or not ref for uid, ref in identities) or len(set(identities)) != expected:
        raise ValueError("Missing/duplicate WER identities")
    wers = []
    for item in items:
        if item.get("error"):
            raise ValueError("Per-item quality error")
        wers.append(v3.number(item, "wer", positive=False))
    if not wers:
        raise ValueError("Missing per-item WER evidence")
    computed = statistics.fmean(wers)
    reported = v3.number(result, "seed_tts_content_error_mean", positive=False)
    v3.close(computed, reported, "seed_tts_content_error_mean")
    return computed, identities


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--expected", required=True, type=int)
    parser.add_argument("--baseline-quality", type=Path)
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    args = parser.parse_args(argv)
    if args.expected <= 0:
        parser.error("--expected must be positive")
    result = json.loads(args.result.read_text())
    if args.baseline_quality:
        if not args.baseline_manifest or not args.candidate_manifest:
            parser.error("quality comparison requires both scorer manifests")
        manifests = [
            json.loads(path.read_text())
            for path in (args.baseline_manifest, args.candidate_manifest)
        ]
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
        print(json.dumps(v3.summarize(result, args.expected), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
