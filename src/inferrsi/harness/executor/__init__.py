"""The process environment shared by Harness execution paths."""

import os
import sys
from importlib.resources import files
from pathlib import Path


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
