from __future__ import annotations

import os
import re
import sys

# GitHub links an Issue for closure on merge when one of these keywords precedes the
# reference, including inside a negated sentence such as "this PR does not close #12".
KEYWORD = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"
REFERENCE = r"(?:[\w.-]+/[\w.-]+)?#\d+|https://github\.com/[\w.-]+/[\w.-]+/issues/\d+"
CLOSING = re.compile(rf"\b{KEYWORD}:?[ \t]+(?:{REFERENCE})\b", re.IGNORECASE)
# A line holding only a keyword and one reference is a deliberate, visible closure.
STANDALONE = re.compile(rf"[ \t]*{KEYWORD}:?[ \t]+(?:{REFERENCE})[ \t]*", re.IGNORECASE)

ADVICE = (
    "GitHub closes the referenced Issue on merge even when the sentence negates it. "
    "Write `Refs #N` instead. For an authorized closure, put `Closes #N` alone on its "
    "own line. See working rule 6 in docs/agent-collaboration.md."
)


def violations(body: str) -> list[tuple[int, str]]:
    return [
        (number, line.strip())
        for number, line in enumerate(body.splitlines(), 1)
        if CLOSING.search(line) and not STANDALONE.fullmatch(line)
    ]


def main() -> int:
    found = violations(os.environ["PR_BODY"])
    # Each printed line starts with "line" so PR text cannot form a workflow command.
    for number, line in found:
        print(f"line {number}: closing syntax inside text: {line}")
    if found:
        print(ADVICE)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
