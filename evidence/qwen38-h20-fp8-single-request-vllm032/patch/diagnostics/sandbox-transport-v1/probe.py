"""Bounded CPU diagnosis of wheel-prefix reads and task-filesystem writes.

No retrieved bytes are installed, imported, extracted or reused for installation.
The prefix hash does not authenticate the complete wheel. Synthetic files remain
in a new private output directory. This does not measure service performance.
"""

import argparse
import hashlib
import json
import os
import signal
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fail_timeout(_number, _frame):
    raise TimeoutError("bounded diagnostic deadline")


def measured(state, name, operation):
    event = {"operation": name, "completed": False}
    state["operations"].append(event)
    started = time.monotonic()
    try:
        value = operation()
        event["completed"] = True
        return value
    except (OSError, ValueError) as error:
        event["error_type"] = type(error).__name__
        raise
    finally:
        event["seconds"] = time.monotonic() - started


def network_probe(policy, state):
    length = policy["prefix_bytes"]
    state.update(
        completed=False,
        received_bytes=0,
        operations=[],
        whole_wheel_authenticated=False,
        payload_written_to_disk=False,
    )
    request = urllib.request.Request(
        policy["url"], headers={"Range": f"bytes=0-{length - 1}"}
    )
    started = time.monotonic()
    digest = hashlib.sha256()
    try:
        with measured(
            state, "open", lambda: urllib.request.urlopen(request, timeout=15)
        ) as response:
            if (
                response.status != 206
                or urlsplit(response.url).hostname != "files.pythonhosted.org"
            ):
                raise ValueError("unexpected wheel-prefix endpoint or response")
            expected = f"bytes 0-{length - 1}/{policy['whole_wheel_bytes']}"
            if response.headers.get("Content-Range") != expected:
                raise ValueError("unexpected wheel-prefix range")
            while state["received_bytes"] < length:
                count = min(262144, length - state["received_bytes"])
                chunk = measured(
                    state, "read", lambda count=count: response.read(count)
                )
                state["operations"][-1]["received_bytes"] = len(chunk)
                if not chunk:
                    raise ValueError("truncated prefix")
                digest.update(chunk)
                state["received_bytes"] += len(chunk)
        state["completed"] = True
    finally:
        state["received_prefix_sha256"] = digest.hexdigest()
        state["elapsed_seconds"] = time.monotonic() - started


def filesystem_probe(output, state):
    state.update(
        completed=False,
        stream_bytes=0,
        small_file_count=0,
        small_file_bytes=0,
        operations=[],
        small_files_fsynced=False,
        physical_storage_throughput_claimed=False,
    )
    block = (b"diagnostic-file-content-" * 11400)[:262144]
    if len(block) != 262144:
        raise ValueError("synthetic block length")
    started = time.monotonic()
    try:
        handle = measured(
            state,
            "stream_open",
            lambda: (output / "synthetic-stream.bin").open("xb", buffering=0),
        )
        try:
            for _ in range(32):
                size = measured(state, "stream_write", lambda: handle.write(block))
                state["stream_bytes"] += size
                if size != len(block):
                    raise ValueError("short synthetic write")
            measured(state, "stream_fsync", lambda: os.fsync(handle.fileno()))
        finally:
            measured(state, "stream_close", handle.close)
        small = output / "synthetic-small-files"
        measured(state, "small_mkdir", small.mkdir)
        for i in range(128):
            handle = measured(
                state,
                "small_open",
                lambda i=i: (small / f"{i}.bin").open("xb", buffering=0),
            )
            try:
                size = measured(
                    state,
                    "small_write",
                    lambda handle=handle: handle.write(block[:4096]),
                )
                state["small_file_bytes"] += size
                if size != 4096:
                    raise ValueError("short synthetic small write")
            finally:
                measured(state, "small_close", handle.close)
            state["small_file_count"] += 1
        state["completed"] = True
    finally:
        state["elapsed_seconds"] = time.monotonic() - started


def persist(output, result):
    raw = json.dumps(result, sort_keys=True)
    # Preserve observations in the Slurm log even if the result-file write fails.
    print(raw, flush=True)
    (output / "observations.json").write_text(raw + "\n")


def run_phases(policy, output, result):
    deadline = time.monotonic() + 300
    try:
        for name, operation in (
            ("network", lambda state: network_probe(policy, state)),
            ("filesystem", lambda state: filesystem_probe(output, state)),
        ):
            state = result[name] = {"completed": False}
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                state["skipped_reason"] = "overall_deadline_exhausted"
            else:
                signal.alarm(max(1, int(remaining)))
                try:
                    operation(state)
                except (OSError, ValueError) as error:
                    state["completed"] = False
                    state["error_type"] = type(error).__name__
            persist(output, result)
        result["completed"] = all(
            result[name].get("completed") is True for name in ("network", "filesystem")
        )
        persist(output, result)
        return 0 if result["completed"] else 1
    finally:
        signal.alarm(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        not os.environ.get("SLURM_JOB_ID")
        or os.environ.get("SLURM_GPUS_ON_NODE", "0") != "0"
    ):
        raise ValueError("CPU-only Slurm allocation required")
    root = Path(os.environ["TASK_ROOT"]).resolve(strict=True)
    output = args.output.resolve(strict=False)
    if not output.is_relative_to(root) or output == root:
        raise ValueError("output escapes task root")
    raw = args.policy.read_bytes()
    if sha(raw) != args.policy_sha256:
        raise ValueError("diagnostic policy changed")
    policy = json.loads(raw)
    if (
        policy["prefix_bytes"] != 8388608
        or policy["whole_wheel_bytes"] != 53931932
        or urlsplit(policy["url"]).scheme != "https"
        or urlsplit(policy["url"]).hostname != "files.pythonhosted.org"
    ):
        raise ValueError("unexpected bounded wheel-prefix policy")
    output.mkdir(mode=0o700, exist_ok=False)
    result = {
        "scope": "bounded_transport_and_filesystem_diagnostic",
        "verdict": "INCONCLUSIVE",
        "completed": False,
        "job_id": os.environ["SLURM_JOB_ID"],
        "policy_sha256": args.policy_sha256,
        "gpu_used": False,
        "installation_performed": False,
        "evaluator_executed": False,
    }
    signal.signal(signal.SIGALRM, fail_timeout)
    return run_phases(policy, output, result)


if __name__ == "__main__":
    raise SystemExit(main())
