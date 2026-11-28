import io
import json
import os
from pathlib import Path
import sys

envelope = json.load(sys.stdin)
payload = envelope["request"]
root = Path(sys.argv[1]).resolve()
assert sys.platform == "linux" and payload["repository"] == root.as_posix()
sys.stdin = io.StringIO(json.dumps(payload))
mutations = {
    "os.mkdir", "os.rmdir", "os.remove", "os.rename", "os.link", "os.symlink",
    "os.chmod", "os.truncate", "os.utime", "os.chown",
}
launches = {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec"}
write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
counts = {"workspaceWrites": 0, "temporaryRuntimeWrites": 0, "otherWrites": 0, "launches": []}

def audit(event, args):
    if event in launches:
        command = args[1] if event == "subprocess.Popen" else args[0]
        counts["launches"].append({"event": event, "command": str(command)})
        return
    if event == "open" and isinstance(args[2], int) and args[2] & write_flags:
        candidates = [args[0]]
    elif event in mutations:
        candidates = args[:2] if event in {"os.rename", "os.link", "os.symlink"} else args[:1]
    else:
        return
    for candidate in candidates:
        if not isinstance(candidate, (str, bytes)):
            continue
        parts = Path(os.path.abspath(os.fsdecode(candidate)))
        if parts.is_relative_to(root):
            counts["workspaceWrites"] += 1
        elif any(part.startswith("inferrsi-runtime-") for part in parts.parts):
            counts["temporaryRuntimeWrites"] += 1
        else:
            counts["otherWrites"] += 1

sys.addaudithook(audit)
try:
    exec(compile(envelope["bootstrap"], "<packaged DSH SSH bootstrap>", "exec"), {"__name__": "__main__"})
finally:
    print("__DSH_PREFLIGHT_AUDIT__ " + json.dumps(counts), file=sys.stderr)
