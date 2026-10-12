from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_evidence_template_segments() -> None:
    base = REPO_ROOT / "evidence" / "_template"
    for seg in ("plan", "results", "patch", "validator"):
        assert (base / seg / "README.md").is_file()


def test_sias_readmes() -> None:
    pkg = REPO_ROOT / "src" / "omnirsi"
    for plane in ("harness", "model", "infra"):
        assert (pkg / plane / "README.md").is_file()


def test_research_doc_stubs() -> None:
    for name in ("positioning.md", "claims.md", "downstream.md", "demo-gate.md"):
        assert (REPO_ROOT / "docs" / name).is_file()
