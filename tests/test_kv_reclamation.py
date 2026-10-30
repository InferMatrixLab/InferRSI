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
    return {"status": "completed", "elapsed_seconds": 0.5,
            "stdout_path": str(output / "stdout.log"),
            "stderr_path": str(output / "stderr.log")}


def test_candidate_receives_only_inputs_not_answers_or_knowledge(tmp_path):
    with patch.object(kv, "sandbox_command", return_value=["sandbox"]), \
         patch.object(kv, "execute_command", side_effect=fake_executor):
        record, value = kv.invoke(b"# source", {"mode": "verify", "events": []},
                                  tmp_path / "output", time.monotonic() + 1)
    assert record["elapsed_seconds"] == 0.5
    assert value == {"observations": [], "pending": []}


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
