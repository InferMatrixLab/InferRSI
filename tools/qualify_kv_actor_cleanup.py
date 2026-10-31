"""Model-free qualification of namespace cleanup with a trusted fork/setsid probe.

No candidate input is accepted. Only this authored probe may fork; the real
candidate profile remains RLIMIT_NPROC=0. Every execution still uses the existing
bubblewrap boundary and execute_command. Missing isolation/visibility is not PASS.
"""

import argparse
import hashlib
import json
import math
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT / "src"))

from inferrsi.harness.skill_eval_engineering import (  # noqa: E402
    SandboxUnavailable,
    read_regular,
    sandbox_command,
)
from inferrsi.infra.artifacts import atomic_write_json  # noqa: E402
from inferrsi.infra.executors.local import execute_command  # noqa: E402
from inferrsi.infra.targets import repository_identity  # noqa: E402

PROBE = '''import json, os, resource, sys, time
resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
try:
    child = os.fork()
except OSError:
    print(json.dumps({"role": "unavailable"}), flush=True)
    raise SystemExit(1)
if child == 0:
    try:
        os.setsid()
    except OSError:
        print(json.dumps({"role": "unavailable"}), flush=True)
        os._exit(1)
    with open("/proc/self/stat") as stream:
        start = int(stream.read().rsplit(")", 1)[1].split()[19])
    print(json.dumps({"role": "detached", "own_session": os.getsid(0) == os.getpid(),
                      "namespace_pid": os.getpid(), "start": start,
                      "pid_namespace": os.readlink("/proc/self/ns/pid")}), flush=True)
    time.sleep(30)
    os._exit(0)
print(json.dumps({"role": "parent"}), flush=True)
time.sleep(0.5 if sys.argv[1] == "normal" else 30)
'''


def _stat(path):
    value = path.read_text().rsplit(")", 1)[1].split()
    return {"state": value[0], "ppid": int(value[1]), "start": int(value[19])}


def _owned_snapshot(parent, known, *, proc=Path("/proc")):
    """Read stat only; retain information only for this probe's descendants."""
    current, visible = {}, True
    try:
        entries = list(proc.iterdir())
    except OSError:
        return {}, False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            current[int(entry.name)] = _stat(entry / "stat")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, IndexError):
            visible = False
    selected = {pid: item for pid, item in current.items()
                if known.get(pid) == item["start"]}
    parents = {parent, *selected}
    while True:
        added = {pid: item for pid, item in current.items()
                 if item["ppid"] in parents and pid != parent and pid not in selected}
        if not added:
            break
        selected.update(added)
        parents.update(added)
    return selected, visible


def _events(path):
    try:
        return [json.loads(line) for line in read_regular(path, 65536).decode().splitlines()]
    except (OSError, ValueError, UnicodeError):
        return []


def _bind_detached(events, owned, *, proc=Path("/proc")):
    """Match a trusted marker to an already-owned host PID, never a count heuristic."""
    markers = [e for e in events if e.get("role") == "detached"]
    if len(markers) != 1:
        return None
    marker = markers[0]
    if (set(marker) != {"role", "own_session", "namespace_pid", "start", "pid_namespace"}
            or marker["own_session"] is not True
            or type(marker["namespace_pid"]) is not int or marker["namespace_pid"] <= 0
            or type(marker["start"]) is not int or marker["start"] < 0
            or type(marker["pid_namespace"]) is not str):
        return None
    matches = []
    for pid, item in owned.items():
        if item["start"] != marker["start"]:
            continue
        try:
            fields = (proc / str(pid) / "status").read_text().splitlines()
            nspid = next(line.split()[1:] for line in fields if line.startswith("NSpid:"))
            namespace = os.readlink(proc / str(pid) / "ns/pid")
            if (int(nspid[-1]) == marker["namespace_pid"]
                    and namespace == marker["pid_namespace"]):
                matches.append({"pid": pid, "start": item["start"]})
        except (OSError, ValueError, IndexError, StopIteration):
            continue
    return matches[0] if len(matches) == 1 else None


def _bind_chain(worker_events, detached, owned):
    markers = [e for e in worker_events if e.get("role") == "worker"]
    if detached is None or len(markers) != 1:
        return None
    worker = markers[0]
    if (set(worker) != {"role", "pid", "start"}
            or type(worker["pid"]) is not int or type(worker["start"]) is not int
            or owned.get(worker["pid"], {}).get("start") != worker["start"]):
        return None
    chain, pid = [], detached["pid"]
    while pid in owned and pid not in chain:
        chain.append(pid)
        if pid == worker["pid"]:
            # At least one nested sandbox process must separate worker and probe.
            return {"worker": {k: worker[k] for k in ("pid", "start")},
                    "detached": detached, "chain_length": len(chain)} if len(chain) >= 3 else None
        pid = owned[pid]["ppid"]
    return None


def nested_worker(mode, work, output, deadline):
    """Trusted stand-in for the actor's nested executor; no candidate input accepted."""
    work = Path(work)
    if (mode not in {"normal", "timeout", "cancel"} or work.is_symlink()
            or {p.name for p in work.iterdir()} != {"runner.py"}
            or read_regular(work / "runner.py", 65536) != PROBE.encode()):
        raise ValueError("Only the exact authored descendant probe is accepted")
    own = _stat(Path("/proc/self/stat"))
    print(json.dumps({"role": "worker", "pid": os.getpid(), "start": own["start"]}), flush=True)
    record = execute_command((*sandbox_command(work), mode), work, output, deadline,
                             environment={"PATH": "/usr/bin:/bin", "LANG": "C"})
    return 0 if record["status"] == "completed" else 1


def probe_worker(mode, output, deadline):
    """Run only in the dedicated qualifier child; cancellation signals THIS child."""
    if mode not in {"normal", "timeout", "cancel"}:
        raise ValueError("Unknown trusted cleanup probe")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    known, visibility, stop = {}, [True], threading.Event()
    cancelled, bound_chain = [False], [None]
    cancel_at = [None]
    stdout = output / "sandbox/stdout.log"
    worker_stdout = output / "worker/stdout.log"

    def observe():
        while not stop.is_set():
            found, visible = _owned_snapshot(os.getpid(), known)
            visibility[0] = visibility[0] and visible
            known.update({pid: item["start"] for pid, item in found.items()})
            observed = _bind_chain(_events(worker_stdout),
                                   _bind_detached(_events(stdout), found), found)
            if observed is not None:
                bound_chain[0] = observed
            if (mode == "cancel" and cancel_at[0] is None
                    and observed is not None):
                cancel_at[0] = time.monotonic() + 0.05
            if (cancel_at[0] is not None and not cancelled[0]
                    and time.monotonic() >= cancel_at[0] and not stop.is_set()):
                cancelled[0] = True
                os.kill(os.getpid(), signal.SIGINT)
            stop.wait(0.02)

    result = {"mode": mode, "verdict": "INCONCLUSIVE", "model_calls": 0,
              "scope": "outer-worker nested sandbox cleanup; trusted probe, NOT candidate profile"}
    observer = threading.Thread(target=observe, daemon=True)
    try:
        with tempfile.TemporaryDirectory(prefix="kv-tree-probe-") as temporary:
            work = Path(temporary)
            (work / "runner.py").write_text(PROBE)
            sandbox_command(work)  # Fail closed before spawning if unavailable.
            command = (sys.executable, "-I", str(Path(__file__).resolve()),
                       "--nested-worker", mode, "--work", str(work),
                       "--output", str(output / "sandbox"), "--deadline", repr(deadline))
            observer.start()
            try:
                record = execute_command(command, work, output / "worker", deadline,
                                         environment={"PATH": "/usr/bin:/bin", "LANG": "C"})
            finally:
                stop.set()
                observer.join(timeout=1)
            found, visible = _owned_snapshot(os.getpid(), known)
            visibility[0] = visibility[0] and visible and not observer.is_alive()
            alive = [pid for pid, item in found.items() if item["state"] != "Z"]
            expected_status = {"normal": "completed", "timeout": "timeout", "cancel": "cancelled"}
            events = _events(stdout)
            detached = bound_chain[0] is not None
            ready = {"role": "parent"} in events and detached
            result.update(executor_status=record["status"], observed_descendants=len(known),
                          detached_session_observed=detached, visibility_complete=visibility[0],
                          surviving_descendants=len(alive), explicit_cancel_sent=cancelled[0],
                          candidate_profile_unchanged=True,
                          outer_worker_supervised=True, bound_chain=bound_chain[0])
            if alive:
                result["verdict"] = "FAIL"
                # Recovery does not turn a failed cleanup test into PASS. Kill
                # only PID+starttime identities observed as this probe's children.
                killed = 0
                for pid in alive:
                    try:
                        if _stat(Path("/proc") / str(pid) / "stat")["start"] == known[pid]:
                            os.kill(pid, signal.SIGKILL)
                            killed += 1
                    except (OSError, ValueError, IndexError):
                        pass
                result["recovery_kills"] = killed
                # SIGKILL delivery is asynchronous. Establish the recovery outcome
                # without changing the failed verdict or granting more worker time.
                recovery_deadline = time.monotonic() + 1
                while True:
                    remaining, visible = _owned_snapshot(os.getpid(), known)
                    survivors = [p for p, item in remaining.items() if item["state"] != "Z"]
                    if not survivors or time.monotonic() >= recovery_deadline:
                        result["recovery_survivors"] = len(survivors)
                        result["recovery_visibility_complete"] = visible
                        break
                    time.sleep(0.01)
            elif (ready and visibility[0] and record["status"] == expected_status[mode]
                    and (mode == "normal" or record["returncode"] == -signal.SIGKILL)):
                result["verdict"] = "PASS"
            else:
                result["reason"] = "isolation_or_observation_incomplete"
    except (SandboxUnavailable, OSError):
        result["reason"] = "sandbox_unavailable"
    finally:
        stop.set()
        if observer.is_alive():
            observer.join(timeout=1)
        atomic_write_json(output / "result.json", result)
    return result


def qualify(output, deadline, probe_seconds):
    """Own a fresh child for each normal/timeout/cancel case, no parent SIGINT."""
    if (type(probe_seconds) not in (float, int) or not 0 < probe_seconds <= 30
            or type(deadline) not in (float, int) or not math.isfinite(deadline)
            or deadline <= time.monotonic()):
        raise ValueError("Explicit bounded probe duration required")
    identity = repository_identity(ROOT)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "kv-actor-descendant-qualification-v1", "model_calls": 0,
              "probe_sha256": hashlib.sha256(PROBE.encode()).hexdigest(), "cases": {},
              "qualifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "revision": identity.get("head"), "snapshot_hash": identity.get("snapshot_hash"),
              "dirty": identity.get("dirty"),
              "scope": "outer-worker nested namespace cleanup; no actor efficacy or provider proof"}
    for mode in ("normal", "timeout", "cancel"):
        worker_deadline = min(deadline - 1, time.monotonic() + probe_seconds)
        command = (sys.executable, "-I", str(Path(__file__).resolve()), "--probe-worker", mode,
                   "--output", str(output / mode), "--deadline", repr(worker_deadline))
        record = execute_command(command, ROOT, output / f"{mode}-supervisor", deadline,
                                 environment={"PATH": "/usr/bin:/bin", "LANG": "C"})
        try:
            case = json.loads(read_regular(output / mode / "result.json", 65536))
        except (OSError, ValueError):
            case = {"verdict": "INCONCLUSIVE", "reason": "probe_worker_incomplete"}
        if record["status"] != "completed":
            case = {**case, "verdict": "INCONCLUSIVE", "worker_status": record["status"]}
        result["cases"][mode] = case
    verdicts = [v["verdict"] for v in result["cases"].values()]
    result["verdict"] = ("FAIL" if "FAIL" in verdicts else "PASS" if set(verdicts) == {"PASS"}
                         else "INCONCLUSIVE")
    after = repository_identity(ROOT)
    result["source_unchanged"] = (identity.get("available") and after.get("available")
                                  and identity.get("snapshot_hash") == after.get("snapshot_hash"))
    if not result["source_unchanged"]:
        result["verdict"] = "INCONCLUSIVE"
    atomic_write_json(output / "qualification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-worker", choices=("normal", "timeout", "cancel"))
    parser.add_argument("--nested-worker", choices=("normal", "timeout", "cancel"))
    parser.add_argument("--work", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--probe-seconds", type=float)
    args = parser.parse_args()
    if args.nested_worker:
        if args.probe_worker or args.work is None:
            parser.error("Nested trusted worker requires its private probe workspace")
        return nested_worker(args.nested_worker, args.work, args.output, args.deadline)
    if args.probe_worker:
        probe_worker(args.probe_worker, args.output, args.deadline)
    else:
        if args.probe_seconds is None:
            parser.error("--probe-seconds must be explicit")
        result = qualify(args.output, args.deadline, args.probe_seconds)
        print(json.dumps({"verdict": result["verdict"], "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
