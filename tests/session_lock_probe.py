"""Hold a real optimization session's lock from a separate Harness process, then export it.

Run by tests/test_session_lock_across_processes.py once per interpreter: against the
checkout in the test run, and against an installed wheel in tests/check_installed.py. It
builds a valid managed session that is not final, starts a child process that
holds ``<session>/.session.lock`` through ``harness.optimization``'s own lock, and exports the
session through the Apps ``export_bundle`` from this process. While the child holds the lock
the export must be refused and publish nothing; after it releases, the same export must
publish a bundle whose ``export.kind`` is ``progress``.

Usage: session_lock_probe.py <workdir>. Prints one JSON line with the observed outcomes.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import inferrsi
from inferrsi.apps import delivery
from inferrsi.apps.storage.artifacts import atomic_write_json, sha256
from inferrsi.harness import optimization

# The child runs with -I and imports inferrsi from the same location as this process.
HOLDER = """
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[4])
from inferrsi.harness.optimization import _locked

root, ready, release = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
with _locked(root):
    ready.write_text("held", encoding="utf-8")
    deadline = time.monotonic() + 60
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
"""


def make_session(root: Path) -> None:
    frozen = root / "frozen"
    frozen.mkdir(parents=True)
    (frozen / "baseline.py").write_text("10", encoding="utf-8")
    (frozen / "TASK.md").write_text("Synthetic lock probe; no accelerator claim", encoding="utf-8")
    plan = {
        "schema_version": 2, "task": "synthetic", "task_source": "project", "condition": "test",
        "candidate_kind": "file", "candidate_name": "candidate.py",
        "baseline_path": "frozen/baseline.py", "working_candidate": "candidate.py",
        "round_mode": "exact", "round_limit": 2, "max_seconds": 600, "final_reserve_seconds": 60,
        "selection": {"direction": "minimize", "metric": "latency", "initial_score": 10},
        "evaluation_settings": {"metric_key": "latency", "metric_unit": "ms",
                                "scope": "synthetic", "direction": "minimize", "repetitions": 2},
        "frozen_files": {p.name: sha256(p) for p in frozen.iterdir()},
    }
    optimization.initialize(root, plan)
    # A round needs recorded bottleneck evidence first. The file sits beside the session
    # root, as in tests/diagnosis_support.py, which an installed wheel does not ship.
    evidence = root.with_name(root.name + "-measurement.txt")
    evidence.write_text("Synthetic workload: reference operation took 4 ms.", encoding="utf-8")
    optimization.record_diagnosis(root, "Reference operation", evidence)

    def execute(root, directory, plan, deadline):
        (directory / "execution").mkdir()
        execution = {"status": "completed", "returncode": 0, "elapsed_seconds": 1}
        atomic_write_json(directory / "execution/execution.json", execution)
        atomic_write_json(directory / "measurement.json",
                          {"synthetic_value": float((directory / "candidate.py").read_text())})
        return execution

    def assess(root, directory, plan, execution):
        value = json.loads((directory / "measurement.json").read_text())["synthetic_value"]
        verdict = "PASS" if value < 10 else "FAIL"
        return {
            "status": "completed", "score": value, "baseline_score": 10, "verdict": verdict,
            "eligible": verdict == "PASS", "quality_passed": True, "speedup": 10 / value,
            "scope": "synthetic", "claim_id": "synthetic-primary",
            "reason": "Synthetic fixture assessment",
            "metrics": {"name": "latency", "unit": "ms", "direction": "minimize", "baseline": 10,
                        "candidate": value, "samples": {"baseline": [10, 10],
                                                        "candidate": [value, value]}},
            "evidence_files": {"measurement.json": sha256(directory / "measurement.json")},
        }

    candidate = root / "candidate.py"
    candidate.write_text("5", encoding="utf-8")
    optimization.evaluate_round(root, candidate=candidate, hypothesis="Synthetic score 5",
                                usage=None, execute=execute, assess=assess)
    # No final round: the session stays active, so its export is a progress export.


def main(work: Path) -> dict:
    # The Apps export refuses a path that crosses a symbolic link, and macOS temporary
    # directories sit under /var, a link to /private/var, so use the resolved path.
    work = work.resolve()
    root = work / "campaign"
    make_session(root)
    ready, release = work / "held", work / "release"
    holder = subprocess.Popen(
        [sys.executable, "-I", "-c", HOLDER, str(root), str(ready), str(release),
         str(Path(inferrsi.__file__).resolve().parents[1])],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not ready.exists():
            assert holder.poll() is None, holder.communicate()
            assert time.monotonic() < deadline, "the Harness holder never took the lock"
            time.sleep(0.02)
        busy = delivery.export_bundle(root, work / "busy", export_id="busy")
        assert "writer is active" in busy.get("error", ""), busy
        busy_published = (work / "busy").exists()
    finally:
        release.write_text("done", encoding="utf-8")
        holder.communicate(timeout=60)
    released = None
    deadline = time.monotonic() + 30
    while True:
        released = delivery.export_bundle(root, work / "released", export_id="released")
        if released["status"] == "published" or time.monotonic() > deadline:
            break
        time.sleep(0.1)
    published = released["status"] == "published"
    return {
        "busy_status": busy["status"], "busy_published": busy_published,
        "released_status": released["status"],
        "released_kind": delivery.read_bundle(work / "released")["export"]["kind"]
        if published else None,
    }


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]))))
