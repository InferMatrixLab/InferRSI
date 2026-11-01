"""Warn on accidental closing syntax in a PR body (not an authorization check).

GitHub does not interpret natural-language negation. Scan raw Markdown rather
than trying to infer intent from quotes, examples or formatting. Only a line
consisting entirely of explicit closing directives is exempt. This deliberately
does not inspect commit messages or Development-sidebar links.

Keyword/reference forms follow GitHub's linking-a-pull-request-to-an-issue docs;
full github.com issue URLs are also recognized conservatively.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KEYWORD = r"(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)"
REFERENCE = (
    r"(?:https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/"
    r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#|#)[0-9]+\b"
)
DIRECTIVE = rf"{KEYWORD}:?[ \t]+{REFERENCE}"
STANDALONE = re.compile(
    rf"[ \t]*{DIRECTIVE}(?:[ \t]*(?:,[ \t]*(?:and[ \t]+)?|and[ \t]+)"
    rf"{DIRECTIVE})*[ \t]*\.?[ \t]*",
    re.IGNORECASE,
)
# Newlines matter too: a wrapped keyword/reference must not evade the warning.
CLOSING = re.compile(rf"\b{KEYWORD}:?\s+{REFERENCE}", re.IGNORECASE)


def violation_lines(body: str) -> list[int]:
    """Return one-based lines containing non-standalone closing directives."""
    lines = [line.rstrip("\r") for line in body.split("\n")]
    violations = set()
    for match in CLOSING.finditer(body):
        start = body.count("\n", 0, match.start())
        end = body.count("\n", 0, match.end())
        if start != end or not STANDALONE.fullmatch(lines[start]):
            violations.add(start + 1)
    return sorted(violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        pull_request = event["pull_request"]
        body = pull_request["body"]
        if body is None:
            body = ""
        if not isinstance(body, str):
            raise ValueError("non-text body")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        # Do not echo exception strings or PR content into Actions command logs.
        print("::error::Cannot read a pull_request body from the event JSON.")
        return 2
    violations = violation_lines(body)
    if violations:
        for line in violations:
            print(
                f"::error::PR body line {line}: closing syntax is embedded in text; "
                "use a non-closing reference, or a standalone closing line only "
                "when closure is authorized. Negation does not prevent closure."
            )
        return 1
    print("PR reference syntax passed; closure authorization was not assessed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
