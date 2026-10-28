"""Unchanged reviewed owned-server cleanup, extracted from formal collector v2."""

import os
import signal
import subprocess


def group_members(pgid):
    rows = subprocess.check_output(["ps", "-eo", "pid=,pgid="], text=True, timeout=2)
    return [int(pid) for pid, group in (r.split() for r in rows.splitlines()) if int(group) == pgid]


def terminate_owned(process):
    forced = False
    errors = []

    def signal_group(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except Exception as exc:
            errors.append({"step": "signal_" + str(sig), "exception": type(exc).__name__})

    signal_group(signal.SIGTERM)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        forced = True
    except Exception as exc:
        forced = True
        errors.append({"step": "term_wait", "exception": type(exc).__name__})
    try:
        remaining = group_members(process.pid)
    except Exception as exc:
        remaining = None
        errors.append({"step": "group_before_kill", "exception": type(exc).__name__})
    if forced or remaining is None or remaining:
        forced = True
        signal_group(signal.SIGKILL)
    try:
        process.wait(timeout=10)
    except Exception as exc:
        errors.append({"step": "kill_wait", "exception": type(exc).__name__})
    try:
        remaining = len(group_members(process.pid))
    except Exception as exc:
        remaining = None
        errors.append({"step": "group_after_kill", "exception": type(exc).__name__})
    return {
        "exit_code": process.returncode,
        "forced": forced,
        "owned_group_remaining": remaining,
        "cleanup_errors": errors,
        "cleanup_complete": remaining == 0 and process.returncode is not None and not errors,
    }
