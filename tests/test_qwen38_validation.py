"""Synthetic evidence tests; these never qualify Qwen or a GPU."""

import json
import sys
from pathlib import Path

import pytest

from examples.qwen38_text.validate import digest, validate

np = pytest.importorskip("numpy")


@pytest.fixture
def trace_bundle(tmp_path):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    workload = tmp_path / "workload.json"
    manifest = tmp_path / "manifest.json"
    run = tmp_path / "run"
    cases = [{"id": "first", "max_steps": 2},
             {"id": "replay", "max_steps": 2, "replay_of": "first"}]
    write(workload, {"model_id": "Qwen/Qwen3.8-27B", "cases": cases})
    write(manifest, {"model_id": "Qwen/Qwen3.8-27B", "revision": "a" * 40})
    write(run / "run.lock.json", {"objective": "correctness", "repetitions": 1,
                                  "model_revision": "a" * 40, "workload_id": digest(workload)})
    write(run / "environment.json", {"requested_device_model": "Synthetic GPU"})
    for side, implementation in (("baseline", "transformers_full"),
                                 ("candidate", "transformers_cached")):
        root = run / side / "trial-001"
        root.mkdir(parents=True)
        outputs = []
        for case in cases:
            path = root / (case["id"] + ".npz")
            np.savez(path, logits=np.array([[1., 2., 3.], [3., 1., 2.]], dtype=np.float32))
            outputs.append({"id": case["id"], "input_ids": [1, 2],
                            "continuation_ids": [2, 0], "greedy_ids": [2, 0],
                            "logits_file": path.name, "logits_sha256": digest(path)})
        write(root / "result.json", {
            "schema_version": 1, "qualification_scope": "reference_self_check",
            "implementation": implementation, "model_id": "Qwen/Qwen3.8-27B",
            "model_revision": "a" * 40, "manifest_sha256": digest(manifest),
            "workload_sha256": digest(workload), "dtype": "bfloat16", "device_type": "cuda",
            "device_count": 1, "tokenization": "raw_text_no_special_tokens", "vocab_size": 3,
            "kernel_policy": {"hub_kernels": False, "full_attention": "eager",
                              "optional_modules": {"fla": False, "causal_conv1d": False}},
            "device_model": "Synthetic GPU", "versions": {"torch": "test", "transformers": "test"},
            "cases": outputs})
        write(root / "execution.json", {"status": "completed", "returncode": 0})
    return run, workload, manifest


def check(bundle):
    return validate(*bundle, max_nrmse=0.01, min_top1=0.99, rms_floor=1e-8)


def mutate_case(bundle, callback):
    path = bundle[0] / "candidate/trial-001/result.json"
    result = json.loads(path.read_text())
    callback(result)
    path.write_text(json.dumps(result))


def test_complete_synthetic_evidence_is_scope_limited(trace_bundle):
    result = check(trace_bundle)
    assert result["verdict"] == "PASS"
    assert result["qualification_scope"] == "reference_self_check"
    assert "No dedicated engine validated" in result["limitations"]


@pytest.mark.parametrize("mutation", [
    lambda r: r["cases"].pop(),
    lambda r: r["cases"].append(r["cases"][0]),
    lambda r: r.update(model_revision="b" * 40),
    lambda r: r.update(implementation="nano_vllm"),
    lambda r: r["cases"][0].update(input_ids=[42]),
    lambda r: r["cases"][0].update(logits_file="../../outside.npz"),
    lambda r: r["cases"][0].update(greedy_ids=[0, 0]),
    lambda r: r.update(dtype="float16"),
    lambda r: r["kernel_policy"]["optional_modules"].update(fla=True),
])
def test_missing_mismatched_and_wrong_scope_evidence_rejected(trace_bundle, mutation):
    mutate_case(trace_bundle, mutation)
    with pytest.raises(ValueError):
        check(trace_bundle)


def test_tampered_array_rejected(trace_bundle):
    path = trace_bundle[0] / "candidate/trial-001/first.npz"
    np.savez(path, logits=np.zeros((2, 3)))
    with pytest.raises(ValueError, match="hash"):
        check(trace_bundle)


def test_complete_numerical_regression_is_fail(trace_bundle):
    root = trace_bundle[0] / "candidate/trial-001"
    def alter(result):
        for case in result["cases"]:
            path = root / case["logits_file"]
            np.savez(path, logits=np.array([[3., 2., 1.], [1., 2., 3.]], dtype=np.float32))
            case.update(logits_sha256=digest(path), greedy_ids=[0, 2])
    mutate_case(trace_bundle, alter)
    assert check(trace_bundle)["verdict"] == "FAIL"


def test_nonfinite_is_incomplete_even_with_matching_hash(trace_bundle):
    root = trace_bundle[0] / "candidate/trial-001"
    def alter(result):
        path = root / result["cases"][0]["logits_file"]
        np.savez(path, logits=np.full((2, 3), np.nan, dtype=np.float32))
        result["cases"][0]["logits_sha256"] = digest(path)
    mutate_case(trace_bundle, alter)
    with pytest.raises(ValueError, match="nonfinite"):
        check(trace_bundle)


def test_replay_change_rejected_even_with_loose_numerical_gates(trace_bundle):
    root = trace_bundle[0] / "candidate/trial-001"
    def alter(result):
        path = root / result["cases"][1]["logits_file"]
        np.savez(path, logits=np.array([[1., 2., 3.01], [3., 1., 2.]], dtype=np.float32))
        result["cases"][1]["logits_sha256"] = digest(path)
    mutate_case(trace_bundle, alter)
    result = check(trace_bundle)
    assert result["verdict"] == "FAIL"
    assert any("reset/replay" in reason for reason in result["reasons"])


def test_synthetic_traces_complete_real_subprocess_loop(trace_bundle, tmp_path):
    from inferrsi.harness.runner import run_experiment
    from inferrsi.runspec import RunSpec

    fixture, workload, manifest = trace_bundle
    repo = tmp_path / "source"
    repo.mkdir()
    emit = (
        "import pathlib,shutil,sys; "
        "src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2]); "
        "shutil.copyfile(src/'result.json',dst); "
        "[shutil.copyfile(p,dst.parent/p.name) for p in src.glob('*.npz')]"
    )
    def command(side):
        return (sys.executable, "-c", emit, str(fixture / side / "trial-001"), "{result}")

    validator = Path(__file__).resolve().parents[1] / "examples/qwen38_text/validate.py"
    spec = RunSpec(
        repo=str(repo), objective="correctness", repetitions=1, max_minutes=1,
        model_revision="a" * 40, workload_id=digest(workload),
        baseline_command=command("baseline"), candidate_command=command("candidate"),
        validation_command=(sys.executable, str(validator), "--run-dir", "{run_dir}",
                            "--workload", str(workload), "--manifest", str(manifest),
                            "--max-nrmse", "0.01", "--min-top1", "0.99",
                            "--rms-floor", "1e-8", "--output", "{result}"),
        output_dir=str(tmp_path / "outputs"),
    )
    result_dir = run_experiment(
        spec, {"requested_device_model": "Synthetic GPU"},
        snapshot=lambda *_: {"available": True, "snapshot_hash": "synthetic-source"},
    )
    evaluation = json.loads((result_dir / "evaluation.json").read_text())
    assert evaluation["verdict"] == "PASS"
    assert evaluation["improvement_pct"] is None
    assert (result_dir / "report.html").exists()
    quality = json.loads((result_dir / "validation/result.json").read_text())
    assert quality["qualification_scope"] == "reference_self_check"
