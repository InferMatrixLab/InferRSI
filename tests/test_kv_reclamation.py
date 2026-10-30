"""Software contract tests; mocks do not establish artifact isolation or efficacy."""

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from inferrsi.harness import kv_reclamation as kv


def test_capture_only_allows_candidate_bytes(tmp_path):
    (tmp_path / "candidate.py").write_text("# starter\n")
    (tmp_path / "contract.md").write_text("contract\n")
    frozen = kv.workspace_hashes(tmp_path)
    (tmp_path / "candidate.py").write_text("# changed\n")
    assert kv.capture_artifact(tmp_path, frozen) == b"# changed\n"
    (tmp_path / "contract.md").write_text("tampered\n")
    with pytest.raises(ValueError, match="Protected"):
        kv.capture_artifact(tmp_path, frozen)


@pytest.mark.parametrize("change", ["missing", "extra", "symlink", "empty", "oversized"])
def test_bad_artifact_and_workspace_fail_before_execution(tmp_path, change):
    target = tmp_path / "candidate.py"
    target.write_text("# starter\n")
    frozen = kv.workspace_hashes(tmp_path)
    if change == "missing":
        target.unlink()
    elif change == "extra":
        (tmp_path / "other.py").write_text("# extra\n")
    elif change == "symlink":
        target.unlink()
        target.symlink_to("other.py")
    else:
        target.write_bytes(b"" if change == "empty" else b"x" * 65537)
    with pytest.raises(ValueError):
        kv.capture_artifact(tmp_path, frozen)


def fake_executor(command, cwd, output, deadline, *, environment):
    assert environment == {"PATH": "/usr/bin:/bin", "LANG": "C"}
    assert set(p.name for p in cwd.iterdir()) == {"candidate.py", "runner.py", "inputs.json"}
    assert "expected" not in (cwd / "inputs.json").read_text()
    assert "oracle" not in (cwd / "inputs.json").read_text()
    output.mkdir(parents=True)
    (output / "stdout.log").write_text(json.dumps({"observations": [], "pending": []}))
    (output / "stderr.log").write_text("INFERRSI_KV_READY\n")
    return {"status": "completed", "returncode": 0, "elapsed_seconds": 0.5,
            "stdout_path": str(output / "stdout.log"),
            "stderr_path": str(output / "stderr.log")}


def test_candidate_receives_only_inputs_not_answers_or_knowledge(tmp_path):
    with patch.object(kv, "sandbox_command", return_value=["sandbox"]), \
         patch.object(kv, "execute_command", side_effect=fake_executor):
        record, value = kv.invoke(b"# source", {"mode": "verify", "events": []},
                                  tmp_path / "output", time.monotonic() + 1)
    assert record["elapsed_seconds"] == 0.5
    assert value == {"observations": [], "pending": []}
    assert json.loads((tmp_path / "output/execution.json").read_text()) == {
        "status": "completed", "returncode": 0, "elapsed_seconds": 0.5}


@pytest.mark.parametrize("status,returncode,output_kind,expected", [
    ("completed", 0, "valid", "value"),
    ("completed", 0, "invalid_json", None),
    ("completed", 0, "empty", None),
    ("failed", 1, "valid", None),
    ("failed", -9, "valid", None),
    ("timeout", -9, "no_logs", None),
    ("cancelled", -15, "no_logs", None),
    ("error", None, "no_logs", None),
    ("completed", 0, "no_marker", kv.SandboxUnavailable),
    ("completed", 0, "missing_stdout", None),
    ("completed", 0, "missing_stderr", FileNotFoundError),
])
def test_invoke_retains_closed_original_execution_before_all_output_paths(
    tmp_path, status, returncode, output_kind, expected
):
    output = tmp_path / "run"
    actual = {"observations": [], "pending": []}
    original = {"status": status, "returncode": returncode, "elapsed_seconds": 0.125,
                "stdout_path": str(output / "stdout.log"),
                "stderr_path": str(output / "stderr.log"), "metric": 123,
                "argv": ["private-canary"], "cwd": "private-canary",
                "error": "private-canary", "environment": {"KEY": "private-canary"},
                "pid": 12345, "extra": "private-canary"}

    def execute(*args, **kwargs):
        output.mkdir()
        if output_kind not in {"no_logs", "missing_stdout"}:
            data = "invalid JSON" if output_kind == "invalid_json" else (
                "" if output_kind == "empty" else json.dumps(actual))
            (output / "stdout.log").write_text(data)
        if output_kind not in {"no_logs", "missing_stderr"}:
            (output / "stderr.log").write_text(
                "" if output_kind == "no_marker" else "INFERRSI_KV_READY\n")
        return original

    before = dict(original)
    with patch.object(kv, "sandbox_command", return_value=["sandbox"]), \
         patch.object(kv, "execute_command", side_effect=execute) as launch:
        if isinstance(expected, type):
            with pytest.raises(expected):
                kv.invoke(b"# source", {}, output, time.monotonic() + 1)
        else:
            record, value = kv.invoke(b"# source", {}, output, time.monotonic() + 1)
            assert record is original
            assert value == (actual if expected == "value" else None)
        launch.assert_called_once()
    assert original == before  # Preserve elapsed/metric and all existing return semantics.
    raw = (output / "execution.json").read_text()
    assert json.loads(raw) == {"status": status, "returncode": returncode,
                               "elapsed_seconds": 0.125}
    assert "private-canary" not in raw and str(tmp_path) not in raw


def test_execution_retention_failure_stops_before_output_check_without_retry(tmp_path):
    with patch.object(kv, "sandbox_command", return_value=["sandbox"]), \
         patch.object(kv, "execute_command", side_effect=fake_executor) as launch, \
         patch.object(kv, "atomic_write_json", side_effect=OSError("storage unavailable")), \
         patch.object(kv, "read_regular") as read:
        with pytest.raises(OSError, match="storage unavailable"):
            kv.invoke(b"# source", {}, tmp_path / "run", time.monotonic() + 1)
        launch.assert_called_once()
        read.assert_not_called()
    assert not (tmp_path / "run/execution.json").exists()


def test_executor_did_not_return_has_no_invented_execution_record(tmp_path):
    with patch.object(kv, "sandbox_command", return_value=["sandbox"]), \
         patch.object(kv, "execute_command", side_effect=KeyboardInterrupt) as launch:
        with pytest.raises(KeyboardInterrupt):
            kv.invoke(b"# source", {}, tmp_path / "run", time.monotonic() + 1)
        launch.assert_called_once()
    assert not (tmp_path / "run/execution.json").exists()


def test_no_sandbox_has_no_host_fallback(tmp_path):
    with patch.object(kv, "sandbox_command", side_effect=kv.SandboxUnavailable("blocked")), \
         patch.object(kv, "execute_command") as execute:
        with pytest.raises(kv.SandboxUnavailable):
            kv.invoke(b"# source", {}, tmp_path, time.monotonic() + 1)
        execute.assert_not_called()


def test_missing_worker_marker_is_infrastructure_failure(tmp_path):
    def execute(*args, **kwargs):
        record = fake_executor(*args, **kwargs)
        Path(record["stderr_path"]).write_bytes(b"")
        return record

    with patch.object(kv, "sandbox_command", return_value=["sandbox"]), \
         patch.object(kv, "execute_command", side_effect=execute):
        with pytest.raises(kv.SandboxUnavailable, match="boundary"):
            kv.invoke(b"# source", {}, tmp_path / "run", time.monotonic() + 1)


def test_each_event_compared_by_trusted_oracle_and_missing_outputs_rejected(tmp_path):
    traces = [{"id": "one", "events": []}, {"id": "two", "events": []}]
    def compare(trace, value):
        return value == trace["id"]
    with patch.object(kv, "invoke", side_effect=[
            ({"status": "completed"}, "one"), ({"status": "completed"}, None)]):
        result = kv.verify_source(b"# source", traces, tmp_path, time.monotonic() + 1, compare)
    assert result == {"verdict": "FAIL", "checks": {"one": True, "two": False}}


def test_grader_failure_is_unverified_not_refuted(tmp_path):
    with patch.object(kv, "invoke", return_value=({"status": "timeout"}, None)):
        result = kv.verify_source(b"# source", [{"id": "one", "events": []}], tmp_path,
                                  time.monotonic() + 1, lambda *_: True)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["checks"] == {}


def test_expired_deadline_never_launches(tmp_path):
    with patch.object(kv, "invoke") as invoke:
        result = kv.verify_source(b"# source", [{"id": "one", "events": []}], tmp_path,
                                  time.monotonic() - 1, lambda *_: True)
    invoke.assert_not_called()
    assert result["verdict"] == "INCONCLUSIVE"


def test_real_executor_expired_before_launch_needs_no_output_files(tmp_path):
    with patch.object(kv, "sandbox_command", return_value=["not-launched"]):
        record, value = kv.invoke(b"# source", {"mode": "verify", "events": []},
                                  tmp_path / "run", time.monotonic() - 1)
    assert record["status"] == "timeout" and value is None
    assert not (tmp_path / "run/stderr.log").exists()
    assert json.loads((tmp_path / "run/execution.json").read_text()) == {
        "status": "timeout", "returncode": None,
        "elapsed_seconds": record["elapsed_seconds"]}


def test_driver_snapshots_mutable_return_buffers():
    assert 'observation = {"reclaimed": list(result)}' in kv.DRIVER
    assert "return list(value)" in kv.DRIVER


@pytest.mark.skipif(sys.platform != "linux", reason="Trusted Linux resource-limit driver")
def test_authored_driver_control_can_reuse_return_buffers(tmp_path):
    # Trusted local software test, not a submitted artifact or sandbox fallback.
    source = '''class Reclaimer:
    def __init__(self):
        self.result = []
        self.state = []
    def apply(self, event):
        self.result[:] = [event["value"]]
        return self.result
    def pending(self):
        self.state[:] = [(str(self.result[0]), 0, (self.result[0],))]
        return self.state
'''
    (tmp_path / "candidate.py").write_text(source)
    (tmp_path / "inputs.json").write_text(json.dumps(
        {"mode": "verify", "events": [{"value": 1}, {"value": 2}]}))
    (tmp_path / "runner.py").write_text(kv.DRIVER.replace("/work/", str(tmp_path) + "/"))
    run = subprocess.run([sys.executable, "-I", "-S", "-B", str(tmp_path / "runner.py")],
                         capture_output=True, text=True, timeout=5, check=False)
    assert run.returncode == 0, run.stderr
    value = json.loads(run.stdout)
    assert value["observations"][0] == {"reclaimed": [1], "pending": [["1", 0, [1]]]}
    assert value["observations"][1] == {"reclaimed": [2], "pending": [["2", 0, [2]]]}


@pytest.mark.parametrize("broken", [None, "inaccessible", "readonly", "clean_env",
                                    "network_blocked", "fork_denied", "limits", "cleanup"])
def test_preflight_requires_each_actual_probe(tmp_path, broken):
    value = {"inaccessible": [True, True], "readonly": True, "clean_env": True,
             "network_blocked": True, "fork_denied": True,
             "limits": {"memory": [268435456, 268435456], "processes": [0, 0], "cpu": [16, 16],
                        "output": [4194304, 4194304], "files": [32, 32], "core": [0, 0]}}
    if broken and broken != "cleanup":
        value[broken] = False
    with patch.object(kv, "invoke", return_value=({"status": "completed"}, value)), \
         patch.object(kv, "process_group_gone", return_value=broken != "cleanup"):
        if broken:
            with pytest.raises(kv.SandboxUnavailable):
                kv.probe_isolation(tmp_path, time.monotonic() + 1, ["/synthetic-hidden"])
        else:
            assert kv.probe_isolation(tmp_path, time.monotonic() + 1,
                                      ["/synthetic-hidden"])["normal_exit_process_group_gone"]


def test_driver_has_no_expected_answers_or_candidate_timing_authority():
    assert "perf_counter" not in kv.DRIVER and "process_time" not in kv.DRIVER
    assert "expected" not in kv.DRIVER and "oracle" not in kv.DRIVER
    assert "resource.RLIMIT_NPROC, (0, 0)" in kv.DRIVER
    assert "resource.RLIMIT_AS, (268435456, 268435456)" in kv.DRIVER
