"""Compatibility exports for :mod:`inferrsi.apps.workflows.benchmark_compare`."""

from .workflows.benchmark_compare import (
    CONFIG_NAME,
    DEFAULT_CONFIG,
    OBSERVED_FIELDS,
    collect,
    compare_command,
    dispatch,
    prepare,
    report,
    resolve_config,
    status,
)

__all__ = [
    "DEFAULT_CONFIG",
    "CONFIG_NAME",
    "OBSERVED_FIELDS",
    "resolve_config",
    "prepare",
    "status",
    "dispatch",
    "collect",
    "report",
    "compare_command",
]
