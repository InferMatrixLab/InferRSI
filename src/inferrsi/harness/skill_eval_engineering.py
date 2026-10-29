"""One public, reconstructed serving-parser engineering task.

The controller supplies retained artifact bytes, not agent-reported checks. Every
artifact invocation is confined by bubblewrap; absence of that boundary is an
infrastructure error, never permission to execute the artifact on the host.
This verifier does not sandbox the agent that produced the artifact.
"""
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ADAPTER = "engineering-artifact-v1"
MAX_SOURCE_BYTES = 65536
STARTER = (
    'def evaluate(status, frames, requested_tokens):\n'
    '    return {"success": status == 200, "reason": "length" if status == 200 else "http_error"}\n'
)
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["artifact", "summary"],
    "properties": {
        "artifact": {"type": "string", "enum": ["parser.py"]},
        "summary": {"type": "string"},
    },
}
PROMPT = (
    "Read task.json and the assigned knowledge. Repair only parser.py, implementing "
    "evaluate(status, frames, requested_tokens) under the public task contract. "
    "Do not change frozen inputs or create other files. No network, installs, other agents, "
    "commits or publication. Return artifact='parser.py' and a concise summary, not a verdict. "
    "The controller retains the actual file and independently checks its behavior."
)
REQUEST = (
    "Repair parser.py: evaluate(status, frames, requested_tokens) returns exactly "
    "{success: bool, reason: str}. Inputs are an integer HTTP status, decoded frames, "
    "and a positive integer requested count. Content frames have exactly {content: str}; "
    "a terminal has exactly {finish_reason: 'length'|'stop', completion_tokens: "
    "nonnegative int}. Boolean counts are invalid. At most one optional final '[DONE]' "
    "is allowed; DONE alone is not a terminal. First reject HTTP non-200 as http_error. "
    "Then inspect frames in order: a dict containing error gives stream_error; malformed "
    "fields, duplicate terminals, post-terminal content, misplaced or duplicate DONE "
    "give malformed_frame. Require a terminal after scanning, otherwise missing_terminal "
    "(also when the final frame is DONE). For length require count == requested; for stop "
    "require count <= requested, otherwise token_mismatch. Only valid length or stop "
    "returns success=true with that reason; every failure returns success=false. "
    "Change only parser.py; all other files are frozen. No imports/dependencies, network "
    "or hardware are required. Tests are public, not holdout. This reconstructed CPU "
    "fixture derives from the HTTP-200 error-stream observation in "
    "https://github.com/InferMatrixLab/InferRSI/pull/90; it does not reproduce the original "
    "server, capacity behavior or GPU performance."
)
REASONS = ("length", "stop", "http_error", "stream_error", "malformed_frame",
           "missing_terminal", "token_mismatch")
# Public behavior probes, not a hidden benchmark or proof of generalization.
# Expected outputs remain in the trusted parent, never in the artifact subprocess.
VECTORS = (
    ("length", 200, [{"content": "text"}, {"finish_reason": "length", "completion_tokens": 3},
                     "[DONE]"], 3, True, "length"),
    ("early_stop", 200, [{"finish_reason": "stop", "completion_tokens": 1}], 3, True, "stop"),
    ("empty_stop", 200, [{"finish_reason": "stop", "completion_tokens": 0}, "[DONE]"],
     3, True, "stop"),
    ("http_failure", 400, [], 3, False, "http_error"),
    ("stream_error", 200, [{"content": "partial"}, {"error": "capacity"}],
     3, False, "stream_error"),
    ("missing_terminal", 200, [{"content": "partial"}, "[DONE]"],
     3, False, "missing_terminal"),
    ("length_mismatch", 200, [{"finish_reason": "length", "completion_tokens": 2}],
     3, False, "token_mismatch"),
    ("stop_overflow", 200, [{"finish_reason": "stop", "completion_tokens": 4}],
     3, False, "token_mismatch"),
    ("unknown_frame", 200, [{"unexpected": True}], 3, False, "malformed_frame"),
    ("boolean_count", 200, [{"finish_reason": "length", "completion_tokens": True}],
     1, False, "malformed_frame"),
    ("duplicate_terminal", 200, [{"finish_reason": "stop", "completion_tokens": 1},
                                 {"finish_reason": "stop", "completion_tokens": 1}],
     3, False, "malformed_frame"),
    ("misplaced_done", 200, ["[DONE]", {"content": "late"}],
     3, False, "malformed_frame"),
    ("negative_count", 200, [{"finish_reason": "stop", "completion_tokens": -1}],
     3, False, "malformed_frame"),
    ("post_terminal_content", 200, [{"finish_reason": "stop", "completion_tokens": 1},
                                   {"content": "late"}], 3, False, "malformed_frame"),
    ("extra_content_field", 200, [{"content": "text", "extra": True}],
     3, False, "malformed_frame"),
    ("extra_terminal_field", 200, [{"finish_reason": "stop", "completion_tokens": 1,
                                   "extra": True}], 3, False, "malformed_frame"),
    ("unknown_finish", 200, [{"finish_reason": "unknown", "completion_tokens": 1}],
     3, False, "malformed_frame"),
    ("duplicate_done", 200, [{"finish_reason": "stop", "completion_tokens": 1},
                            "[DONE]", "[DONE]"], 3, False, "malformed_frame"),
    ("non_object_frame", 200, [42], 3, False, "malformed_frame"),
)


class SandboxUnavailable(RuntimeError):
    """The required artifact execution boundary could not be established."""



def read_regular(path: Path, limit: int) -> bytes:
    """Bounded no-follow snapshot after the producer has stopped.

    Reject symlink ancestors and special files; this is not an adversarial
    directory-rename sandbox. The actual replay has a separate OS boundary.
    """
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Artifact/evidence paths must not contain symlinks")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("Cannot read regular evidence file") from error
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Evidence is not a bounded regular file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Evidence exceeds byte bound")
    return data


def input_hashes(workspace: Path) -> dict:
    """Frozen engineering inputs only; special nodes are never opened."""
    if any(path.is_symlink() for path in (workspace.absolute(), *workspace.absolute().parents)):
        raise ValueError("Workspace paths must not contain symlinks")
    hashes = {}
    for path in workspace.rglob("*"):
        name = path.relative_to(workspace).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError("Workspace contains a symlink or special node")
        if stat.S_ISREG(mode) and name != "parser.py":
            hashes[name] = hashlib.sha256(read_regular(path, 16 * 1024 * 1024)).hexdigest()
    return hashes

def validate_task(task):
    if not isinstance(task, dict) or set(task) != {"id", "split", "request", "provenance"}:
        raise ValueError("Engineering task requires id/split/request/provenance only")
    if any(type(value) is not str or not value.strip() for value in task.values()):
        raise ValueError("Engineering task metadata must be nonempty strings")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", task["id"]):
        raise ValueError("Engineering task ID must be a safe path component")
    if task["request"] != REQUEST:
        raise ValueError("Engineering adapter supports only its frozen serving-parser request")
    if task["split"] != "development":
        raise ValueError("Engineering probes are public development cases, not holdout/discovery")


# Only one vector is visible per process. No checks/expected answers are loaded.
RUNNER = '''import json, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
if sys.argv[1:] == ["probe"]:
    print('{"ready": true}')
else:
    print("INFERRSI_ARTIFACT_READY", file=sys.stderr, flush=True)
    arguments = json.loads(sys.stdin.read())
    namespace = {"__name__": "submitted_parser"}
    with open("/work/parser.py", encoding="utf-8") as source:
        exec(compile(source.read(), "parser.py", "exec"), namespace)
    value = namespace["evaluate"](*arguments)
    print(json.dumps(value, allow_nan=False))
'''


def sandbox_command(work: Path, *, probe=False):
    """Linux system Python only; do not mount the caller's venv/home/repository."""
    bwrap = shutil.which("bwrap")
    python = Path("/usr/bin/python3").resolve()
    match = re.fullmatch(r"python(3\.\d+)", python.name)
    if sys.platform != "linux" or bwrap is None or not match or not python.is_file():
        raise SandboxUnavailable("Artifact replay requires Linux bubblewrap and system Python")
    stdlib = Path("/usr/lib") / ("python" + match[1])
    libraries = [path for path in (Path("/usr/lib/x86_64-linux-gnu"),
                                  Path("/usr/lib/aarch64-linux-gnu"), Path("/usr/lib64"))
                 if path.is_dir()]
    if not stdlib.is_dir() or not libraries:
        raise SandboxUnavailable("System Python runtime layout is unsupported")
    command = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
               "--ro-bind", str(python), "/usr/bin/python3",
               "--ro-bind", str(stdlib), str(stdlib)]
    for path in libraries:
        command += ["--ro-bind", str(path), str(path)]
    command += ["--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                "--ro-bind", str(work), "/work", "--proc", "/proc", "--dev", "/dev",
                "--chdir", "/work", "--remount-ro", "/",
                "--", "/usr/bin/python3", "-I", "-S", "-B", "/work/runner.py"]
    if probe:
        command.append("probe")
    return command


def _invoke(work, arguments=None, *, probe=False):
    # Files, not PIPE capture: child output cannot grow parent memory. Hard
    # RLIMIT_FSIZE in the trusted runner bounds each retained stream to 64 KiB.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                sandbox_command(work, probe=probe), stdin=subprocess.PIPE,
                stdout=stdout, stderr=stderr, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                start_new_session=True,
            )
        except OSError as error:
            raise SandboxUnavailable("Cannot start artifact sandbox") from error
        timed_out = False
        try:
            process.communicate(json.dumps(arguments).encode(), timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            timed_out = True
        if not probe:
            stderr.seek(0)
            if not stderr.read(128).startswith(b"INFERRSI_ARTIFACT_READY\n"):
                raise SandboxUnavailable("Artifact worker did not establish its trusted boundary")
        if timed_out:
            return None
        stdout.seek(0)
        raw = stdout.read(65537)
        if process.returncode or len(raw) > 65536:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return None


def verify(task, output):
    validate_task(task)
    valid = (isinstance(output, dict)
             and set(output) == {"artifact", "summary", "artifact_source"}
             and output["artifact"] == "parser.py"
             and type(output["summary"]) is str
             and type(output["artifact_source"]) is str)
    if not valid:
        return {"passed": False, "assertions": {"artifact_schema": False}}
    try:
        source = output["artifact_source"].encode("utf-8")
    except UnicodeEncodeError:
        source = b""
    if not source or len(source) > MAX_SOURCE_BYTES:
        return {"passed": False, "assertions": {"artifact_size": False}}
    with tempfile.TemporaryDirectory(prefix="skill-artifact-") as temporary:
        work = Path(temporary)
        (work / "runner.py").write_text(RUNNER, encoding="utf-8")
        (work / "parser.py").write_bytes(source)
        if _invoke(work, probe=True) != {"ready": True}:
            raise SandboxUnavailable("Artifact sandbox preflight failed; no host fallback")
        checks = {}
        for name, status, frames, count, success, reason in VECTORS:
            actual = _invoke(work, [status, frames, count])
            checks[name] = (isinstance(actual, dict) and set(actual) == {"success", "reason"}
                            and type(actual["success"]) is bool
                            and actual == {"success": success, "reason": reason})
    return {"passed": all(checks.values()), "assertions": checks}


def main():
    task = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    result = verify(task, output)
    Path(os.environ["INFERRSI_RESULT_PATH"]).write_text(json.dumps(result), encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
