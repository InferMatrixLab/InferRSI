"""Shared-oracle and isolated artifact controls; never model-benefit evidence."""

import base64
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from inferrsi.harness import skill_eval_benchmark as benchmark
from inferrsi.harness import skill_eval_engineering as engineering
from inferrsi.harness.benchmarks import numpy_task
from inferrsi.harness.benchmarks.contract import load_builtin_task, load_task

READY = {"ready": True, "numpy": np.__version__, "python": "3.10.0", "machine": "x86_64"}


def answer(name="rmsnorm-cpu", source=None):
    task = benchmark.task_descriptor(name)
    return task, {"artifact": benchmark.ARTIFACT, "summary": "Authored software control",
                  "artifact_source": source or benchmark.starter(task).decode()}


def oracle_transport(task):
    """Synthetic transport exercises parent grading only, never executes source."""
    package = load_builtin_task(task["benchmark"]["task_id"])
    prepared, _, _ = benchmark._prepare(package, np)
    outputs = [{"output": {"shape": list(x.shape), "dtype": "float32",
                           "data": base64.b64encode(expected.tobytes()).decode()},
                "input_after": base64.b64encode(x.tobytes()).decode()}
               for _, x, expected, _, _ in prepared]
    return {"outputs": outputs}


@pytest.mark.parametrize("name", ["softmax-cpu", "rmsnorm-cpu"])
def test_descriptor_freezes_builtin_task_and_shared_grader(name):
    task, _ = answer(name)
    benchmark.validate_task(task)
    package = load_task(name)
    assert task["contract"] == package.manifest
    assert task["benchmark"] == {
        "task_id": name, "task_sha256": package.task_sha256,
        "grader_sha256": package.grader_sha256,
    }
    assert benchmark.starter(task) == (package.root / "candidate.py").read_bytes()


def shadow_softmax(directory):
    """A reviewed-path task is valid but must never replace the formal rubric."""
    canonical = load_builtin_task("softmax-cpu")
    shadow = directory / "softmax-cpu"
    shutil.copytree(canonical.root, shadow, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = canonical.manifest
    manifest["oracle"]["atol"] = 1
    (shadow / "task.json").write_text(json.dumps(manifest), encoding="utf-8")
    (shadow / "candidate.py").write_text(
        "import numpy as np\ndef compute(x, *, eps): return np.zeros_like(x)\n",
        encoding="utf-8",
    )
    return canonical, shadow


def test_cwd_shadow_cannot_replace_descriptor_starter_or_parent_oracle(tmp_path, monkeypatch):
    canonical, shadow = shadow_softmax(tmp_path)
    original, _ = answer("softmax-cpu")
    monkeypatch.chdir(tmp_path)
    # Trusted callers can still deliberately load an external reviewed task.
    assert load_task("softmax-cpu").root == shadow
    assert load_task(shadow).manifest["oracle"]["atol"] == 1
    assert load_builtin_task("softmax-cpu").root == canonical.root
    task, output = answer("softmax-cpu")
    assert task == original
    assert task["benchmark"]["task_sha256"] == canonical.task_sha256
    assert benchmark.starter(task) == (canonical.root / "candidate.py").read_bytes()
    assert benchmark.starter(task) != (shadow / "candidate.py").read_bytes()
    # Synthetic returned arrays test parent grading, not sandbox source execution.
    transport = oracle_transport(task)
    for record in transport["outputs"]:
        record["output"]["data"] = base64.b64encode(
            bytes(len(base64.b64decode(record["output"]["data"])))
        ).decode()
    with mock.patch.object(benchmark, "_invoke", side_effect=[READY, transport]):
        result = benchmark.verify(task, output)
    assert not result["passed"]
    assert not result["assertions"]["normal.values"]
    assert "metrics" not in result


@pytest.mark.parametrize("change", ["adapter", "environment"])
def test_formal_artifact_path_rejects_new_backend_packages(change, monkeypatch):
    package = load_builtin_task("rmsnorm-cpu")
    manifest = package.manifest
    if change == "adapter":
        manifest["adapter"] = "torch-npu-rmsnorm-v1"
    else:
        manifest["environment"] = {"backend": "ascend", "runtime": "torch_npu",
                                   "dtype": "float32"}
    unsupported = replace(package, frozen_manifest=json.dumps(manifest))
    monkeypatch.setattr(benchmark, "load_builtin_task", lambda _: unsupported)
    with pytest.raises(ValueError, match="NumPy CPU adapter"):
        benchmark.task_descriptor("rmsnorm-npu")


@pytest.mark.parametrize("change", ["hash", "holdout", "path", "request", "extra", "contract"])
def test_descriptor_drift_and_noncanonical_tasks_rejected(change):
    task, _ = answer()
    if change == "hash":
        task["benchmark"]["task_sha256"] = "0" * 64
    elif change == "path":
        task["benchmark"]["task_id"] = "../rmsnorm-cpu"
    elif change == "holdout":
        task["split"] = "holdout"
    elif change == "request":
        task["request"] += " instead use a new oracle"
    elif change == "contract":
        task["contract"]["oracle"]["atol"] = 1
    else:
        task["expected"] = True
    with pytest.raises(ValueError):
        benchmark.validate_task(task)


@pytest.mark.parametrize("change", [{"artifact": "parser.py"}, {"artifact_source": ""},
                                    {"artifact_source": "x" * 65537}, {"passed": True}])
def test_invalid_artifact_does_not_start_source(change):
    task, output = answer()
    with mock.patch.object(benchmark, "_invoke") as invoke:
        assert not benchmark.verify(task, {**output, **change})["passed"]
        invoke.assert_not_called()


def test_no_sandbox_means_explicit_unavailable_never_host_execution(tmp_path):
    marker = tmp_path / "must-not-exist"
    task, output = answer(source=f"open({str(marker)!r}, 'w').write('bad')")
    with mock.patch.object(benchmark, "_invoke", return_value=None):
        with pytest.raises(benchmark.SandboxUnavailable):
            benchmark.verify(task, output)
    assert not marker.exists()


def test_missing_numpy_is_explicit_unavailable():
    task, output = answer()
    with mock.patch.dict("sys.modules", {"numpy": None}):
        with pytest.raises(benchmark.SandboxUnavailable, match="requires NumPy"):
            benchmark.verify(task, output)


@pytest.mark.parametrize("name", ["softmax-cpu", "rmsnorm-cpu"])
def test_parent_oracle_uses_identical_shared_sequence_and_checks_every_call(name):
    task, output = answer(name)
    transport = oracle_transport(task)
    calls = []

    def invoke(work, request=None, *, probe=False):
        assert sorted(p.name for p in work.iterdir()) == ["implementation.py", "runner.py"]
        assert (work / "implementation.py").read_bytes() == output["artifact_source"].encode()
        if probe:
            return READY
        calls.append(request)
        assert set(request) == {"eps", "inputs"}
        assert all(set(x) == {"shape", "layout", "data"} for x in request["inputs"])
        return transport

    with mock.patch.object(benchmark, "_invoke", side_effect=invoke):
        result = benchmark.verify(task, output)
    package = load_task(name)
    # Use only the repository-authored candidate for comparison, not submitted source.
    trusted = numpy_task.evaluate(package, package.root / "candidate.py", "check", Path("."))
    assert result["passed"] and len(result["assertions"]) == 164
    assert result["assertions"] == trusted["assertions"]
    for key in ("workloads", "input_sequence"):
        assert result["benchmark"][key] == trusted[key]
    assert result["benchmark"]["returned_calls"] == trusted["executed_calls"]
    assert len(calls) == 1 and len(calls[0]["inputs"]) == 41
    assert result["benchmark"]["timing"] == "not measured"


@pytest.mark.parametrize("wrong", ["dtype", "values", "mutation", "truncated", "malformed"])
def test_parent_rejects_wrong_or_malformed_returned_arrays(wrong):
    task, output = answer()
    transport = oracle_transport(task)
    record = transport["outputs"][10]
    if wrong == "dtype":
        record["output"]["dtype"] = "float64"
    elif wrong == "values":
        record["output"]["data"] = base64.b64encode(
            bytes(len(base64.b64decode(record["output"]["data"])))
        ).decode()
    elif wrong == "mutation":
        record["input_after"] = base64.b64encode(
            bytes(len(base64.b64decode(record["input_after"])))
        ).decode()
    elif wrong == "truncated":
        transport["outputs"].pop()
    else:
        record["output"]["data"] = "!bad-base64"
    with mock.patch.object(benchmark, "_invoke",
                           side_effect=[READY, transport]):
        result = benchmark.verify(task, output)
    assert not result["passed"]
    assert "metrics" not in result


def test_workspace_freeze_excludes_only_implementation(tmp_path):
    (tmp_path / "task.json").write_text("{}")
    (tmp_path / "implementation.py").write_text("original")
    (tmp_path / "parser.py").write_text("frozen")
    before = benchmark.input_hashes(tmp_path)
    assert set(before) == {"task.json", "parser.py"}
    (tmp_path / "implementation.py").write_text("candidate")
    assert benchmark.input_hashes(tmp_path) == before
    (tmp_path / "parser.py").write_text("changed")
    assert benchmark.input_hashes(tmp_path) != before


def test_numpy_mounts_extend_existing_boundary_without_host_venv_or_repository():
    original = ["bwrap", "--unshare-all", "--clearenv", "--ro-bind", "/safe/work", "/work",
                "--remount-ro", "/", "--", "/usr/bin/python3", "-I", "-S", "-B",
                "/work/runner.py"]
    runtime = mock.Mock(stdout=json.dumps({"version": np.__version__,
                                          "root": "/opt/public-runtime/numpy"}).encode())
    with mock.patch.object(engineering, "sandbox_command", return_value=original), \
         mock.patch.object(benchmark.subprocess, "run", return_value=runtime), \
         mock.patch.object(Path, "is_dir", return_value=True), \
         mock.patch.object(Path, "is_absolute", return_value=True), \
         mock.patch.object(Path, "resolve", return_value=Path("/opt/public-runtime/numpy.libs")):
        command = benchmark.sandbox_command(Path("/safe/work"))
    assert "--unshare-all" in command and "--clearenv" in command
    assert command[-5:] == original[-5:]
    assert command.count("--ro-bind") == 3
    assert "/runtime/numpy" in command and "/runtime/numpy.libs" in command
    assert command.index("/runtime/numpy.libs") < command.index("--remount-ro")
    assert "--share-net" not in command
    assert "OPENBLAS_NUM_THREADS" in command


def test_runtime_version_mismatch_is_unavailable():
    runtime = mock.Mock(stdout=json.dumps({"version": "different", "root": "/runtime/numpy"}))
    with mock.patch.object(engineering, "sandbox_command", return_value=["--"]), \
         mock.patch.object(benchmark.subprocess, "run", return_value=runtime):
        with pytest.raises(benchmark.SandboxUnavailable):
            benchmark.sandbox_command(Path("/safe/work"))


@pytest.mark.parametrize("ready", [False, True])
def test_worker_startup_is_distinct_from_artifact_failure(ready):
    process = mock.Mock(returncode=1)

    def start(*args, **kwargs):
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C"}
        if ready:
            kwargs["stderr"].write(b"INFERRSI_BENCHMARK_READY\n")
        return process

    with mock.patch.object(benchmark, "sandbox_command", return_value=["sandbox"]), \
         mock.patch.object(benchmark.subprocess, "Popen", side_effect=start):
        if ready:
            assert benchmark._invoke(Path("/unused"), {}) is None
        else:
            with pytest.raises(benchmark.SandboxUnavailable):
                benchmark._invoke(Path("/unused"), {})


def run_real(task, output):
    try:
        return benchmark.verify(task, output)
    except benchmark.SandboxUnavailable as error:
        if os.environ.get("INFERRSI_REQUIRE_BENCHMARK_SANDBOX") == "1":
            pytest.fail(str(error))
        pytest.skip(str(error))


@pytest.mark.parametrize("name", ["softmax-cpu", "rmsnorm-cpu"])
def test_real_sandbox_correct_and_wrong_authored_controls(name):
    task, output = answer(name)
    result = run_real(task, output)
    assert result["passed"] and len(result["assertions"]) == 164
    wrong = {**output, "artifact_source":
             "import numpy as np\ndef compute(x, *, eps): return np.zeros_like(x)\n"}
    rejected = run_real(task, wrong)
    assert not rejected["passed"] and "metrics" not in rejected


def test_real_sandbox_rejects_zero_output_despite_cwd_shadow(tmp_path, monkeypatch):
    canonical, shadow = shadow_softmax(tmp_path)
    monkeypatch.chdir(tmp_path)
    task, wrong = answer("softmax-cpu", source=(shadow / "candidate.py").read_text())
    assert task["benchmark"]["task_sha256"] == canonical.task_sha256
    result = run_real(task, wrong)
    assert not result["passed"] and not result["assertions"]["normal.values"]
    assert "metrics" not in result


def test_real_sandbox_preserves_sequence_state_and_rejects_cached_output_replay():
    source = """import numpy as np
cache = {}
def compute(x, *, eps):
    key = (x.shape, x.strides)
    if key not in cache:
        cache[key] = x / np.sqrt(np.mean(x*x, axis=1, keepdims=True) + eps)
    return cache[key]
"""
    task, output = answer(source=source)
    result = run_real(task, output)
    assert not result["passed"]
    assert result["assertions"]["normal.values"]
    assert not result["assertions"]["normal.call-0.values"]


def test_real_sandbox_cannot_read_host_sentinel_or_oracle(tmp_path):
    sentinel = tmp_path / "host-only-secret.txt"
    sentinel.write_text("must not be visible to submitted code")
    task, output = answer()
    source = output["artifact_source"] + f"""
from pathlib import Path
assert not Path({str(sentinel)!r}).exists()
assert sorted(p.name for p in Path('/work').iterdir()) == ['implementation.py', 'runner.py']
assert not Path('/proc/1/root{str(sentinel)}').exists()
"""
    result = run_real(task, {**output, "artifact_source": source})
    assert result["passed"]
