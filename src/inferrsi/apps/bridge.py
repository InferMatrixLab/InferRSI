"""Compatibility exports for :mod:`inferrsi.apps.handoff.bridge`."""

from .handoff.bridge import (
    bind_execution,
    check_assessment_identity,
    execution_fields,
    to_evidence,
    verify_protocol,
)

__all__ = [
    "execution_fields",
    "verify_protocol",
    "check_assessment_identity",
    "bind_execution",
    "to_evidence",
]
