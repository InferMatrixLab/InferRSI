import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_evidence_template_segments() -> None:
    base = REPO_ROOT / "evidence" / "_template"
    for seg in ("plan", "results", "patch", "validator"):
        assert (base / seg / "README.md").is_file()


def test_sias_readmes() -> None:
    pkg = REPO_ROOT / "src" / "inferrsi"
    for plane in ("harness", "model", "infra"):
        assert (pkg / plane / "README.md").is_file()


def test_maintained_documentation_links_resolve() -> None:
    documents = [REPO_ROOT / "README.md", REPO_ROOT / "AGENTS.md"]
    documents += list((REPO_ROOT / "docs").rglob("*.md"))
    documents += list((REPO_ROOT / "skills").rglob("*.md"))
    documents += list((REPO_ROOT / "src/inferrsi/data/skill_library").rglob("*.md"))
    documents += [REPO_ROOT / "evidence/README.md"]
    for document in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", document.read_text()):
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = (document.parent / unquote(parsed.path)).resolve()
            assert path.exists(), f"{document.relative_to(REPO_ROOT)}: broken link {target}"
