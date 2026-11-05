"""Clean this MoE invocation's torchrun workers, including detached sessions.

torchrun workers may create their own sessions, outside the executor's process
group. Only the launcher receives a fresh marker; it cannot reach the invoking
shell or allocator. This is lifecycle supervision for reviewed code, not a sandbox.
The marker must be generated in this driver after it starts, as evaluate() does.
"""

import os
import signal
import time
from pathlib import Path

MARKER = "INFERRSI_MOE_RUN_ID"


def _members(token: str, proc: Path = Path("/proc")) -> list[dict]:
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
        # Unreadable in-scope live same-user processes still make the cleanup
        # check inconclusive; in particular never swallow PermissionError.
    return found


def cleanup(token: str, *, grace_seconds: float = 5.0) -> dict:
    """Clean a marker minted by this driver; preserve PID-reuse protection."""
    killed = set()
    deadline = time.monotonic() + grace_seconds
    try:
        while True:
            members = _members(token)
            if not members:
                return {"verified": True, "signalled_pids": sorted(killed), "remaining": []}
            for item in members:
                try:
                    fields = Path(f"/proc/{item['pid']}/stat").read_text().rsplit(")", 1)[1].split()
                    if int(fields[19]) == item["start_ticks"]:
                        os.kill(item["pid"], signal.SIGKILL)
                        killed.add(item["pid"])
                except (FileNotFoundError, ProcessLookupError):
                    pass
            if time.monotonic() >= deadline:
                return {"verified": False, "signalled_pids": sorted(killed),
                        "remaining": _members(token)}
            time.sleep(0.05)
    except (OSError, ValueError, IndexError) as exc:
        return {"verified": False, "signalled_pids": sorted(killed), "error": str(exc)}
