"""Run an authenticated export through a fresh, unqualified evaluator prototype."""

import argparse
import json
import os
import resource
import select
import subprocess
import sys
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))
# The fixed source directory is deliberately restored under isolated Python (-I).
import bounds_driver as supervisor  # noqa: E402
import contract  # noqa: E402
import fixtures  # noqa: E402

runtime = supervisor.runtime
STATIC_FILES = (
    "runtime.py",
    "bounds_driver.py",
    "synthetic_probe.py",
    "contract.py",
    "inner.py",
    "executor.py",
    "policy.json",
    "fixtures.py",
)


def write(path, value):
    with Path(path).open("xb") as stream:
        stream.write(contract.canonical(value) + b"\n")


def inventory(bundle, output):
    runtime.inventory(bundle, output)
    original = contract.decode((output / "rootfs.json").read_bytes())
    entries = list(original["entries"])
    for name in STATIC_FILES:
        raw = (SOURCE / name).read_bytes()
        entries.append(
            {
                "path": "/opt/executor/" + name,
                "type": "file",
                "bytes": len(raw),
                "sha256": contract.sha(raw),
            }
        )
    entries.sort(key=lambda row: row["path"])
    value = {
        **original,
        "entries": entries,
        "rootfs_digest": "sha256:" + contract.sha(contract.canonical(entries)),
    }
    write(output / "executor-rootfs.json", value)
    return value, contract.decode((output / "runtime-locators.private.json").read_bytes())


def command(locators, snapshot, policy, policy_sha256, export_sha256, cohort_sha256):
    args = runtime.command(locators, SOURCE / "synthetic_probe.py", {}, "/unmounted")
    # Retain the reviewed mount base, replace the concrete work/shm sizes, and
    # replace the legacy diagnostic dispatch without calling its limits().
    for mount, capacity in (("/work", policy["work_bytes"]), ("/dev/shm", policy["shm_bytes"])):
        index = args.index(mount)
        if args[index - 3 : index] != ["--size", args[index - 2], "--tmpfs"]:
            raise ValueError("legacy mount command shape changed")
        args[index - 2] = str(capacity)
    payload_index = args.index("/opt/python/" + locators["python_relative"])
    mounts = []
    for name in STATIC_FILES:
        mounts += ["--ro-bind", str(SOURCE / name), "/opt/executor/" + name]
    mounts += ["--ro-bind", str(snapshot), "/input", "--remount-ro", "/dev"]
    mount_index = args.index("--remount-ro")
    return (
        args[:mount_index]
        + mounts
        + args[mount_index:payload_index]
        + [
            args[payload_index],
            "-IB",
            "/opt/executor/inner.py",
            policy_sha256,
            export_sha256,
            cohort_sha256,
        ]
    )


def limits(policy):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    for name, value in (
        ("AS", policy["as_bytes"]),
        ("CPU", policy["cpu_seconds"]),
        ("NOFILE", policy["nofile"]),
        ("FSIZE", policy["file_bytes"]),
        ("CORE", 0),
    ):
        resource.setrlimit(getattr(resource, "RLIMIT_" + name), (value, value))


def status_end(fd, status_raw):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
            break
        data = os.read(fd, 4096)
        if not data:
            return True
        status_raw.extend(data)
        if len(status_raw) > 65536:
            raise ValueError("unexpected status stream size")
    return False


def execute(args, rootfs, output, policy):
    output.mkdir()
    read_fd, write_fd = os.pipe()
    block_read, block_write = os.pipe()
    args[1:1] = ["--json-status-fd", str(write_fd), "--block-fd", str(block_read)]
    process, init_fd = None, None
    status_raw = bytearray()
    report = {
        "mode": "external-export",
        "passed": False,
        "timed_out": False,
        "qualified": False,
        "generated_code_executed": False,
    }
    write(output / "command.private.json", args)
    try:
        with (
            (output / "stdout.json").open("xb") as stdout,
            (output / "stderr.private.log").open("xb") as stderr,
        ):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-IB",
                    str(SOURCE / "executor.py"),
                    "_exec",
                    contract.sha((SOURCE / "policy.json").read_bytes()),
                    json.dumps(args),
                ],
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                pass_fds=(write_fd, block_read),
                start_new_session=True,
            )
            os.close(write_fd)
            write_fd = -1
            os.close(block_read)
            block_read = -1
            supervisor.read_line(read_fd, time.monotonic() + 10, status_raw)
            start = contract.decode(status_raw)
            init_fd, identity = supervisor.bind_init(start, process.pid)
            report["init_identity"] = identity
            report["initial_status"] = start
            os.write(block_write, b"1")
            os.close(block_write)
            block_write = -1
            process.stdin.write(supervisor.START_TOKEN)
            process.stdin.flush()
            process.stdin.close()
            report["authorization_sent"] = True
            started = time.monotonic()
            try:
                process.wait(timeout=policy["wall_seconds"])
            except subprocess.TimeoutExpired:
                report["timed_out"] = True
                raise
            report["elapsed_seconds"] = time.monotonic() - started
            report["exit_code"] = process.returncode
            report["init_exit_observed"] = supervisor.exited(init_fd, 5000)
            report["status_eof"] = status_end(read_fd, status_raw)
            report["passed"] = (
                process.returncode == 0 and report["init_exit_observed"] and report["status_eof"]
            )
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        supervisor.finalize_case(
            report,
            process,
            init_fd,
            [],
            (read_fd, write_fd, block_read, block_write),
            output,
            status_raw,
            rootfs,
        )
    return report


def evaluate_export(args):
    policy = contract.policy(SOURCE / "policy.json", args.policy_sha256)
    raw, export, samples = contract.inputs(
        args.inputs, args.export_sha256, args.cohort_sha256, policy["input_bytes"]
    )
    # This readiness entry never accepts model output or benchmark questions.
    if raw != fixtures.payloads():
        raise ValueError("prototype only permits the exact declared handwritten fixtures")
    args.output.mkdir(parents=False, exist_ok=False)
    snapshot = args.output / "input-snapshot"
    snapshot.mkdir()
    for name, content in raw.items():
        with (snapshot / name).open("xb") as stream:
            stream.write(content)
    if supervisor.capability(args.output / "pidfd-capability.json") != 0:
        raise ValueError("actual pidfd capability failed before sandbox creation")
    before, locators = inventory(args.bundle, args.output / "inventory-before")
    launch = command(
        locators, snapshot, policy, args.policy_sha256, args.export_sha256, args.cohort_sha256
    )
    report = execute(launch, before, args.output / "execution", policy)
    after, _ = inventory(args.bundle, args.output / "inventory-after")
    unchanged = before == after
    statuses = None
    error = None
    success = (
        report.get("passed") is True
        and report.get("cleanup_complete") is True
        and report.get("outputs_stable") is True
        and unchanged
    )
    if success:
        try:
            result_raw = contract.read(
                args.output / "execution/stdout.json", policy["result_bytes"]
            )
            statuses = contract.results(result_raw, export, samples, policy["result_bytes"])
        except (ValueError, OSError) as failure:
            error = {"type": type(failure).__name__, "message": str(failure)}
            success = False
    identity = {
        "schema_version": 1,
        "runtime_kind": "readonly-bind-set-v1",
        "runtime_digest": before["rootfs_digest"],
        "evaluator_revision": runtime.REVISION,
        "executor_sha256": contract.sha((SOURCE / "inner.py").read_bytes()),
        "driver_sha256": contract.sha((SOURCE / "executor.py").read_bytes()),
        "sandbox_binary_sha256": before["executor"]["binary_sha256"],
        "policy_sha256": args.policy_sha256,
    }
    write(
        args.output / "execution-record.json",
        {
            "scope": policy["scope"],
            "protocol": None,
            "observed_identity": identity,
            "qualified": False,
            "verdict": "INCONCLUSIVE",
            "execution_completed": success,
            "network": "none",
            "exit_code": report.get("final_launcher_exit_code"),
            "timed_out": report["timed_out"],
            "cleanup_complete": report["cleanup_complete"],
            "runtime_unchanged": unchanged,
            "export_sha256": args.export_sha256,
            "cohort_sha256": args.cohort_sha256,
            "samples_sha256": export["samples_sha256"],
            "dataset_sha256": export["dataset_sha256"],
            "results_sha256": report["stdout_sha256"],
            "statuses": statuses,
            "validation_error": error,
        },
    )
    return 0 if success else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--export-sha256", required=True)
    parser.add_argument("--cohort-sha256", required=True)
    return evaluate_export(parser.parse_args())


if __name__ == "__main__":
    if not os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_GPUS_ON_NODE", "0") != "0":
        raise ValueError("CPU-only Slurm allocation required")
    if len(sys.argv) == 4 and sys.argv[1] == "_exec":
        selected = contract.policy(SOURCE / "policy.json", sys.argv[2])
        limits(selected)
        launch = contract.decode(sys.argv[3])
        os.execv(launch[0], launch)
    raise SystemExit(main())
