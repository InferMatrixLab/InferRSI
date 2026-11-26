"""Local execution targets, generation preparation and verified input bindings."""

import hashlib
import os
import sys
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

from inferrsi.contracts import json_v1

__all__ = [
    "LocalCpuTarget", "prepare_generation", "process_group_empty", "project_prepared_binding",
    "read_prepared_binding", "request_digest", "runtime_environment", "verify_prepared_binding",
]


def __getattr__(name):
    if name == "LocalCpuTarget":
        from ._target import LocalCpuTarget

        return LocalCpuTarget
    if name == "prepare_generation":
        from ._generation import prepare_generation

        return prepare_generation
    if name in ("project_prepared_binding", "read_prepared_binding", "verify_prepared_binding"):
        from . import _prepared_binding

        return getattr(_prepared_binding, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def process_group_empty(group: int) -> bool | None:
    """Return whether the recorded group is empty, or None if it cannot be inspected."""
    from .local_process import _group_empty

    return _group_empty(group)


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
