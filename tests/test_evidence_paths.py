from pathlib import Path

from inferrsi.evidence_paths import campaign_evidence_root, ensure_evidence_layout


def test_campaign_root_under_evidence(tmp_path: Path) -> None:
    root = campaign_evidence_root(tmp_path, "demo-campaign")
    assert root == tmp_path / "evidence" / "demo-campaign"


def test_ensure_layout_creates_dirs(tmp_path: Path) -> None:
    root = tmp_path / "evidence" / "x"
    paths = ensure_evidence_layout(root)
    assert all(p.is_dir() for p in paths.values())
