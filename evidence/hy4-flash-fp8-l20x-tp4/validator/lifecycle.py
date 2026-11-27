"""Drain every serving descendant before InferRSI inspects the owned process group."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import time

def run_service(argv, cwd, env, receipt, info):
    # On Linux an orphaned worker becomes our child, so waitpid can reap it.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'cannot become a child subreaper')
    proc = subprocess.Popen(argv, cwd=cwd, env=env)
    info['server_pid'] = proc.pid
    temp = receipt.with_suffix('.pending')
    temp.write_text(json.dumps(info))
    temp.replace(receipt)
    status = proc.wait()
    while True:
        try:
            os.waitpid(-1, 0)
        except ChildProcessError:
            break
    receipt.with_suffix('.drained').write_text(info['binding']['service_id'])
    return status

def drain(receipt, info):
    marked = receipt.with_suffix('.drained')
    if marked.exists():
        assert marked.read_text() == info['binding']['service_id']
        return
    owner = info['pid']
    group = os.getpgid(owner)
    if group != owner:
        raise RuntimeError('unexpected service process group')
    started = time.monotonic()
    api = info['server_pid']
    if not marked.exists():
        try:
            if os.getpgid(api) != group:
                raise RuntimeError('API server left the owned group')
            os.kill(api, signal.SIGTERM)
        except ProcessLookupError:
            pass
    while not marked.exists():
        elapsed = time.monotonic() - started
        if elapsed > 160:
            raise TimeoutError('serving processes did not drain')
        if elapsed > 90:
            for stat in Path('/proc').glob('[0-9]*/stat'):
                try:
                    fields = stat.read_text().rsplit(')',1)[1].split()
                    pid = int(stat.parent.name)
                    if int(fields[2]) == group and pid != owner and fields[0] != 'Z':
                        os.kill(pid, signal.SIGKILL if elapsed > 130 else signal.SIGTERM)
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    pass
        time.sleep(.2)
    assert marked.read_text() == info['binding']['service_id']
