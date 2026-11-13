"""Standalone resource and independent-reference regression checks."""

import importlib.util
import json
import shutil
import subprocess
import sys
from importlib.resources import files

import pytest

TASK = files("inferrsi.benchmark").joinpath("tasks", "qwen21-denoise-npu")


def load(name):
    path = TASK.joinpath(name + ".py")
    spec = importlib.util.spec_from_file_location("qwen21_test_" + name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_task_entry_can_be_copied_and_opened_without_engine_or_inferrsi(tmp_path):
    for name in (
        "benchmark.py",
        "baseline.py",
        "reference.py",
        "workload.py",
        "task.json",
        "TASK.md",
        "NOTICE.md",
        "LICENSE",
    ):
        shutil.copyfile(str(TASK.joinpath(name)), tmp_path / name)
    result = subprocess.run(
        [sys.executable, "-I", str(tmp_path / "benchmark.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "--candidate" in result.stdout and "--check-only" in result.stdout
    assert not list(tmp_path.glob("result.json"))


@pytest.mark.parametrize("case_id", ["smoke", "padded-batch"])
def test_cached_prefix_matches_full_joint_reference_after_weight_update(case_id):
    torch = pytest.importorskip("torch")
    workload, baseline, reference = (load(name) for name in ("workload", "baseline", "reference"))
    task = json.loads(TASK.joinpath("task.json").read_text(encoding="utf-8"))
    case = {**task["defaults"], **next(c for c in task["cases"] if c["id"] == case_id)}
    params = workload.parameters(case, 17, "cpu", torch.float32)
    inputs = workload.inputs(case, 29, "cpu", torch.float32)
    with torch.inference_mode():
        before = baseline.compute(*inputs, params, config=case)
        expected = reference.compute(*inputs, params, config=case)
        torch.testing.assert_close(before, expected, rtol=1e-5, atol=1e-6)
        params["image_out"].neg_()
        after = baseline.compute(*inputs, params, config=case)
        updated = reference.compute(*inputs, params, config=case)
        torch.testing.assert_close(after, updated, rtol=1e-5, atol=1e-6)
        assert not torch.allclose(before, after)


def test_standalone_import_guard_blocks_engine_names():
    guard = load("benchmark").EngineImportGuard()
    for name in ("vllm", "vllm_omni.diffusion", "diffusers", "transformers.models"):
        with pytest.raises(ModuleNotFoundError):
            guard.find_spec(name)
    assert guard.find_spec("torch_npu") is None


@pytest.mark.parametrize("source", ["def compute(:\n", "VALUE = 1\n",
                                        "def compute(x):\n    return x\n"])
def test_candidate_entry_contract_errors_consume_round_without_blocking(
    tmp_path, monkeypatch, source,
):
    worker = load("benchmark")
    candidate, output = tmp_path / "candidate.py", tmp_path / "measurement"
    candidate.write_text(source)

    def import_candidate(args, output, record):
        record.update(phase="candidate_import", round_consumed=True)
        worker.candidate_function(output / "snapshot/candidate.py")

    monkeypatch.setattr(worker, "run", import_candidate)
    monkeypatch.setattr(sys, "argv", [
        "benchmark.py", "--candidate", str(candidate), "--output-dir", str(output),
        "--pairs", "1", "--samples", "1", "--warmups", "0",
    ])
    assert worker.main() == 2
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == "candidate_failure" and result["round_consumed"]
    assert result["speedup"] is None
    assert load("optimization").assess(tmp_path, {}, {"status": "failed", "returncode": 2})[
        "status"] == "candidate_failure"


@pytest.mark.parametrize("phase,explicit_check,expected", [
    ("candidate_measurement", False, "infrastructure_failure"),
    ("candidate_correctness", True, "candidate_failure"),
    ("baseline_correctness", True, "infrastructure_failure"),
])
def test_unknown_runtime_errors_are_not_claimed_as_wrong_outputs(
    tmp_path, monkeypatch, phase, explicit_check, expected
):
    worker = load("benchmark")
    protocol = load("optimization")

    def fail(args, output, record):
        record["phase"] = phase
        exception = worker.OutputValidationError if explicit_check else RuntimeError
        raise exception(
            "Synthetic output rejection" if explicit_check else "Synthetic driver error")

    monkeypatch.setattr(worker, "run", fail)
    output = tmp_path / "measurement"
    monkeypatch.setattr(sys, "argv", [
        "benchmark.py", "--candidate", str(TASK.joinpath("baseline.py")),
        "--output-dir", str(output),
        "--device", "npu", "--pairs", "1", "--samples", "1", "--warmups", "0",
    ])
    code = worker.main()
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == expected
    verdict = "FAIL" if explicit_check and phase.startswith("candidate_") else "INCONCLUSIVE"
    assert result["correctness"] == verdict
    assessment = protocol.assess(tmp_path, {}, {"status": "failed", "returncode": code})
    assert assessment["status"] == expected
    assert assessment["verdict"] == verdict
