import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# H local process control domain (moved from infra in H02): one command inside its
# Windows Job or POSIX process group, deadline and cancellation, and tree cleanup.
# Benchmark or quality results are never interpreted here.

# Cancellation handles are polled at this interval; without one, wait is unchanged.
_POLL_SECONDS = 0.05
# Bound for confirming that a terminated process domain holds no live member.
_DRAIN_SECONDS = 10.0


class _Cancelled(Exception):
    """The caller's cancellation handle was set while the command ran."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _WindowsJob:
    """A native Job Object owns descendants; taskkill may lack sandbox privileges."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IOCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IOCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class Accounting(ctypes.Structure):
            # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION; ActiveProcesses counts live members.
            _fields_ = [
                ("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        self.ctypes = ctypes
        self._accounting = Accounting
        # None until close(): True when the Job was confirmed empty before its handle closed.
        self.emptied: bool | None = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.kernel.QueryInformationJobObject.restype = wintypes.BOOL
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            failure = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise failure

    def attach(self, process: subprocess.Popen) -> None:
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise OSError("Windows subprocess handle unavailable for Job Object supervision")
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process_handle)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def _active_processes(self) -> int | None:
        info = self._accounting()
        if not self.kernel.QueryInformationJobObject(
            self.handle, 1, self.ctypes.byref(info), self.ctypes.sizeof(info), None
        ):
            return None
        return info.ActiveProcesses

    def _drain(self) -> bool | None:
        """Terminate remaining members until the Job holds none; None when unobservable."""
        deadline = time.monotonic() + _DRAIN_SECONDS
        while True:
            active = self._active_processes()
            if active is None:
                return None
            if active == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            # Exit code 0 is what kill-on-close gives members (measured), so legacy
            # timeout records keep their returncode; kill-on-close stays the backstop.
            if not self.kernel.TerminateJobObject(self.handle, 0):
                return None
            time.sleep(_POLL_SECONDS)

    def close(self) -> None:
        if self.handle:
            self.emptied = self._drain()
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _stop_tree(process: subprocess.Popen, windows_job: _WindowsJob | None = None) -> None:
    if windows_job is not None:
        windows_job.close()
    elif os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def _group_empty(group: int) -> bool | None:
    """Confirm a POSIX process group has no member left; None when unobservable."""
    deadline = time.monotonic() + _DRAIN_SECONDS
    while True:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return None
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_SECONDS)


def _wait(process: subprocess.Popen, deadline: float, cancellation) -> None:
    """Wait until exit; TimeoutExpired at the deadline, _Cancelled once the handle is set."""
    if cancellation is None:
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return
    while True:
        if cancellation.is_set():
            raise _Cancelled
        remaining = deadline - time.monotonic()
        try:
            process.wait(timeout=max(0.001, min(remaining, _POLL_SECONDS)))
            return
        except subprocess.TimeoutExpired:
            if remaining <= _POLL_SECONDS:
                raise


def _supervise(
    argv: list[str],
    cwd: Path,
    environment: dict,
    stdout_path: Path,
    stderr_path: Path,
    deadline: float,
    *,
    cancellation=None,
) -> dict:
    """Run one command inside its own process domain and return the observed facts.

    ``deadline`` is a ``time.monotonic()`` value. ``cancellation`` is an optional handle
    with ``is_set()``. ``status`` keeps the legacy vocabulary: completed, failed, timeout,
    cancelled or error. ``domain_empty`` is True only when the Job or process group was
    confirmed to hold no live member after cleanup.
    """
    run = {
        "status": "pending",
        "returncode": None,
        "pid": None,
        "process_group_id": None,
        "error": None,
        "started_at": None,
        "ended_at": None,
        "process_seconds": None,
        "termination_requested": False,
        "cancellation_source": None,
        "cancellation_requested_at": None,
        "domain_empty": None,
        "elapsed_seconds": None,
    }
    started, process, windows_job, attached, launched = time.monotonic(), None, None, False, None
    try:
        remaining = deadline - started
        if remaining <= 0:
            run.update(status="timeout", error="whole-run deadline exhausted before command start")
        else:
            options = (
                {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            if os.name == "nt":
                windows_job = _WindowsJob()
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    **options,
                )
                launched = time.monotonic()
                run["started_at"] = _utc_now()
                run["pid"] = process.pid
                run["process_group_id"] = process.pid if os.name != "nt" else None
                if windows_job is not None:
                    windows_job.attach(process)
                attached = True
                try:
                    _wait(process, deadline, cancellation)
                    run.update(
                        status="completed" if process.returncode == 0 else "failed",
                        returncode=process.returncode,
                    )
                except subprocess.TimeoutExpired:
                    run["termination_requested"] = True
                    _stop_tree(process, windows_job)
                    run.update(
                        status="timeout",
                        returncode=process.returncode,
                        error="whole-run deadline exceeded",
                    )
                except (KeyboardInterrupt, _Cancelled) as exc:
                    run.update(
                        termination_requested=True,
                        cancellation_requested_at=_utc_now(),
                        cancellation_source=(
                            "caller" if isinstance(exc, _Cancelled) else "keyboard_interrupt"
                        ),
                    )
                    _stop_tree(process, windows_job)
                    run.update(
                        status="cancelled",
                        returncode=process.returncode,
                        error=(
                            "cancellation requested"
                            if isinstance(exc, _Cancelled)
                            else "interrupted by user"
                        ),
                    )
    except (OSError, subprocess.SubprocessError) as exc:
        if process is not None and process.poll() is None:
            run["termination_requested"] = True
            _stop_tree(process, windows_job)
        run.update(status="error", error=str(exc))
    finally:
        if windows_job is not None:
            windows_job.close()
        if process is not None and os.name != "nt":
            _stop_tree(process)
        if process is not None:
            # A process that never joined its domain leaves that domain unconfirmed.
            if attached:
                run["domain_empty"] = (
                    windows_job.emptied if windows_job is not None else _group_empty(process.pid)
                )
            run["ended_at"] = _utc_now()
            run["process_seconds"] = time.monotonic() - launched
        run["elapsed_seconds"] = time.monotonic() - started
    return run


def execute_command(command: tuple[str, ...], cwd: Path, trial_dir: Path, deadline: float, *,
                    environment: dict | None = None) -> dict:
    """Legacy trial record: execute argv under a whole-run deadline in trial_dir."""
    trial_dir.mkdir(parents=True)
    result_path = trial_dir / "result.json"
    argv = [arg.replace("{result}", str(result_path)) for arg in command]
    record = {
        "status": "pending",
        "argv": argv,
        "cwd": str(cwd),
        "returncode": None,
        "result_path": str(result_path),
        "stdout_path": str(trial_dir / "stdout.log"),
        "stderr_path": str(trial_dir / "stderr.log"),
        "metric": None,
        "metric_error": None,
    }
    environment = os.environ.copy() if environment is None else environment.copy()
    environment["INFERRSI_RESULT_PATH"] = str(result_path)
    run = _supervise(
        argv, cwd, environment, trial_dir / "stdout.log", trial_dir / "stderr.log", deadline
    )
    # Same keys, order and values as the record built before H02.
    record.update(status=run["status"], returncode=run["returncode"])
    if run["pid"] is not None:
        record["pid"] = run["pid"]
        record["process_group_id"] = run["process_group_id"]
    if run["error"] is not None:
        record["error"] = run["error"]
    record["elapsed_seconds"] = run["elapsed_seconds"]
    return record
