from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# GitHub links an Issue for closure on merge when one of these keywords precedes the
# reference, including inside a negated sentence such as "this PR does not close #12".
KEYWORD = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"
REFERENCE = r"(?:[\w.-]+/[\w.-]+)?#\d+|https://github\.com/[\w.-]+/[\w.-]+/issues/\d+"
CLOSING = re.compile(rf"\b{KEYWORD}:?[ \t]+(?:{REFERENCE})\b", re.IGNORECASE)
GOVERNING_REF = re.compile(r"^Refs #([1-9][0-9]*)[ \t]*\r?$", re.MULTILINE)
ARCHITECTURE = "docs/architecture.md"
CONTRACT_PATHS = (
    ARCHITECTURE,
    "docs/contracts/",
    "docs/module-layout.md",
    "docs/legacy-knowledge-manifest.json",
)
ANCHOR_SECTION = re.compile(
    r"^## Architecture anchors[ \t]*(?:\n|\Z).*?(?=^##[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)

ADVICE = (
    "GitHub closes the referenced Issue on merge even when the sentence negates it. "
    "Write `Refs #N` and close the Issue separately once authorized and complete. "
    "See working rule 6 in docs/agent-collaboration.md."
)


def violations(body: str) -> list[tuple[int, str]]:
    return [
        (number, line.strip())
        for number, line in enumerate(body.splitlines(), 1)
        if CLOSING.search(line)
    ]


def anchor_section(markdown: str) -> str | None:
    match = ANCHOR_SECTION.search(markdown)
    return match.group() if match else None


def _git(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), encoding="utf-8", stderr=subprocess.PIPE
    )


def contracts_changed(base: str, head: str) -> bool:
    if _git("show", "-s", "--format=%P", "HEAD").split() != [base, head]:
        raise ValueError("Checkout does not match the pull request merge commit")
    changes = _git(
        "diff", "--name-status", "--no-renames", "-z", "HEAD^1", "HEAD",
        "--", *CONTRACT_PATHS,
    ).rstrip("\0").split("\0")
    for status, path in zip(changes[::2], changes[1::2]):
        if path != ARCHITECTURE:
            return True
        before = "" if status == "A" else _git("show", f"HEAD^1:{path}")
        after = "" if status == "D" else _git("show", f"HEAD:{path}")
        if anchor_section(before) != anchor_section(after):
            return True
    return False


def _load_issue(repo_url: str, number: str, token: str) -> dict:
    request = Request(
        f"{repo_url}/issues/{number}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code in (404, 410):
            return {}
        raise


def scope_advice(body: str, repo_url: str, token: str) -> tuple[str, str]:
    ref = GOVERNING_REF.search(body)
    if not ref:
        return "warning", "A9 requires a plain Refs #N for the governing Issue."
    number = ref[1]
    issue = _load_issue(repo_url, number, token)
    if (
        issue.get("repository_url", "").casefold() != repo_url.casefold()
        or "pull_request" in issue
        or "status:accepted" not in {label["name"] for label in issue.get("labels", [])}
    ):
        return "warning", f"For A9, Refs #{number} needs a local Issue labelled status:accepted."
    return "notice", f"Verify the decision recorded in #{number} accepts this contract change."


def _advise_on_contract_scope(body: str, base: str) -> None:
    try:
        if not contracts_changed(base, os.environ["PR_HEAD_SHA"]):
            return
        api = os.environ["GITHUB_API_URL"].rstrip("/")
        repo_url = f"{api}/repos/{os.environ['GITHUB_REPOSITORY']}"
        level, advice = scope_advice(body, repo_url, os.environ["GITHUB_TOKEN"])
    except (subprocess.CalledProcessError, ValueError, KeyError, OSError, HTTPException):
        level = "warning"
        advice = "A9 check unavailable. Verify the live contract diff and accepted Issue."
    print(f"::{level}::{advice}")


def main() -> int:
    body = os.environ["PR_BODY"]
    found = violations(body)
    # Each printed line starts with "line" so PR text cannot form a workflow command.
    for number, line in found:
        print(f"line {number}: closing syntax in PR body: {line}")
    if found:
        print(ADVICE)
    if base := os.environ.get("PR_BASE_SHA"):
        _advise_on_contract_scope(body, base)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
