"""Compose Harness parallel-round orchestration with Benchmark v0 gates.

Harness owns prepare / submit / serve / close scheduling. This package binds the
legacy assess port so ``inferrsi.harness.parallel_round`` never imports Benchmark.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from inferrsi.apps.host.platforms.cuda import qualify_devices
from inferrsi.apps.legacy.evaluation import run_rules
from inferrsi.benchmark.legacy_run_v0 import evaluate as _evaluate
from inferrsi.contracts import RunSpec


def make_assess(spec: RunSpec) -> Callable:
    """Bind v0 gates for one ``RunSpec``; the returned port matches ``runner.run_experiment``."""
    rules = run_rules(spec)

    def assess(baseline, candidate, validation, integrity, error):
        return _evaluate(
            rules, baseline, candidate, validation, integrity, run_error=error
        )

    return assess


def serve_ticket(
    round_dir: Path,
    ticket: str,
    incumbent: Path,
    *,
    backend,
    now: datetime | None = None,
    clock=None,
) -> dict:
    """Serve one ticket with the v0 assess composition."""
    from inferrsi.harness import parallel_round as harness

    return harness.serve_ticket(
        round_dir,
        ticket,
        incumbent,
        backend=backend,
        make_assess=make_assess,
        qualify_devices=qualify_devices,
        now=now,
        clock=clock,
    )


def close_round(
    round_dir: Path,
    incumbent: Path,
    *,
    backend,
    now: datetime | None = None,
    clock=None,
) -> dict:
    """Close one round with the v0 assess composition."""
    from inferrsi.harness import parallel_round as harness

    return harness.close_round(
        round_dir,
        incumbent,
        backend=backend,
        make_assess=make_assess,
        qualify_devices=qualify_devices,
        now=now,
        clock=clock,
    )
