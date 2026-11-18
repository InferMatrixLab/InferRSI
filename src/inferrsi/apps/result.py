"""Compatibility exports for :mod:`inferrsi.apps.storage.result`."""

from .storage.result import (
    assessment_result,
    execution_result,
    is_public_error,
    preparation_result,
    publication_error,
    validate_artifact_ref,
    validate_result,
)

__all__ = [
    "is_public_error",
    "execution_result",
    "preparation_result",
    "assessment_result",
    "publication_error",
    "validate_artifact_ref",
    "validate_result",
]
