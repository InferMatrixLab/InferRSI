"""Subprocess controls for testing the optimization session boundary."""

import os
import subprocess
import sys
import time
import venv
from pathlib import Path


def target_python(tmp_path, monkeypatch, runtime):
    """Model a coordinator whose site-packages shadow a target-only dependency."""
    environment = tmp_path / "target"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    target_site = Path(subprocess.check_output(
        [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True,
    ).strip())
    (target_site / "session_target_dependency.py").write_text("VALUE = 2\n", encoding="utf-8")
    coordinator = tmp_path / "coordinator-site"
    (coordinator / "inferrsi").mkdir(parents=True)
    (coordinator / "session_target_dependency.py").write_text("VALUE = 99\n", encoding="utf-8")
    execute = runtime._session_execute

    def execute_with_coordinator_site(*args):
        with monkeypatch.context() as patch:
            patch.setattr(runtime, "files", lambda name: coordinator / name)
            return execute(*args)

    monkeypatch.setattr(runtime, "_session_execute", execute_with_coordinator_site)
    return python


def kill_controller(program, arguments, marker):
    """Wait for the test child to run, then kill only its controller."""
    source = Path(__file__).resolve().parents[2] / "src"
    environment = {**os.environ, "PYTHONPATH": str(source)}
    with subprocess.Popen(
        [sys.executable, "-c", program, *arguments], env=environment, cwd=marker.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) as controller:
        try:
            deadline = time.monotonic() + 10
            while (not marker.is_file() and controller.poll() is None
                   and time.monotonic() < deadline):
                time.sleep(0.02)
            assert marker.is_file(), f"Child did not start, controller exit: {controller.poll()}"
            assert controller.poll() is None
        finally:
            if controller.poll() is None:
                controller.kill()
            controller.wait(timeout=10)
