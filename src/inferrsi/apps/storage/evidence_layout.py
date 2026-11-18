"""Create the standard evidence directories for one campaign root.

This is the host I/O half of the evidence layout. The segment names and path rules
are ``inferrsi.contracts.evidence``, which never touches the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from inferrsi.contracts.evidence import evidence_subpaths


def ensure_evidence_layout(root: Path) -> dict[str, Path]:
    """Create standard evidence subdirectories if missing (local/dev helper)."""
    paths = evidence_subpaths(root)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
