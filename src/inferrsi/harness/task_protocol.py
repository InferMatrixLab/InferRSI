"""Freeze supplied task resources and run their task-owned evaluation protocol.

Task discovery belongs to the caller. This module accepts a resource directory;
it neither imports Benchmark nor contains model-specific acceptance rules. Protocol
code never runs in this process: each operation runs ``protocol_child.py`` in a
separate isolated interpreter under a deadline, inside its own process group or
Windows Job, and returns one strict JSON envelope (#412 R3).
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import local_process, protocol_child
from .artifact_primitives import sha256

# One protocol operation must finish within this time; the child and every process in
# its group or Job are then stopped and the operation fails with kind "timeout".
PROTOCOL_TIMEOUT_SECONDS = 120.0
# The child writes stdout and stderr to files in a private scratch directory. These two
# limits apply when Harness reads those files, not while the child writes them; the
# deadline above bounds the run. Harness reads at most this many bytes of envelope ...
STDOUT_LIMIT_BYTES = 16 * 1024 * 1024
# ... and copies at most this tail of stderr to its own stderr after every operation.
STDERR_TAIL_BYTES = 4096
# The child entry that every operation runs as a separate script.
CHILD_ENTRY = Path(protocol_child.__file__).resolve()
_RESULT_TYPES = {"validate_arguments": dict, "arguments": list, "assess": dict}


class TaskProtocolError(ValueError):
    """A protocol operation gave no valid result. ``kind`` names the failure class.

    For ``protocol_exception`` the protocol itself raised: ``str()`` is its own message
    and ``reason`` its ``"<Type>: <message>"``, the text the in-process call gave before
    #412 R3. For every other kind both name the transport failure, so the two stay
    distinguishable.
    """

    def __init__(self, kind: str, message: str, *, error_type: str | None = None):
        super().__init__(message if kind == "protocol_exception" else f"{kind}: {message}")
        self.kind = kind
        self.reason = (f"{error_type}: {message}" if kind == "protocol_exception"
                       else f"{type(self).__name__}: {self}")


def _tail(path: Path) -> str:
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - STDERR_TAIL_BYTES))
        return stream.read().decode("utf-8", "replace")


def _response_problem(response, operation: str) -> str | None:
    if not isinstance(response, dict):
        return "envelope is not an object"
    version = response.get("schema_version")
    if type(version) is not int or version != protocol_child.SCHEMA_VERSION:
        return "envelope schema_version mismatch"
    keys = set(response)
    if keys == {"schema_version", "operation", "result"}:
        if response["operation"] != operation:
            return "envelope answers another operation"
        result = response["result"]
        if not isinstance(result, _RESULT_TYPES[operation]):
            return f"{operation} result must be a {_RESULT_TYPES[operation].__name__}"
        if operation == "arguments" and not all(isinstance(item, str) for item in result):
            return "arguments result must be a list of strings"
        return None
    if keys != {"schema_version", "operation", "error"}:
        return "envelope must hold either result or error"
    error = response["error"]
    if not isinstance(error, dict) or error.get("kind") not in protocol_child.CHILD_ERROR_KINDS:
        return "envelope error has no known kind"
    expected = {"kind", "type", "message"} | (
        {"exit_code"} if error["kind"] == "system_exit" else set())
    if (set(error) != expected or not isinstance(error["type"], str)
            or not isinstance(error["message"], str)
            or (error["kind"] == "system_exit" and type(error["exit_code"]) is not int)):
        return "envelope error object is malformed"
    if response["operation"] != (None if error["kind"] == "request" else operation):
        return "envelope answers another operation"
    return None


def run(root: Path, protocol_sha256: str, operation: str, **arguments):
    """Run one operation of ``root/optimization.py`` whose bytes have ``protocol_sha256``.

    Path arguments must be absolute. The child's stderr tail is copied to this process's
    stderr after every operation. A protocol ``SystemExit`` is raised again with its
    exit code; every other failure raises ``TaskProtocolError``. Descendants that the
    protocol leaves running are stopped with the child.
    """
    path = Path(root).resolve() / "optimization.py"
    if sha256(path) != protocol_sha256:
        raise TaskProtocolError("identity", "protocol bytes differ from the frozen digest")
    request = {"schema_version": protocol_child.SCHEMA_VERSION, "operation": operation,
               "protocol": str(path), "protocol_sha256": protocol_sha256,
               "arguments": {name: str(value) if isinstance(value, Path) else value
                             for name, value in arguments.items()}}
    try:
        protocol_child.check_request(request)
        data = protocol_child.dumps_strict(request)
    except (TypeError, ValueError) as error:
        raise TaskProtocolError("request", str(error)) from error
    with tempfile.TemporaryDirectory(prefix="inferrsi-protocol-") as temporary:
        work = Path(temporary)
        (work / "request.json").write_bytes(data)
        argv = [sys.executable, "-I", "-B", str(CHILD_ENTRY), str(work / "request.json")]
        # The scratch directory is the working directory, so a stray relative write
        # cannot land among the frozen resources.
        record = local_process._supervise(
            argv, work, dict(os.environ), work / "stdout", work / "stderr",
            time.monotonic() + PROTOCOL_TIMEOUT_SECONDS)
        stderr = _tail(work / "stderr") if (work / "stderr").is_file() else ""
        # Diagnostics contract: after every operation, whatever its result, the last
        # STDERR_TAIL_BYTES of the child's stderr (protocol prints included) are copied to
        # this process's stderr. The scratch directory with the full logs is then deleted.
        sys.stderr.write(stderr)
        sys.stderr.flush()
        if record["status"] == "cancelled" and record["cancellation_source"] == (
                "keyboard_interrupt"):
            raise KeyboardInterrupt
        if record["status"] == "timeout":
            raise TaskProtocolError(
                "timeout", f"{operation} exceeded {PROTOCOL_TIMEOUT_SECONDS:g} s; {stderr}")
        if record["status"] not in ("completed", "failed"):
            raise TaskProtocolError("launch", f"{record['status']}: {record['error']}")
        if record["returncode"] != 0:
            raise TaskProtocolError(
                "exit_status", f"child exited with {record['returncode']}; {stderr}")
        if record["domain_empty"] is not True:
            raise TaskProtocolError("cleanup", "the protocol left a live process behind")
        if (work / "stdout").stat().st_size > STDOUT_LIMIT_BYTES:
            raise TaskProtocolError("output_limit", f"envelope exceeds {STDOUT_LIMIT_BYTES} bytes")
        raw = (work / "stdout").read_bytes()
    try:
        response = protocol_child.loads_strict(raw)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise TaskProtocolError("malformed_response", str(error)) from error
    problem = _response_problem(response, operation)
    if problem is not None:
        raise TaskProtocolError("invalid_response", problem)
    if "result" in response:
        return response["result"]
    error = response["error"]
    if error["kind"] == "system_exit":
        raise SystemExit(error["exit_code"])
    if error["kind"] == "protocol_exception":
        raise TaskProtocolError("protocol_exception", error["message"], error_type=error["type"])
    raise TaskProtocolError(error["kind"], f"{error['type']}: {error['message']}")


def prepare(source: Path, destination: Path, arguments: list[str]) -> dict:
    path = source / "optimization.py"
    if not path.is_file():
        raise ValueError("This task has no iterative evaluation protocol")
    digest = sha256(path)
    settings = run(source, digest, "validate_arguments", arguments=arguments)
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Task resources must be regular files")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    frozen = {path.relative_to(destination).as_posix(): sha256(path)
              for path in destination.rglob("*") if path.is_file()}
    # The validated bytes are the frozen bytes that every later operation must match.
    if frozen["optimization.py"] != digest:
        raise ValueError("The task protocol changed while its resources were frozen")
    return {"evaluation_settings": settings, "frozen_files": frozen}
