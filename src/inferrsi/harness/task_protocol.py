"""Freeze supplied task resources and load their task-owned evaluation protocol.

Task discovery belongs to the caller. This module accepts a resource directory;
it neither imports Benchmark nor contains model-specific acceptance rules.
"""

import importlib.util
import shutil
from pathlib import Path

from ..infra.artifacts import sha256


def protocol(root: Path):
    path = root / "optimization.py"
    if not path.is_file():
        raise ValueError("This task has no iterative evaluation protocol")
    spec = importlib.util.spec_from_file_location("task_optimization_protocol", path)
    module = importlib.util.module_from_spec(spec)
    # Always read the frozen source; do not create or consume a mutable bytecode cache.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def prepare(source: Path, destination: Path, arguments: list[str]) -> dict:
    settings = protocol(source).validate_arguments(arguments)
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Task resources must be regular files")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return {
        "evaluation_settings": settings,
        "frozen_files": {path.relative_to(destination).as_posix(): sha256(path)
                         for path in destination.rglob("*") if path.is_file()},
    }
