"""Resolve packaged tasks at the application boundary and launch their entries."""

import subprocess
import sys
from pathlib import Path

from inferrsi.benchmark.registry import task_resources
from inferrsi.harness import optimization_session


def run_task(name: str, arguments: list[str]) -> int:
    entry = task_resources(name).joinpath("benchmark.py")
    if not entry.is_file():
        raise ValueError(f"Missing benchmark.py entry for task: {name}")
    return subprocess.call(
        [sys.executable, str(Path(optimization_session.__file__).resolve()),
         str(entry), *arguments],
        env=optimization_session.runtime_environment(),
    )
