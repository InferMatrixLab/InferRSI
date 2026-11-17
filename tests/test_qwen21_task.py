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
    candidate = tmp_path / "candidate.py"
    shutil.copyfile(str(TASK.joinpath("baseline.py")), candidate)

    def fail(args, output, record):
        record["phase"] = phase
        exception = worker.OutputValidationError if explicit_check else RuntimeError
        raise exception(
            "Synthetic output rejection" if explicit_check else "Synthetic driver error")

    monkeypatch.setattr(worker, "run", fail)
    output = tmp_path / "measurement"
    monkeypatch.setattr(sys, "argv", [
        "benchmark.py", "--candidate", str(candidate),
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


@pytest.mark.parametrize("candidate,baseline_verified,module,expected", [
    (True, True, "tbe", True),
    (True, True, "tbe.common", True),
    (False, True, "tbe", False),
    (True, False, "tbe", False),
    (True, True, "torch_npu", False),
    (True, True, "tbe_other", False),
    (True, True, None, False),
])
def test_optional_dependency_classification_requires_candidate_and_verified_baseline(
    candidate, baseline_verified, module, expected,
):
    worker = load("benchmark")
    original = ModuleNotFoundError("Synthetic missing dependency", name=module)

    def compute(*args, **kwargs):
        raise original

    exception = worker.CandidateDependencyError if expected else ModuleNotFoundError
    with pytest.raises(exception) as caught:
        worker.invoke_compute(compute, (), {}, {}, candidate=candidate,
                              baseline_verified=baseline_verified)
    if expected:
        assert caught.value.__cause__ is original
        assert caught.value.module == module
    else:
        assert caught.value is original


@pytest.fixture
def dependency_failure(tmp_path, monkeypatch):
    """Exercise the actual worker receipt and task assessor without a device."""
    worker = load("benchmark")
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "def compute(*args, **kwargs):\n"
        "    raise ModuleNotFoundError('Synthetic missing TBE', name='tbe')\n",
        encoding="utf-8",
    )

    def run(args, output, record):
        record.update(phase="candidate_correctness", round_consumed=True)
        function = worker.candidate_function(output / "snapshot/candidate.py")
        # Controlled baseline precondition; this is a classification/lifecycle
        # regression, not evidence that a real NPU baseline executed.
        record["baseline_recheck"] = {"case": "smoke", "correctness": "PASS"}
        record["dependency_failure"] = {"case": "smoke"}
        record["calls"].append({"case": "smoke", "label": "baseline",
                                "phase": "recovery_check", "correctness": "PASS"})
        worker.invoke_compute(function, (), {}, {}, candidate=True, baseline_verified=True)

    monkeypatch.setattr(worker, "run", run)
    monkeypatch.setattr(sys, "argv", [
        "benchmark.py", "--candidate", str(candidate),
        "--output-dir", str(tmp_path / "measurement"),
        "--pairs", "1", "--samples", "1", "--warmups", "0",
    ])
    assert worker.main() == 2
    return tmp_path


def test_dependency_failure_retains_bound_sources_and_error(dependency_failure):
    assessment = load("optimization").assess(
        dependency_failure, {}, {"status": "failed", "returncode": 2})
    assert assessment["status"] == "candidate_failure"
    assert assessment["score"] is None and assessment["verdict"] == "FAIL"
    assert assessment["failure_kind"] == "unsupported_candidate_dependency"
    assert assessment["missing_module"] == "tbe"
    assert "measurement/snapshot/candidate.py" in assessment["evidence_files"]
    assert "measurement/error.log" in assessment["evidence_files"]


def test_dependency_rejection_requires_retained_baseline_recheck(dependency_failure):
    path = dependency_failure / "measurement/result.json"
    result = json.loads(path.read_bytes())
    result.pop("baseline_recheck")
    path.write_text(json.dumps(result), encoding="utf-8")
    assessment = load("optimization").assess(
        dependency_failure, {}, {"status": "failed", "returncode": 2})
    assert assessment["status"] == "infrastructure_failure"
    assert assessment["reason"] == "missing_baseline_recheck"


CANN_IMPORT_ERROR = (
    "SetPrecisionMode: NPU function error: "
    "at_npu::native::AclSetCompileopt(aclCompileOpt::ACL_PRECISION_MODE, precision_mode), "
    "error code is 500001\n"
    "Environment_Error_Import_Python_Module_Failed(EC0010): "
    "Failed to import Python module ModuleNotFoundError: No module named 'tbe'."
)


@pytest.mark.parametrize("message,candidate,verified,recognized", [
    (CANN_IMPORT_ERROR, True, True, True),
    (CANN_IMPORT_ERROR, False, True, False),
    (CANN_IMPORT_ERROR, True, False, False),
    (CANN_IMPORT_ERROR.replace("(EC0010)", "(EC9999)"), True, True, False),
    (CANN_IMPORT_ERROR.replace("'tbe'", "'torch_npu'"), True, True, False),
    (CANN_IMPORT_ERROR.replace("AclSetCompileopt", "DeviceSynchronize"), True, True, False),
    ("ACL error 500001; tbe", True, True, False),
])
def test_wrapped_cann_import_failure_requires_specific_diagnostic_and_baseline(
    message, candidate, verified, recognized,
):
    worker = load("benchmark")
    original = RuntimeError(message)

    def compute(*args, **kwargs):
        raise original

    with pytest.raises(RuntimeError) as caught:
        worker.invoke_compute(compute, (), {}, {}, candidate=candidate, baseline_verified=verified)
    assert isinstance(caught.value, worker.CandidateDependencyError) == recognized
    if recognized:
        assert caught.value.__cause__ is original
    else:
        assert caught.value is original


@pytest.mark.parametrize("break_baseline", [False, True])
def test_real_math_baseline_recheck_controls_dependency_rejection(tmp_path, break_baseline):
    pytest.importorskip("torch")
    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "import torch.nn.functional as F\n"
        "def broken(*args, **kwargs):\n    raise RuntimeError('Synthetic unhealthy baseline')\n"
        "def compute(latents, text, text_mask, sigmas, positions, params, *, config):\n"
        "    latents.zero_()\n    params['image_in'].zero_()\n"
        + ("    F.linear = broken\n" if break_baseline else "")
        + f"    raise RuntimeError({CANN_IMPORT_ERROR!r})\n", encoding="utf-8",
    )
    output = tmp_path / "measurement"
    execution = subprocess.run([
        sys.executable, str(TASK.joinpath("benchmark.py")), "--candidate", str(candidate),
        "--output-dir", str(output), "--device", "cpu", "--check-only", "--case", "smoke",
        "--pairs", "1", "--samples", "1", "--warmups", "0",
    ], capture_output=True, text=True, timeout=60)
    assert execution.returncode == (1 if break_baseline else 2), execution.stderr
    result = json.loads((output / "result.json").read_bytes())
    assert result["dependency_failure"]["module"] == "tbe"
    assert result["speedup"] is None
    assert result["status"] == ("infrastructure_failure" if break_baseline else "candidate_failure")
    if break_baseline:
        assert result["phase"] == "baseline_recovery_check"
        assert "baseline_recheck" not in result
        assert "Synthetic unhealthy baseline" in (output / "error.log").read_text()
    else:
        assert result["phase"] == "candidate_correctness"
        assert result["baseline_recheck"] == {"case": "smoke", "correctness": "PASS"}
        assert [call["phase"] for call in result["calls"]] == ["correctness", "recovery_check"]
    assessment = load("optimization").assess(
        tmp_path, {}, {"status": "failed", "returncode": execution.returncode})
    assert assessment["status"] == result["status"]


@pytest.mark.parametrize("status,code", [
    ("timeout", 2), ("cancelled", 2), ("error", 2), ("pending", None),
    ("failed", None), ("failed", -9), ("failed", 1), ("completed", 0),
    ("failed", True),
])
def test_written_candidate_failure_does_not_override_execution_failure(
    dependency_failure, status, code,
):
    assessment = load("optimization").assess(
        dependency_failure, {}, {"status": status, "returncode": code})
    assert assessment["status"] == "infrastructure_failure"
    assert assessment["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("relative", [
    "candidate.py", "measurement/snapshot/candidate.py", "measurement/snapshot/benchmark.py",
])
def test_candidate_rejection_cannot_resume_with_changed_sources(dependency_failure, relative):
    path = dependency_failure / relative
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="candidate|snapshot"):
        load("optimization").assess(
            dependency_failure, {}, {"status": "failed", "returncode": 2})


@pytest.mark.parametrize("phase", ["setup", "candidate_import", "baseline_correctness"])
def test_missing_tbe_outside_candidate_invocation_remains_infrastructure_failure(
    tmp_path, monkeypatch, phase,
):
    worker = load("benchmark")

    def fail(args, output, record):
        record["phase"] = phase
        raise ModuleNotFoundError("Synthetic missing TBE", name="tbe")

    monkeypatch.setattr(worker, "run", fail)
    monkeypatch.setattr(sys, "argv", [
        "benchmark.py", "--candidate", str(TASK.joinpath("baseline.py")),
        "--output-dir", str(tmp_path / "measurement"),
        "--pairs", "1", "--samples", "1", "--warmups", "0",
    ])
    assert worker.main() == 1
    result = json.loads((tmp_path / "measurement/result.json").read_text())
    assert result["status"] == "infrastructure_failure"
    assert result["correctness"] == "INCONCLUSIVE"
