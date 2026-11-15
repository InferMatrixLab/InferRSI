"""Evidence segment names and per-campaign path rules (portable; no campaign pins).

Path construction only. Nothing here reads or writes the filesystem; creating the
directories is ``inferrsi.apps.evidence_layout.ensure_evidence_layout``.
"""

from __future__ import annotations

from pathlib import Path

EVIDENCE_SEGMENTS = ("plan", "results", "patch", "validator")


def campaign_evidence_root(repo_root: Path, campaign_id: str) -> Path:
    """Root directory for one campaign's published evidence tree."""
    return repo_root / "evidence" / campaign_id


def evidence_subpaths(root: Path) -> dict[str, Path]:
    """Map standard evidence segment names to paths under a campaign root."""
    return {name: root / name for name in EVIDENCE_SEGMENTS}
