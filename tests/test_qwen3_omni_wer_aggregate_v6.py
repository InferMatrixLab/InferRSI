"""The v6 WER successor must reconcile the aggregate; frozen v3 bytes stay put."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "evidence/qwen3-omni-2gpu-20261023"
V3 = CAMPAIGN / "validator/check_results_v3.py"
V6 = CAMPAIGN / "validator/check_results_v6.py"
RETAINED = (
    "results/baseline-v3-quality.json",
    "results/full-cuda-quality.json",
    "results/adapter-quality.json",
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v6 = load_module("qwen3_omni_check_results_v6", V6)


def quality_result(wers, reported):
    return {
        "seed_tts_content_evaluated": len(wers),
        "seed_tts_request_failed": 0,
        "seed_tts_no_pcm": 0,
        "seed_tts_asr_failed": 0,
        "seed_tts_empty_audio": 0,
        "seed_tts_content_error_mean": reported,
        "seed_tts_wer_eval_items": [
            {
                "utterance_id": f"utt-{index}",
                "reference_raw": f"reference {index}",
                "wer": wer,
            }
            for index, wer in enumerate(wers)
        ],
    }


def write_pair(tmp_path, baseline, candidate):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    manifest = tmp_path / "scorer.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    manifest.write_text(json.dumps({"quality_scorer": "synthetic-scorer"}), encoding="utf-8")
    return baseline_path, candidate_path, manifest


def run_gate(script, tmp_path, baseline, candidate):
    baseline_path, candidate_path, manifest = write_pair(tmp_path, baseline, candidate)
    return subprocess.run(
        [
            sys.executable,
            str(script),
            str(candidate_path),
            "--expected",
            str(len(candidate["seed_tts_wer_eval_items"])),
            "--baseline-quality",
            str(baseline_path),
            "--baseline-manifest",
            str(manifest),
            "--candidate-manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_frozen_v3_bytes_remain_pinned():
    pinned = json.loads((CAMPAIGN / "plan/frozen-files-v5.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(V3.read_bytes()).hexdigest()
    assert digest == pinned["validator/check_results_v3.py"]
    successor = json.loads((CAMPAIGN / "plan/frozen-files-v6.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(V6.read_bytes()).hexdigest() == successor["validator/check_results_v6.py"]


def test_matching_aggregate_still_passes(tmp_path):
    baseline = quality_result([0.1, 0.3], 0.2)
    candidate = quality_result([0.0, 0.2], 0.1)
    completed = run_gate(V6, tmp_path, baseline, candidate)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"quality_gate": "PASS", "scope": "paired WER only"}


def test_stale_lower_aggregate_cannot_pass_regressed_items(tmp_path):
    """Negative mismatch control: items regress, supplied mean stays lower."""
    baseline = quality_result([0.1, 0.3], 0.2)
    regressed = quality_result([0.4, 0.6], 0.1)
    with pytest.raises(ValueError, match="Raw/aggregate mismatch: seed_tts_content_error_mean"):
        v6.quality(regressed, 2)
    completed = run_gate(V6, tmp_path, baseline, regressed)
    assert completed.returncode != 0
    assert "quality_gate" not in completed.stdout
    assert "Raw/aggregate mismatch: seed_tts_content_error_mean" in completed.stderr

    # The frozen predecessor still trusts the stale aggregate on this fixture.
    predecessor_dir = tmp_path / "v3"
    predecessor_dir.mkdir()
    predecessor = run_gate(V3, predecessor_dir, baseline, regressed)
    assert predecessor.returncode == 0, predecessor.stderr
    assert json.loads(predecessor.stdout)["quality_gate"] == "PASS"


def test_honest_regression_still_fails(tmp_path):
    baseline = quality_result([0.1, 0.3], 0.2)
    candidate = quality_result([0.4, 0.6], 0.5)
    completed = run_gate(V6, tmp_path, baseline, candidate)
    assert completed.returncode != 0
    assert "WER regression" in completed.stderr
    assert "quality_gate" not in completed.stdout


def test_retained_historical_means_agree_with_validated_items():
    means = []
    for relative in RETAINED:
        result = json.loads((CAMPAIGN / relative).read_text(encoding="utf-8"))
        computed, identities = v6.quality(result, 256)
        assert len(identities) == 256
        assert computed == pytest.approx(result["seed_tts_content_error_mean"], rel=1e-6, abs=1e-6)
        means.append(computed)
    baseline, full_cuda, adapter = means
    assert full_cuda > baseline
    assert adapter > baseline
