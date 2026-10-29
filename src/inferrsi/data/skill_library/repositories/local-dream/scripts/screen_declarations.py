"""Compare explicit Local Dream boundary declarations, never runtime observations.

Original InferRSI helper; informed by pinned xororz/local-dream source contracts.
See ../references/repo-provenance.md for CC BY-NC source rights and limitations.
No upstream implementation is imported or executed.
"""

from __future__ import annotations

import json
import os
import stat
import sys

MAX_BYTES = 16_384
CONFIG_FIELDS = {"model_id", "backend_type", "width", "height", "listen_on_all"}


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid declaration")
    return value


def _string(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.strip():
        raise ValueError("invalid declaration")


def _integer(value):
    if type(value) is not int or not 0 < value <= 1_000_000:
        raise ValueError("invalid declaration")


def _config(value):
    if value is None:
        return
    _object(value, CONFIG_FIELDS)
    for name in ("model_id", "backend_type"):
        _string(value[name])
    for name in ("width", "height"):
        _integer(value[name])
    if type(value["listen_on_all"]) is not bool:
        raise ValueError("invalid declaration")


def audit(value):
    """Return mismatches only; valid declarations are not native qualification."""
    _object(value, {"schema_version", "desired", "serving", "abi", "sdk"})
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("invalid declaration")
    _config(value["desired"])
    _config(value["serving"])
    abi = _object(value["abi"], {"caller_version", "engine_version", "entry_present"})
    _integer(abi["caller_version"])
    _integer(abi["engine_version"])
    if type(abi["entry_present"]) is not bool:
        raise ValueError("invalid declaration")
    sdk = _object(value["sdk"], {"build_label", "staged_label", "runtime_stamp_label"})
    for label in sdk.values():
        _string(label)
    desired, serving = value["desired"], value["serving"]
    if desired is None or serving is None:
        delta = [] if desired is serving else ["presence"]
    else:
        delta = sorted(name for name in CONFIG_FIELDS if desired[name] != serving[name])
    findings = []
    if delta:
        findings.append("declared_process_configuration_differs")
    if not abi["entry_present"]:
        findings.append("declared_entry_missing")
    if abi["caller_version"] != abi["engine_version"]:
        findings.append("declared_abi_version_differs")
    if len(set(sdk.values())) != 1:
        findings.append("declared_sdk_labels_differ")
    return {
        "schema_version": 1,
        "configuration_fields_different": delta,
        "configuration_declarations_equal": not delta,
        "running_process_proven": False,
        "readiness": "not_observed",
        "artifact_bytes": "not_read",
        "native_execution": "not_run",
        "qualification": "INCONCLUSIVE",
        "findings": findings,
        "limits": [
            "No coroutine, grace-window, request ordering or service simulation.",
            "No resolution snapping or complete upstream input validation.",
            "No actual symbols, ABI layout, SDK bytes, device or model verification.",
            "No prompt-cache, cancellation, memory, image quality or performance test.",
        ],
    }


def example():
    config = {"model_id": "synthetic-model", "backend_type": "synthetic-backend",
              "width": 512, "height": 512, "listen_on_all": False}
    return {"schema_version": 1, "desired": dict(config), "serving": dict(config),
            "abi": {"caller_version": 1, "engine_version": 1, "entry_present": True},
            "sdk": {"build_label": "synthetic-sdk", "staged_label": "synthetic-sdk",
                    "runtime_stamp_label": "synthetic-sdk"}}


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _reject_constant(_):
    raise ValueError("invalid constant")


def _read(path):
    if path == "-":
        return sys.stdin.buffer.read(MAX_BYTES + 1)
    # No FIFOs/devices/directories or symlink traversal through the final component.
    mode = os.lstat(path).st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("regular file required")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("regular file required")
        return handle.read(MAX_BYTES + 1)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ["--help"]:
        print("Usage: screen_declarations.py --example | <regular-json-file> | -")
        return 0
    if args == ["--example"]:
        print(json.dumps(example(), indent=2))
        return 0
    try:
        if len(args) != 1 or args[0].startswith("--"):
            raise ValueError("invalid arguments")
        raw = _read(args[0])
        if len(raw) > MAX_BYTES:
            raise ValueError("input too large")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_reject_constant)
        result = audit(value)
    except (OSError, ValueError, TypeError, RecursionError):
        print("Invalid declaration input; use --help or --example.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
