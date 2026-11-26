import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import SplitResult, unquote, urlsplit

import pytest

from tools.check_pr_references import anchor_section

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "docs" / "architecture.md"
CODE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\n]*)$")
HEADING = re.compile(r"^#{1,6}[ \t]+([^\n]+)$")


def _heading_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    fence = ""
    for line in path.read_text(encoding="utf-8").split("\n"):
        marker = CODE_FENCE.fullmatch(line)
        if fence:
            if marker and marker[1].startswith(fence) and not marker[2].strip(" \t"):
                fence = ""
            continue
        if marker and (marker[1][0] == "~" or "`" not in marker[2]):
            fence = marker[1]
            continue
        heading = HEADING.fullmatch(line)
        if not heading:
            continue
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading[1]).strip(" #")
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


@pytest.mark.parametrize(("opening", "shorter", "closing"), [
    ("```bash", "~~~", "```"),
    ("   ```` bash", "```", "  `````"),
    ("~~~sh", "```", "~~~"),
])
def test_heading_ids_ignore_code_fences(tmp_path, opening, shorter, closing):
    document = tmp_path / "target.md"
    document.write_text(
        f"# Policy\n{opening}\n# Policy\n{shorter}\n# Install dependencies\n"
        f"{closing}\n# Policy\n",
        encoding="utf-8",
    )
    assert _heading_ids(document) == {"policy", "policy-1"}


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
