"""Validate release refs and clean installed versions without publishing anything."""

import argparse
import re
import subprocess


def release_version(tag: str) -> str:
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"v{number}\.{number}\.{number}", tag):
        raise ValueError("Release tags must have the stable form vMAJOR.MINOR.PATCH")
    return tag[1:]


def resolve_release(tag: str, default_branch: str, expected_commit: str = "") -> str:
    release_version(tag)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
            text=True, stderr=subprocess.PIPE,
        ).strip()
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit,
             f"refs/remotes/origin/{default_branch}"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            "Release requires an existing tag reachable from the default branch"
        ) from error
    if expected_commit and commit != expected_commit:
        raise ValueError("Release tag no longer matches the triggering commit")
    return commit


def check_versions(tag: str, distribution: str, runtime: str) -> None:
    version = release_version(tag)
    if distribution != version or runtime != version:
        raise ValueError("Tag, installed distribution and runtime versions must agree exactly")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ref = commands.add_parser("ref")
    ref.add_argument("--tag", required=True)
    ref.add_argument("--default-branch", required=True)
    ref.add_argument("--expected-commit", default="")
    installed = commands.add_parser("installed")
    installed.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        if args.command == "ref":
            commit = resolve_release(args.tag, args.default_branch, args.expected_commit)
            print(f"tag={args.tag}")
            print(f"commit={commit}")
        else:
            from importlib.metadata import version

            from inferrsi import __version__

            check_versions(args.tag, version("inferrsi"), __version__)
            print("Installed release versions agree")
    except ValueError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
