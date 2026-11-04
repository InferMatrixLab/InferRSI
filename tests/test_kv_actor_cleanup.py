"""Observer and fail-closed controls; no submitted artifact executes on host."""

import json
import sys
import time

import pytest

from tools import qualify_kv_actor_cleanup as cleanup


def stat_file(root, pid, parent, start, state="S"):
    path = root / str(pid)
    path.mkdir()
    fields = [state, str(parent)] + ["0"] * 17 + [str(start)]
    (path / "stat").write_text(f"{pid} (trusted fixture) " + " ".join(fields))


def test_observer_tracks_only_owned_tree_and_starttime_not_reused_pid(tmp_path):
    stat_file(tmp_path, 10, 1, 100)
    stat_file(tmp_path, 11, 10, 101)
    stat_file(tmp_path, 12, 11, 102)
    stat_file(tmp_path, 99, 1, 999)
    owned, visible = cleanup._owned_snapshot(10, {}, proc=tmp_path)
    assert visible and set(owned) == {11, 12}
    # A formerly owned PID reused by an unrelated process is not a survivor.
    owned, visible = cleanup._owned_snapshot(50, {99: 998}, proc=tmp_path)
    assert visible and owned == {}
    # An owned detached/reparented descendant remains tracked by PID+starttime.
    owned, visible = cleanup._owned_snapshot(50, {12: 102}, proc=tmp_path)
    assert visible and set(owned) == {12}


def test_unreadable_proc_is_not_empty_success(tmp_path):
    assert cleanup._owned_snapshot(1, {}, proc=tmp_path / "missing") == ({}, False)
    (tmp_path / "12").mkdir()
    (tmp_path / "12/stat").write_text("malformed")
    assert cleanup._owned_snapshot(1, {}, proc=tmp_path)[1] is False


def test_no_sandbox_never_runs_probe_on_host(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "sandbox_command", lambda *_: (_ for _ in ()).throw(
        cleanup.SandboxUnavailable("blocked")))
    monkeypatch.setattr(cleanup, "execute_command",
                        lambda *_args, **_kwargs: pytest.fail("no fallback"))
    result = cleanup.probe_worker("normal", tmp_path / "out", time.monotonic() + 1)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["reason"] == "sandbox_unavailable"


def test_qualification_requires_all_three_modes_and_readable_worker_evidence(tmp_path, monkeypatch):
    calls = []
    def execute(command, cwd, output, deadline, **kwargs):
        calls.append(command[4])
        assert command[1] == "-I"
        assert kwargs["environment"] == {"PATH": "/usr/bin:/bin", "LANG": "C"}
        destination = tmp_path / "out" / command[4]
        destination.mkdir(parents=True)
        (destination / "result.json").write_text(json.dumps({"verdict": "PASS"}))
        return {"status": "completed"}
    monkeypatch.setattr(cleanup, "execute_command", execute)
    result = cleanup.qualify(tmp_path / "out", time.monotonic() + 10, 1)
    assert calls == ["normal", "timeout", "cancel"] and result["verdict"] == "PASS"


def test_probe_is_authored_fork_setsid_only_not_candidate_or_provider():
    assert "os.fork()" in cleanup.PROBE and "os.setsid()" in cleanup.PROBE
    assert "candidate" not in cleanup.PROBE and "exec(" not in cleanup.PROBE
    assert "SKILL_EVAL" not in cleanup.PROBE


def test_nested_worker_rejects_other_source_before_execution(tmp_path, monkeypatch):
    (tmp_path / "runner.py").write_text("raise RuntimeError('not the trusted probe')\n")
    monkeypatch.setattr(cleanup, "execute_command", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ValueError, match="exact authored"):
        cleanup.nested_worker("normal", tmp_path, tmp_path / "out", time.monotonic() + 1)


def test_detached_marker_requires_exact_owned_host_identity(tmp_path):
    stat_file(tmp_path, 10, 1, 100)
    stat_file(tmp_path, 11, 10, 101)
    stat_file(tmp_path, 12, 11, 102)
    marker = {"role": "detached", "own_session": True, "namespace_pid": 3,
              "start": 102, "pid_namespace": "pid:[1234]"}
    owned, _ = cleanup._owned_snapshot(1, {}, proc=tmp_path)
    # A marker plus two ancestors never substitutes for observing the detached PID.
    assert cleanup._bind_detached([marker], {p: owned[p] for p in (10, 11)}, proc=tmp_path) is None
    (tmp_path / "12/status").write_text("Name:\ttrusted\nNSpid:\t12\t3\n")
    (tmp_path / "12/ns").mkdir()
    (tmp_path / "12/ns/pid").symlink_to("pid:[1234]")
    detached = cleanup._bind_detached([marker], owned, proc=tmp_path)
    assert detached == {"pid": 12, "start": 102}
    assert cleanup._bind_chain([{"role": "worker", "pid": 10, "start": 100}],
                               detached, owned)["chain_length"] == 3
    for altered in ({"start": 999}, {"namespace_pid": 4}, {"pid_namespace": "pid:[4321]"}):
        assert cleanup._bind_detached([{**marker, **altered}], owned, proc=tmp_path) is None
    assert cleanup._bind_chain([{"role": "worker", "pid": 11, "start": 101}],
                               detached, owned) is None


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux proc identity observation")
@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_outer_worker_loss_detects_and_recovers_independent_session_survivors(
    tmp_path, monkeypatch, mode
):
    # Authored host-only fixture intentionally lacks bubblewrap die-with-parent.
    # It exercises negative observer/supervisor behavior, never candidate code or
    # qualification success. The detached descendants must be detected and killed.
    output = tmp_path / "out"
    events = output / "sandbox/stdout.log"
    events.parent.mkdir(parents=True)
    detached = '''import json, os, time
with open("/proc/self/stat") as stream:
    start = int(stream.read().rsplit(")", 1)[1].split()[19])
print(json.dumps({"role": "detached", "own_session": os.getsid(0) == os.getpid(),
    "namespace_pid": os.getpid(), "start": start,
    "pid_namespace": os.readlink("/proc/self/ns/pid")}), flush=True)
print(json.dumps({"role": "parent"}), flush=True)
time.sleep(30)
'''
    middle = f'''import subprocess, sys, time
with open({str(events)!r}, "w") as stream:
    subprocess.Popen([sys.executable, "-c", {detached!r}], stdout=stream, start_new_session=True)
    time.sleep(30)
'''
    worker = f'''import json, os, subprocess, sys, time
with open("/proc/self/stat") as stream:
    start = int(stream.read().rsplit(")", 1)[1].split()[19])
print(json.dumps({{"role": "worker", "pid": os.getpid(), "start": start}}), flush=True)
subprocess.Popen([sys.executable, "-c", {middle!r}], start_new_session=True)
time.sleep(30)
'''
    execute = cleanup.execute_command

    def fixture_execute(command, cwd, trial, deadline, **kwargs):
        assert "--nested-worker" in command
        return execute((sys.executable, "-c", worker), cwd, trial, deadline, **kwargs)

    monkeypatch.setattr(cleanup, "sandbox_command", lambda _: ("never-run",))
    monkeypatch.setattr(cleanup, "execute_command", fixture_execute)
    # probe_worker owns creation, not the fixture's precreated output parent.
    events.parent.rmdir()
    output.rmdir()
    original_events = cleanup._events

    def read_events(path):
        events.parent.mkdir(parents=True, exist_ok=True)
        return original_events(path)

    monkeypatch.setattr(cleanup, "_events", read_events)
    result = cleanup.probe_worker(mode, output, time.monotonic() + 2)
    assert result["verdict"] == "FAIL"
    assert result["outer_worker_supervised"] and result["bound_chain"]["chain_length"] >= 3
    assert result["surviving_descendants"] > 0 and result["recovery_kills"] > 0
    assert result["recovery_survivors"] == 0 and result["recovery_visibility_complete"]
    assert result["explicit_cancel_sent"] == (mode == "cancel")
    for role in ("worker", "detached"):
        identity = result["bound_chain"][role]
        try:
            current = cleanup._stat(cleanup.Path("/proc") / str(identity["pid"]) / "stat")
        except FileNotFoundError:
            continue
        assert current["start"] != identity["start"] or current["state"] == "Z"
