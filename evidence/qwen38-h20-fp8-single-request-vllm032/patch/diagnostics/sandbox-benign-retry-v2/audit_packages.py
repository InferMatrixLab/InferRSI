"""Verify the complete installed set against authenticated exact dependency pins."""

import importlib.metadata
import json
import re
import sys
from pathlib import Path


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def locked(paths):
    expected = {}
    for path in paths:
        rows = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", path.read_text(), re.MULTILINE)
        if not rows:
            raise ValueError("Empty lock")
        for name, version in rows:
            key = normalize(name)
            if key in expected and expected[key] != version:
                raise ValueError("Conflicting build/runtime pins")
            expected[key] = version
    return expected


def validate(expected, rows, phase):
    actual = {}
    for name, version in rows:
        key = normalize(name)
        if key in actual:
            raise ValueError("Duplicate installed distribution")
        actual[key] = version
    wanted = dict(expected)
    if phase == "evaluator":
        if "evalplus" not in actual:
            raise ValueError("EvalPlus missing")
        # Its version is SCM-derived; source bytes are independently authenticated.
        wanted["evalplus"] = actual["evalplus"]
    elif phase != "dependencies":
        raise ValueError("Unknown phase")
    if actual != wanted:
        raise ValueError("Installed distribution set or versions differ from locks")
    return actual


def main():
    build, runtime, phase, output = sys.argv[1:]
    expected = locked([Path(build), Path(runtime)])
    rows = [(dist.metadata["Name"], dist.version) for dist in importlib.metadata.distributions()]
    actual = validate(expected, rows, phase)
    with Path(output).open("x") as stream:
        json.dump({"phase": phase, "expected": expected, "actual": actual}, stream, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
