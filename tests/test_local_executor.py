import json
import os
import subprocess
import sys
from pathlib import Path


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
        "from inferrsi.infra.executors.local import execute_command\n"
        "command = (sys.executable, str(Path(__file__).with_name('child.py')))\n"
        "result = execute_command(command, Path.cwd(), Path('trial'), time.monotonic() + 30)\n"
        "print(json.dumps({'status': result['status']}))\n",
        encoding="utf-8",
    )
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
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
