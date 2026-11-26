"""Execution request identity and child process environment."""

import hashlib
import os
import sys
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

from inferrsi.contracts import json_v1


def runtime_environment() -> dict[str, str]:
    """Return a child environment bound to this InferRSI installation."""
    environment = dict(os.environ)
    # Children use the same installed/runtime bundle as this process, including
    # when a different editable installation is present in site-packages.
    import_paths = [str(Path(str(files("inferrsi"))).resolve().parent)]
    if inherited := environment.get("PYTHONPATH"):
        import_paths.append(inherited)
    environment["PYTHONPATH"] = os.pathsep.join(import_paths)
    if sys.dont_write_bytecode:
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def request_digest(spec: Mapping) -> str:
    """Return the D017 semantic identifier of a complete ExecutionSpec."""
    return "sha256:" + hashlib.sha256(json_v1.encode(spec)).hexdigest()
