# Child entry for one operation of a frozen task protocol (#412 R3).
#
# Harness starts this file as ``python -I -B protocol_child.py REQUEST`` from
# ``run_task_protocol``; nothing executes protocol code in the Harness process. The file
# imports only the standard library, so the child never loads inferrsi. It reads the
# protocol bytes once, checks them against the request's SHA-256, compiles exactly those
# bytes and calls one protocol function. Descriptor 1 carries only the response envelope:
# everything the protocol prints, from Python, native code or its own children, goes to
# stderr. This is an interpreter and process boundary, not a filesystem or network sandbox.
# The protocol supervisor imports this module only for the shared envelope contract below.

import hashlib
import json
import math
import os
import sys
import types
from pathlib import Path

SCHEMA_VERSION = 1
# Operation name -> its request argument names, in call order.
OPERATIONS = {
    "validate_arguments": ("arguments",),
    "arguments": ("candidate", "output", "settings"),
    "assess": ("directory", "settings", "execution"),
}
REQUEST_KEYS = frozenset({"schema_version", "operation", "protocol", "protocol_sha256",
                          "arguments"})
# Failure kinds the child itself reports in an error envelope.
CHILD_ERROR_KINDS = frozenset({"request", "identity", "protocol_exception", "system_exit",
                               "result"})


def _unique_pairs(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate JSON object key")
    return dict(pairs)


def _non_finite(name):
    raise ValueError(f"non-finite JSON number {name}")


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number {text}")
    return value


def loads_strict(data: bytes):
    """Parse UTF-8 JSON that has no duplicate key and no NaN or infinite number."""
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                      parse_constant=_non_finite, parse_float=_finite_float)


def dumps_strict(value) -> bytes:
    """Encode JSON in ASCII; NaN, infinity and non-JSON values raise ValueError or TypeError."""
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode("ascii")


def check_request(request) -> None:
    """Raise ValueError unless ``request`` is a complete version-1 request."""
    if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
        raise ValueError("request must hold exactly " + ", ".join(sorted(REQUEST_KEYS)))
    if type(request["schema_version"]) is not int or request["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"request schema_version must be {SCHEMA_VERSION}")
    operation = request["operation"]
    if operation not in OPERATIONS:
        raise ValueError(f"unknown protocol operation {operation!r}")
    if not isinstance(request["protocol"], str) or not Path(request["protocol"]).is_absolute():
        raise ValueError("protocol must be an absolute path")
    digest = request["protocol_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or set(digest) - set("0123456789abcdef"):
        raise ValueError("protocol_sha256 must be 64 lowercase hex digits")
    arguments = request["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != set(OPERATIONS[operation]):
        raise ValueError(f"{operation} takes exactly " + ", ".join(OPERATIONS[operation]))
    if operation == "validate_arguments":
        values = arguments["arguments"]
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError("validate_arguments takes a list of strings")
        return
    paths = ("candidate", "output") if operation == "arguments" else ("directory",)
    for name in paths:
        if not isinstance(arguments[name], str) or not Path(arguments[name]).is_absolute():
            raise ValueError(f"{name} must be an absolute path")
    objects = ("settings",) if operation == "arguments" else ("settings", "execution")
    for name in objects:
        if not isinstance(arguments[name], dict):
            raise ValueError(f"{name} must be an object")


def _error(operation, kind, error_type, message, **extra):
    return {"schema_version": SCHEMA_VERSION, "operation": operation,
            "error": {"kind": kind, "type": error_type, "message": message, **extra}}


def _call(module, operation, arguments):
    if operation == "validate_arguments":
        return module.validate_arguments(list(arguments["arguments"]))
    if operation == "arguments":
        return module.arguments(Path(arguments["candidate"]), Path(arguments["output"]),
                                arguments["settings"])
    return module.assess(Path(arguments["directory"]), arguments["settings"],
                         arguments["execution"])


def _respond(argv) -> dict:
    if len(argv) != 1:
        return _error(None, "request", "UsageError", "expected exactly one request path")
    try:
        request = loads_strict(Path(argv[0]).read_bytes())
        check_request(request)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return _error(None, "request", type(error).__name__, str(error))
    operation = request["operation"]
    path = Path(request["protocol"])
    try:
        source = path.read_bytes()
    except OSError as error:
        return _error(operation, "identity", type(error).__name__, str(error))
    if hashlib.sha256(source).hexdigest() != request["protocol_sha256"]:
        return _error(operation, "identity", "ProtocolIdentityError",
                      "protocol bytes differ from the frozen digest")
    # argparse in a protocol names itself after argv[0].
    sys.argv = [str(path)]
    module = types.ModuleType("task_optimization_protocol")
    module.__file__ = str(path)
    try:
        # The digest-checked bytes themselves are compiled; no bytecode cache is involved.
        exec(compile(source, str(path), "exec"), module.__dict__)
        result = _call(module, operation, request["arguments"])
    except SystemExit as stop:
        code = stop.code
        if code is not None and type(code) is not int:
            print(code, file=sys.stderr)
            code = 1
        return _error(operation, "system_exit", "SystemExit", "protocol exited",
                      exit_code=0 if code is None else code)
    except Exception as error:
        return _error(operation, "protocol_exception", type(error).__name__, str(error))
    try:
        dumps_strict(result)
    except (TypeError, ValueError) as error:
        return _error(operation, "result", type(error).__name__, str(error))
    return {"schema_version": SCHEMA_VERSION, "operation": operation, "result": result}


def main(argv) -> int:
    # Keep a private copy of descriptor 1 for the envelope, then point descriptor 1 at
    # stderr so protocol output and inherited descriptors cannot reach the envelope.
    envelope = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    response = _respond(argv)
    sys.stdout.flush()
    with envelope:
        envelope.write(dumps_strict(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
