"""Prepare, review and explicitly publish a single redacted optimization record."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__:
    from . import optimization_records as records
else:
    import optimization_records as records

BASE_REF = "refs/remotes/inferrsi-record-upstream/main"
RECORD_ROOT = Path("evidence/records")
FORK_URL = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)"
)
GIT_IDENTITY = re.compile(r"([^<>\r\n]+ <[^<>\s]+>) [0-9]+ [+-][0-9]{4}")


class SubmissionError(ValueError):
    """A workflow error whose message contains no input paths or payloads."""


def command(*args):
    completed = subprocess.run(args, capture_output=True, check=False)
    if completed.returncode:
        # A command may echo private configuration or paths. Keep diagnostics local and generic.
        raise ValueError(f"{args[0]} {args[1]} failed (exit {completed.returncode})")
    return completed.stdout


def git(*args):
    return command("git", *args)


def gh(*args):
    return command("gh", *args)


def branch_name(record_id):
    return f"codex/optimization-record/{record_id}"


def require_branch(record_id):
    if git("symbolic-ref", "--short", "HEAD").decode().strip() != branch_name(record_id):
        raise ValueError("Use this record's dedicated submission branch")


def clean_changes():
    return git("status", "--porcelain=v1", "-z", "--untracked-files=all")


def stage(prepared):
    _, files = records.load_record(prepared)
    require_branch(prepared.name)
    records.regular(RECORD_ROOT.parent, directory=True)
    records.regular(RECORD_ROOT, directory=True)
    destination = RECORD_ROOT / prepared.name
    if destination.exists():
        if records.load_record(destination)[1] != files:
            raise ValueError("A different record already exists on this branch")
    else:
        if clean_changes():
            raise ValueError("Use a clean submission worktree")
        if git("merge-base", BASE_REF, "HEAD") != git("rev-parse", "HEAD"):
            raise ValueError("The submission branch must start from the fetched upstream main")
        records.publish_files(RECORD_ROOT, prepared.name, files)
    git("add", "--", destination.as_posix())
    return destination


def push_repository(push_remote):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", push_remote):
        raise ValueError("Invalid submission remote name")
    url = git("remote", "get-url", "--push", "--all", push_remote).decode().strip()
    parsed = FORK_URL.fullmatch(url)
    if not parsed or ".." in parsed[2]:
        raise ValueError("Select a remote for InferRSI or your GitHub fork")
    return f"{parsed[1]}/{parsed[2].removesuffix('.git')}"


def pr_text(record_id, acceptance_issue):
    title = f"evidence: submit optimization run record {record_id}"
    body = f"Submit a user-reviewed redacted run record at `evidence/records/{record_id}/`."
    if acceptance_issue is not None:
        body = f"Refs #{acceptance_issue}\n\n{body}"
    return title, body


def _identity(raw):
    parsed = GIT_IDENTITY.fullmatch(raw.decode("utf-8").rstrip("\n"))
    if not parsed or any(ord(c) < 32 for c in parsed[1]):
        raise SubmissionError("Git must provide a valid public name and email")
    return parsed[1]


def _commit_preview(record_id, attribution):
    author = _identity(git("var", "GIT_AUTHOR_IDENT"))
    committer = _identity(git("var", "GIT_COMMITTER_IDENT"))
    title = f"evidence: add optimization record {record_id}"
    trailers = f"Agent-assisted-by: {attribution}\n" if attribution is not None else ""
    return {"author": author, "committer": committer,
            "message": f"{title}\n\n{trailers}Signed-off-by: {committer}\n"}


def _verify_commit(head, base, expected):
    header, message = git("cat-file", "commit", head).split(b"\n\n", 1)
    rows = [row.split(b" ", 1) for row in header.split(b"\n")]
    if [row[0] for row in rows] != [b"tree", b"parent", b"author", b"committer"]:
        raise SubmissionError("Submission commit has unexpected headers or parents")
    if (rows[1][1] != base.encode() or _identity(rows[2][1]) != expected["author"]
            or _identity(rows[3][1]) != expected["committer"]
            or message != expected["message"].encode()):
        raise SubmissionError("Commit metadata differs from the approved identities and message")


def _check_entries(entries, paths, *, tree):
    parsed = {}
    for item in entries.rstrip(b"\0").split(b"\0"):
        if not item:
            continue
        meta, name = item.split(b"\t", 1)
        fields = meta.split()
        if fields[0] != b"100644" or fields[1 if tree else 2] != (b"blob" if tree else b"0"):
            raise ValueError("Only ordinary non-executable record files may be published")
        parsed[name.decode()] = True
    if set(parsed) != set(paths):
        raise ValueError("The selected record has unexpected index entries")


def review(record_id, attribution, push_remote="origin"):
    if not re.fullmatch(records.RECORD_ID, record_id):
        raise ValueError("Invalid record ID")
    if attribution is not None and (
        not attribution or len(attribution) > 180 or any(ord(c) < 32 for c in attribution)
        or records.sanitize_prompt(attribution) != attribution
    ):
        raise ValueError("Provide only public agent attribution")
    require_branch(record_id)
    directory = RECORD_ROOT / record_id
    records.regular(RECORD_ROOT.parent, directory=True)
    records.regular(RECORD_ROOT, directory=True)
    manifest, files = records.load_record(directory)
    head = git("rev-parse", "HEAD").decode().strip()
    base = git("merge-base", BASE_REF, head).decode().strip()
    count = int(git("rev-list", "--count", f"{base}..{head}"))
    commit = _commit_preview(record_id, attribution)
    paths = {f"{directory.as_posix()}/{path}": data for path, data in files.items()}
    if count == 0:
        changes = git("diff", "--cached", "--name-status", "--no-renames", "-z", base)
        entries = git("ls-files", "--stage", "-z", "--", directory.as_posix())
        spec = ":"
    elif count == 1 and not clean_changes():
        _verify_commit(head, base, commit)
        changes = git("diff", "--name-status", "--no-renames", "-z", base, head)
        entries = git("ls-tree", "-r", "-z", head, "--", directory.as_posix())
        spec = f"{head}:"
    else:
        raise ValueError("Submission must contain exactly one staged or committed record")
    expected = b"".join(b"A\0" + path.encode() + b"\0" for path in sorted(paths))
    if changes != expected:
        raise ValueError("The PR diff must add only the exact files for the selected record")
    _check_entries(entries, paths, tree=count == 1)
    if any(git("show", f"{spec}{path}") != content for path, content in paths.items()):
        raise ValueError("Git contains different bytes from the validated record")
    title, body = pr_text(record_id, manifest["acceptance_issue"])
    details = {
        "repository": records.REPOSITORY, "base": "main", "base_commit": base,
        "push_repository": push_repository(push_remote), "push_remote": push_remote,
        "branch": branch_name(record_id), "title": title, "body": body,
        "commit": commit, "files": {
            path: records.sha256(content) for path, content in paths.items()
        },
        "omissions": manifest["omissions"],
    }
    return {**details, "review_digest": records.sha256(records.json_bytes(details)),
            "committed_head": head if count == 1 else None}


def _find_pr(fork, branch, head, title, body):
    candidates = json.loads(gh(
        "api", "--hostname", "github.com", "--method", "GET",
        f"repos/{records.REPOSITORY}/pulls",
        "-f", f"head={fork.split('/')[0]}:{branch}", "-f", "base=main",
        "-f", "state=all", "-f", "per_page=100",
    ))
    for candidate in candidates:
        if ((candidate["head"].get("repo") or {}).get("full_name", "").lower() != fork.lower()
                or candidate["head"]["ref"] != branch
                or candidate["base"]["repo"]["full_name"] != records.REPOSITORY):
            continue
        if (candidate["head"]["sha"] != head
                or candidate["base"]["ref"] != "main"
                or not re.fullmatch(
                    rf"https://github\.com/{records.REPOSITORY}/pull/[1-9][0-9]*",
                    candidate["html_url"],
                )):
            raise SubmissionError("An existing submission PR has a different head or destination")
        if candidate["title"] != title or candidate["body"] != body:
            raise SubmissionError("Existing submission PR does not match the approved title/body")
        if candidate["state"] != "open" and not candidate["merged_at"]:
            raise SubmissionError("The existing submission PR was closed without merging")
        return candidate["html_url"]
    return None


def publish(record_id, approval, attribution, push_remote="origin"):
    checked = review(record_id, attribution, push_remote)
    if checked["review_digest"] != approval:
        raise SubmissionError("Publication requires authorization of the exact reviewed content")
    fork, branch = checked["push_repository"], checked["branch"]
    if fork.lower() != records.REPOSITORY.lower():
        remote = json.loads(gh(
            "repo", "view", f"github.com/{fork}", "--json", "nameWithOwner,parent"
        ))
        if (remote["nameWithOwner"].lower() != fork.lower()
                or (remote["parent"] or {}).get("nameWithOwner", "").lower()
                != records.REPOSITORY.lower()):
            raise ValueError("The push destination must be InferRSI or its GitHub fork")
    if not checked["committed_head"]:
        with TemporaryDirectory(prefix="inferrsi-record-commit-") as directory:
            message = Path(directory) / "message.txt"
            message.write_bytes(checked["commit"]["message"].encode())
            git("-c", "i18n.commitEncoding=UTF-8", "commit", "--no-gpg-sign",
                "--cleanup=verbatim", "-s", "-F", str(message))
    committed = review(record_id, attribution, push_remote)
    head = committed["committed_head"]
    if not head or committed["review_digest"] != approval:
        raise ValueError("Committed content differs from the approved review")
    lookup = (fork, branch, head, checked["title"], checked["body"])
    if url := _find_pr(*lookup):
        return url
    # Push the checked object, not a moving HEAD. Never push tags or force-update a branch.
    git("push", "--no-follow-tags", push_remote, f"{head}:refs/heads/{branch}")
    if url := _find_pr(*lookup):
        return url
    with TemporaryDirectory(prefix="inferrsi-record-pr-") as directory:
        body_file = Path(directory) / "body.md"
        body_file.write_bytes(checked["body"].encode("utf-8"))
        pr_head = branch if fork.lower() == records.REPOSITORY.lower() else (
            f"{fork.split('/')[0]}:{branch}"
        )
        try:
            gh("pr", "create", "--repo", records.REPOSITORY, "--base", "main",
               "--head", pr_head, "--title", checked["title"],
               "--body-file", str(body_file))
        except ValueError:
            if url := _find_pr(*lookup):
                return url
            raise
    if url := _find_pr(*lookup):
        return url
    raise SubmissionError("PR creation unconfirmed. Retry with the same record and digest")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare")
    prepare.add_argument("delivery", type=Path)
    prepare.add_argument("scratch", type=Path)
    prepare.add_argument("--facts", type=Path)
    prompt = prepare.add_mutually_exclusive_group()
    prompt.add_argument("--prompt", type=Path)
    prompt.add_argument("--withhold-prompt", action="store_true")
    prepare.add_argument("--public-acceptance-issue", type=int)
    prepare.add_argument("--public-archive-manifest", type=Path)
    staging = actions.add_parser("stage")
    staging.add_argument("prepared", type=Path)
    for action in ("review", "publish"):
        submit = actions.add_parser(action)
        submit.add_argument("record_id")
        submit.add_argument("--agent-attribution")
        submit.add_argument("--push-remote", default="origin")
        if action == "publish":
            submit.add_argument("--approved-review", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            checkout = Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve()
            if args.scratch.resolve().is_relative_to(checkout):
                raise ValueError("Prepare records in private scratch space outside the worktree")
            path = records.prepare_record(
                args.delivery, args.scratch,
                facts=records.read_object(args.facts) if args.facts else {},
                prompt=records.regular(args.prompt).read_text(encoding="utf-8")
                if args.prompt else None,
                omit_prompt=args.withhold_prompt, acceptance_issue=args.public_acceptance_issue,
                archive_manifest=args.public_archive_manifest,
            )
            result = {"record_id": path.name}
        elif args.action == "stage":
            result = {"record": stage(args.prepared).as_posix()}
        elif args.action == "review":
            result = review(args.record_id, args.agent_attribution, args.push_remote)
        else:
            result = {"record": (RECORD_ROOT / args.record_id).as_posix(),
                      "pr": publish(args.record_id, args.approved_review, args.agent_attribution,
                                    args.push_remote)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        # Never echo source payloads, JSON decoder input or OS paths in a report.
        detail = str(error) if isinstance(error, SubmissionError) else (
            "Check the source, record layout, and workflow prerequisites."
        )
        parser.exit(2, f"Record {args.action} failed. {detail}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
