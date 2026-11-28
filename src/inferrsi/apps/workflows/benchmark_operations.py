"""Resolve packaged tasks at the application boundary and launch their entries."""

import subprocess
from pathlib import Path

from inferrsi.benchmark import registry
from inferrsi.harness.executor import benchmark_command, runtime_environment


def session_task(name: str) -> tuple[Path, dict]:
    """Resolve the task bundle and metrics policy to freeze on session start."""
    from inferrsi.benchmark.summary import POLICY

    return Path(str(registry.task_resources(name))), {"benchmark_metrics": POLICY}


def run_task(name: str, arguments: list[str]) -> int:
    entry = registry.task_resources(name).joinpath("benchmark.py")
    if not entry.is_file():
        raise ValueError(f"Missing benchmark.py entry for task: {name}")
    return subprocess.call(
        benchmark_command(entry, arguments),
        env=runtime_environment(),
    )
