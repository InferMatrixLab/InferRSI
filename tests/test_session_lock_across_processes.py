"""The Harness and Apps session locks exclude each other across real processes.

Harness writers hold ``<session>/.session.lock`` through ``harness.artifact_primitives``.
An Apps export holds it through ``apps.artifacts``. Each side has its own copy of the lock
code, so per-copy parity tests can pass while the pair fails to exclude. These tests start a
separate process for each holder, so they cover the actual writer and reader on Windows
(msvcrt byte range) and POSIX (flock) alike. #498 slice 3b; the busy-writer mapping of #494
stays a separate assertion in tests/test_result_delivery.py.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferrsi.apps import artifacts as apps_artifacts
from inferrsi.apps import delivery
from inferrsi.harness import artifact_primitives as harness_artifacts

SRC = str(Path(__file__).resolve().parents[1] / "src")

# A child process takes the named lock, reports it, then waits for a release file.
HOLDER = """
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
side, lock, ready, release = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
if side == "harness":
    from inferrsi.harness.artifact_primitives import file_lock
else:
    from inferrsi.apps.artifacts import file_lock
with file_lock(lock):
    ready.write_text("held", encoding="utf-8")
    deadline = time.monotonic() + 60
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
"""

# A child process tries the named lock once without blocking and reports the outcome.
PROBE = """
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
side, lock = sys.argv[2], Path(sys.argv[3])
if side == "harness":
    from inferrsi.harness.artifact_primitives import file_lock
else:
    from inferrsi.apps.artifacts import file_lock
try:
    with file_lock(lock):
        outcome = {"acquired": True}
except OSError as error:
    outcome = {"acquired": False, "error": type(error).__name__}
print(json.dumps(outcome))
"""


def _wait_for(path: Path, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 30
    while not path.exists():
        assert process.poll() is None, process.communicate()
        assert time.monotonic() < deadline, "the holder never took the lock"
        time.sleep(0.02)


def _probe(side: str, lock: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-I", "-c", PROBE, SRC, side, str(lock)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return json.loads(result.stdout)


@pytest.fixture
def hold(tmp_path):
    """Start a process that holds the lock of the given side until released."""
    started = []

    def start(side: str, lock: Path):
        ready, release = tmp_path / f"{side}.ready", tmp_path / f"{side}.release"
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", HOLDER, SRC, side, str(lock), str(ready), str(release)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        started.append((process, release))
        _wait_for(ready, process)
        return release

    yield start
    for process, release in started:
        release.write_text("done", encoding="utf-8")
        process.communicate(timeout=60)


@pytest.mark.parametrize("holder, contender", [("harness", "apps"), ("apps", "harness")])
def test_a_held_lock_excludes_the_other_copy_in_another_process(tmp_path, hold, holder, contender):
    lock = tmp_path / ".session.lock"
    release = hold(holder, lock)
    blocked = _probe(contender, lock)
    assert blocked["acquired"] is False, blocked
    release.write_text("done", encoding="utf-8")
    deadline = time.monotonic() + 30
    while True:
        outcome = _probe(contender, lock)
        if outcome["acquired"]:
            break
        assert time.monotonic() < deadline, "the lock was never released"
        time.sleep(0.05)
    assert outcome == {"acquired": True}


def _campaign(root: Path) -> Path:
    root.mkdir()
    (root / "state.json").write_text(json.dumps({"started_at": 1.0}), encoding="utf-8")
    return root


def test_an_apps_reader_is_refused_while_a_harness_process_holds_the_session(tmp_path, hold):
    # The actual writer and reader pair: a Harness process holds the session lock, and the
    # Apps copy of the lock, which `delivery.project` takes, cannot be taken by another
    # process until it is released. The retryable `SnapshotBusy` mapping of that refusal is
    # #494 and stays a separate assertion in tests/test_result_delivery.py; this test needs
    # only the contention itself, which is a PermissionError on Windows (msvcrt) and a
    # BlockingIOError on POSIX (flock).
    root = _campaign(tmp_path / "campaign")
    lock = root / ".session.lock"
    release = hold("harness", lock)
    assert _probe("apps", lock)["acquired"] is False
    release.write_text("done", encoding="utf-8")
    deadline = time.monotonic() + 30
    while not _probe("apps", lock)["acquired"]:
        assert time.monotonic() < deadline, "the Harness holder never released"
        time.sleep(0.05)
    # Released: the whole export now succeeds against a managed session or fails for a
    # reason other than the lock, never as a busy writer.
    with pytest.raises(ValueError) as outcome:
        delivery.project(root, export_id="released")
    assert "writer is active" not in str(outcome.value)
    with apps_artifacts.file_lock(lock), pytest.raises(OSError):
        with harness_artifacts.file_lock(lock):
            pass
