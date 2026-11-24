# Harness-owned digest, file hash and file lock. Each function body equals the one in
# inferrsi.apps.storage.artifacts, so digests, hashes and lock files are byte-identical and the two
# locks exclude each other on the same path; Harness does not import that module here.
# tests/test_artifact_helper_copies.py keeps the copies equal.

import errno
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path):
    """Hold a nonblocking OS file lock, released even if the process crashes."""
    with path.open("a+b") as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except PermissionError as error:
                if error.errno != errno.EACCES:
                    raise
                # LK_NBLCK reports a lock violation as EACCES.
                raise BlockingIOError(errno.EAGAIN, "File lock is held", path) from error
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()
