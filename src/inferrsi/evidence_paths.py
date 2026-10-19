"""First-class evidence directory layout (portable; no campaign pins)."""

from __future__ import annotations

from pathlib import Path

EVIDENCE_SEGMENTS = ("plan", "results", "patch", "validator")


def campaign_evidence_root(repo_root: Path, campaign_id: str) -> Path:
    """Root directory for one campaign's published evidence tree."""
    return repo_root / "evidence" / campaign_id


def evidence_subpaths(root: Path) -> dict[str, Path]:
    """Map standard evidence segment names to paths under a campaign root."""
    return {name: root / name for name in EVIDENCE_SEGMENTS}


def ensure_evidence_layout(root: Path) -> dict[str, Path]:
    """Create standard evidence subdirectories if missing (local/dev helper)."""
    paths = evidence_subpaths(root)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
