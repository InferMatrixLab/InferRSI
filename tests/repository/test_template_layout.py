import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_evidence_template_segments() -> None:
    base = REPO_ROOT / "evidence" / "_template"
    for seg in ("plan", "results", "patch", "validator"):
        assert (base / seg / "README.md").is_file()


def test_sias_readmes() -> None:
    pkg = REPO_ROOT / "src" / "inferrsi"
    # #498 removed the model and infra planes; harness keeps its README.
    assert (pkg / "harness" / "README.md").is_file()
    assert not (pkg / "model").exists() and not (pkg / "infra").exists()


def test_maintained_documentation_links_resolve() -> None:
    documents = [REPO_ROOT / "README.md", REPO_ROOT / "AGENTS.md"]
    documents += list((REPO_ROOT / "docs").rglob("*.md"))
    documents += list((REPO_ROOT / "src/inferrsi/knowledge/data/skill_library").rglob("*.md"))
    documents += [REPO_ROOT / "evidence/README.md", REPO_ROOT / "tests/README.md"]
    documents.extend(sorted((REPO_ROOT / "evidence/_template/plan").glob("*.md")))
    for document in documents:
        for target in re.findall(
            r"\[[^\]]*\]\(([^\s)]+)\)", document.read_text(encoding="utf-8")
        ):
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = (document.parent / unquote(parsed.path)).resolve()
            assert path.exists(), f"{document.relative_to(REPO_ROOT)}: broken link {target}"
