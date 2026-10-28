"""Finite handwritten kernel-boundary probes; no model programs or task data."""

import ctypes
import errno
import json
import mmap
import os
import platform
import resource
import select
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

TASK_LIMIT = 16
MEMORY_LIMIT = 2147483648
START_TOKEN = b"inferrsi-trusted-start-v2\n"
IPC_SYSCALLS = (29, 30, 31, 64, 65, 66, 67, 68, 69, 70, 71, 220, 240)


def authorize_start(fd=0, timeout=5):
    """Require the supervisor's complete token and EOF before any dispatch."""
    deadline = time.monotonic() + timeout
    received = bytearray()
    while len(received) <= len(START_TOKEN):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError("startup token deadline exceeded")
        part = os.read(fd, len(START_TOKEN) + 1 - len(received))
        if not part:
            if bytes(received) != START_TOKEN:
                raise ValueError("startup token absent or invalid")
            return
        received.extend(part)
    raise ValueError("startup token too long")


def filter_instructions():
    # Linux v6.12 x86 syscall table; reject other architectures and the x32 ABI.
    result = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x35, 0, 1, 0x40000000),
        (0x06, 0, 0, 0x80000000),
    ]
    for number in IPC_SYSCALLS:
        result.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    return [*result, (0x06, 0, 0, 0x7FFF0000)]


def install_ipc_filter():
    if platform.machine() != "x86_64" or sys.maxsize != 2**63 - 1:
        raise ValueError("trusted filter requires Linux x86_64 LP64")

    class Instruction(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint32),
        ]

    class Program(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ushort),
            ("instructions", ctypes.POINTER(Instruction)),
        ]

    instructions = filter_instructions()
    array = (Instruction * len(instructions))(
        *(Instruction(*row) for row in instructions)
    )
    program = Program(len(instructions), array)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.restype = ctypes.c_int
    if (
        libc.prctl(38, 1, 0, 0, 0) != 0
        or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0
    ):
        raise OSError(ctypes.get_errno(), "fixed seccomp policy could not be installed")


def ipc_attempts():
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    attempts = []
    # Finite minimal allocations only, even if the expected rejection is absent.
    for number, arguments in (
        (29, (0, 4096, 0o600)),
        (64, (0, 1, 0o600)),
        (68, (0, 0o600)),
    ):
        ctypes.set_errno(0)
        value = libc.syscall(
            ctypes.c_long(number), *(ctypes.c_long(v) for v in arguments)
        )
        attempts.append(
            {"syscall": number, "return": value, "errno": ctypes.get_errno()}
        )
    ctypes.set_errno(0)
    value = libc.syscall(
        ctypes.c_long(240),
        ctypes.c_char_p(b"trusted-probe"),
        ctypes.c_long(os.O_CREAT | os.O_WRONLY),
        ctypes.c_long(0o600),
        ctypes.c_void_p(),
    )
    attempts.append({"syscall": 240, "return": value, "errno": ctypes.get_errno()})
    return attempts


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def limits_record():
    return {
        name: list(resource.getrlimit(getattr(resource, "RLIMIT_" + name)))
        for name in (
            "AS",
            "CPU",
            "NOFILE",
            "FSIZE",
            "CORE",
            "NPROC",
            "MEMLOCK",
            "MSGQUEUE",
        )
    }


def finite_forks():
    children = []
    read_fd, write_fd = os.pipe()
    rejected = None
    try:
        for _ in range(TASK_LIMIT + 1):
            try:
                child = os.fork()
            except OSError as error:
                rejected = error.errno
                break
            if child == 0:
                os.close(write_fd)
                signal.alarm(8)
                os.read(read_fd, 1)
                os._exit(0)
            children.append(child)
    finally:
        os.close(write_fd)
        os.close(read_fd)
        for child in children:
            os.waitpid(child, 0)
    return {
        "created": len(children),
        "rejection_errno": rejected,
        "attempt_cap": TASK_LIMIT + 1,
    }


def finite_threads():
    threads = []
    stop = threading.Event()
    rejected = None
    try:
        for _ in range(TASK_LIMIT + 1):
            thread = threading.Thread(target=stop.wait, args=(8,))
            try:
                thread.start()
            except RuntimeError as error:
                rejected = str(error)
                break
            threads.append(thread)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=2)
    return {
        "created": len(threads),
        "rejection": rejected,
        "all_joined": all(not thread.is_alive() for thread in threads),
        "attempt_cap": TASK_LIMIT + 1,
    }


def bounds():
    before = limits_record()
    raises = {}
    for name in (
        "NPROC",
        "AS",
        "CPU",
        "NOFILE",
        "FSIZE",
        "CORE",
        "MEMLOCK",
        "MSGQUEUE",
    ):
        code = getattr(resource, "RLIMIT_" + name)
        soft, hard = resource.getrlimit(code)
        try:
            resource.setrlimit(code, (soft, hard + 1))
        except (ValueError, PermissionError) as error:
            raises[name] = type(error).__name__
        else:
            raises[name] = "unexpected_success"
    try:
        mapping = mmap.mmap(-1, MEMORY_LIMIT + mmap.PAGESIZE)
    except OSError as error:
        as_errno = error.errno
    else:
        mapping.close()
        as_errno = None
    inherited = subprocess.run(
        [sys.executable, "-I", "-B", "/opt/probe.py", "inherit"],
        input=START_TOKEN,
        capture_output=True,
        timeout=5,
        check=False,
    )
    inherited_payload = json.loads(inherited.stdout)
    forks = finite_forks()
    threads = finite_threads()
    descriptors = []
    fd_errno = None
    try:
        for _ in range(65):
            try:
                descriptors.append(os.open("/dev/null", os.O_RDONLY))
            except OSError as error:
                fd_errno = error.errno
                break
    finally:
        for fd in descriptors:
            os.close(fd)
    old_handler = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    try:
        with open("/work/size-check", "wb") as stream:
            try:
                stream.truncate(1048577)
            except OSError as error:
                size_errno = error.errno
            else:
                size_errno = None
    finally:
        signal.signal(signal.SIGXFSZ, old_handler)
    cpu = subprocess.run(
        [sys.executable, "-I", "-B", "/opt/probe.py", "cpu"],
        input=START_TOKEN,
        capture_output=True,
        timeout=5,
        check=False,
    )
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    expected = {
        "AS": [MEMORY_LIMIT] * 2,
        "CPU": [30] * 2,
        "NOFILE": [64] * 2,
        "FSIZE": [1048576] * 2,
        "CORE": [0, 0],
        "NPROC": [TASK_LIMIT] * 2,
        "MEMLOCK": [0, 0],
        "MSGQUEUE": [0, 0],
    }
    ipc = ipc_attempts()
    try:
        with open("/dev/creation-check", "xb"):
            pass
    except OSError as error:
        dev_errno = error.errno
    else:
        dev_errno = None
    with open("/dev/zero", "rb") as stream:
        zero = stream.read(4)
    checks = {
        "exact_limits": before == expected and limits_record() == expected,
        "nonroot": os.getuid() == os.geteuid() == 65534,
        "no_effective_capabilities": int(status["CapEff"].strip(), 16) == 0,
        "no_new_privileges": status["NoNewPrivs"].strip() == "1",
        "seccomp_filter_present": status["Seccomp"].strip() == "2",
        "sysv_creation_denied": all(
            row["return"] == -1 and row["errno"] == errno.EPERM for row in ipc
        ),
        "device_mount_readonly": dev_errno == errno.EROFS,
        "device_read_available": zero == b"\x00" * 4,
        "raise_hard_limit_denied": all(
            value != "unexpected_success" for value in raises.values()
        ),
        "address_space_denied": as_errno == errno.ENOMEM,
        "fork_exec_inheritance": inherited.returncode == 0
        and inherited_payload["limits"] == expected,
        "fork_exec_filter_inheritance": inherited.returncode == 0
        and all(
            row["return"] == -1 and row["errno"] == errno.EPERM
            for row in inherited_payload["ipc"]
        ),
        "bounded_fork_denied": 0 < forks["created"] < TASK_LIMIT
        and forks["rejection_errno"] == errno.EAGAIN,
        "bounded_thread_denied": 0 < threads["created"] < TASK_LIMIT
        and threads["rejection"] is not None
        and threads["all_joined"],
        "descriptor_limit_denied": fd_errno == errno.EMFILE,
        "file_size_denied": size_errno == errno.EFBIG,
        "cpu_limit_kills": cpu.returncode == -signal.SIGKILL,
    }
    emit(
        {
            "mode": "bounds",
            "checks": checks,
            "passed": all(checks.values()),
            "limits": before,
            "hard_limit_raise_results": raises,
            "as_errno": as_errno,
            "forks": forks,
            "threads": threads,
            "descriptor_errno": fd_errno,
            "opened_descriptors": len(descriptors),
            "file_size_errno": size_errno,
            "cpu_exit_code": cpu.returncode,
            "ipc_attempts": ipc,
            "device_creation_errno": dev_errno,
            "inherited_exit_code": inherited.returncode,
            "generated_code_executed": False,
        }
    )
    return 0 if all(checks.values()) else 2


def cleanup(mode):
    read_fd, write_fd = os.pipe()
    direct = os.fork()
    if direct == 0:
        os.close(read_fd)
        os.write(write_fd, f"{os.getpid()}\n".encode())
        os.close(write_fd)
        time.sleep(15)
        os._exit(0)
    intermediate = os.fork()
    if intermediate == 0:
        os.close(read_fd)
        os.setsid()
        grandchild = os.fork()
        if grandchild == 0:
            os.write(write_fd, f"{os.getpid()}\n".encode())
            os.close(write_fd)
            time.sleep(15)
            os._exit(0)
        os._exit(0)
    os.close(write_fd)
    with os.fdopen(read_fd, "r") as stream:
        live = sorted(int(line) for line in stream)
    os.waitpid(intermediate, 0)
    emit(
        {
            "mode": mode,
            "ready": True,
            "probe_pid": os.getpid(),
            "live_descendant_pids": live,
            "direct_pid": direct,
            "namespace_pid": os.readlink("/proc/self/ns/pid"),
            "generated_code_executed": False,
        }
    )
    if mode == "normal":
        # Allow the supervisor to open pidfds for both deliberately live children.
        time.sleep(2)
        return 0
    time.sleep(15)
    return 3


def synthetic_evaluator():
    import base64
    import contextlib
    import hashlib
    import importlib
    import io

    sys.path.insert(0, "/opt/site-packages")
    import psutil

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    os.environ["EVALPLUS_MAX_MEMORY_BYTES"] = str(MEMORY_LIMIT)
    os.environ.pop("EVALPLUS_TIMEOUT_PER_TASK", None)
    os.environ["XDG_CACHE_HOME"] = "/work/cache"
    os.environ["HUMANEVAL_OVERRIDE_PATH"] = "/work/synthetic-dataset.jsonl"
    work = Path("/work")
    samples = work / "synthetic-samples.jsonl"
    dataset = work / "synthetic-dataset.jsonl"
    output = work / "output/synthetic-results.json"
    assert not samples.exists() and not dataset.exists() and not output.exists()
    assert not (work / "cache").exists()
    solutions = {
        "Synthetic/correct": "def f(x):\n    return x + 1\n",
        "Synthetic/plus_wrong": "def f(x):\n    return 1\n",
        "Synthetic/exception": "def f(x):\n    raise ArithmeticError('synthetic')\n",
        "Synthetic/input_timeout": "import time\ndef f(x):\n    time.sleep(5)\n    return x + 1\n",
    }
    rows = [
        {
            "task_id": task_id,
            "prompt": "def f(x):\n",
            "canonical_solution": "    return x + 1\n",
            "contract": "",
            "entry_point": "f",
            "base_input": [[0]],
            "plus_input": [[1]],
            "atol": 0,
        }
        for task_id in solutions
    ]
    dataset.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    samples.write_text(
        "".join(
            json.dumps({"task_id": key, "solution": value}, sort_keys=True) + "\n"
            for key, value in solutions.items()
        )
    )
    parent = psutil.Process()
    captured_out, captured_err = io.StringIO(), io.StringIO()
    started = time.monotonic()
    with (
        contextlib.redirect_stdout(captured_out),
        contextlib.redirect_stderr(captured_err),
    ):
        evaluator = importlib.import_module("evalplus.evaluate")
        evaluator.evaluate(
            dataset="humaneval",
            samples=str(samples),
            output_file=str(output),
            parallel=1,
            base_only=False,
            mini=False,
            noextreme=False,
            test_details=True,
        )
    result = json.loads(output.read_bytes())
    statuses = {
        task_id: [[row["base_status"], row["plus_status"]] for row in values]
        for task_id, values in result["eval"].items()
    }
    # The upstream per-input exception handler reports time-limit exceptions as
    # fail. This is distinct from its outer child-process timeout classification.
    expected = {
        "Synthetic/correct": [["pass", "pass"]],
        "Synthetic/plus_wrong": [["pass", "fail"]],
        "Synthetic/exception": [["fail", "fail"]],
        "Synthetic/input_timeout": [["fail", "fail"]],
    }
    checks = {
        "four_exact_status_pairs": statuses == expected,
        "dataset_hash": result["hash"] == hashlib.md5(dataset.read_bytes()).hexdigest(),
        "bounded_output": output.stat().st_size <= 1048576,
        "timeout_override_absent": "EVALPLUS_TIMEOUT_PER_TASK" not in os.environ,
    }
    payload = {
        "checks": checks,
        "passed": all(checks.values()),
        "statuses": statuses,
        "elapsed_seconds": time.monotonic() - started,
        "dataset_sha256": digest(dataset.read_bytes()),
        "samples_sha256": digest(samples.read_bytes()),
        "results_sha256": digest(output.read_bytes()),
        "results": result,
        "results_raw_base64": base64.b64encode(output.read_bytes()).decode("ascii"),
        "evaluator_module_sha256": digest(Path(evaluator.__file__).read_bytes()),
        "evaluator_stdout": captured_out.getvalue(),
        "evaluator_stderr": captured_err.getvalue(),
        "live_children_after_evaluate": len(parent.children(recursive=True)),
        "generated_code_executed": False,
        "real_benchmark_data_mounted": False,
        "full_evaluator_executed": True,
        "qualified_generated_code_executor": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] else 2


def main():
    try:
        authorize_start()
    except (ValueError, OSError):
        os.write(2, b"PAYLOAD_START_REJECTED\n")
        return 23
    # The authorization pipe is never available to evaluator code or children.
    devnull = os.open("/dev/null", os.O_RDONLY)
    os.dup2(devnull, 0)
    if devnull != 0:
        os.close(devnull)
    os.write(2, b"PAYLOAD_START_AUTHORIZED\n")
    mode = sys.argv[1]
    if mode == "gate_check":
        emit({"passed": True, "mode": "gate_check"})
        return 0
    if mode == "inherit":
        emit({"limits": limits_record(), "ipc": ipc_attempts()})
        return 0
    if mode == "cpu":
        resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
        signal.alarm(4)
        while True:
            pass
    resource.setrlimit(resource.RLIMIT_NPROC, (TASK_LIMIT, TASK_LIMIT))
    resource.setrlimit(resource.RLIMIT_MEMLOCK, (0, 0))
    resource.setrlimit(resource.RLIMIT_MSGQUEUE, (0, 0))
    install_ipc_filter()
    signal.alarm(40)
    if mode == "synthetic":
        return synthetic_evaluator()
    if mode == "bounds":
        return bounds()
    if mode in ("normal", "timeout", "launcher_kill"):
        return cleanup(mode)
    raise ValueError("unknown trusted probe mode")


if __name__ == "__main__":
    raise SystemExit(main())
