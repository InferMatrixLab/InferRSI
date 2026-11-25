"""Compatibility exports for :mod:`inferrsi.apps.integrations.mindie.project`."""

from ..integrations.mindie.project import (
    ReadFailure,
    call,
    describe,
    disable,
    dispatch,
    enable,
    project_root,
)

__all__ = ["ReadFailure", "project_root", "enable", "disable", "describe", "call", "dispatch"]
