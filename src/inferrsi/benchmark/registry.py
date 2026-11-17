"""Discover task-owned resources without importing their execution runtimes."""

import json
import re
from importlib.resources import files


def _library_root():
    return files("inferrsi.benchmark").joinpath("tasks")


def builtin_tasks() -> list[str]:
    registry = json.loads(_library_root().joinpath("index.json").read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or type(registry.get("schema_version")) is not int:
        raise ValueError("Task registry requires integer schema_version 1")
    if registry["schema_version"] != 1:
        raise ValueError("Unsupported task registry schema_version")
    packages = registry.get("packages")
    if not isinstance(packages, list):
        raise ValueError("Task registry packages must be a list")
    for name in packages:
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError(f"Invalid task package name: {name!r}")
    if len(set(packages)) != len(packages):
        raise ValueError("Duplicate task package in registry")
    return sorted(packages)


def task_resources(name: str):
    if name not in builtin_tasks():
        raise ValueError(f"Unknown engineering benchmark: {name}")
    root = _library_root().joinpath(name)
    if not root.is_dir():
        raise ValueError(f"Missing registered task package: {name}")
    return root


def describe_task(name: str) -> dict:
    root = task_resources(name)
    return {
        "package": name,
        "manifest": json.loads(root.joinpath("task.json").read_text(encoding="utf-8")),
        "files": sorted(path.name for path in root.iterdir() if path.is_file()),
    }
