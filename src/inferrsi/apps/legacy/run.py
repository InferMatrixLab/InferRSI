# The old `run` chain, composed here: Harness executes trials and records facts,
# Benchmark's v0 gates judge them, and this package writes the report.

from collections.abc import Callable
from functools import partial
from pathlib import Path

from inferrsi.benchmark.legacy_run_v0 import evaluate as _evaluate
from inferrsi.benchmark.legacy_run_v0 import read_metric, trial_metric
from inferrsi.harness.runner import run_experiment as _run_experiment
from inferrsi.harness.scenarios.external import execute_trial as _execute_trial
from inferrsi.infra.targets import repository_identity
from inferrsi.runspec import RunSpec

from .evaluation import run_rules
from .reporting import write_report


def execute_trial(
    command: tuple[str, ...],
    cwd: Path,
    trial_dir: Path,
    deadline: float,
    metric_key: str | None,
    *,
    metric_reader: Callable[[dict, str], float] = read_metric,
    environment: dict | None = None,
) -> dict:
    """Run one trial in Harness with Benchmark's metric contract applied to the reader."""
    return _execute_trial(
        command,
        cwd,
        trial_dir,
        deadline,
        metric_key,
        metric=partial(trial_metric, reader=metric_reader),
        environment=environment,
    )


def run_experiment(
    spec: RunSpec,
    environment: dict,
    *,
    execute: Callable[[tuple[str, ...], Path, Path, float, str | None], dict] = execute_trial,
    snapshot: Callable[[Path, Path | None], dict] = repository_identity,
) -> Path:
    """Run paired commands, judge them with the v0 gates and write the report."""

    def assess(baseline, candidate, validation, integrity, error):
        return _evaluate(
            run_rules(spec), baseline, candidate, validation, integrity, run_error=error
        )

    return _run_experiment(
        spec, environment, execute=execute, snapshot=snapshot, assess=assess, report=write_report
    )
