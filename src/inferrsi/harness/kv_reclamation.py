"""Bounded synthetic CPU artifact replay; no agent or model execution adapter.

The oracle stays in the controller. Submitted code sees only inputs inside the
existing Linux bubblewrap boundary. Unavailable isolation has no host fallback.
"""

import hashlib
import json
import os
import socket
import tempfile
import time
from pathlib import Path

from ..infra.artifacts import atomic_write_json, write_json
from ..infra.executors.local import execute_command
from .skill_eval_engineering import SandboxUnavailable, read_regular, sandbox_command

MAX_SOURCE_BYTES = 65536

# This driver contains no expected answers, verifier, knowledge or timing API.
# Timing is the existing host executor's elapsed time, not an artifact assertion.
DRIVER = '''import json, os, resource, socket, sys
resource.setrlimit(resource.RLIMIT_CPU, (16, 16))
resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
resource.setrlimit(resource.RLIMIT_FSIZE, (4194304, 4194304))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
print("INFERRSI_KV_READY", file=sys.stderr, flush=True)
with open("/work/inputs.json", encoding="utf-8") as stream:
    payload = json.load(stream)
if payload["mode"] == "probe":
    inaccessible = []
    for path in payload["inaccessible"]:
        try:
            with open(path, "rb") as stream:
                stream.read(1)
        except OSError:
            inaccessible.append(True)
        else:
            inaccessible.append(False)
    try:
        open("/work/write-probe", "w").close()
        readonly = False
    except OSError:
        readonly = True
    connection = socket.socket()
    connection.settimeout(0.25)
    try:
        network_blocked = connection.connect_ex(("127.0.0.1", payload["host_port"])) != 0
    except OSError:
        network_blocked = True
    finally:
        connection.close()
    try:
        child = os.fork()
    except OSError:
        fork_denied = True
    else:
        if child == 0:
            os._exit(0)
        os.waitpid(child, 0)
        fork_denied = False
    print(json.dumps({"inaccessible": inaccessible, "readonly": readonly,
                      "clean_env": "KV_QUALIFICATION_SECRET" not in os.environ,
                      "network_blocked": network_blocked, "fork_denied": fork_denied,
                      "limits": {name: list(resource.getrlimit(k)) for name, k in
                          (("memory", resource.RLIMIT_AS), ("processes", resource.RLIMIT_NPROC),
                           ("cpu", resource.RLIMIT_CPU), ("output", resource.RLIMIT_FSIZE),
                           ("files", resource.RLIMIT_NOFILE), ("core", resource.RLIMIT_CORE))}}))
else:
    namespace = {"__name__": "submitted_candidate"}
    with open("/work/candidate.py", encoding="utf-8") as stream:
        exec(compile(stream.read(), "candidate.py", "exec"), namespace)
    target = namespace["Reclaimer"]()
    observations = []
    def pending():
        value = target.pending()
        if (type(value) is not list or any(type(item) is not tuple or len(item) != 3
                or type(item[0]) is not str or type(item[1]) is not int
                or type(item[2]) is not tuple
                or any(type(block) is not int for block in item[2]) for item in value)):
            raise TypeError("pending shape")
        return list(value)
    for event in payload["events"]:
        try:
            result = target.apply(event)
        except ValueError:
            observation = {"error": "ValueError"}
        else:
            if type(result) is not list or any(type(block) is not int for block in result):
                raise TypeError("reclaimed shape")
            observation = {"reclaimed": list(result)}
        if payload["mode"] == "verify":
            observation["pending"] = pending()
        observations.append(observation)
    print(json.dumps({"observations": observations, "pending": pending()}, allow_nan=False))
'''


def source_bytes(path: Path) -> bytes:
    source = read_regular(path, MAX_SOURCE_BYTES)
    if not source:
        raise ValueError("Candidate source is empty")
    source.decode("utf-8")
    return source


def workspace_hashes(workspace: Path) -> dict:
    """Only candidate.py may differ; reject symlinks, special and extra nodes."""
    hashes = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Task workspace contains unsafe nodes")
        if path.is_file():
            hashes[path.relative_to(workspace).as_posix()] = hashlib.sha256(
                read_regular(path, 16 * 1024 * 1024)).hexdigest()
    return hashes


def capture_artifact(workspace: Path, frozen: dict) -> bytes:
    current = workspace_hashes(workspace)
    if set(current) != set(frozen) or any(current[name] != value
                                         for name, value in frozen.items()
                                         if name != "candidate.py"):
        raise ValueError("Protected paths changed or artifact missing")
    return source_bytes(workspace / "candidate.py")


def invoke(source: bytes, payload: dict, output: Path, deadline: float) -> tuple[dict, dict | None]:
    """One resource-bounded process; output/answer checking belongs to the parent."""
    if type(source) is not bytes or not 0 < len(source) <= MAX_SOURCE_BYTES:
        raise ValueError("Candidate source must be bounded nonempty bytes")
    source.decode("utf-8")
    with tempfile.TemporaryDirectory(prefix="kv-replay-") as temporary:
        work = Path(temporary)
        (work / "candidate.py").write_bytes(source)
        (work / "runner.py").write_text(DRIVER, encoding="utf-8", newline="\n")
        write_json(work / "inputs.json", payload)
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C"}
        if payload.get("mode") == "probe":
            environment["KV_QUALIFICATION_SECRET"] = "synthetic-not-a-secret"
        record = execute_command(
            tuple(sandbox_command(work)), work, output, deadline,
            environment=environment,
        )
        # Retain the original outcome before readiness/output checks can return or raise.
        # Closed projection only: no host paths, arbitrary error text or environment.
        atomic_write_json(output / "execution.json", {
            name: record.get(name) for name in ("status", "returncode", "elapsed_seconds")
        })
    if record["status"] in {"timeout", "error", "cancelled"}:
        return record, None
    marker = Path(record["stderr_path"]).read_bytes()[:128]
    if not marker.startswith(b"INFERRSI_KV_READY\n"):
        raise SandboxUnavailable("KV replay did not establish its sandbox boundary")
    if record["status"] != "completed":
        return record, None
    try:
        data = read_regular(Path(record["stdout_path"]), 4 * 1024 * 1024)
        return record, json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        return record, None


def process_group_gone(record: dict) -> bool:
    group = record.get("process_group_id")
    if os.name == "nt" or group is None:
        return False
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


def probe_isolation(output: Path, deadline: float, forbidden: list[str]) -> dict:
    forbidden = [*forbidden, f"/proc/{os.getpid()}/cmdline"]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        record, value = invoke(b"# no submitted code\n", {
            "mode": "probe", "inaccessible": forbidden,
            "host_port": listener.getsockname()[1],
        }, output, deadline)
    if (record["status"] != "completed" or not isinstance(value, dict)
            or value.get("inaccessible") != [True] * len(forbidden)
            or value.get("readonly") is not True or value.get("clean_env") is not True
            or value.get("network_blocked") is not True or value.get("fork_denied") is not True
            or value.get("limits") != {"memory": [268435456, 268435456],
                                       "processes": [0, 0], "cpu": [16, 16],
                                       "output": [4194304, 4194304], "files": [32, 32],
                                       "core": [0, 0]}
            or not process_group_gone(record)):
        raise SandboxUnavailable("KV isolation probes failed; no host fallback")
    value["normal_exit_process_group_gone"] = True
    return value


def verify_source(source: bytes, traces: list[dict], output: Path, deadline: float,
                  compare) -> dict:
    """Compare every event and pending state using an independently frozen oracle."""
    checks = {}
    for index, trace in enumerate(traces):
        if time.monotonic() >= deadline:
            return {"verdict": "INCONCLUSIVE", "checks": checks, "reason": "deadline"}
        record, value = invoke(source, {"mode": "verify", "events": trace["events"]},
                               output / f"trace-{index:03d}", deadline)
        if record["status"] in {"error", "timeout", "cancelled"}:
            return {"verdict": "INCONCLUSIVE", "checks": checks,
                    "reason": record["status"]}
        checks[trace["id"]] = compare(trace, value)
    return {"verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
