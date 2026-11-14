"""List the paths a knowledge PR changes and the declaration fields Git can derive.

Read-only. It reports the full head SHA and the protected, policy, generated and other
changed paths under the target branch's policy, including deletions and both rename
endpoints. It never fills in authors, models, efforts or exceptions; those stay explicit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
POLICY = ".github/knowledge-model-policy.json"
GENERATED = ("src/inferrsi/knowledge/data/repo_packs/inferrsi/knowledge/", "docs/skill-coverage.md")
GIT = ("git", "--no-replace-objects", "--no-lazy-fetch")


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        [*GIT, "-C", str(project), *args], check=True, capture_output=True
    ).stdout.decode("utf-8")


def changed_paths(project: Path, base: str, head: str) -> set[str]:
    # Same scope as the policy check: every path a change touches, both rename endpoints.
    fields = _git(project, "diff", "--name-status", "-z", "--find-renames",
                  f"{base}...{head}").split("\0")[:-1]
    paths, index = set(), 0
    while index < len(fields):
        status = fields[index]
        count = 2 if status[0] in "RC" else 1
        paths.update(fields[index + 1:index + 1 + count])
        index += 1 + count
    return paths


def report(project: Path, base: str, head: str) -> dict:
    head_sha = _git(project, "rev-parse", "--verify", f"{head}^{{commit}}").strip()
    # The base branch's policy decides admission, not the PR's own copy.
    policy = json.loads(_git(project, "show", f"{base}:{POLICY}"))
    paths = changed_paths(project, base, head_sha)

    def matching(patterns):
        return sorted(p for p in paths if any(fnmatchcase(p, pattern) for pattern in patterns))

    protected = matching(policy["protected_paths"])
    controls = matching(policy["policy_paths"])
    return {
        "head_sha": head_sha,
        "protected_paths": protected,
        "policy_paths": controls,
        "generated_paths": sorted(p for p in paths if p.startswith(GENERATED)),
        "other_paths": sorted(paths - set(protected) - set(controls)),
        "declaration_required": bool(protected),
        # An exception, if separately approved, must cover exactly these paths.
        "exception_scope": protected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="Target branch revision")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)
    result = report(PROJECT, args.base, args.head)
    print(json.dumps(result, indent=2))
    if result["declaration_required"]:
        print(
            "\nDeclare every material AI author with the actual tool, model_id and effort "
            f"and set head_sha to {result['head_sha']}. This helper does not supply them."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
