"""Prepare a local, reviewable knowledge contribution report or declaration.

Supply --base with a freshly fetched target-branch tip. Its committed policy is
used, not a proposed working-tree policy. The PR-style diff is merge-base..HEAD;
renames are reported as deletion/addition so both endpoints remain in scope.
This helper neither publishes nor approves anything and never infers authorship.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__:
    from . import check_knowledge_model_policy as checker
else:
    import check_knowledge_model_policy as checker

PROJECT = Path(__file__).resolve().parents[1]
POLICY = ".github/knowledge-model-policy.json"
GENERATED = "src/inferrsi/data/repo_packs/inferrsi/knowledge/"
GENERATED_FILES = {"docs/skill-coverage.md"}
GIT_READ = ("git", "--no-replace-objects", "--no-lazy-fetch")


def _git(project: Path, *args: str) -> bytes:
    return subprocess.run(
        [*GIT_READ, "-C", str(project), *args], check=True, capture_output=True,
    ).stdout


def _revision(project: Path, name: str) -> str:
    return _git(project, "rev-parse", "--verify", "--end-of-options",
                f"{name}^{{commit}}").decode("ascii").strip()


def _paths(raw: bytes) -> list[str]:
    # Git's -z format retains tabs/newlines/quotes literally. JSON escapes them
    # on output; undecodable filenames fail rather than silently losing scope.
    return [path.decode("utf-8") for path in raw.split(b"\0") if path]


def _dirty_paths(project: Path, head: str) -> list[str]:
    tracked = _paths(_git(project, "diff", "--no-ext-diff", "--no-textconv",
                          "--no-renames", "--name-only", "-z", head, "--"))
    staged = _paths(_git(project, "diff", "--cached", "--no-ext-diff", "--no-textconv",
                         "--no-renames", "--name-only", "-z", head, "--"))
    untracked = _paths(_git(project, "ls-files", "--others", "--exclude-standard", "-z"))
    return sorted(set(tracked + staged + untracked))


def contribution_report(project: Path, base: str) -> dict:
    """Report committed HEAD only; local changes are separately and fully listed."""
    head = _revision(project, "HEAD")
    base_sha = _revision(project, base)
    ancestors = _git(project, "merge-base", "--all", base_sha, head).decode("ascii").split()
    if len(ancestors) != 1:
        raise ValueError("A unique merge base is required")
    merge_base = ancestors[0]
    policy = json.loads(_git(project, "show", f"{base_sha}:{POLICY}"),
                        object_pairs_hook=checker.unique_object)
    if (not isinstance(policy, dict) or type(policy.get("schema_version")) is not int
            or policy["schema_version"] != 1):
        raise ValueError("Unsupported trusted-base policy schema")
    for key in ("protected_paths", "policy_paths"):
        if not isinstance(policy.get(key), list) or any(
            not checker.text(pattern) for pattern in policy[key]
        ):
            raise ValueError("Invalid trusted-base policy paths")
    paths = sorted(set(_paths(_git(
        project, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
        "--name-only", "-z", merge_base, head, "--",
    ))))
    protected = sorted(checker.matching(paths, policy["protected_paths"]))
    generated = [path for path in paths
                 if path.startswith(GENERATED) or path in GENERATED_FILES]
    dirty = _dirty_paths(project, head)
    if _revision(project, "HEAD") != head:
        raise ValueError("HEAD changed while preparing report; rerun")
    return {
        "schema_version": 1,
        "head_sha": head,
        "base_sha": base_sha,
        "policy_sha": base_sha,
        "merge_base_sha": merge_base,
        "comparison": "merge-base..HEAD (renames retain both paths)",
        "changed_paths": paths,
        "protected_paths": protected,
        "policy_paths": sorted(checker.matching(paths, policy["policy_paths"])),
        "exception_paths": protected,
        "generated_paths": generated,
        "substantive_paths": sorted(set(paths) - set(generated)),
        "classification_note": (
            "Generated means the index directory or skill coverage document, not verified "
            "mechanical content. "
            "Other paths are substantive review inputs. All protected paths remain in scope."
        ),
        "dirty_paths": dirty,
        "note": (
            "Committed HEAD only; commit remaining changes and rerun. Refresh the target branch "
            "before choosing --base. This local report is not admission, review or approval. "
            "Exception paths are a scope preview, not an exception request or grant."
        ),
    }


def declaration_block(project: Path, report: dict, authors: dict,
                      exception_reason: str | None = None) -> str:
    """Fill mechanical fields only, retaining explicit supplied author facts verbatim."""
    if report["dirty_paths"] or _dirty_paths(project, report["head_sha"]):
        raise ValueError("Commit or remove local changes before generating a declaration")
    if _revision(project, "HEAD") != report["head_sha"]:
        raise ValueError("HEAD changed; rerun the contribution report")
    checker.fields(authors, ("human_only", "material_ai_authors"))
    value = {"schema_version": 1, "head_sha": report["head_sha"], **authors}
    if exception_reason is not None:
        if not checker.text(exception_reason):
            raise ValueError("Supply an explicit nonempty exception reason")
        value["exception"] = {"paths": report["exception_paths"], "reason": exception_reason}
    block = "```knowledge-model-policy\n" + json.dumps(value, indent=2, ensure_ascii=True) + "\n```"
    # Validate shape, not admission: unknown model/effort stay truthful. Only the
    # trusted remote checker can evaluate current approval and lifecycle facts.
    checker.declaration(block, report["head_sha"])
    return block


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Fresh target-branch tip (ref or commit)")
    parser.add_argument("--authors-file", type=Path, help=(
        "Explicit JSON object with human_only and material_ai_authors; prints one declaration "
        "instead of the report. Keep this file outside the worktree."
    ))
    parser.add_argument("--exception-reason", help=(
        "Explicitly request an exception for every protected changed path; does not approve it"
    ))
    args = parser.parse_args(argv)
    if args.exception_reason is not None and args.authors_file is None:
        parser.error("--exception-reason requires --authors-file")
    try:
        report = contribution_report(PROJECT, args.base)
        if args.authors_file is None:
            print(json.dumps(report, indent=2, ensure_ascii=True))
        else:
            authors = json.loads(args.authors_file.read_text(encoding="utf-8"),
                                 object_pairs_hook=checker.unique_object)
            print(declaration_block(PROJECT, report, authors, args.exception_reason))
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        # Git stderr can contain private paths/configuration; never echo it.
        message = (str(error) if isinstance(error, ValueError)
                   else "Required local input unavailable")
        print(f"Contribution helper: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
