from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from inferrsi import _json_v1
from inferrsi.harness import run_store
from inferrsi.harness.errors import PublicError

# Child process for the H01 RunStore tests: it claims, commits, reads, or dies at one
# injected crash point. Crash points replace module helpers inside this child only.
REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "docs" / "contracts" / "fixtures" / "t108-v4"
CHILD = Path(__file__)
# Exit status that proves the child reached its injected crash point.
CRASH = 86
ARTIFACT = "candidate output 候选\n".encode("utf-8")
ARTIFACT_MEDIA_TYPE = "text/plain"


def make_attempt() -> dict:
    return run_store.allocate_attempt(
        run_id="run-h01",
        owner="h01-test",
        target_request={
            "target_id": "cpu-h01", "executor_kind": "local_cpu", "config_revision": "1",
        },
        deadline_utc="2099-01-01T00:00:00Z",
        resources={"cpu_count": 1, "memory_bytes": None, "required_capabilities": []},
        budget={
            "policy_ref": None, "scope_id": "campaign-h01", "declared_by": "h01-test",
            "dimensions": [], "required_enforcement": [],
        },
    )


def make_digest(attempt: dict, output_root: str = "out") -> str:
    # The store treats request_digest as opaque; H execute computes it from a full spec.
    return run_store.request_digest({"attempt": attempt, "output_root": output_root})


def make_payload(
    attempt: dict, digest: str, version: int, phase: str, artifact_ref: dict | None = None
) -> dict:
    """The fixture not_started payload rebound to this attempt, or a started running one."""
    payload = _json_v1.decode((FIXTURES / "record-payload.json").read_bytes())
    payload.update(
        request_id=attempt["request_id"],
        attempt_id=attempt["attempt_id"],
        run_id=attempt["run_id"],
        owner=attempt["owner"],
        request_digest=digest,
        target_request=copy.deepcopy(attempt["target_request"]),
        retry_of=attempt["retry_of"],
        retry_reason=attempt["retry_reason"],
        record_version=version,
        recorded_at=f"2099-01-01T00:00:{version:02d}Z",
        phase=phase,
    )
    for check in payload["checks"]:
        check["attempt_id"] = attempt["attempt_id"]
    if phase == "running":
        payload.update(started=True, process_outcome=None, errors=[])
        payload["cleanup"]["status"] = "unknown"
        payload["steps"][0].update(
            status="running", started_at="2099-01-01T00:00:00Z", reasons=[]
        )
    if artifact_ref is not None:
        payload["artifacts"] = [
            {
                "role": "output",
                "artifact": artifact_ref,
                "format_schema": {"name": "text", "revision": "1"},
                "attempt_id": attempt["attempt_id"],
                "step_id": "main",
                "status": "available",
                "reasons": [],
            }
        ]
    return payload


def child_env() -> dict:
    paths = [str(REPO / "src"), os.environ.get("PYTHONPATH", "")]
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(path for path in paths if path),
        "PYTHONIOENCODING": "utf-8",
    }


def start_child(scenario: str, params: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(CHILD), scenario, str(params)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env(), encoding="utf-8",
    )


def run_child(scenario: str, params: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHILD), scenario, str(params)],
        capture_output=True, env=child_env(), encoding="utf-8", timeout=120,
    )


def _exit(*args: object, **kwargs: object) -> None:
    os._exit(CRASH)


@contextmanager
def _exit_before_commit(conn: object, begin: str = "BEGIN IMMEDIATE"):
    # The transaction's writes happen; the process dies before COMMIT.
    conn.execute(begin)
    yield
    os._exit(CRASH)


def _wait_for(path: Path, limit: float = 60.0) -> None:
    deadline = time.monotonic() + limit
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(path.name)
        time.sleep(0.01)


def _read(params: dict) -> int:
    reader = run_store.RunStoreReader.from_mount(params["mount"])
    committed = reader.committed(params["attempt_id"])
    fixed = reader.committed(params["attempt_id"], params["record_version"])
    record_bytes = reader.open(committed.record_ref["artifact"]).read()
    objects = [
        reader.open(item["artifact"]).read().decode("utf-8")
        for item in committed.payload["artifacts"]
    ]
    flat = reader.read(params["attempt_id"])
    print(json.dumps({
        "latest_ref": committed.record_ref,
        "fixed_ref": fixed.record_ref,
        "record_bytes": record_bytes.decode("utf-8"),
        "objects": objects,
        "flat_outer": sorted(set(flat) - set(committed.payload)),
        "flat_payload_equal": {key: flat[key] for key in committed.payload} == committed.payload,
    }, ensure_ascii=False))
    return 0


def main(scenario: str, params_path: str) -> int:
    params = json.loads(Path(params_path).read_text(encoding="utf-8"))
    if scenario == "read":
        return _read(params)
    work = Path(params["work"])
    attempt, digest = params["attempt"], params["digest"]
    store = run_store.RunStore(params["root"], params["namespace"])
    if scenario == "contend":
        _wait_for(work / "go")
        try:
            claim = store.claim(attempt, digest)
        except PublicError as exc:
            print(json.dumps({"outcome": exc.code}), flush=True)
            return 0
        print(json.dumps({"outcome": "claimed"}), flush=True)
        # Hold the owner lock until every other contender has answered.
        _wait_for(work / "release")
        claim.release()
        return 0
    if scenario == "crash-claim":
        run_store._transaction = _exit_before_commit
        store.claim(attempt, digest)
        return 1
    claim = store.claim(attempt, digest)
    if scenario == "side-effect":
        (work / "side-effect.txt").write_text("external side effect", encoding="utf-8")
        os._exit(CRASH)
    if scenario == "running-then-crash":
        claim.commit(make_payload(attempt, digest, 1, "running"))
        os._exit(CRASH)
    if scenario == "lost-response":
        claim.commit(make_payload(attempt, digest, 1, "finished"))
        os._exit(CRASH)
    ref = run_store.artifact_ref(params["namespace"], ARTIFACT, ARTIFACT_MEDIA_TYPE)
    payload = make_payload(attempt, digest, 1, "finished", artifact_ref=ref)
    if scenario == "crash-temp":
        run_store._publish = _exit
    elif scenario == "crash-object":
        run_store.RunStore._append = _exit
    elif scenario == "crash-record":
        run_store._transaction = _exit_before_commit
    else:
        raise SystemExit(f"unknown scenario {scenario}")
    claim.commit(payload, [(ref, ARTIFACT)])
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
