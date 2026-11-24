"""Launch the MindIE reader already contained in a Windows Job Object."""

import ctypes
import msvcrt
import os
import subprocess
import time
import weakref
from contextlib import ExitStack
from ctypes import wintypes as win

_KILL_ON_JOB_CLOSE = 0x2000
_LIMIT_ACTIVE_PROCESSES = 0x8
_PROCESS_IDS = 3
_EXTENDED_LIMITS = 9
_HANDLE_LIST = 0x20002
_JOB_LIST = 0x2000D
_USE_STD_HANDLES = 0x100
_EXTENDED_STARTUPINFO = 0x80000
_UNICODE_ENVIRONMENT = 0x400
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_MAX_WAIT_MS = 0xFFFFFFFE
_SYNCHRONIZE = 0x100000
_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_INVALID_PARAMETER = 87
_ERROR_MORE_DATA = 234
_CLEANUP_SECONDS = 0.5


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("per_process_time", ctypes.c_int64), ("per_job_time", ctypes.c_int64),
        ("flags", win.DWORD), ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t), ("process_limit", win.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", win.DWORD), ("scheduling", win.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits), ("io_counters", ctypes.c_uint64 * 6),
        ("memory_limits", ctypes.c_size_t * 4),
    ]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("size", win.DWORD), ("reserved", win.LPWSTR), ("desktop", win.LPWSTR),
        ("title", win.LPWSTR), ("coordinates_and_fill", win.DWORD * 7),
        ("flags", win.DWORD), ("show_window", win.WORD), ("reserved_bytes", win.WORD),
        ("reserved_data", ctypes.c_void_p), ("stdin", win.HANDLE), ("stdout", win.HANDLE),
        ("stderr", win.HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", win.HANDLE), ("thread", win.HANDLE), ("pid", win.DWORD),
        ("thread_id", win.DWORD),
    ]


_KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
_SIZE = ctypes.c_size_t
_POINTER = ctypes.c_void_p


def _winapi(name, result, *arguments):
    fn = getattr(_KERNEL, name)
    fn.restype = result
    fn.argtypes = arguments
    return fn


_create_job = _winapi("CreateJobObjectW", win.HANDLE, _POINTER, win.LPCWSTR)
_set_job = _winapi("SetInformationJobObject", win.BOOL, win.HANDLE, ctypes.c_int,
                   _POINTER, win.DWORD)
_query_job = _winapi("QueryInformationJobObject", win.BOOL, win.HANDLE, ctypes.c_int,
                     _POINTER, win.DWORD, _POINTER)
_terminate_job = _winapi("TerminateJobObject", win.BOOL, win.HANDLE, win.UINT)
_close_handle = _winapi("CloseHandle", win.BOOL, win.HANDLE)
_open_process = _winapi("OpenProcess", win.HANDLE, win.DWORD, win.BOOL, win.DWORD)
_is_in_job = _winapi("IsProcessInJob", win.BOOL, win.HANDLE, win.HANDLE, ctypes.POINTER(win.BOOL))
_init_attributes = _winapi("InitializeProcThreadAttributeList", win.BOOL, _POINTER,
                           win.DWORD, win.DWORD, ctypes.POINTER(_SIZE))
_update_attributes = _winapi("UpdateProcThreadAttribute", win.BOOL, _POINTER, win.DWORD,
                             _SIZE, _POINTER, _SIZE, _POINTER, _POINTER)
_delete_attributes = _winapi("DeleteProcThreadAttributeList", None, _POINTER)
_create_process = _winapi("CreateProcessW", win.BOOL, win.LPCWSTR, win.LPWSTR, _POINTER,
                         _POINTER, win.BOOL, win.DWORD, _POINTER, win.LPCWSTR,
                         ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInfo))
_wait = _winapi("WaitForSingleObject", win.DWORD, win.HANDLE, win.DWORD)
_exit_code = _winapi("GetExitCodeProcess", win.BOOL, win.HANDLE, ctypes.POINTER(win.DWORD))


def _check(success):
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())
    return success


def _launch(argv, cwd, environment, job, input_handle, output_handle, stderr_handle):
    size = _SIZE()
    _init_attributes(None, 2, 0, ctypes.byref(size))
    attributes = ctypes.create_string_buffer(size.value)
    _check(_init_attributes(attributes, 2, 0, ctypes.byref(size)))
    try:
        handles = (win.HANDLE * 3)(input_handle, output_handle, stderr_handle)
        jobs = (win.HANDLE * 1)(job)
        for attribute, value in ((_HANDLE_LIST, handles), (_JOB_LIST, jobs)):
            _check(_update_attributes(
                attributes, 0, attribute, value, ctypes.sizeof(value), None, None,
            ))
        startup = _StartupInfoEx()
        startup.startup.size = ctypes.sizeof(startup)
        startup.startup.flags = _USE_STD_HANDLES
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles
        startup.attributes = ctypes.addressof(attributes)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        env = ctypes.create_unicode_buffer("\0".join(
            f"{key}={environment[key]}" for key in sorted(environment, key=str.upper)
        ) + "\0")
        info = _ProcessInfo()
        flags = subprocess.CREATE_NO_WINDOW | _EXTENDED_STARTUPINFO | _UNICODE_ENVIRONMENT
        _check(_create_process(
            argv[0], command, None, None, True, flags, env, str(cwd),
            ctypes.byref(startup), ctypes.byref(info),
        ))
        _close_handle(info.thread)
        return info.process
    finally:
        _delete_attributes(attributes)


def _inheritable(stream):
    handle = msvcrt.get_osfhandle(stream.fileno())
    os.set_handle_inheritable(handle, True)
    return handle


def _set_limits(job, flags):
    limits = _ExtendedLimits()
    limits.basic.flags = flags
    _check(_set_job(job, _EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)))


def _process_ids(job):
    count = 16
    while True:
        class _ProcessIds(ctypes.Structure):
            _fields_ = [("assigned", win.DWORD), ("listed", win.DWORD), ("pids", _SIZE * count)]

        members = _ProcessIds()
        found = _query_job(job, _PROCESS_IDS, ctypes.byref(members), ctypes.sizeof(members), None)
        if found and members.assigned == members.listed:
            return members.pids[:members.listed]
        if not found and ctypes.get_last_error() != _ERROR_MORE_DATA:
            _check(found)
        if members.assigned <= count:
            raise OSError("Windows returned an incomplete MindIE worker process list")
        count = members.assigned


def _wait_for_process(handle, timeout):
    milliseconds = int(min(max(0, timeout), _MAX_WAIT_MS / 1000) * 1000)
    result = _wait(handle, milliseconds)
    if result == _WAIT_TIMEOUT:
        raise subprocess.TimeoutExpired("MindIE reader", timeout)
    _check(result == _WAIT_OBJECT_0)


class WindowsWorker:
    def __init__(self, argv, *, cwd, env):
        with ExitStack() as launch, ExitStack() as owned:
            job = _check(_create_job(None, None))
            owned.callback(_close_handle, job)
            _set_limits(job, _KILL_ON_JOB_CLOSE)

            input_read, input_write = os.pipe()
            self.stdin = owned.enter_context(os.fdopen(input_write, "wb"))
            child_stdin = launch.enter_context(os.fdopen(input_read, "rb"))
            output_read, output_write = os.pipe()
            self.stdout = owned.enter_context(os.fdopen(output_read, "rb"))
            child_stdout = launch.enter_context(os.fdopen(output_write, "wb"))
            child_stderr = launch.enter_context(open(os.devnull, "wb"))
            self._process = _launch(
                argv, cwd, env, job, _inheritable(child_stdin), _inheritable(child_stdout),
                _inheritable(child_stderr),
            )
            # A waiter can still be unwinding on the channel thread during cancellation.
            # Keep the process handle until the last user releases this worker object.
            weakref.finalize(self, _close_handle, self._process)
            self._job = job
            self._confirmed_empty = False
            owned.pop_all()

    def wait(self, timeout):
        _wait_for_process(self._process, timeout)
        code = win.DWORD()
        _check(_exit_code(self._process, ctypes.byref(code)))
        return code.value

    def _terminate_and_wait(self):
        deadline = time.monotonic() + _CLEANUP_SECONDS
        # A zero process limit prevents new job members while handles are collected.
        # Job accounting can reach zero before an exiting process handle signals.
        _set_limits(self._job, _KILL_ON_JOB_CLOSE | _LIMIT_ACTIVE_PROCESSES)
        with ExitStack() as handles:
            processes = [self._process]
            for pid in _process_ids(self._job):
                if time.monotonic() >= deadline:
                    return False
                handle = _open_process(_SYNCHRONIZE | _QUERY_LIMITED_INFORMATION, False, pid)
                if not handle and ctypes.get_last_error() == _ERROR_INVALID_PARAMETER:
                    continue  # The member exited before its handle was opened.
                _check(handle)
                handles.callback(_close_handle, handle)
                member = win.BOOL()
                _check(_is_in_job(handle, self._job, ctypes.byref(member)))
                if member.value:
                    processes.append(handle)
            if len(processes) > 1:
                _check(_terminate_job(self._job, 1))
            for handle in processes:
                _wait_for_process(handle, deadline - time.monotonic())
        return not _process_ids(self._job)

    def stop(self):
        if self._job is not None:
            try:
                self._confirmed_empty = self._terminate_and_wait()
            finally:
                # Closing the non-inheritable job is also a kill-on-close backstop.
                _check(_close_handle(self._job))
                self._job = None
        if not self._confirmed_empty:
            raise OSError("MindIE worker tree cleanup could not be confirmed")
