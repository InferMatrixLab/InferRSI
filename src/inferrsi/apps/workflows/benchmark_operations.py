"""Resolve packaged tasks at the application boundary and launch their entries."""

import subprocess

from inferrsi.benchmark.registry import task_resources
from inferrsi.harness.executor import benchmark_command, runtime_environment


def run_task(name: str, arguments: list[str]) -> int:
    entry = task_resources(name).joinpath("benchmark.py")
    if not entry.is_file():
        raise ValueError(f"Missing benchmark.py entry for task: {name}")
    return subprocess.call(
        benchmark_command(entry, arguments),
        env=runtime_environment(),
    )
