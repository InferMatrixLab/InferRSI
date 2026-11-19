"""Evaluate one reviewed MoE candidate on two caller-allocated Ascend NPUs.

No agent, scheduler, SSH, search policy or token accounting is started here.
Importing this module and reading task resources require no device libraries.
"""

import argparse
import importlib.util
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

from inferrsi.benchmark.artifacts import atomic_write_json
from inferrsi.benchmark.metrics import read_metric

# Worker cleanup for this MoE invocation, including detached torchrun sessions.
# torchrun workers may create their own sessions, outside the executor's process
# group. Only the launcher receives a fresh marker; it cannot reach the invoking
# shell or allocator. This is lifecycle supervision for reviewed code, not a sandbox.
# The marker must be generated in this driver after it starts, as evaluate() does.
MARKER = "INFERRSI_MOE_RUN_ID"


def _members(token: str, proc: Path = Path("/proc"), *, errors=None) -> list[dict]:
    marker = (MARKER + "=" + token).encode()
    found = []
    # A fresh marker can only be inherited by processes started after this
    # driver. Older same-user services may have unreadable environments; they
    # cannot own this invocation. Keep same-tick processes in scope because
    # Linux start times have tick granularity, not a strict ordering within it.
    driver_fields = (proc / "self" / "stat").read_text().rsplit(")", 1)[1].split()
    driver_start = int(driver_fields[19])
    # A missing procfs must raise, never be interpreted as successful cleanup.
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] == "Z":
                continue
            start_ticks = int(fields[19])
            if start_ticks < driver_start:
                continue
            if marker in (entry / "environ").read_bytes().split(b"\0"):
                found.append({"pid": int(entry.name), "start_ticks": start_ticks})
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, IndexError) as exc:
            if errors is None:
                raise
            # Preserve confirmed workers even when another process is unreadable.
            # The caller must keep the resulting cleanup verdict inconclusive.
            errors.add(str(exc))
    return found


def cleanup(token: str, *, grace_seconds: float = 5.0) -> dict:
    """Clean a marker minted by this driver; preserve PID-reuse protection."""
    killed = set()
    errors = set()
    deadline = time.monotonic() + grace_seconds
    try:
        while True:
            members = _members(token, errors=errors)
            if not members:
                return {"verified": not errors, "signalled_pids": sorted(killed),
                        "remaining": [], **({"error": "; ".join(sorted(errors))} if errors else {})}
            for item in members:
                try:
                    fields = Path(f"/proc/{item['pid']}/stat").read_text().rsplit(")", 1)[1].split()
                    if int(fields[19]) == item["start_ticks"]:
                        os.kill(item["pid"], signal.SIGKILL)
                        killed.add(item["pid"])
                except (FileNotFoundError, ProcessLookupError):
                    pass
                except (OSError, ValueError, IndexError) as exc:
                    errors.add(str(exc))
            if time.monotonic() >= deadline:
                remaining = _members(token, errors=errors)
                return {"verified": False, "signalled_pids": sorted(killed),
                        "remaining": remaining,
                        **({"error": "; ".join(sorted(errors))} if errors else {})}
            time.sleep(0.05)
    except (OSError, ValueError, IndexError) as exc:
        return {"verified": False, "signalled_pids": sorted(killed), "error": str(exc)}


# The protocol is a task-owned file, loaded by exact path from this bundle.
# Its pure rules are also used by the isolated Harness protocol interpreter.
_spec = importlib.util.spec_from_file_location("moe_task_protocol", Path(__file__).with_name(
    "optimization.py"))
_protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_protocol)
TASK_FILES = _protocol.TASK_FILES
_positive = _protocol._positive
_hashes = _protocol._hashes
_adjudicate = _protocol._adjudicate


def task_resources():
    return Path(__file__).resolve().parent


def _preflight(candidate: Path, output: Path, pairs: int, timeout_seconds: float):
    if type(pairs) is not int or pairs <= 0:
        raise ValueError("pairs must be a positive integer")
    if not _positive(timeout_seconds):
        raise ValueError("timeout-seconds must be finite and positive")
    if not candidate.is_file() or candidate.suffix != ".py":
        raise ValueError("candidate must be a reviewed, self-contained Python file")
    if output.exists():
        raise FileExistsError("output-dir must be new; use a separate directory per candidate")
    if sys.platform != "linux":
        raise OSError("MoE execution requires Linux, readable /proc and two allocated Ascend NPUs")
    Path("/proc/self/stat").read_text()
    visible = os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "").split(",")
    if len(visible) != 2 or any(not x.strip().isdigit() for x in visible):
        raise ValueError("Allocate two NPUs first (npu run --gpus 2); do not choose fixed card IDs")
    if len({int(x.strip()) for x in visible}) != 2:
        raise ValueError("ASCEND_RT_VISIBLE_DEVICES must contain two distinct allocated devices")


def _prepare(candidate: Path, output: Path, pairs: int) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("task", "candidate", "runner", "results"):
        (output / directory).mkdir()
    for name in TASK_FILES:
        (output / "task" / name).write_bytes(task_resources().joinpath(name).read_bytes())
    (output / "candidate" / "implementation.py").write_bytes(candidate.read_bytes())
    grader = task_resources().joinpath("grader.py").read_bytes()
    (output / "runner" / "grade.py").write_bytes(grader)
    atomic_write_json(output / "request.json", {"repetitions": pairs})
    names = ["task/" + name for name in TASK_FILES]
    names += ["candidate/implementation.py", "runner/grade.py", "request.json"]
    identity = _hashes(output, names)
    atomic_write_json(output / "identity.json", identity)
    return identity


def _launch(root: Path, token: str):
    # exec starts a process with the marker in its initial environment, visible
    # in /proc and inherited even by torchrun children with their own sessions.
    os.environ[MARKER] = token
    argv = [sys.executable, "-B", "-m", "torch.distributed.run", "--standalone",
            "--nnodes=1", "--nproc-per-node=2", str(root / "runner" / "grade.py"),
            "--run-dir", str(root)]
    os.execv(sys.executable, argv)


def evaluate(candidate: Path, output: Path, *, pairs: int, timeout_seconds: float,
             execute_trial) -> dict:
    started = time.monotonic()
    candidate, output = candidate.resolve(), output.resolve()
    _preflight(candidate, output, pairs, timeout_seconds)
    if not callable(execute_trial):
        raise ValueError("Supply execute_trial through the application entry or Python caller")
    identity = _prepare(candidate, output, pairs)
    token = uuid.uuid4().hex
    # This small launcher is frozen too and receives the marker only after the
    # executor starts it; the calling shell and npu allocator never inherit it.
    launcher = output / "runner" / "launch.py"
    launcher.write_bytes(_protocol.LAUNCHER_SOURCE.encode("utf-8"))
    identity.update(_hashes(output, ["runner/launch.py"]))
    atomic_write_json(output / "identity.json", identity)
    execution = {"status": "error", "metric": None, "returncode": None}
    try:
        execution = execute_trial(
            (sys.executable, "-B", str(launcher), str(output), token), output,
            output / "execution", started + timeout_seconds, "metrics.suite_latency_ms",
            metric=read_metric)
    except (OSError, ValueError, RuntimeError) as exc:
        execution["error"] = str(exc)
    finally:
        guard = cleanup(token)
    result = _adjudicate(output, execution, guard, identity, pairs)
    result["elapsed_seconds"] = time.monotonic() - started
    result["pairs"] = pairs
    result["timeout_seconds"] = timeout_seconds
    atomic_write_json(output / "result.json", result)
    return result


def main(argv=None, *, execute_trial=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.candidate, args.output_dir, pairs=args.pairs,
                          timeout_seconds=args.timeout_seconds, execute_trial=execute_trial)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps({k: result.get(k) for k in (
        "status", "correctness", "speedup", "metrics", "elapsed_seconds", "error")}))
    return 0 if result["completed"] else 2 if result["status"] == "candidate_failure" else 1


if __name__ == "__main__":
    sys.exit(main(execute_trial=globals().get("execute_trial")))
