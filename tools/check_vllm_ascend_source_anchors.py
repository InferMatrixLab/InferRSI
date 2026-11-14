"""Check selected anchors against local Git objects, offline (requires Git 2.49+)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

OWNER = (Path(__file__).resolve().parents[1]
         / "src/inferrsi/knowledge/data/skill_library/repositories/vllm-ascend")
DEFAULT_DOC = OWNER / "references/communication-config.md"
DEFAULT_METADATA = OWNER / "metadata.json"
SOURCE_URL = "https://github.com/vllm-project/vllm-ascend"
MAX_ANCHOR_LINES = 5
EXPECTED = {
    "current defaults": ("vllm_ascend/ascend_config.py", "enable_fused_mc2: int = 0"),
    "Capacity field": ("vllm_ascend/ascend_config.py", "mega_moe_max_tokens: int = 65536"),
}


def metadata_pin(metadata: Path, source_url: str = SOURCE_URL) -> str:
    sources = json.loads(metadata.read_text(encoding="utf-8"))["sources"]
    matches = [source for source in sources
               if source.get("type") == "git" and source.get("url") == source_url]
    if len(matches) != 1:
        raise ValueError(f"metadata must contain exactly one Git source for {source_url}")
    pin = matches[0].get("commit")
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise ValueError("metadata source pin must be a full 40-character commit SHA")
    return pin


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo), *args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError(f"local Git source unavailable: {result.stderr.strip()}")
    return result.stdout


def verify_anchors(
    repo: Path,
    markdown: str,
    pin: str,
    expectations: Mapping[str, tuple[str, str]] = EXPECTED,
    source_url: str = SOURCE_URL,
) -> list[str]:
    """Require each named link's short source span to contain its exact definition.

    Read only Git objects, never the checkout or the network. Expectations map a
    unique Markdown link label to (source path, stripped source definition).
    """
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise ValueError("source pin must be a full 40-character commit SHA")
    if git(repo, "cat-file", "-t", pin).strip() != "commit":
        raise ValueError("source pin must identify a commit object")
    links = re.findall(r"\[([^\]\n]+)\]\(([^)\s]+)\)", markdown)
    pattern = (re.escape(source_url.rstrip("/"))
               + r"/blob/([0-9a-f]{40})/(.+)#L([1-9]\d*)(?:-L([1-9]\d*))?")
    verified = []
    for label, (expected_path, definition) in expectations.items():
        urls = [url for text, url in links if text == label]
        if len(urls) != 1:
            raise ValueError(f"{label}: expected exactly one Markdown link")
        match = re.fullmatch(pattern, urls[0])
        if match is None:
            raise ValueError(f"{label}: expected an immutable source blob link with a line anchor")
        linked_pin, path, first, last = match.groups()
        if linked_pin != pin:
            raise ValueError(f"{label}: link commit {linked_pin} differs from source pin {pin}")
        if path != expected_path:
            raise ValueError(f"{label}: expected source path {expected_path}, got {path}")
        start, end = int(first), int(last or first)
        if not 1 <= end - start + 1 <= MAX_ANCHOR_LINES:
            raise ValueError(f"{label}: anchor span must contain 1-{MAX_ANCHOR_LINES} lines")
        lines = git(repo, "cat-file", "blob", f"{pin}:{path}").splitlines()
        if end > len(lines):
            raise ValueError(f"{label}: anchor exceeds source length ({len(lines)} lines)")
        if definition not in [line.strip() for line in lines[start - 1:end]]:
            raise ValueError(f"{label}: anchored source does not contain {definition!r}")
        verified.append(f"{label}: {path}#L{start}-L{end}: {definition}")
    return verified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="local vllm-ascend Git repository")
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    args = parser.parse_args(argv)
    try:
        pin = metadata_pin(args.metadata)
        verified = verify_anchors(args.repo, args.doc.read_text(encoding="utf-8"), pin)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Source anchor check failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {len(verified)} source anchors at {pin}.")
    print("\n".join(verified))
    return 0


if __name__ == "__main__":
    sys.exit(main())
