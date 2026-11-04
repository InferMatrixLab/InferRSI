"""Device-free contract controls; actual NPU execution is explicitly opted in."""

import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from inferrsi.harness.benchmarks import load_builtin_task, load_task
from inferrsi.harness.benchmarks.consumers import grade_artifact, run_action
from inferrsi.harness.benchmarks.npu_task import check_output, device_kernels, reference
from inferrsi.harness.skill_eval_benchmark import task_descriptor
from tools.npu_benchmark_validate import validation_passed


def test_discovery_has_no_torch_dependency_and_formal_cpu_path_refuses_npu():
    task = load_builtin_task("rmsnorm-npu")
    assert task.manifest["environment"]["backend"] == "ascend"
    subprocess.run([sys.executable, "-c", "import sys; "
                    "from inferrsi.harness.benchmarks import load_builtin_task; "
                    "load_builtin_task('rmsnorm-npu'); "
                    "assert 'torch' not in sys.modules and 'torch_npu' not in sys.modules"],
                   check=True)
    with pytest.raises(ValueError, match="CPU"):
        task_descriptor("rmsnorm-npu")


@pytest.mark.parametrize("field,value", [
    ("environment", {"backend": "cpu", "runtime": "numpy", "dtype": "float32"}),
    ("oracle.operation", "softmax"), ("measurement.boundary", "synchronous-compute-call"),
    ("workloads.0.layout", "strided"), ("workloads.0.shape", [2, 3, 4]),
])
def test_npu_contract_rejects_wrong_execution_semantics(field, value, tmp_path):
    root = tmp_path / "task"
    shutil.copytree(load_builtin_task("rmsnorm-npu").root, root)
    manifest = json.loads((root / "task.json").read_text(encoding="utf-8"))
    current = manifest
    parts = field.split(".")
    for key in parts[:-1]:
        current = current[int(key)] if isinstance(current, list) else current[key]
    current[parts[-1]] = value
    (root / "task.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_task(root)


def test_unallocated_device_is_inconclusive_without_import_or_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("ASCEND_RT_VISIBLE_DEVICES", raising=False)
    task = load_builtin_task("rmsnorm-npu")
    grade = grade_artifact(task, task.root / "candidate.py", tmp_path / "run", timeout_seconds=20)
    assert grade["verdict"] == "INCONCLUSIVE"
    result = json.loads((tmp_path / "run" / "result.json").read_text(encoding="utf-8"))
    assert result["error_type"] == "RuntimeError" and "metrics" not in result


def test_scalar_affine_oracle_preserves_epsilon_and_weight():
    np = pytest.importorskip("numpy")
    x = np.array([[0, 0], [1e-7, -1e-7]], dtype=np.float32)
    weight = np.array([2, -3], dtype=np.float32)
    y = reference(x, weight, 1e-5, np)
    np.testing.assert_allclose(y[0], [0, 0])
    np.testing.assert_allclose(y[1], [2e-7 / (1e-5 + 1e-14)**0.5,
                                     3e-7 / (1e-5 + 1e-14)**0.5], rtol=1e-6)


def test_profile_requires_hardware_kernel_records():
    launch = {"pid": 1, "ph": "X", "name": "npu_rms_norm", "cat": "cpu_op"}
    metadata = {"pid": 2, "name": "process_name", "args": {"name": "Ascend Hardware"}}
    flow = {"pid": 2, "ph": "f", "cat": "async_npu"}
    kernel = {"pid": 2, "ph": "X", "name": "RmsNorm", "dur": 5.0,
              "args": {"Task Type": "KERNEL_AIVEC"}}
    assert device_kernels([launch, metadata, flow]) == []
    assert device_kernels({"traceEvents": [launch, metadata, flow, kernel]}) == [kernel]


@pytest.mark.parametrize("status,code,passed,expected", [
    ("completed", 0, True, True), ("failed", 1, False, False),
    ("timeout", None, True, False), ("completed", 0, False, False),
])
def test_noop_qualification_requires_final_quality_pass(status, code, passed, expected):
    assert validation_passed({"execution_status": status, "returncode": code,
                              "result": {"status": "completed", "passed": passed}}) is expected


def test_changed_input_shape_and_broadcast_output_cannot_pass():
    np = pytest.importorskip("numpy")

    class Tensor:
        dtype = "float32"
        device = "npu:0"

        def __init__(self, array):
            self.array, self.shape = array, array.shape

        def cpu(self):
            return self

        def detach(self):
            return self

        def numpy(self):
            return self.array

        def is_contiguous(self):
            return True

    torch = SimpleNamespace(Tensor=Tensor, float32="float32", device=lambda value: value)
    original = np.array([[1., 2., 3.]], dtype=np.float32)
    weight = np.ones(3, dtype=np.float32)
    # Identical bytes, wrong metadata, and values that allclose could broadcast.
    squeezed = Tensor(original.reshape(3))
    checks = check_output(squeezed, squeezed, Tensor(weight), original, weight, original,
                          {"rtol": 1e-5, "atol": 1e-6}, torch, np)
    assert checks["shape_dtype_device"] is False
    assert checks["input_preserved"] is False
    assert checks["values"] is False


@pytest.mark.skipif(os.environ.get("INFERRSI_REQUIRE_NPU_BENCHMARK") != "1",
                    reason="Requires explicitly scheduled Ascend NPU execution")
def test_real_npu_baseline_fused_wrong_output_and_profile(tmp_path):
    task = load_builtin_task("rmsnorm-npu")
    for name in ("baseline", "candidate"):
        report = grade_artifact(task, task.root / f"{name}.py", tmp_path / name,
                                timeout_seconds=180)
        assert report["verdict"] == "PASS"
    wrong = tmp_path / "wrong.py"
    wrong.write_text("import torch\ndef compute(x, weight, *, eps): return torch.zeros_like(x)\n")
    result = run_action(task, wrong, "measure", tmp_path / "wrong", timeout_seconds=180)
    record = json.loads(open(result["result_path"]).read())
    assert not record["passed"] and "metrics" not in record
    result = run_action(task, task.root / "candidate.py", "profile", tmp_path / "profile",
                        timeout_seconds=180)
    record = json.loads(open(result["result_path"]).read())
    assert record["passed"] and "metrics" not in record
    assert any("RmsNorm" in kernel["name"] for kernel in record["diagnostic"]["kernels"])
