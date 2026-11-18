"""Compatibility exports for :mod:`inferrsi.apps.storage.archive`."""

from .storage.archive import (
    ResourceReader,
    RunOutput,
    archive_assessment,
    archive_mount,
    archive_prepared,
    publish_result,
    read_archive_artifact,
    read_assessment,
    read_prepared,
    read_result,
    validate_output_id,
)

__all__ = [
    "ResourceReader",
    "RunOutput",
    "archive_mount",
    "archive_prepared",
    "read_archive_artifact",
    "read_prepared",
    "archive_assessment",
    "read_assessment",
    "validate_output_id",
    "read_result",
    "publish_result",
]
