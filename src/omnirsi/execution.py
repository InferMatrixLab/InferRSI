"""Compatibility entry points for the local experiment runner.

New integrations use harness.runner and infra directly. Existing imports and
legacy injection points continue to delegate to the same implementations.
"""

from pathlib import Path

from .harness.runner import run_experiment as _run_experiment
from .harness.scenarios.external import execute_trial as _execute
from .infra.processes import _stop_tree, _WindowsJob
from .infra.targets import repository_identity
from .runspec import RunSpec

__all__ = ["run_experiment", "repository_identity", "_execute", "_WindowsJob", "_stop_tree"]


def run_experiment(spec: RunSpec, environment: dict) -> Path:
    return _run_experiment(spec, environment, execute=_execute, snapshot=repository_identity)
