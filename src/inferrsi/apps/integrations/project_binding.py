"""Identify the checkout behind a frozen external knowledge session."""

import stat
from pathlib import Path


def _identity(path: Path) -> dict:
    info = path.stat()
    result = {"device": info.st_dev, "inode": info.st_ino}
    if hasattr(info, "st_birthtime"):
        result["created"] = info.st_birthtime
    return result


def checkout_identity(root: Path) -> dict:
    marker = root / ".git"
    mode = marker.lstat().st_mode
    if stat.S_ISDIR(mode):
        git_dir = marker
    elif stat.S_ISREG(mode):
        with marker.open("rb") as stream:
            raw = stream.read(4097)
        declaration = raw.decode().strip()
        prefix, _, target = declaration.partition(": ")
        if len(raw) > 4096 or prefix != "gitdir" or not target or "\n" in target:
            raise ValueError("Invalid worktree Git directory declaration")
        git_dir = (root / target).resolve(strict=True)
    else:
        raise ValueError("Cannot verify the project Git marker")
    if not git_dir.is_dir():
        raise ValueError("Cannot verify the worktree Git directory")
    return {
        "root": _identity(root), "marker": _identity(marker),
        "git_dir": str(git_dir), "git_dir_identity": _identity(git_dir),
    }


def matches_checkout(root: Path, expected: dict) -> bool:
    try:
        return checkout_identity(root) == expected
    except (OSError, ValueError, RuntimeError):
        return False
