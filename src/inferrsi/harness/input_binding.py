from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import BinaryIO

# H input capture and byte-equivalent copies. H owns these digests and writes and never
# imports infra.artifacts. A source is read once into a snapshot; every later copy comes
# from that snapshot, never again from the mutable source.
_CHUNK = 1024 * 1024
# Schema ``Path``: relative and slash-separated; no '.'/'..' segment, backslash, colon,
# or control character.
RELATIVE_PATH = re.compile(
    r"(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))(?!.*[\\:\x00-\x1f\x7f])[^/]+(?:/[^/]+)*"
)


class BindingError(Exception):
    """A source or produced file cannot be bound; ``code`` is the recorded reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def file_sha256(path: Path) -> tuple[str, int]:
    """sha256 hex digest and byte size of one file."""
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK), b""):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def copy_stream(stream: BinaryIO, target: Path) -> tuple[str, int]:
    """Write the stream's bytes to a new file; return the digest and size actually written."""
    hasher = hashlib.sha256()
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "xb") as out:
            for chunk in iter(lambda: stream.read(_CHUNK), b""):
                out.write(chunk)
                hasher.update(chunk)
                size += len(chunk)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return hasher.hexdigest(), size


def open_regular(root: Path, relative: str) -> BinaryIO:
    """Open a regular, non-link file confined to ``root``; FileNotFoundError when absent."""
    if not RELATIVE_PATH.fullmatch(relative):
        raise BindingError("unsafe_path", "path is not a relative schema Path")
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            raise BindingError("unsafe_path", "path contains a link")
    if not stat.S_ISREG(os.lstat(current).st_mode):
        raise BindingError("not_a_regular_file", "path is not a regular file")
    if not current.resolve().is_relative_to(root.resolve()):
        raise BindingError("unsafe_path", "path leaves its authorized root")
    return open(current, "rb")


def materialize(snapshot: Path, target: Path, sha256: str, size: int) -> None:
    """Copy a captured snapshot to the path the process reads, and verify the copy."""
    with open(snapshot, "rb") as stream:
        copied = copy_stream(stream, target)
    if copied != (sha256, size) or file_sha256(target) != (sha256, size):
        raise BindingError("materialization_mismatch", "materialized bytes differ from capture")
