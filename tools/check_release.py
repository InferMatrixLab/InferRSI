"""Plan daily stable releases and validate their packages without publishing."""

import argparse
import json
import re
import subprocess
import tarfile
from pathlib import Path


def release_version(tag: str) -> str:
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"v{number}\.{number}\.{number}", tag):
        raise ValueError("Release tags must have the stable form vMAJOR.MINOR.PATCH")
    return tag[1:]


def version_tuple(tag: str) -> tuple[int, ...]:
    return tuple(map(int, release_version(tag).split(".")))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()


def plan_release(default_branch: str, releases: list[dict], initial_version: str) -> dict:
    initial = version_tuple(f"v{initial_version}")
    source = git("rev-parse", "--verify", f"refs/remotes/origin/{default_branch}^{{commit}}")
    stable = {}
    for tag in git("tag", "--list").splitlines():
        try:
            stable[tag] = version_tuple(tag)
        except ValueError:
            continue
    published = []
    reserved = []
    for release in releases:
        tag = release["tag_name"]
        try:
            value = version_tuple(tag)
        except ValueError:
            continue
        reserved.append(value)
        if release["draft"] is False and release["prerelease"] is False:
            published.append((value, tag))
    previous_tag = max(published)[1] if published else ""
    if previous_tag:
        previous = git("rev-parse", "--verify", f"refs/tags/{previous_tag}^{{commit}}")
        subprocess.run(["git", "merge-base", "--is-ancestor", previous, source],
                       check=True, capture_output=True)
        if git("rev-parse", f"{previous}^{{tree}}") == git("rev-parse", f"{source}^{{tree}}"):
            return {"release": "false"}
    used = [*stable.values(), *reserved]
    if used:
        major, minor, patch = max(used)
        version = max(initial, (major, minor, patch + 1))
    else:
        version = initial
    return {"release": "true", "tag": "v" + ".".join(map(str, version)),
            "version": ".".join(map(str, version)),
            "commit": source, "previous_tag": previous_tag}


def check_versions(tag: str, distribution: str, runtime: str) -> None:
    version = release_version(tag)
    if distribution != version or runtime != version:
        raise ValueError("Tag, installed distribution and runtime versions must agree exactly")


def check_sdist(path: Path) -> None:
    # setuptools-scm's file finder must not expand the release to all tracked files.
    allowed = {"src", "pyproject.toml", "README.md", "LICENSE", "MANIFEST.in",
               "PKG-INFO", "setup.cfg"}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if ".." in parts or Path(member.name).is_absolute():
                raise ValueError("Unsafe source-distribution path")
            if len(parts) > 1 and parts[1] not in allowed:
                raise ValueError("Source distribution includes repository-only material")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--default-branch", required=True)
    plan.add_argument("--releases", type=Path, required=True)
    installed = commands.add_parser("installed")
    installed.add_argument("--tag", required=True)
    sdist = commands.add_parser("sdist")
    sdist.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            # The workflow uses Python 3.11; importing these helpers remains 3.10-safe.
            import tomllib

            config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
            pages = json.loads(args.releases.read_text(encoding="utf-8"))
            releases = [release for page in pages for release in page]
            result = plan_release(args.default_branch, releases,
                                  config["tool"]["inferrsi"]["release"]["initial_version"])
            for key, value in result.items():
                print(f"{key}={value}")
        elif args.command == "sdist":
            check_sdist(args.path)
        else:
            from importlib.metadata import version

            from inferrsi import __version__

            check_versions(args.tag, version("inferrsi"), __version__)
            print("Installed release versions agree")
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release validation failed: {error}\n")


if __name__ == "__main__":
    main()
