"""Validate complete raw task transcripts before session selection."""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.benchmark.registry import task_resources
from tests.engineering_task_support import load_task_module

protocol = load_task_module("qwen21-denoise-npu", "optimization")


@pytest.fixture
def transcript(tmp_path):
    root = Path(str(task_resources("qwen21-denoise-npu")))
    settings = {"pairs": 2, "samples": 2, "warmups": 1}
    output = tmp_path / "measurement"
    snapshot = output / "snapshot"
    snapshot.mkdir(parents=True)
    (tmp_path / "candidate.py").write_text("submitted candidate\n", encoding="utf-8")
    names = ("baseline.py", "reference.py", "workload.py", "task.json", "TASK.md",
             "benchmark.py", "LICENSE", "NOTICE.md")
    for name in names:
        shutil.copyfile(root / name, snapshot / name)
    shutil.copyfile(tmp_path / "candidate.py", snapshot / "candidate.py")
    identity = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in snapshot.iterdir()}
    (output / "identity.json").write_text(json.dumps(identity), encoding="utf-8")
    task = json.loads((root / "task.json").read_text())
    result = {"status": "completed", "correctness": "PASS", "score_scope": "complete_task",
              "selected_cases": [case["id"] for case in task["cases"]],
              "protocol": {**settings, "check_only": False}, "cases": [], "calls": [],
              "speedup": 2.0}
    for case in task["cases"]:
        config = {**task["defaults"], **case}
        phases = [("correctness", None, None), ("warmup", None, None)]
        if case["measured"]:
            phases += [("measurement", index // 2, index) for index in range(4)]
            result["cases"].append({
                "id": case["id"], "samples_ms": {"baseline": [10.0] * 4,
                                                "candidate": [5.0] * 4},
                "baseline_median_ms": 10.0, "candidate_median_ms": 5.0, "speedup": 2.0,
            })
        phases.append(("weight_update", None, None))
        for phase, pair, sample in phases:
            for label in ("baseline", "candidate"):
                result["calls"].append({"case": case["id"], "label": label,
                                        "phase": phase, "pair": pair, "sample": sample,
                                        "elapsed_ms": 10.0 if label == "baseline" else 5.0,
                                        "step_nrmse": [0.001] * (len(config["sigmas"]) - 1),
                                        "correctness": "PASS"})
    return tmp_path, settings, result


def assess(transcript):
    directory, settings, result = transcript
    (directory / "measurement/result.json").write_text(json.dumps(result), encoding="utf-8")
    return protocol.assess(directory, settings, {"status": "completed", "returncode": 0})


def test_complete_transcript_is_recomputed_and_bound_to_source(transcript):
    result = assess(transcript)
    assert result["status"] == "completed" and result["score"] == 2.0
    assert "measurement/identity.json" in result["evidence_files"]


@pytest.mark.parametrize("damage", ["partial", "missing_call", "duplicate_call", "median",
                                    "aggregate", "binding", "source", "step_error"])
def test_incomplete_or_changed_evidence_cannot_select_a_candidate(transcript, damage):
    directory, settings, original = transcript
    result = copy.deepcopy(original)
    if damage == "partial":
        result["score_scope"] = "selected_cases"
    elif damage == "missing_call":
        result["calls"].pop()
    elif damage == "duplicate_call":
        result["calls"].append(result["calls"][0])
    elif damage == "median":
        result["cases"][0]["candidate_median_ms"] = 1.0
    elif damage == "aggregate":
        result["speedup"] = 100.0
    elif damage == "binding":
        (directory / "candidate.py").write_text("different candidate\n", encoding="utf-8")
    elif damage == "source":
        (directory / "measurement/snapshot/baseline.py").write_text("changed\n", encoding="utf-8")
    else:
        result["calls"][0]["step_nrmse"] = [1.0]
    with pytest.raises(ValueError):
        assess((directory, settings, result))
