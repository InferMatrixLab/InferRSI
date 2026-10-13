"""Git source identity shared by all model and hardware scenarios."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


def repository_identity(repo: str | Path, exclude: Path | None = None) -> dict:
    """Fingerprint Git revision, tracked diff and nonignored untracked files."""
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
            if not raw:
                continue
            name = os.fsdecode(raw)
            path = repo / name
            if exclude and path.absolute().is_relative_to(Path(exclude).resolve()):
                continue
            if path.is_symlink():
                digest = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            else:
                hasher = hashlib.sha256()
                with path.open("rb") as file:
                    for block in iter(lambda: file.read(1024 * 1024), b""):
                        hasher.update(block)
                digest = hasher.hexdigest()
            untracked.append({"path": name, "sha256": digest})
        dirty_data = {"diff_sha256": hashlib.sha256(diff).hexdigest(), "untracked": untracked}
        dirty_hash = hashlib.sha256(json.dumps(dirty_data, sort_keys=True).encode()).hexdigest()
        identity.update(
            available=True,
            head=head,
            git_root=str(git_root),
            dirty=bool(diff or untracked),
            dirty_hash=dirty_hash,
            untracked=untracked,
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
