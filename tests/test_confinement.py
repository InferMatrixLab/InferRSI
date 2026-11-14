"""Confinement policy. The fixture backend is not an operating-system boundary."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferrsi.infra import confinement
from inferrsi.infra.confinement import (
    ConfinementUnavailable,
    FixtureBackend,
    UnavailableBackend,
    UnreapedCommand,
    UnshareBackend,
    _elf_interpreter,
    _kill_group,
    confined_execute,
    minimal_environment,
    namespace_plan,
    namespaces_available,
    select_backend,
    supervisor_command,
)


def test_build_write_outside_the_checkout_is_denied_and_does_not_run(tmp_path):
    checkout = tmp_path / "candidate"
    checkout.mkdir()
    ledger = tmp_path / "ledger.json"
    ledger.write_text("safe", encoding="utf-8")
    argv = (
        sys.executable,
        "-c",
        "open(__import__('sys').argv[1], 'w').write('pwned')",
        str(ledger),
    )
    with pytest.raises(ConfinementUnavailable, match="outside writable"):
        confined_execute(
            argv,
            checkout,
            (checkout,),
            (),
            time.monotonic() + 5,
            backend=FixtureBackend(),
        )
    assert ledger.read_text(encoding="utf-8") == "safe"


def test_missing_backend_refuses_without_running(tmp_path):
    marker = tmp_path / "ran"
    argv = (sys.executable, "-c", "open('ran','w').write('yes')")
    with pytest.raises(ConfinementUnavailable, match="unavailable"):
        confined_execute(
            argv,
            tmp_path,
            (tmp_path,),
            (),
            time.monotonic() + 5,
            backend=UnavailableBackend(),
        )
    assert not marker.exists()


def test_select_backend_fails_closed_when_namespaces_are_disabled(monkeypatch):
    monkeypatch.setattr("inferrsi.infra.confinement.namespaces_available", lambda: False)
    assert isinstance(select_backend(), UnavailableBackend)


def test_unshare_failure_does_not_fall_back(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    real_popen = subprocess.Popen

    class FailedUnshare:
        def __init__(self, argv):
            self.args = argv
            self.returncode = None
            calls.append(json.loads(Path(argv[-1]).read_text(encoding="utf-8")))

        def communicate(self, timeout=None):
            del timeout
            self.returncode = 1
            return "", "unshare failed"

    def fake_popen(argv, **kwargs):
        if argv and argv[0] == "unshare":
            return FailedUnshare(argv)
        return real_popen(argv, **kwargs)

    monkeypatch.setattr("inferrsi.infra.confinement.subprocess.Popen", fake_popen)
    with pytest.raises(ConfinementUnavailable, match="unshare failed"):
        UnshareBackend().run(
            (sys.executable, "-c", "print('should-not-run')"),
            tmp_path,
            (tmp_path,),
            (),
            time.monotonic() + 5,
        )
    assert calls
    assert "SECRET_CANARY" not in calls[0]["env"]
    assert "/" not in {item["source"] for item in calls[0]["mounts"]}


_LATE_CHILD = """
import pathlib, sys, time
pathlib.Path(sys.argv[1], "started").write_text("1")
time.sleep(float(sys.argv[2]))
pathlib.Path(sys.argv[1], "late").write_text("1")
"""


def test_unshare_timeout_kills_the_whole_process_group(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    (tmp_path / "child.py").write_text(_LATE_CHILD, encoding="utf-8")
    child = [str(tmp_path / "child.py"), str(tmp_path), "1.5"]
    payload = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, *{child!r}])\n"
        "time.sleep(30)\n"
    )

    def fake_popen(argv, **kwargs):
        if argv and argv[0] == "unshare":
            argv = [sys.executable, "-c", payload]
        return real_popen(argv, **kwargs)

    monkeypatch.setattr("inferrsi.infra.confinement.subprocess.Popen", fake_popen)
    with pytest.raises(ConfinementUnavailable, match="timed out"):
        UnshareBackend().run(
            (sys.executable, "-c", "print('unused')"),
            tmp_path,
            (tmp_path,),
            (),
            time.monotonic() + 1,
        )
    time.sleep(2)
    assert (tmp_path / "started").exists()
    assert not (tmp_path / "late").exists()


def test_unshare_timeout_kills_a_direct_child_that_left_the_session(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    (tmp_path / "child.py").write_text(_LATE_CHILD, encoding="utf-8")
    child = [str(tmp_path / "child.py"), str(tmp_path), "1.5"]
    payload = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, *{child!r}], start_new_session=True)\n"
        "time.sleep(30)\n"
    )

    def fake_popen(argv, **kwargs):
        if argv and argv[0] == "unshare":
            argv = [sys.executable, "-c", payload]
        return real_popen(argv, **kwargs)

    monkeypatch.setattr("inferrsi.infra.confinement.subprocess.Popen", fake_popen)
    with pytest.raises(ConfinementUnavailable, match="timed out"):
        UnshareBackend().run(
            (sys.executable, "-c", "print('unused')"),
            tmp_path,
            (tmp_path,),
            (),
            time.monotonic() + 1,
        )
    time.sleep(2)
    assert (tmp_path / "started").exists()
    assert not (tmp_path / "late").exists()


def test_a_group_that_never_empties_is_reported_unreaped(monkeypatch):
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    real_killpg = os.killpg

    def killpg(pgid, sig):
        if sig != 0:
            real_killpg(pgid, sig)

    monkeypatch.setattr(confinement, "_REAP_SECONDS", 0.2)
    monkeypatch.setattr(confinement.os, "killpg", killpg)
    with pytest.raises(UnreapedCommand):
        _kill_group(process)


def test_supervisor_ignores_a_shadow_package_in_the_candidate(tmp_path):
    shadow = tmp_path / "candidate"
    (shadow / "inferrsi" / "infra").mkdir(parents=True)
    canary = tmp_path / "shadow-imported"
    (shadow / "inferrsi" / "__init__.py").write_text(
        f"open({str(canary)!r}, 'w').write('1')\n", encoding="utf-8"
    )
    (shadow / "inferrsi" / "infra" / "__init__.py").write_text("", encoding="utf-8")
    (shadow / "inferrsi" / "infra" / "confinement.py").write_text(
        "def enter_namespace(path):\n    raise SystemExit('shadow')\n", encoding="utf-8"
    )
    completed = subprocess.run(
        supervisor_command(tmp_path / "missing.json"),
        cwd=shadow,
        env={**minimal_environment(), "PYTHONPATH": str(shadow)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode != 0
    assert not canary.exists()
    assert "shadow" not in completed.stderr
    assert "FileNotFoundError" in completed.stderr
    assert str(Path(confinement.__file__).resolve()) in completed.stderr


def test_namespace_plan_includes_the_loader_but_not_a_private_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    private = tmp_path / "private"
    private.mkdir()
    (private / "canary.txt").write_text("CANARY-FILE", encoding="utf-8")
    plan = namespace_plan((tmp_path / "work",), ())
    sources = {item["source"] for item in plan["mounts"]}
    interpreter = _elf_interpreter(Path(sys.executable))
    assert interpreter is not None
    assert interpreter in sources or any(
        Path(interpreter).is_relative_to(Path(source)) for source in sources
    )
    assert "/" not in sources
    assert str(private) not in sources
    assert "SECRET_CANARY" not in plan["env"]


@pytest.mark.skipif(not namespaces_available(), reason="user namespaces are unavailable")
def test_unshare_starts_python_and_hides_a_private_canary(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    private = tmp_path / "private"
    private.mkdir()
    (private / "canary.txt").write_text("CANARY-FILE", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    script = (
        "import os\n"
        "print('STARTED')\n"
        "print(os.environ.get('SECRET_CANARY', ''))\n"
        "print(os.path.exists(%r))\n" % str(private / "canary.txt")
    )
    record = UnshareBackend().run(
        (sys.executable, "-c", script),
        work,
        (work,),
        (),
        time.monotonic() + 30,
    )
    assert record["status"] == "completed"
    assert "STARTED" in record["stdout"]
    assert "CANARY-ENV" not in record["stdout"]
    assert "True" not in record["stdout"]


@pytest.mark.skipif(not namespaces_available(), reason="user namespaces are unavailable")
def test_unshare_timeout_leaves_no_detached_child(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "child.py").write_text(_LATE_CHILD, encoding="utf-8")
    script = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(work / 'child.py')!r}, {str(work)!r}, '4'], "
        "start_new_session=True)\n"
        "time.sleep(30)\n"
    )
    with pytest.raises(ConfinementUnavailable, match="timed out"):
        UnshareBackend().run(
            (sys.executable, "-c", script),
            work,
            (work,),
            (),
            time.monotonic() + 3,
        )
    time.sleep(3)
    assert (work / "started").exists()
    assert not (work / "late").exists()


@pytest.mark.skipif(not namespaces_available(), reason="user namespaces are unavailable")
def test_unshare_timeout_kills_a_pid_1_that_left_the_session(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "child.py").write_text(_LATE_CHILD, encoding="utf-8")
    script = (
        "import os, subprocess, sys, time\n"
        "os.setsid()\n"
        f"subprocess.Popen([sys.executable, {str(work / 'child.py')!r}, {str(work)!r}, '4'])\n"
        "time.sleep(30)\n"
    )
    with pytest.raises(ConfinementUnavailable, match="timed out"):
        UnshareBackend().run(
            (sys.executable, "-c", script),
            work,
            (work,),
            (),
            time.monotonic() + 3,
        )
    time.sleep(3)
    assert (work / "started").exists()
    assert not (work / "late").exists()


def test_blocked_unshare_reports_namespaces_unavailable(monkeypatch):
    real = Path.read_text

    def fake_read(self, *args, **kwargs):
        if self.name == "max_user_namespaces":
            return "1"
        return real(self, *args, **kwargs)

    def blocked(argv, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(argv, 1, stderr=b"Operation not permitted")

    monkeypatch.setattr(Path, "read_text", fake_read)
    monkeypatch.setattr("inferrsi.infra.confinement.subprocess.run", blocked)
    assert namespaces_available() is False


def test_namespace_plan_keeps_host_root_and_secrets_out(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    plan = namespace_plan((tmp_path / "writable",), (tmp_path / "readable",))
    assert "/" not in {item["source"] for item in plan["mounts"]}
    assert "SECRET_CANARY" not in plan["env"]
    assert str(tmp_path / "private") not in {item["source"] for item in plan["mounts"]}


def test_build_and_trial_cannot_see_private_canaries(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_CANARY", "CANARY-ENV")
    private = tmp_path / "private"
    private.mkdir()
    (private / "canary.txt").write_text("CANARY-FILE", encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    trial = tmp_path / "trial"
    trial.mkdir()
    script = (
        "import os\n"
        "print(os.environ.get('SECRET_CANARY', ''))\n"
        "try:\n"
        "    print(open(%r).read())\n"
        "except PermissionError:\n"
        "    print('FILE-HIDDEN')\n" % str(private / "canary.txt")
    )
    argv = (sys.executable, "-c", script)
    backend = FixtureBackend()
    stages = (
        confined_execute(argv, checkout, (checkout,), (), time.monotonic() + 10, backend=backend),
        confined_execute(
            argv, checkout, (trial,), (checkout,), time.monotonic() + 10, backend=backend
        ),
    )
    for record in stages:
        assert record["status"] == "completed"
        assert "CANARY-ENV" not in record["stdout"]
        assert "CANARY-FILE" not in record["stdout"]
        assert "FILE-HIDDEN" in record["stdout"]


def test_namespace_plan_binds_device_nodes_and_asks_for_a_fresh_proc(tmp_path):
    runtime = tmp_path / "driver"
    runtime.mkdir()
    plan = namespace_plan(
        (tmp_path / "work",),
        (),
        devices=(Path("/dev/null"),),
        runtime=(runtime,),
        env={"CUDA_VISIBLE_DEVICES": "0"},
    )
    modes = {item["source"]: item["mode"] for item in plan["mounts"]}
    assert modes["/dev/null"] == "dev"
    assert modes[str(runtime)] == "ro"
    assert "/proc" not in modes
    assert plan["proc"] is True
    assert plan["env"]["CUDA_VISIBLE_DEVICES"] == "0"
    assert namespace_plan((tmp_path / "work",), ())["proc"] is False


@pytest.mark.skipif(not namespaces_available(), reason="user namespaces are unavailable")
def test_unshare_binds_a_device_node_with_a_fresh_proc_and_scratch_dirs(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    script = (
        "import os, stat\n"
        "open('/dev/null', 'w').write('x')\n"
        "open('/tmp/x', 'w').write('x')\n"
        "open('/dev/shm/x', 'w').write('x')\n"
        "print('PID', os.getpid())\n"
        "print('DEV', sorted(os.listdir('/dev')))\n"
        "print('PROC', os.path.isdir('/proc/self'))\n"
        "print('TMP', oct(stat.S_IMODE(os.stat('/tmp').st_mode)))\n"
        "print('ENV', os.environ.get('GPU_PICK'))\n"
    )
    record = UnshareBackend().run(
        (sys.executable, "-c", script),
        work,
        (work,),
        (),
        time.monotonic() + 30,
        devices=(Path("/dev/null"),),
        env={"GPU_PICK": "7"},
    )
    assert record["status"] == "completed"
    lines = record["stdout"].splitlines()
    assert "PID 1" in lines
    assert "DEV ['null', 'shm']" in lines
    assert "PROC True" in lines
    assert "TMP 0o1777" in lines
    assert "ENV 7" in lines


def _gpu_ready() -> bool:
    return (
        namespaces_available()
        and Path("/dev/nvidiactl").exists()
        and importlib.util.find_spec("torch") is not None
    )


@pytest.mark.skipif(not _gpu_ready(), reason="needs user namespaces, an NVIDIA GPU and torch")
def test_unshare_gpu_trial_sees_only_the_held_device(tmp_path):
    device = os.environ.get("INFERRSI_GPU_TEST_DEVICE", "0")
    nodes = tuple(
        path
        for path in (
            Path(f"/dev/nvidia{device}"),
            Path("/dev/nvidiactl"),
            Path("/dev/nvidia-uvm"),
            Path("/dev/nvidia-uvm-tools"),
            Path("/dev/zero"),
            Path("/dev/urandom"),
        )
        if path.exists()
    )
    found = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, check=False)
    libraries = sorted(
        {
            str(Path(line.split("=>")[-1].strip()).parent)
            for line in found.stdout.splitlines()
            if "libcuda.so" in line or "libnvidia-ml.so" in line
        }
    )
    work = tmp_path / "work"
    work.mkdir()
    script = (
        "import os, torch\n"
        "x = torch.ones(256, 256, device='cuda')\n"
        "print('COUNT', torch.cuda.device_count())\n"
        "print('SUM', float((x @ x).sum()))\n"
        "print('NODES', sorted(n for n in os.listdir('/dev') if n[6:].isdigit()))\n"
    )
    record = UnshareBackend().run(
        (sys.executable, "-c", script),
        work,
        (work,),
        (),
        time.monotonic() + 300,
        devices=nodes,
        runtime=tuple(Path(item) for item in libraries),
        env={"HOME": "/tmp"},
    )
    assert record["status"] == "completed", record
    lines = record["stdout"].splitlines()
    assert "COUNT 1" in lines
    assert f"SUM {256.0 * 256 * 256}" in lines
    assert f"NODES ['nvidia{device}']" in lines
