"""Git source identity shared by all model and hardware scenarios."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


def _file_digest(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _directory_digest(root: Path) -> str:
    """Hash every file below a directory; Git's own state is never source."""
    entries = []
    for directory, subdirectories, filenames in os.walk(root):
        base = Path(directory)
        # A symlinked directory selects a source elsewhere; record its target and
        # stop there, or retargeting it would leave the snapshot hash unchanged.
        links = sorted(
            name for name in subdirectories if name != ".git" and (base / name).is_symlink()
        )
        subdirectories[:] = sorted(
            name for name in subdirectories if name != ".git" and name not in links
        )
        for name in links:
            path = base / name
            entries.append(f"{path.relative_to(root).as_posix()}\0{_file_digest(path)}\n")
        for name in sorted(filenames):
            if name == ".git":
                continue
            path = base / name
            entries.append(f"{path.relative_to(root).as_posix()}\0{_file_digest(path)}\n")
    return hashlib.sha256("".join(entries).encode()).hexdigest()


def _decode_name(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            "Untracked path is not valid UTF-8: " + raw.decode("utf-8", "backslashreplace")
        ) from None


def _untracked_facts(repo: Path, name: str, exclude: Path | None) -> dict | None:
    path = repo / name
    if exclude and path.absolute().is_relative_to(Path(exclude).resolve()):
        return None
    if path.is_dir():
        # Git reports an untracked nested repository as one directory entry
        # rather than listing its files, so its contents are hashed directly.
        return {"path": name, "contents": "directory", "sha256": _directory_digest(path)}
    return {"path": name, "sha256": _file_digest(path)}


def _submodule_facts(repo: Path, entry: str) -> dict:
    """Record a gitlink's own identity; the parent diff sees only "<commit>-dirty"."""
    path = entry.split(None, 3)[3]
    worktree = repo / path
    if not (worktree / ".git").exists():
        return {"path": path, "contents": "uninitialized"}
    checkout = repository_identity(worktree)
    if not checkout["available"]:
        # Recording a partial identity would hide the unreadable checkout behind
        # a parent hash that still looks complete.
        raise ValueError(f"Submodule {path} identity unavailable: {checkout['error']}")
    return {
        "path": path,
        "contents": "checkout",
        "available": True,
        "snapshot_hash": checkout["snapshot_hash"],
        "dirty": checkout["dirty"],
    }


def repository_identity(repo: str | Path, exclude: Path | None = None) -> dict:
    """Fingerprint Git revision, tracked diff, untracked files and submodule contents."""

    repo = Path(repo).resolve()
    identity = {"path": str(repo), "available": False}

    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        if result.returncode:
            raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
        return result.stdout

    try:
        git_root = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve()
        if git_root != repo:
            raise ValueError("repo must be the root of its Git checkout")
        head = git("rev-parse", "HEAD").decode("ascii").strip()
        # Output roots may overlap source subdirectories. Only untracked
        # generated artifacts can be excluded; tracked changes remain evidence.
        diff = git("diff", "--binary", "HEAD", "--", ".")
        untracked = []
        for raw in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
            if raw:
                facts = _untracked_facts(repo, _decode_name(raw), exclude)
                if facts:
                    untracked.append(facts)
        submodules = []
        if (repo / ".gitmodules").is_file():
            submodules = [
                _submodule_facts(repo, os.fsdecode(raw).replace("\t", " "))
                for raw in git("ls-files", "--stage", "-z").split(b"\0")
                if raw.startswith(b"160000 ")
            ]
        dirty_data = {
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "untracked": untracked,
            "submodules": submodules,
        }
        dirty_hash = hashlib.sha256(
            json.dumps(dirty_data, sort_keys=True).encode("utf-8")
        ).hexdigest()
        identity.update(
            available=True,
            head=head,
            git_root=str(git_root),
            dirty=bool(diff or untracked)
            or any(item.get("dirty", False) or not item.get("available", True)
                   for item in submodules),
            dirty_hash=dirty_hash,
            untracked=untracked,
            submodules=submodules,
            snapshot_hash=hashlib.sha256(f"{head}:{dirty_hash}".encode()).hexdigest(),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        identity["error"] = str(exc)
    return identity


def source_snapshot(source):
    identity = repository_identity(source)
    if not identity.get("available"):
        raise ValueError(f"Source identity unavailable: {identity.get('error')}")
    return identity
