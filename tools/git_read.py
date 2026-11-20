"""Requirements for tools that inspect Git objects without replacements or lazy fetches."""

import re
import subprocess

GIT_READ = ("git", "--no-replace-objects", "--no-lazy-fetch")


class GitVersionError(ValueError):
    pass


def require_git_version(version: str, purpose: str = "Snapshot preparation") -> None:
    parsed = re.match(r"git version (\d+)\.(\d+)(?:\.|$)", version.strip())
    if parsed is None or tuple(map(int, parsed.groups())) < (2, 45):
        raise GitVersionError(
            f"{purpose} requires Git >= 2.45 for --no-lazy-fetch; found {version.strip()}. "
            "Upgrade Git and retry."
        )


def check_git_version(purpose: str = "Snapshot preparation") -> None:
    try:
        version = subprocess.check_output(["git", "--version"], text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitVersionError(
            f"{purpose} requires Git >= 2.45. Install Git on PATH and retry."
        ) from error
    require_git_version(version, purpose)
