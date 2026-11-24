import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

from tools.check_pr_references import anchor_section

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "docs" / "architecture.md"


def _heading_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    markdown = path.read_text(encoding="utf-8")
    headings = re.findall(r"^#{1,6}[ \t]+([^\n]+)$", markdown, re.MULTILINE)
    for heading in headings:
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading).strip(" #")
        slug = re.sub(r"[^\w -]", "", text.lower()).replace(" ", "-")
        unique = slug
        suffix = 1
        while unique in ids:
            unique = f"{slug}-{suffix}"
            suffix += 1
        ids.add(unique)
    return ids


def _links(text: str) -> list[SplitResult]:
    return [urlsplit(url) for url in re.findall(r"\]\(([^)\s]+)\)", text)]


def test_architecture_anchors_resolve_to_existing_sources_and_checks():
    section = anchor_section(ARCHITECTURE.read_text(encoding="utf-8"))
    assert section, "docs/architecture.md needs an Architecture anchors section"
    _, *entries = re.split(r"^###[ \t]+([^\n]+)\n", section, flags=re.MULTILINE)
    assert 1 <= len(entries) // 2 <= 10

    test_refs = set()
    for number, (title, content) in enumerate(zip(entries[::2], entries[1::2]), 1):
        assert title.startswith(f"A{number} — "), f"Expected A{number}, got {title}"
        summary, marker, checks = content.partition("**Checked by**")
        assert marker and checks.strip(), f"{title} needs a Checked by line"
        assert any(
            link.fragment and not (link.scheme or link.netloc) for link in _links(summary)
        ), f"{title} needs a source heading"
        for link in _links(content):
            if link.scheme or link.netloc:
                continue
            destination = (
                (ARCHITECTURE.parent / unquote(link.path)).resolve()
                if link.path else ARCHITECTURE
            )
            assert destination.is_relative_to(ROOT) and destination.is_file(), (title, link)
            if link.fragment:
                assert unquote(link.fragment) in _heading_ids(destination), (title, link)
        test_refs.update(re.findall(r"`(tests/[^`\n]+)`", checks))

    if test_refs:
        for ref in test_refs:
            path = (ROOT / ref.partition("::")[0]).resolve()
            assert path.is_relative_to(ROOT / "tests") and path.is_file(), ref
        command = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="]
        result = subprocess.run(
            [*command, *sorted(test_refs)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
