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


@pytest.mark.parametrize("source", [
    "def compute(:\n",
    "VALUE = 1\n",
    "def compute(x):\n    return x\n",
    "compute = iter\n",
    "def compute(*args, **kwargs):\n    pass\ncompute.__wrapped__ = compute\n",
])
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
    ("candidate_import", False, "infrastructure_failure"),
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


SHAPE_ERRORS = {
    "shapes cannot be multiplied": "mm: mat1 and mat2 shapes cannot be multiplied (4x8 and 16x16)",
    "must match the size of tensor": (
        "The size of tensor a (4) must match the size of tensor b (5) "
        "at non-singleton dimension 0"),
    "is invalid for input of size": "shape '[3, 5]' is invalid for input of size 16",
    "Sizes of tensors must match": (
        "Sizes of tensors must match except in dimension 1. "
        "Expected size 4 but got size 5 for tensor number 1 in the list."),
}
DEVICE_SYNC_ERROR = (
    "NPU function error: c10_npu::acl::AclrtSynchronizeDeviceWithTimeout(), "
    "error code is 507035\n"
    "EZ9999: Inner Error! The error from device(chipId:0, dieId:0), aicore exception occurred."
)
DEVICE_SHAPE_ERROR = (
    "EZ9999: Inner Error! The size of tensor a (4) must match the size of tensor b (5) "
    "at non-singleton dimension 0 [ERROR] NPU function error"
)
# Device/backend reports that carry a complete shape message inside other wording,
# without a known device marker. Their source is unproven: never attributed.
DEVICE_LOST_SHAPE_ERROR = "device lost: " + SHAPE_ERRORS["must match the size of tensor"]
BACKEND_SHAPE_ERROR = "backend device unavailable: " + SHAPE_ERRORS["shapes cannot be multiplied"]


@pytest.mark.parametrize("exception,message,candidate,verified,diagnostic", [
    *[(RuntimeError, message, True, True, fragment) for fragment, message in SHAPE_ERRORS.items()],
    # Older PyTorch omits the operator prefix; inferred and empty view shapes.
    (RuntimeError, "mat1 and mat2 shapes cannot be multiplied (4x8 and 16x16)", True, True,
     "shapes cannot be multiplied"),
    (RuntimeError, "shape '[-1, 5]' is invalid for input of size 16", True, True,
     "is invalid for input of size"),
    (RuntimeError, "shape '[0, -1]' is invalid for input of size 16", True, True,
     "is invalid for input of size"),
    (RuntimeError, "shape '[]' is invalid for input of size 2", True, True,
     "is invalid for input of size"),
    # A shape message inside other wording has no host-check provenance.
    (RuntimeError, DEVICE_LOST_SHAPE_ERROR, True, True, None),
    (RuntimeError, BACKEND_SHAPE_ERROR, True, True, None),
    (RuntimeError, SHAPE_ERRORS["is invalid for input of size"] + " (device lost)", True, True,
     None),
    (RuntimeError, SHAPE_ERRORS["Sizes of tensors must match"] + "\nbackend unavailable", True,
     True, None),
    (RuntimeError, "aten: " + SHAPE_ERRORS["shapes cannot be multiplied"], True, True, None),
    # Complete messages whose reported sizes do not actually conflict.
    (RuntimeError, "mm: mat1 and mat2 shapes cannot be multiplied (4x8 and 8x16)", True, True,
     None),
    (RuntimeError, "The size of tensor a (1) must match the size of tensor b (5) "
     "at non-singleton dimension 0", True, True, None),
    (RuntimeError, "shape '[3, 5]' is invalid for input of size 15", True, True, None),
    (RuntimeError, "shape '[-1, 5]' is invalid for input of size 15", True, True, None),
    (RuntimeError, "shape '[-1, -1]' is invalid for input of size 16", True, True, None),
    (RuntimeError, "Sizes of tensors must match except in dimension 1. Expected size 4 "
     "but got size 4 for tensor number 1 in the list.", True, True, None),
    (RuntimeError, SHAPE_ERRORS["shapes cannot be multiplied"], False, True, None),
    (RuntimeError, SHAPE_ERRORS["shapes cannot be multiplied"], True, False, None),
    (RuntimeError, DEVICE_SHAPE_ERROR, True, True, None),
    (RuntimeError, SHAPE_ERRORS["is invalid for input of size"] + " (ACL error 507015)", True,
     True, None),
    (RuntimeError, SHAPE_ERRORS["Sizes of tensors must match"] + " after synchronization", True,
     True, None),
    (RuntimeError, SHAPE_ERRORS["must match the size of tensor"] + " in torch_npu.npu_rotary_mul",
     True, True, None),
    (RuntimeError, "[ERROR] (Device:0) ERR01002 OPS " + SHAPE_ERRORS["shapes cannot be multiplied"],
     True, True, None),
    (RuntimeError, DEVICE_SYNC_ERROR, True, True, None),
    (RuntimeError, "Synthetic driver error", True, True, None),
    (RuntimeError, "Expected size for first two dimensions of batch2 tensor", True, True, None),
    (ValueError, SHAPE_ERRORS["shapes cannot be multiplied"], True, True, None),
])
def test_candidate_contract_diagnostic_requires_recognized_message_and_verified_baseline(
    exception, message, candidate, verified, diagnostic,
):
    worker = load("benchmark")
    original = exception(message)

    def compute(*args, **kwargs):
        raise original

    with pytest.raises(exception) as caught:
        worker.invoke_compute(compute, (), {}, {}, candidate=candidate, baseline_verified=verified)
    if diagnostic:
        assert isinstance(caught.value, worker.CandidateComputeContractError)
        assert caught.value.__cause__ is original
        assert caught.value.diagnostic == diagnostic
        assert caught.value.details() == {"diagnostic": diagnostic, "error": message}
    else:
        assert caught.value is original


def test_host_shape_templates_match_installed_torch_shape_diagnostics():
    torch = pytest.importorskip("torch")
    worker = load("benchmark")
    failures = {
        "shapes cannot be multiplied": lambda: torch.ones(4, 8) @ torch.ones(16, 16),
        "must match the size of tensor": lambda: torch.ones(4) + torch.ones(5),
        "is invalid for input of size": lambda: torch.ones(16).view(3, 5),
        "Sizes of tensors must match": lambda: torch.cat([torch.ones(4, 2), torch.ones(5, 3)], 1),
    }
    assert set(failures) == set(worker.HOST_SHAPE_DIAGNOSTICS)
    for fragment, failure in failures.items():
        with pytest.raises(worker.CandidateComputeContractError) as caught:
            worker.invoke_compute(lambda *args, **kwargs: failure(), (), {}, {},
                                  candidate=True, baseline_verified=True)
        assert caught.value.diagnostic == fragment
        assert type(caught.value.__cause__) is RuntimeError

    # Core PyTorch Python frames below the submitted call and a decorated entry
    # keep the submitted file as the nearest non-torch caller.
    @torch.inference_mode()
    def decorated(*args, **kwargs):
        return torch.broadcast_tensors(torch.ones(4), torch.ones(5))

    with pytest.raises(worker.CandidateComputeContractError) as caught:
        worker.invoke_compute(decorated, (), {}, {}, candidate=True, baseline_verified=True)
    assert caught.value.diagnostic == "must match the size of tensor"
    frames = []
    trace = caught.value.__cause__.__traceback__
    while trace is not None:
        frames.append(trace.tb_frame.f_code.co_filename)
        trace = trace.tb_next
    assert frames[-1].endswith("functional.py")


def test_contract_attribution_requires_plain_error_raised_by_submitted_source(tmp_path):
    """The complete message alone is not enough; the error itself must be attributable."""
    worker = load("benchmark")
    message = SHAPE_ERRORS["must match the size of tensor"]

    class BackendError(RuntimeError):
        pass

    def subclass(*args, **kwargs):
        raise BackendError(message)

    def chained(*args, **kwargs):
        raise RuntimeError(message) from OSError("device lost")

    def during_other_failure(*args, **kwargs):
        try:
            raise OSError("backend device unavailable")
        except OSError:
            raise RuntimeError(message)

    # A runtime wrapper outside the submission and outside core PyTorch raises it.
    runtime = {}
    exec(compile(f"def launch():\n    raise RuntimeError({message!r})\n",
                 str(tmp_path / "torch_npu" / "runtime.py"), "exec"), runtime)

    def foreign(*args, **kwargs):
        runtime["launch"]()

    def direct(*args, **kwargs):
        raise RuntimeError(message)

    for compute in (subclass, chained, during_other_failure, foreign):
        with pytest.raises(RuntimeError) as caught:
            worker.invoke_compute(compute, (), {}, {}, candidate=True, baseline_verified=True)
        assert not isinstance(caught.value, worker.CandidateRecheckedError), compute.__name__
    with pytest.raises(worker.CandidateComputeContractError):
        worker.invoke_compute(direct, (), {}, {}, candidate=True, baseline_verified=True)


CANDIDATE_HEADER = (
    "import torch\n"
    "def compute(latents, text, text_mask, sigmas, positions, params, *, config):\n"
)


def run_cpu_worker(tmp_path, body):
    """Run the real worker on the trusted CPU baseline math; no device is involved."""
    candidate = tmp_path / "candidate.py"
    candidate.write_text(CANDIDATE_HEADER + body, encoding="utf-8")
    output = tmp_path / "measurement"
    execution = subprocess.run([
        sys.executable, str(TASK.joinpath("benchmark.py")), "--candidate", str(candidate),
        "--output-dir", str(output), "--device", "cpu", "--check-only", "--case", "smoke",
        "--pairs", "1", "--samples", "1", "--warmups", "0",
    ], capture_output=True, text=True, timeout=60)
    return execution, json.loads((output / "result.json").read_bytes()), output


# Genuine candidate bugs, raised by PyTorch's host-side shape checks on real inputs.
CANDIDATE_SHAPE_BUGS = {
    "shapes cannot be multiplied": "    return latents.flatten(0, 1) @ latents.flatten(0, 1)\n",
    "is invalid for input of size": "    return latents.view(-1, latents.shape[-1] + 1)\n",
}


@pytest.fixture
def contract_failure(tmp_path):
    pytest.importorskip("torch")
    execution, _, _ = run_cpu_worker(tmp_path, CANDIDATE_SHAPE_BUGS["shapes cannot be multiplied"])
    assert execution.returncode == 2, execution.stderr
    return tmp_path


@pytest.mark.parametrize("diagnostic", sorted(CANDIDATE_SHAPE_BUGS))
def test_attributable_candidate_shape_error_consumes_one_round_after_baseline_recheck(
    tmp_path, diagnostic,
):
    pytest.importorskip("torch")
    execution, result, output = run_cpu_worker(tmp_path, CANDIDATE_SHAPE_BUGS[diagnostic])
    assert execution.returncode == 2, execution.stderr
    assert result["status"] == "candidate_failure" and result["correctness"] == "FAIL"
    assert result["round_consumed"] and result["speedup"] is None
    assert result["phase"] == "candidate_correctness"
    assert result["failure_kind"] == "rejected_candidate_contract"
    assert "missing_module" not in result and "dependency_failure" not in result
    assert result["contract_failure"]["case"] == "smoke"
    assert result["contract_failure"]["phase"] == "candidate_correctness"
    assert result["contract_failure"]["diagnostic"] == diagnostic
    assert diagnostic in result["contract_failure"]["error"]
    assert result["baseline_recheck"] == {"case": "smoke", "correctness": "PASS"}
    # Exactly one consumed candidate call: the baseline passed, the candidate raised,
    # and only the trusted baseline was retried once on pristine inputs.
    assert [(call["label"], call["phase"]) for call in result["calls"]] == [
        ("baseline", "correctness"), ("baseline", "recovery_check")]
    log = (output / "error.log").read_text()
    assert "CandidateComputeContractError" in log and diagnostic in log
    assessment = load("optimization").assess(
        tmp_path, {}, {"status": "failed", "returncode": execution.returncode})
    assert assessment["status"] == "candidate_failure" and assessment["verdict"] == "FAIL"
    assert assessment["score"] is None and assessment["quality_passed"] is False
    assert assessment["failure_kind"] == "rejected_candidate_contract"
    assert assessment["missing_module"] is None
    for name in ("measurement/snapshot/candidate.py", "measurement/snapshot/benchmark.py",
                 "measurement/identity.json", "measurement/error.log"):
        assert name in assessment["evidence_files"]


BLOCKING_COMPUTE_FAILURES = {
    # The candidate breaks the trusted baseline math before its own shape bug.
    "baseline_recheck_failure": (
        "    import torch.nn.functional as F\n"
        "    def broken(*args, **kwargs):\n"
        "        raise RuntimeError('Synthetic unhealthy baseline')\n"
        "    F.linear = broken\n"
        + CANDIDATE_SHAPE_BUGS["shapes cannot be multiplied"]),
    "device_synchronize_failure": f"    raise RuntimeError({DEVICE_SYNC_ERROR!r})\n",
    "device_reported_shape_error": f"    raise RuntimeError({DEVICE_SHAPE_ERROR!r})\n",
    "device_lost_shape_error": f"    raise RuntimeError({DEVICE_LOST_SHAPE_ERROR!r})\n",
    "backend_unavailable_shape_error": f"    raise RuntimeError({BACKEND_SHAPE_ERROR!r})\n",
}
BLOCKING_LOG_TEXT = {
    "device_synchronize_failure": "EZ9999",
    "device_reported_shape_error": "EZ9999",
    "device_lost_shape_error": "device lost",
    "backend_unavailable_shape_error": "backend device unavailable",
}


@pytest.mark.parametrize("failure", sorted(BLOCKING_COMPUTE_FAILURES))
def test_device_sync_or_recheck_failure_in_candidate_compute_stays_inconclusive(
    tmp_path, failure,
):
    pytest.importorskip("torch")
    execution, result, output = run_cpu_worker(tmp_path, BLOCKING_COMPUTE_FAILURES[failure])
    assert execution.returncode == 1, execution.stderr
    assert result["status"] == "infrastructure_failure"
    assert result["correctness"] == "INCONCLUSIVE" and result["speedup"] is None
    assert "baseline_recheck" not in result and "failure_kind" not in result
    if failure == "baseline_recheck_failure":
        assert result["phase"] == "baseline_recovery_check"
        assert result["contract_failure"]["diagnostic"] == "shapes cannot be multiplied"
        assert "Synthetic unhealthy baseline" in (output / "error.log").read_text()
        assert [call["phase"] for call in result["calls"]] == ["correctness"]
    else:
        # The baseline was healthy, so a wrongly attributed error would have passed
        # the recheck and consumed the round; unproven source never starts the recheck.
        assert result["phase"] == "candidate_correctness"
        assert "contract_failure" not in result
        assert BLOCKING_LOG_TEXT[failure] in (output / "error.log").read_text()
        assert [(call["label"], call["phase"], call["correctness"])
                for call in result["calls"]] == [("baseline", "correctness", "PASS")]
    assessment = load("optimization").assess(
        tmp_path, {}, {"status": "failed", "returncode": execution.returncode})
    assert assessment["status"] == "infrastructure_failure"
    assert assessment["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("tamper", ["drop_recheck", "drop_recheck_call", "other_case"])
def test_contract_rejection_requires_retained_baseline_recheck(contract_failure, tamper):
    path = contract_failure / "measurement/result.json"
    result = json.loads(path.read_bytes())
    if tamper == "drop_recheck":
        result.pop("baseline_recheck")
    elif tamper == "drop_recheck_call":
        result["calls"] = [call for call in result["calls"] if call["phase"] != "recovery_check"]
    else:
        result["contract_failure"]["case"] = "compact"
    path.write_text(json.dumps(result), encoding="utf-8")
    assessment = load("optimization").assess(
        contract_failure, {}, {"status": "failed", "returncode": 2})
    assert assessment["status"] == "infrastructure_failure"
    assert assessment["verdict"] == "INCONCLUSIVE"
    assert assessment["reason"] == "missing_baseline_recheck"


@pytest.mark.parametrize("failure", [
    "candidate_contract", "device_synchronize_failure", "device_lost_shape_error",
    "backend_unavailable_shape_error",
])
def test_harness_continues_only_after_attributed_contract_rejection(tmp_path, failure):
    """Round 1 is the real CPU worker and Qwen assessor; later rows are synthetic stand-ins."""
    pytest.importorskip("torch")
    from inferrsi.apps.artifacts import atomic_write_json, sha256
    from inferrsi.harness import optimization
    from tests.diagnosis_support import diagnosis_evidence

    root = tmp_path / "campaign"
    (root / "frozen").mkdir(parents=True)
    shutil.copyfile(str(TASK.joinpath("baseline.py")), root / "frozen/baseline.py")
    optimization.initialize(root, {
        "schema_version": 2, "task": "qwen21-attribution-control", "task_source": "project",
        "condition": "test", "candidate_kind": "file", "candidate_name": "candidate.py",
        "baseline_path": "frozen/baseline.py", "working_candidate": "candidate.py",
        "round_mode": "exact", "round_limit": 2, "max_seconds": 600,
        "final_reserve_seconds": 60,
        "selection": {"direction": "maximize", "metric": "speedup", "initial_score": 1.0},
        "evaluation_settings": {"metric_key": "speedup", "direction": "maximize"},
        "frozen_files": {"baseline.py": sha256(root / "frozen/baseline.py")},
    })
    optimization.record_diagnosis(root, "Synthetic attribution control",
                                  diagnosis_evidence(root))
    worker_body = (CANDIDATE_SHAPE_BUGS["shapes cannot be multiplied"]
                   if failure == "candidate_contract" else BLOCKING_COMPUTE_FAILURES[failure])

    def execute(root, directory, plan, deadline):
        (directory / "execution").mkdir()
        if directory.parent.name == "round-01":
            process = subprocess.run([
                sys.executable, str(TASK.joinpath("benchmark.py")),
                "--candidate", str(directory / "candidate.py"),
                "--output-dir", str(directory / "measurement"), "--device", "cpu",
                "--check-only", "--case", "smoke", "--pairs", "1", "--samples", "1",
                "--warmups", "0",
            ], capture_output=True, text=True, timeout=60)
            execution = {"status": "completed" if process.returncode == 0 else "failed",
                         "returncode": process.returncode, "elapsed_seconds": 1}
        else:
            execution = {"status": "completed", "returncode": 0, "elapsed_seconds": 1}
        atomic_write_json(directory / "execution/execution.json", execution)
        return execution

    def assess(root, directory, plan, execution):
        if directory.parent.name == "round-01":
            return load("optimization").assess(directory, {}, execution)
        # A completed Qwen score needs an NPU; this row only exercises continuation.
        return {"status": "completed", "score": 2.0, "baseline_score": 1.0, "verdict": "PASS",
                "quality_passed": True, "reason": "Synthetic continuation stand-in"}

    candidate = root / "candidate.py"
    candidate.write_text(CANDIDATE_HEADER + worker_body, encoding="utf-8")
    view = optimization.evaluate_round(root, candidate=candidate, hypothesis="Shape bug",
                                       usage=None, execute=execute, assess=assess)
    state = json.loads((root / "state.json").read_text())
    first = state["rounds"][0]
    assert len(state["rounds"]) == 1 and state["best"]["kind"] == "baseline"
    assert first["assessment"]["score"] is None
    if failure != "candidate_contract":
        # Never charged as a candidate FAIL: the session blocks before any next round or final.
        assert first["assessment"]["status"] == "infrastructure_failure"
        assert first["assessment"]["verdict"] == "INCONCLUSIVE"
        assert state["state"] == "blocked"
        for final in (False, True):
            with pytest.raises(ValueError, match="blocked"):
                optimization.evaluate_round(
                    root, candidate=candidate, hypothesis="Next", usage=None,
                    execute=execute, assess=assess, final=final, reason="stop")
        return
    assert first["assessment"]["status"] == "candidate_failure"
    assert first["assessment"]["failure_kind"] == "rejected_candidate_contract"
    assert state["state"] == "active", view
    candidate.write_text(TASK.joinpath("baseline.py").read_text(encoding="utf-8")
                         + "# Repaired shape contract\n", encoding="utf-8")
    optimization.evaluate_round(root, candidate=candidate, hypothesis="Repaired",
                                usage=None, execute=execute, assess=assess)
    optimization.evaluate_round(root, candidate=None, hypothesis="Independent final",
                                usage=None, execute=execute, assess=assess, final=True)
    state = json.loads((root / "state.json").read_text())
    assert [row["assessment"]["status"] for row in state["rounds"]] == [
        "candidate_failure", "completed"]
    assert state["best"]["candidate_id"] == "candidate-002"
    assert state["final"]["assessment"]["status"] == "completed"
    assert state["state"] == "completed"
