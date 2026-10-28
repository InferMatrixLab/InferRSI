"""Supervise only fixed trusted probes and retain actual namespace-init exit evidence."""

import argparse
import hashlib
import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

RUNTIME_PATH = Path(__file__).with_name("runtime.py")
RUNTIME_SHA256 = "997cbfed8398e8ad62d1beb4f6b4bc6e61a0f4572b9156cfd0c6f3fb52b03233"
if hashlib.sha256(RUNTIME_PATH.read_bytes()).hexdigest() != RUNTIME_SHA256:
    raise ValueError("unexpected runtime source bytes")
runtime_spec = importlib.util.spec_from_file_location("trusted_bound_runtime", RUNTIME_PATH)
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_line(fd, deadline, raw):
    while time.monotonic() < deadline and len(raw) <= 1048576:
        ready, _, _ = select.select([fd], [], [], max(0, deadline - time.monotonic()))
        if not ready:
            break
        data = os.read(fd, 1)
        if not data:
            raise ValueError("premature protocol EOF")
        raw.extend(data)
        if data == b"\n":
            return bytes(raw)
    raise ValueError("trusted protocol size or time limit exceeded")


def read_ready_file(path, deadline):
    while time.monotonic() < deadline:
        raw = path.read_bytes()
        if len(raw) > 1048576:
            raise ValueError("trusted output exceeds size limit")
        if raw.endswith(b"\n"):
            return raw
        time.sleep(0.01)
    raise ValueError("trusted readiness deadline exceeded")


def exited(fd, milliseconds=0):
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    events = poller.poll(milliseconds)
    if any(mask & (select.POLLERR | select.POLLNVAL) for _, mask in events):
        raise ValueError("pidfd wait failed")
    return any(mask & (select.POLLIN | select.POLLHUP) for _, mask in events)


def status(pid):
    return dict(
        line.split(":", 1)
        for line in Path(f"/proc/{pid}/status").read_text().splitlines()
        if ":" in line
    )


def bind_init(record, launcher_pid):
    pid = record.get("child-pid")
    if type(pid) is not int or pid <= 1:
        raise ValueError("invalid namespace-init PID")
    fd = os.pidfd_open(pid)
    try:
        fields = status(pid)
        if exited(fd) or int(fields["PPid"]) != launcher_pid:
            raise ValueError("namespace init identity or parent changed")
        namespace_pids = [int(value) for value in fields["NSpid"].split()]
        if namespace_pids[0] != pid or namespace_pids[-1] != 1:
            raise ValueError("reported child is not namespace PID1")
        # The child is blocked before payload execution. Only the PID namespace
        # is compared: bwrap can create a further user namespace during setup.
        pid_namespace = os.readlink(f"/proc/{pid}/ns/pid")
        if pid_namespace != f"pid:[{record.get('pid-namespace')}]":
            raise ValueError("reported PID namespace identity differs")
        if exited(fd):
            raise ValueError("namespace init exited during binding")
        return fd, {"pid": pid, "namespace_pids": namespace_pids, "pid_namespace": pid_namespace}
    except BaseException:
        os.close(fd)
        raise


def bind_children(init_pid, readiness):
    wanted = readiness.get("live_descendant_pids")
    if not isinstance(wanted, list) or len(wanted) != 2 or len(set(wanted)) != 2:
        raise ValueError("expected two registered live trusted children")
    if any(type(pid) is not int or pid <= 2 for pid in wanted):
        raise ValueError("invalid trusted child PID")
    held = []
    records = []
    try:
        for child in psutil.Process(init_pid).children(recursive=True):
            try:
                fields = status(child.pid)
            except FileNotFoundError:
                continue
            namespace_pids = [int(value) for value in fields["NSpid"].split()]
            if namespace_pids[-1] not in wanted:
                continue
            fd = os.pidfd_open(child.pid)
            held.append(fd)
            current = status(child.pid)
            if exited(fd) or current["NSpid"] != fields["NSpid"]:
                raise ValueError("trusted child exited during binding")
            records.append({"pid": child.pid, "namespace_pids": namespace_pids})
        if sorted(row["namespace_pids"][-1] for row in records) != sorted(wanted):
            raise ValueError("registered trusted children not both observed")
        return held, records
    except BaseException:
        for fd in held:
            os.close(fd)
        raise


def finalize_case(report, process, init_fd, children, pipes, output, status_raw, rootfs):
    errors = []
    report["forced_cleanup"] = False

    def attempt(name, operation):
        try:
            return operation()
        except BaseException as error:
            errors.append({"operation": name, "type": type(error).__name__, "message": str(error)})
            return None

    if init_fd is not None:
        if attempt("check_init_exit", lambda: exited(init_fd)) is not True:
            try:
                signal.pidfd_send_signal(init_fd, signal.SIGKILL)
                report["forced_cleanup"] = True
            except ProcessLookupError:
                # Exit between poll and signal is not a failed cleanup if the
                # stable pidfd independently confirms that same process exited.
                confirmed = attempt("confirm_signal_race", lambda: exited(init_fd))
                report["signal_race_already_exited"] = confirmed is True
                if confirmed is not True:
                    errors.append({"operation": "signal_init", "type": "UnconfirmedExitRace"})
            except BaseException as error:
                errors.append(
                    {
                        "operation": "signal_init",
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                )
            report["forced_init_exit_observed"] = attempt(
                "wait_init_exit", lambda: exited(init_fd, 5000)
            )
            if report["forced_init_exit_observed"] is not True:
                errors.append({"operation": "wait_init_exit", "type": "ExitNotConfirmed"})
        attempt("close_init_fd", lambda: os.close(init_fd))
    if process is not None:
        if attempt("poll_launcher", process.poll) is None:
            report["forced_cleanup"] = True
            attempt("kill_launcher", process.kill)
            attempt("wait_launcher", lambda: process.wait(timeout=5))
        report["final_launcher_exit_code"] = process.returncode
        if process.returncode is None:
            errors.append({"operation": "wait_launcher", "type": "ExitNotConfirmed"})
    report["cleanup_registered_child_exits"] = []
    for fd in children:
        observed = attempt("wait_child_exit", lambda fd=fd: exited(fd, 1000))
        report["cleanup_registered_child_exits"].append(observed)
        if observed is not True:
            errors.append({"operation": "wait_child_exit", "type": "ExitNotConfirmed"})
        attempt("close_child_fd", lambda fd=fd: os.close(fd))
    for fd in pipes:
        if fd >= 0:
            attempt("close_pipe_fd", lambda fd=fd: os.close(fd))
    stdout_raw = attempt("read_stdout", (output / "stdout.json").read_bytes)
    attempt("write_status", lambda: (output / "status.private.jsonl").write_bytes(status_raw))
    report["stdout_sha256"] = runtime.sha(stdout_raw) if stdout_raw is not None else None
    report["status_sha256"] = runtime.sha(status_raw)
    report["rootfs_digest"] = rootfs["rootfs_digest"]
    report["cleanup_or_evidence_errors"] = errors
    if report["forced_cleanup"] or errors:
        report["passed"] = False
    # If even the report destination fails, the wrapper still captures the
    # nonzero process status and stderr; no success record is fabricated.
    runtime.write(output / "report.json", report)


def run_case(locators, rootfs, mode, output):
    output.mkdir()
    sentinel = output / "unmounted-sentinel.private"
    sentinel.write_text("trusted synthetic marker")
    namespaces = {
        name: os.readlink("/proc/self/ns/" + name) for name in ("user", "net", "pid", "uts", "ipc")
    }
    args = runtime.command(
        locators, Path(__file__).with_name("synthetic_probe.py"), namespaces, sentinel
    )
    status_read, status_write = os.pipe()
    block_read, block_write = os.pipe()
    # Additional mount policy; the independent /dev/shm remains a bounded tmpfs.
    args[1:1] = ["--json-status-fd", str(status_write), "--block-fd", str(block_read)]
    payload_index = args.index("/opt/python/" + locators["python_relative"])
    args[payload_index:payload_index] = ["--remount-ro", "/dev"]
    args.append(mode)
    process = None
    init_fd = None
    children = []
    report = {"mode": mode, "passed": False, "generated_code_executed": False}
    stdout_raw = b""
    status_raw = bytearray()
    try:
        with (
            (output / "stderr.private.log").open("xb") as stderr,
            (output / "stdout.json").open("xb") as stdout,
        ):
            process = subprocess.Popen(
                [sys.executable, "-IB", str(Path(__file__).resolve()), "_exec", json.dumps(args)],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                pass_fds=(status_write, block_read),
                start_new_session=True,
            )
            os.close(status_write)
            status_write = -1
            os.close(block_read)
            block_read = -1
            read_line(status_read, time.monotonic() + 10, status_raw)
            start = json.loads(status_raw, object_pairs_hook=unique)
            init_fd, identity = bind_init(start, process.pid)
            report["init_identity"] = identity
            report["initial_status"] = start
            os.write(block_write, b"1")
            os.close(block_write)
            block_write = -1
            if mode in ("bounds", "synthetic"):
                process.wait(timeout=60)
                stdout_raw = (output / "stdout.json").read_bytes()
                payload = json.loads(stdout_raw, object_pairs_hook=unique)
                report["probe_passed"] = payload.get("passed") is True
            else:
                stdout_raw = read_ready_file(output / "stdout.json", time.monotonic() + 10)
                payload = json.loads(stdout_raw, object_pairs_hook=unique)
                if payload.get("ready") is not True or payload.get("mode") != mode:
                    raise ValueError("trusted cleanup probe did not become ready")
                if payload.get("namespace_pid") != identity["pid_namespace"]:
                    raise ValueError("payload PID namespace differs from bound init")
                children, child_records = bind_children(identity["pid"], payload)
                report["registered_child_identities"] = child_records
                if mode == "timeout":
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        report["timeout_observed"] = True
                        signal.pidfd_send_signal(init_fd, signal.SIGKILL)
                    else:
                        raise ValueError("timeout probe returned before deadline")
                elif mode == "launcher_kill":
                    process.kill()
                process.wait(timeout=8)
                stdout_raw = (output / "stdout.json").read_bytes()
                report["probe_passed"] = True
            report["exit_code"] = process.returncode
            report["init_exit_observed"] = exited(init_fd, 5000)
            report["registered_child_exit_observed"] = [exited(fd, 1000) for fd in children]
            # Parent has exited and bwrap's payload closes the status fd. Read
            # the remainder with a finite deadline; EOF is expected.
            deadline = time.monotonic() + 2
            status_eof = False
            while time.monotonic() < deadline:
                ready, _, _ = select.select(
                    [status_read], [], [], max(0, deadline - time.monotonic())
                )
                if not ready:
                    break
                data = os.read(status_read, 4096)
                if not data:
                    status_eof = True
                    break
                status_raw += data
                if len(status_raw) > 65536:
                    raise ValueError("status stream unexpectedly large")
            report["status_eof"] = status_eof
            expected_exit = (
                -signal.SIGKILL if mode == "launcher_kill" else 137 if mode == "timeout" else 0
            )
            report["passed"] = (
                report["probe_passed"]
                and process.returncode == expected_exit
                and report["init_exit_observed"]
                and all(report["registered_child_exit_observed"])
                and status_eof
            )
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        finalize_case(
            report,
            process,
            init_fd,
            children,
            (status_read, status_write, block_read, block_write),
            output,
            status_raw,
            rootfs,
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("probe",))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rootfs = json.loads((args.inventory / "rootfs.json").read_bytes())
    locators = json.loads((args.inventory / "runtime-locators.private.json").read_bytes())
    if runtime.sha(Path(locators["bwrap"]).read_bytes()) != rootfs["executor"]["binary_sha256"]:
        raise ValueError("bwrap binary differs from inventory")
    args.output.mkdir()
    results = [
        run_case(locators, rootfs, mode, args.output / mode)
        for mode in ("bounds", "synthetic", "normal", "timeout", "launcher_kill")
    ]
    runtime.write(
        args.output / "summary.json",
        {
            "scope": "trusted_kernel_boundary_and_cleanup_probes",
            "passed": all(row["passed"] for row in results),
            "cases": results,
            "generated_code_executed": False,
            "qualified_generated_code_executor": False,
            "verdict": "INCONCLUSIVE",
            "driver_sha256": runtime.sha(Path(__file__).read_bytes()),
            "probe_sha256": runtime.sha(
                Path(__file__).with_name("synthetic_probe.py").read_bytes()
            ),
            "runtime_sha256": runtime.sha(Path(runtime.__file__).read_bytes()),
        },
    )
    return 0 if all(row["passed"] for row in results) else 2


if __name__ == "__main__":
    if not os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_GPUS_ON_NODE", "0") != "0":
        raise ValueError("CPU-only Slurm allocation required")
    if len(sys.argv) == 3 and sys.argv[1] == "_exec":
        runtime.limits()
        command = json.loads(sys.argv[2])
        os.execv(command[0], command)
    raise SystemExit(main())
