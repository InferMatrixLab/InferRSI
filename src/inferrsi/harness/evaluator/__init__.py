"""Assess ordinary attempts against frozen rules and retained evidence."""

from ._measurement import (
    CONFIDENCE,
    DIRECTIONS,
    METHOD,
    MIN_PAIRS,
    explain,
    gate_speedup,
    interval_rank,
    median_interval,
    min_pairs,
    paired_speedups,
    paired_statistics,
    profile_evidence,
    relative_mad,
    validate_mechanism,
)
from ._project import assess_project, inspect_project_step, project_steps

__all__ = [
    "CONFIDENCE", "DIRECTIONS", "METHOD", "MIN_PAIRS", "assess_ordinary", "assess_project",
    "explain", "gate_speedup",
    "inspect_project_step", "interval_rank", "median_interval", "min_pairs", "paired_speedups",
    "paired_statistics", "profile_evidence", "project_steps", "relative_mad", "validate_mechanism",
]


def assess_ordinary(root, directory, plan, execution, mechanism=None, *, assess_packaged):
    """Read project evidence or delegate to the packaged task's supplied assessor."""
    if plan["task_source"] == "project":
        return assess_project(
            directory, plan["evaluation_settings"], execution, mechanism=mechanism,
        )
    return assess_packaged(root, directory, plan, execution)
