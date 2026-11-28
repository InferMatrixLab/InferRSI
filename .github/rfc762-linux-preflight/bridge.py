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
# The audit events for shutil.rmtree use paths relative to an opened directory.
# Resolve the descriptor so removing the extracted runtime is attributed to /tmp.
mutation_paths = {
    "os.mkdir": ((0, 2),), "os.rmdir": ((0, 1),), "os.remove": ((0, 1),),
    "os.rename": ((0, 2), (1, 3)), "os.link": ((0, 2), (1, 3)),
    "os.symlink": ((1, 2),), "os.chmod": ((0, 2),), "os.truncate": ((0, None),),
    "os.utime": ((0, 3),), "os.chown": ((0, 3),),
}
launches = {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec"}
write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
counts = {"workspaceWrites": 0, "temporaryRuntimeWrites": 0, "otherWrites": 0,
          "workspaceWriteSamples": [], "launches": []}


def mutation_path(candidate, descriptor=None):
    if isinstance(candidate, int):
        return Path(os.readlink(f"/proc/self/fd/{candidate}"))
    if not isinstance(candidate, (str, bytes)):
        return None
    path = Path(os.fsdecode(candidate))
    if not path.is_absolute() and descriptor is not None and descriptor >= 0:
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}")) / path
    return Path(os.path.abspath(path))

def audit(event, args):
    if event in launches:
        command = args[1] if event == "subprocess.Popen" else args[0]
        counts["launches"].append({"event": event, "command": str(command)})
        return
    if event == "open" and isinstance(args[2], int) and args[2] & write_flags:
        paths = ((0, None),)
    elif event in mutation_paths:
        paths = mutation_paths[event]
    else:
        return
    for path_index, descriptor_index in paths:
        descriptor = args[descriptor_index] if descriptor_index is not None else None
        try:
            path = mutation_path(args[path_index], descriptor)
        except OSError:
            counts["otherWrites"] += 1
            continue
        if path is None:
            continue
        if path.is_relative_to(root):
            counts["workspaceWrites"] += 1
            samples = counts["workspaceWriteSamples"]
            if len(samples) < 8:
                samples.append({"event": event, "path": path.relative_to(root).as_posix()})
        elif any(part.startswith("inferrsi-runtime-") for part in path.parts):
            counts["temporaryRuntimeWrites"] += 1
        else:
            counts["otherWrites"] += 1

sys.addaudithook(audit)
try:
    exec(compile(envelope["bootstrap"], "<packaged DSH SSH bootstrap>", "exec"), {"__name__": "__main__"})
finally:
    print("__DSH_PREFLIGHT_AUDIT__ " + json.dumps(counts), file=sys.stderr)
