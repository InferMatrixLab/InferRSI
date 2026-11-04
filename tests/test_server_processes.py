"""Server helpers fail closed and clean only their Linux process groups."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from inferrsi.infra import processes


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_unsupported_platform_rejected_before_launch_or_cleanup(monkeypatch, platform):
    monkeypatch.setattr(processes.sys, "platform", platform)
    with patch.object(processes.subprocess, "Popen") as launch:
        with pytest.raises(OSError, match="require Linux"):
            processes.launch_server([], ".", {}, None)
        launch.assert_not_called()
    with pytest.raises(OSError, match="require Linux"):
        processes.stop_server(Mock(), {})


@pytest.mark.parametrize("failure", [FileNotFoundError, PermissionError])
def test_unavailable_proc_never_means_empty_group(monkeypatch, failure):
    monkeypatch.setattr(processes.sys, "platform", "linux")
    with patch.object(Path, "read_text", side_effect=failure("proc unavailable")):
        with pytest.raises(failure):
            processes._live_group_members(123)
        with patch.object(processes.subprocess, "Popen") as launch:
            with pytest.raises(failure):
                processes.launch_server([], ".", {}, None)
            launch.assert_not_called()
        with pytest.raises(failure):
            processes.stop_server(Mock(), {})


def test_unreadable_process_table_fails_before_launch(monkeypatch):
    monkeypatch.setattr(processes.sys, "platform", "linux")
    with (
        patch.object(Path, "read_text", return_value="synthetic stat"),
        patch.object(Path, "iterdir", side_effect=PermissionError("proc unavailable")),
        patch.object(processes.subprocess, "Popen") as launch,
    ):
        with pytest.raises(PermissionError):
            processes.launch_server([], ".", {}, None)
        launch.assert_not_called()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process ownership contract")
@pytest.mark.parametrize("supervised", [False, True])
def test_cleanup_after_leader_exit_preserves_unrelated_process(tmp_path, supervised):
    server = tmp_path / "server.py"
    server.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import os, pathlib, signal, sys, time; '"
        "'signal.signal(signal.SIGTERM, signal.SIG_IGN); '"
        "'pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); '"
        "'time.sleep(60)', sys.argv[1]])\n"
        "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(.01)\n",
        encoding="utf-8",
    )
    # The helper runs in its own group, as it would inside the trial executor.
    helper = """
import json, os, sys
from inferrsi.infra.processes import launch_server, stop_server
with open(sys.argv[3], 'wb') as log:
    process, owner = launch_server([sys.executable, sys.argv[1], sys.argv[2]],
                                  '.', os.environ.copy(), log)
    print(json.dumps(owner), flush=True)
    process.wait(timeout=10)
    cleanup = stop_server(process, owner, grace_seconds=.1)
    print(json.dumps(cleanup), flush=True)
"""
    environment = os.environ.copy()
    environment.pop("INFERRSI_RESULT_PATH", None)
    if supervised:
        environment["INFERRSI_RESULT_PATH"] = "synthetic-result"
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    worker_file = tmp_path / "worker.pid"
    runner = subprocess.Popen(
        [sys.executable, "-c", helper, str(server), str(worker_file), str(tmp_path / "log")],
        env=environment, start_new_session=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    owner = None
    try:
        stdout, stderr = runner.communicate(timeout=15)
        if stdout:
            owner = json.loads(stdout.splitlines()[0])
        assert runner.returncode == 0, stderr
        cleanup = json.loads(stdout.splitlines()[1])
        assert owner["mode"] == ("inferrsi_trial_group" if supervised else "server_session")
        assert cleanup["status"] == "completed"
        assert cleanup["kill_sent"] is True
        assert cleanup["remaining_pids"] == []
        assert unrelated.poll() is None
        worker = Path("/proc") / worker_file.read_text() / "stat"
        assert not worker.exists() or worker.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    finally:
        for group in {runner.pid, owner["process_group_id"] if owner else runner.pid}:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        runner.wait(timeout=5)
        unrelated.kill()
        unrelated.wait(timeout=5)
