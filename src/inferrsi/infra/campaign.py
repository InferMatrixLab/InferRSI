"""Compatibility imports for campaign scripts using the shared infrastructure.

New integrations can import the owning modules directly. This module contains
no model recipe, request protocol, accelerator choice, or quality threshold.
"""

from pathlib import Path

from .artifacts import digest, sha256, write_json
from .environment import dependency_versions, semantic_dependency_versions, storage_locations
from .processes import launch_server, stop_server
from .targets import source_snapshot

__all__ = [
    "digest",
    "sha256",
    "write_json",
    "dependency_versions",
    "semantic_dependency_versions",
    "storage_locations",
    "launch_server",
    "stop_server",
    "source_snapshot",
    "helper_hashes",
]


def helper_hashes() -> dict[str, str]:
    """Freeze transitive package implementation for new campaign references."""
    root = Path(__file__).resolve().parents[1]
    return {
        "inferrsi/" + str(path.relative_to(root)): sha256(path)
        for path in sorted(root.rglob("*.py"))
    }
