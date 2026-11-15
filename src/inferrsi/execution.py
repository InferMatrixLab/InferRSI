"""Compatibility entry points for the local experiment runner.

The old run is composed in apps.legacy.run. Existing imports and legacy
injection points continue to delegate to the same implementations.
"""

from pathlib import Path

from .apps.legacy.run import execute_trial as _execute
from .apps.legacy.run import run_experiment as _run_experiment
from .harness.local_process import _stop_tree, _WindowsJob
from .infra.targets import repository_identity
from .runspec import RunSpec

__all__ = ["run_experiment", "repository_identity", "_execute", "_WindowsJob", "_stop_tree"]


def run_experiment(spec: RunSpec, environment: dict) -> Path:
    return _run_experiment(spec, environment, execute=_execute, snapshot=repository_identity)
