"""Ownership and cleanup of local commands and supervised serving workers."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


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

        self.ctypes = ctypes
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

    def close(self) -> None:
        if self.handle:
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


def _require_server_platform():
    if sys.platform != "linux":
        raise OSError("Server helpers require Linux with a readable /proc filesystem")
    # A missing/inaccessible procfs must never count as an empty process group.
    Path("/proc/self/stat").read_text()


def launch_server(argv, source, environment, log):
    """Keep supervised workers inside the runner's group, including hard timeout."""
    _require_server_platform()
    helper_pid, helper_group = os.getpid(), os.getpgrp()
    _live_group_members(helper_group)  # Verify enumeration before creating any worker.
    marker = bool(os.environ.get("INFERRSI_RESULT_PATH"))
    if marker and helper_group != helper_pid:
        raise ValueError(
            "InferRSI helper must be its trial group leader; invoke the prepared Python directly"
        )
    supervised = marker and helper_group == helper_pid
    process = subprocess.Popen(
        argv,
        cwd=source,
        env=environment,
        stdout=log,
        stderr=log,
        start_new_session=not supervised,
        shell=False,
    )
    ownership = {
        "mode": "inferrsi_trial_group" if supervised else "server_session",
        "server_pid": process.pid,
        "helper_pid": helper_pid,
        "process_group_id": helper_group if supervised else process.pid,
        "helper_process_group_id": helper_group,
        "server_start_new_session": not supervised,
    }
    return process, ownership


def _live_group_members(group, exclude=()):
    _require_server_platform()
    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        path = entry / "stat"
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            pid = int(path.parent.name)
            if int(fields[2]) == group and fields[0] != "Z" and pid not in exclude:
                members.append(pid)
        except (FileNotFoundError, ProcessLookupError):
            continue
    return members


def stop_server(process, ownership, grace_seconds=20):
    """Clean the owned group even when its original server leader already exited."""
    _require_server_platform()
    group = ownership["process_group_id"]
    inherited = ownership["mode"] == "inferrsi_trial_group"
    if inherited:
        if group != os.getpid() or group != os.getpgrp() or ownership["helper_pid"] != os.getpid():
            raise ValueError("Refusing cleanup of a group not owned by this supervised helper")
        excluded = (os.getpid(),)
    else:
        if (
            group != process.pid
            or group == os.getpgrp()
            or ownership["server_start_new_session"] is not True
        ):
            raise ValueError("Refusing cleanup of an unknown server group")
        excluded = ()

    def signal_members(number):
        if inherited:
            for pid in _live_group_members(group, excluded):
                try:
                    if os.getpgid(pid) == group:
                        os.kill(pid, number)
                except ProcessLookupError:
                    pass
        else:
            try:
                os.killpg(group, number)
            except ProcessLookupError:
                pass

    signal_members(signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while _live_group_members(group, excluded) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.05)
    remaining = _live_group_members(group, excluded)
    killed = bool(remaining)
    if remaining:
        signal_members(signal.SIGKILL)
        deadline = time.monotonic() + 5
        while _live_group_members(group, excluded) and time.monotonic() < deadline:
            process.poll()
            time.sleep(0.05)
    if process.poll() is None:
        process.wait(timeout=5)
    remaining = _live_group_members(group, excluded)
    return {
        "status": "failed" if remaining else "completed",
        "mode": ownership["mode"],
        "process_group_id": group,
        "term_sent": True,
        "kill_sent": killed,
        "remaining_pids": remaining,
        "server_returncode": process.returncode,
    }
