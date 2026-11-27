import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.harness.executor import local_process, process_group_empty


@pytest.mark.parametrize("error,expected", [(None, False), (ProcessLookupError, True),
                                            (PermissionError, None)])
def test_process_group_cleanup_receipt(monkeypatch, error, expected):
    def killpg(group, signal):
        assert (group, signal) == (81, 0)
        if error is not None:
            raise error()

    monkeypatch.setattr(local_process, "os", SimpleNamespace(killpg=killpg))
    monkeypatch.setattr(local_process, "_DRAIN_SECONDS", 0)
    assert process_group_empty(81) is expected


def test_process_group_cleanup_without_a_native_probe(monkeypatch):
    monkeypatch.setattr(local_process, "os", SimpleNamespace())
    assert process_group_empty(81) is None


def test_local_executor_does_not_inherit_parent_stdin(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path('received.txt').write_bytes(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import json\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "from inferrsi.harness.executor.local_process import execute_command\n"
        "command = (sys.executable, str(Path(__file__).with_name('child.py')))\n"
        "result = execute_command(command, Path.cwd(), Path('trial'), time.monotonic() + 30)\n"
        "print(json.dumps({'status': result['status']}))\n",
        encoding="utf-8",
    )
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    completed = subprocess.run(
        (sys.executable, str(parent)),
        cwd=tmp_path,
        env=environment,
        input="Unexpected instructions from the caller's input stream.\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    assert json.loads(completed.stdout) == {"status": "completed"}
    assert (tmp_path / "received.txt").read_bytes() == b""
