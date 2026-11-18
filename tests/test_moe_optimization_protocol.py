"""No-device controls for the MoE iterative protocol and retained raw evidence."""

import copy
import hashlib
import json
import statistics
from pathlib import Path

import pytest

from inferrsi.harness import task_protocol
from tests.engineering_task_support import load_task_module

moe = load_task_module("moe-forward-npu", "benchmark")
protocol = load_task_module("moe-forward-npu", "optimization")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def transcript(tmp_path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def compute(*args, **kwargs): pass\n", encoding="utf-8")
    output = tmp_path / "measurement"
    identity = moe._prepare(candidate, output, 1)
    launcher = output / "runner/launch.py"
    launcher.write_bytes(protocol.LAUNCHER_SOURCE.encode("utf-8"))
    identity["runner/launch.py"] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    write(output / "identity.json", identity)
    task = json.loads((output / "task/task.json").read_text(encoding="utf-8"))
    measure = task["measurement"]
    cases = []
    for case in task["cases"]:
        if case["measured"]:
            samples = {"baseline": [12.0] * measure["samples_per_pair"],
                       "candidate": [6.0] * measure["samples_per_pair"]}
            cases.append({"id": case["id"], "baseline_median_ms": 12.0,
                          "candidate_median_ms": 6.0, "speedup": 2.0,
                          "samples_ms": samples})
    summary = {"completed": True, "correctness": "PASS", "cases": cases, "speedup": 2.0,
               "aggregation": "geometric_mean_case_speedups",
               "measurement_protocol":
                   "shape-matched-different-values-warmup-both-labels-before-paired-timing",
               "metrics": {"suite_latency_ms": 18.0}}
    for rank in (0, 1):
        calls, samples = [], []
        for index, case in enumerate(task["cases"]):
            base = 100000 + index * 10000
            phases = [(base + i, "correctness", "standard", None, None) for i in range(2)]
            if case["measured"]:
                phases += [(base + 10 + i, "warmup", "standard", None, None)
                           for i in range(measure["warmups"])]
                for sample in range(measure["samples_per_pair"]):
                    phases += [(base + 100 + sample, "shape_warmup", "shape_warmup", 0, sample),
                               (base + 100 + sample, "measurement", "standard", 0, sample)]
            for seed, phase, variant, pair, sample in phases:
                for label in ("baseline", "candidate"):
                    latency = (10.0 + 2 * rank) / (2 if label == "candidate" else 1)
                    call = {"case_id": case["id"], "seed": seed, "label": label,
                            "phase": phase, "variant": variant, "pair": pair, "sample": sample,
                            "included_in_score": phase == "measurement", "all_ranks_correct": True,
                            "local_elapsed_ms": latency, "input_sha256": f"{rank}-{seed}-{variant}",
                            "checks": {key: True for key in ("shape_dtype_device", "finite",
                                       "values", "nrmse_pass", "input_parameters_preserved")}}
                    calls.append(call)
                    if phase == "measurement":
                        samples.append({key: call[key] for key in (
                            "case_id", "seed", "label", "pair", "sample", "local_elapsed_ms",
                            "input_sha256")})
                        samples[-1]["slowest_rank_elapsed_ms"] = (
                            6.0 if label == "candidate" else 12.0)
        write(output / f"results/rank-{rank}.json", {
            "rank": rank, "completed": True, "correctness": "PASS", "phase": "completed",
            "calls": calls, "samples": samples, "cases": cases, "speedup": 2.0,
        })
    write(output / "results/summary.json", summary)
    inner = {"status": "completed", "returncode": 0, "metric": 18.0, "metric_error": None}
    write(output / "execution/execution.json", inner)
    settings = {"pairs": 1, "timeout_seconds": 900.0}
    guard = {"verified": True, "remaining": [], "signalled_pids": []}
    result = protocol._adjudicate(output, inner, guard, identity, 1)
    result.update(pairs=1, timeout_seconds=900.0, elapsed_seconds=2.0)
    write(output / "result.json", result)
    return tmp_path, settings


def assess(transcript, **changes):
    directory, settings = transcript
    return protocol.assess(directory, settings, {"status": "completed", "returncode": 0, **changes})


def document(transcript, name):
    path = transcript[0] / "measurement" / name
    return path, json.loads(path.read_text(encoding="utf-8"))


def rejection(transcript, *, cleanup=True, inner_status="failed", inner_code=1):
    for rank in (0, 1):
        path, value = document(transcript, f"results/rank-{rank}.json")
        value.update(completed=False, correctness="INCONCLUSIVE", error="candidate exception",
                     phase="candidate_import", calls=[], samples=[])
        write(path, value)
    inner = {"status": inner_status, "returncode": inner_code, "metric": None}
    directory, settings = transcript
    output = directory / "measurement"
    write(output / "execution/execution.json", inner)
    identity = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    result = protocol._adjudicate(output, inner, {"verified": cleanup}, identity, settings["pairs"])
    result.update(pairs=1, timeout_seconds=900.0)
    write(output / "result.json", result)


def test_complete_raw_result_runs_in_isolated_protocol_child(transcript):
    directory, settings = transcript
    source = Path(protocol.__file__)
    result = task_protocol.run(source.parent, hashlib.sha256(source.read_bytes()).hexdigest(),
                               "assess", directory=directory, settings=settings,
                               execution={"status": "completed", "returncode": 0})
    assert result["status"] == "completed" and result["score"] == 2.0
    assert result["quality_passed"] is True
    assert len(result["case_metrics"]) == 3
    for name in ("results/rank-0.json", "results/rank-1.json", "results/summary.json",
                 "execution/execution.json", "task/optimization.py", "candidate/implementation.py"):
        assert "measurement/" + name in result["evidence_files"]


@pytest.mark.parametrize("arguments", [
    ["--pairs", "0", "--timeout-seconds", "10"],
    ["--pairs", "1", "--timeout-seconds", "nan"],
    ["--pairs", "1", "--timeout-seconds", "inf"],
])
def test_invalid_sampling_or_time_budget_is_rejected(arguments):
    with pytest.raises(ValueError):
        protocol.validate_arguments(arguments)


def test_arguments_bind_retained_candidate_and_output(tmp_path):
    settings = protocol.validate_arguments(["--pairs", "2", "--timeout-seconds", "900"])
    candidate, output = tmp_path / "candidate.py", tmp_path / "measurement"
    assert protocol.arguments(candidate, output, settings) == [
        "--candidate", str(candidate), "--output-dir", str(output),
        "--pairs", "2", "--timeout-seconds", "900.0",
    ]


def test_protocol_prepares_without_device_imports_and_reuses_frozen_arguments(tmp_path):
    frozen = tmp_path / "frozen"
    prepared = task_protocol.prepare(Path(protocol.__file__).parent, frozen,
                                     ["--pairs", "2", "--timeout-seconds", "900"])
    assert prepared["evaluation_settings"] == {"pairs": 2, "timeout_seconds": 900.0}
    assert set(protocol.TASK_FILES) <= prepared["frozen_files"].keys()
    arguments = task_protocol.run(
        frozen, prepared["frozen_files"]["optimization.py"], "arguments",
        candidate=tmp_path / "retained.py", output=tmp_path / "measurement",
        settings=prepared["evaluation_settings"],
    )
    assert arguments[:4] == ["--candidate", str(tmp_path / "retained.py"),
                              "--output-dir", str(tmp_path / "measurement")]


def test_partial_case_selection_is_not_an_iterative_protocol_option():
    with pytest.raises(SystemExit) as error:
        protocol.validate_arguments(["--pairs", "1", "--timeout-seconds", "900",
                                     "--case", "balanced-small"])
    assert error.value.code == 2


@pytest.mark.parametrize("damage", ["candidate", "task", "missing_identity", "extra_identity",
                                    "request", "launcher", "pairs", "timeout", "inner_receipt",
                                    "missing_rank", "missing_call", "duplicate_sample",
                                    "rank_max", "summary", "aggregate"])
def test_partial_drifted_or_forged_result_cannot_select_candidate(transcript, damage):
    directory, _ = transcript
    if damage == "candidate":
        (directory / "candidate.py").write_text("different candidate\n", encoding="utf-8")
    elif damage in ("task", "launcher"):
        name = "task/baseline.py" if damage == "task" else "runner/launch.py"
        (directory / "measurement" / name).write_text("modified\n", encoding="utf-8")
    elif damage in ("missing_identity", "extra_identity", "request"):
        path, value = document(transcript, "identity.json")
        if damage == "missing_identity":
            value.pop("runner/grade.py")
        elif damage == "extra_identity":
            value["../candidate.py"] = value["candidate/implementation.py"]
        else:
            request = directory / "measurement/request.json"
            write(request, {"repetitions": 2})
            value["request.json"] = hashlib.sha256(request.read_bytes()).hexdigest()
        write(path, value)
    elif damage in ("pairs", "timeout", "aggregate"):
        path, value = document(transcript, "result.json")
        value[{"pairs": "pairs", "timeout": "timeout_seconds", "aggregate": "speedup"}[damage]] = 99
        write(path, value)
    elif damage == "inner_receipt":
        path, value = document(transcript, "execution/execution.json")
        value["returncode"] = 2
        write(path, value)
    elif damage == "missing_rank":
        (directory / "measurement/results/rank-1.json").unlink()
    elif damage == "summary":
        path, value = document(transcript, "results/summary.json")
        value["speedup"] = 99
        write(path, value)
    else:
        path, value = document(transcript, "results/rank-1.json")
        if damage == "missing_call":
            value["calls"].pop()
        elif damage == "duplicate_sample":
            value["samples"].append(copy.deepcopy(value["samples"][0]))
        else:
            value["samples"][0]["slowest_rank_elapsed_ms"] = 100.0
        write(path, value)
    with pytest.raises(ValueError):
        assess(transcript)


@pytest.mark.parametrize("status,code", [("timeout", 0), ("cancelled", -9), ("error", None),
                                        ("failed", 2), ("completed", True)])
def test_outer_execution_failure_cannot_reuse_successful_result(transcript, status, code):
    result = assess(transcript, status=status, returncode=code)
    assert result["status"] == "infrastructure_failure" and result["score"] is None


def test_completed_candidate_rejection_remains_a_consumed_failed_round(transcript):
    rejection(transcript)
    result = assess(transcript, status="failed", returncode=2)
    assert result["status"] == "candidate_failure" and result["verdict"] == "FAIL"
    assert result["round_consumed"] and result["score"] is None


@pytest.mark.parametrize("cleanup,status,code", [(False, "failed", 1), (True, "timeout", None),
                                               (True, "failed", -9)])
def test_rejection_cannot_resume_after_unknown_cleanup_or_interruption(
    transcript, cleanup, status, code
):
    rejection(transcript, cleanup=cleanup, inner_status=status, inner_code=code)
    result = assess(transcript, status="failed", returncode=2)
    assert result["status"] == "infrastructure_failure" and result["score"] is None
    assert result["round_consumed"]


@pytest.mark.parametrize("damage", ["missing", "invalid_rank"])
def test_missing_rank_cannot_make_a_resumable_rejection(transcript, damage):
    rejection(transcript)
    directory, settings = transcript
    output = directory / "measurement"
    if damage == "missing":
        (output / "results/rank-1.json").unlink()
    else:
        path, record = document(transcript, "results/rank-1.json")
        record["rank"] = True
        write(path, record)
    _, value = document(transcript, "result.json")
    identity = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    value = protocol._adjudicate(output, value["execution"], value["process_cleanup"],
                                identity, settings["pairs"])
    value.update(pairs=1, timeout_seconds=900.0)
    write(output / "result.json", value)
    result = assess(transcript, status="failed", returncode=2)
    assert result["status"] == "infrastructure_failure" and result["score"] is None


def test_median_is_recomputed_from_both_rank_samples(transcript):
    result = assess(transcript)
    for case in result["case_metrics"]:
        assert case["candidate_median_ms"] == statistics.median(case["samples_ms"]["candidate"])
        assert case["baseline_median_ms"] == 12.0  # rank zero alone was 10 ms
