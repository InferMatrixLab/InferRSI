"""Changed-WAV resume must not bind saved scores to new audio hashes."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SUCCESSOR = (
    Path(__file__).resolve().parents[1]
    / "evidence/minicpmo45-l20x-20261021/validator/score_outputs_v2.py"
)


def load_successor():
    spec = importlib.util.spec_from_file_location("score_outputs_v2", SUCCESSOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def provenance(digest="a" * 64):
    return {"successor": "score_outputs_v2", "files": {"sim/wavlm_large.pt": digest}}


def wavs(*digests):
    return {
        f"prompt-{index}": {"wav_sha256": digest, "duration_s": 1.25}
        for index, digest in enumerate(digests)
    }


def completed(module, audio, scorer):
    document = module.bind_resume(None, list(audio), audio, scorer)
    document["tasks"].append("wer")
    document["rows"]["prompt-0"]["wer"] = {"wer": 0.1, "hits": 10}
    return document


def test_changed_wav_resume_does_not_rebind_scores(tmp_path):
    module = load_successor()
    scorer = provenance()
    original_audio = wavs("1" * 64, "2" * 64)
    document = completed(module, original_audio, scorer)
    out = tmp_path / "scores.json"
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    before = out.read_bytes()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    snapshot = copy.deepcopy(loaded)
    changed = wavs("3" * 64, "4" * 64)
    with pytest.raises(module.StaleScoringOutput, match="WAV provenance differs"):
        module.resume_output(out, list(changed), changed, scorer)
    assert out.read_bytes() == before
    assert loaded == snapshot
    assert loaded["rows"]["prompt-0"]["wer"]["wer"] == 0.1
    assert loaded["rows"]["prompt-0"]["wav_sha256"] == "1" * 64


def test_duration_id_and_scorer_mismatches_are_rejected(tmp_path):
    module = load_successor()
    scorer = provenance()
    audio = wavs("a" * 64)
    document = completed(module, audio, scorer)
    out = tmp_path / "scores.json"
    out.write_text(json.dumps(document), encoding="utf-8")
    longer = {"prompt-0": {"wav_sha256": "a" * 64, "duration_s": 2.5}}
    other_ids = wavs("b" * 64)
    other_ids["prompt-1"] = other_ids.pop("prompt-0")
    other_scorer = provenance("b" * 64)
    historical = copy.deepcopy(document)
    del historical["scorer_provenance"]
    cases = (
        (list(longer), longer, scorer, "WAV provenance differs"),
        (["prompt-1"], other_ids, scorer, "prompt IDs differ"),
        (list(audio), audio, other_scorer, "scorer provenance differs"),
    )
    for ids, candidate, candidate_scorer, message in cases:
        with pytest.raises(module.StaleScoringOutput, match=message):
            module.bind_resume(document, ids, candidate, candidate_scorer)
    with pytest.raises(module.StaleScoringOutput, match="scorer provenance"):
        module.bind_resume(historical, list(audio), audio, scorer)
    assert out.read_bytes()  # the rejected checks never receive this path


def test_matching_resume_preserves_completed_scores():
    module = load_successor()
    scorer = provenance()
    audio = wavs("c" * 64, "d" * 64)
    document = completed(module, audio, scorer)
    resumed = module.bind_resume(document, list(audio), audio, scorer)
    assert resumed["tasks"] == ["wer"]
    assert resumed["rows"]["prompt-0"]["wer"] == {"wer": 0.1, "hits": 10}
    assert resumed["rows"]["prompt-1"]["wav_sha256"] == "d" * 64
    assert "wer" not in resumed["rows"]["prompt-1"]
    assert document == completed(module, audio, scorer)


def test_scorer_provenance_changes_when_weight_bytes_change(tmp_path):
    module = load_successor()
    weight = tmp_path / "sim" / "wavlm_large.pt"
    weight.parent.mkdir()
    weight.write_bytes(b"weight-a")
    first = module.scorer_provenance(tmp_path)
    weight.write_bytes(b"weight-b")
    second = module.scorer_provenance(tmp_path)
    assert first["files"]["sim/wavlm_large.pt"] != second["files"]["sim/wavlm_large.pt"]
    audio = wavs("e" * 64)
    with pytest.raises(module.StaleScoringOutput, match="scorer provenance differs"):
        module.bind_resume(completed(module, audio, first), list(audio), audio, second)
