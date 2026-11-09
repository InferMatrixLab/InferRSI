"""Expand a verified private runtime without exposing deep paths to the host importer."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import runpy
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def _io_path(path: Path) -> Path:
    value = str(path.resolve())
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)
    return Path(value)


def verified_files(archive: zipfile.ZipFile, manifest: dict) -> dict[str, bytes]:
    """Reject aliases/traversal and verify every byte before writing or executing it."""
    hashes = manifest["files"]
    names = archive.namelist()
    if not hashes or len(names) != len(set(names)) or set(names) != set(hashes):
        raise ValueError("Runtime manifest must cover every bundled runtime file")
    destinations = set()
    spellings = {}
    result = {}
    for member in archive.infolist():
        name = PurePosixPath(member.filename)
        if (not name.parts or name.parts[0] != "inferrsi" or len(name.parts) < 2
                or name.is_absolute() or ".." in name.parts or member.is_dir()
                or member.filename != name.as_posix()
                or "\\" in member.filename or ":" in member.filename
                or name.as_posix().casefold() in destinations
                or stat.S_ISLNK(member.external_attr >> 16)
                or any(part.endswith((".", " ")) or re.search(r'[<>"|?*]', part)
                       or re.fullmatch(r"con|prn|aux|nul|com[1-9]|lpt[1-9]",
                                       part.split(".")[0], re.IGNORECASE)
                       for part in name.parts)):
            raise ValueError("Unsafe runtime ZIP entry")
        destinations.add(name.as_posix().casefold())
        for depth in range(1, len(name.parts) + 1):
            prefix = "/".join(name.parts[:depth])
            if spellings.setdefault(prefix.casefold(), prefix) != prefix:
                raise ValueError("Unsafe runtime ZIP directory alias")
        data = archive.read(member)
        if hashlib.sha256(data).hexdigest() != hashes[member.filename]:
            raise ValueError("Bundled runtime checksum mismatch")
        result[member.filename] = data
    identity = "\n".join(f"{name}\0{digest}" for name, digest in sorted(hashes.items()))
    if hashlib.sha256(identity.encode("utf-8")).hexdigest() != manifest["content_sha256"]:
        raise ValueError("Runtime content identity mismatch")
    return result


def _plain(path: Path, attributes=None) -> None:
    attributes = path.lstat() if attributes is None else attributes
    if (stat.S_ISLNK(attributes.st_mode)
            or getattr(attributes, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise ValueError("Runtime cache must not contain links or reparse points")


def cache_runtime(manifest_bytes: bytes, launcher: bytes, content: dict[str, bytes]) -> Path:
    """Publish a private content-addressed cache, then verify it before every invocation."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")
    if not base.is_absolute():
        raise ValueError("Runtime cache base must be absolute, outside the target repository")
    cache_parent = base / "InferRSI" / "workswarm-runtime"
    for directory in (cache_parent.parent, cache_parent):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _plain(directory)
        if os.name != "nt":
            attributes = directory.stat()
            if attributes.st_uid != os.getuid() or attributes.st_mode & 0o022:
                raise ValueError("Runtime cache must be owned by this user and not shared writable")
    cache_parent = _io_path(cache_parent)
    identity = hashlib.sha256(manifest_bytes + launcher).hexdigest()
    root = cache_parent / identity
    expected = {"runtime/" + name: data for name, data in content.items()}
    expected["runtime/manifest.json"] = manifest_bytes
    expected["skills/inferrsi/scripts/inferrsi.py"] = launcher
    if not root.exists():
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=cache_parent))
        try:
            directories = {parent for name in expected for parent in Path(name).parents
                           if parent != Path(".")}
            for directory in sorted(directories, key=lambda path: len(path.parts)):
                (staging / directory).mkdir()
            for name, data in expected.items():
                path = staging / name
                path.write_bytes(data)
            try:
                staging.rename(root)
            except OSError:
                # Another first invocation can atomically publish the same key.
                if not root.is_dir():
                    raise
        finally:
            if staging.exists():
                _plain(staging)
                if staging.parent != cache_parent:
                    raise ValueError("Runtime cache staging escaped its owned parent")
                shutil.rmtree(staging)
    _plain(root)

    def mismatch(reason):
        return ValueError(
            f"Runtime cache verification failed; {reason}. Stop owned InferRSI invocations, "
            f"remove only cache entry {identity} under InferRSI/workswarm-runtime, then retry"
        )

    actual = set()
    pending = [root]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                # Windows DirEntry caches enumeration attributes, avoiding a
                # separate lstat/is_file round trip for every knowledge file.
                attributes = entry.stat(follow_symlinks=False)
                path = Path(entry.path)
                _plain(path, attributes)
                if stat.S_ISDIR(attributes.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(attributes.st_mode):
                    name = path.relative_to(root).as_posix()
                    actual.add(name)
                    if name not in expected or path.read_bytes() != expected[name]:
                        raise mismatch("cached files were modified")
                else:
                    raise mismatch("cache contains a special file")
    if actual != set(expected):
        raise mismatch("cached files are missing")
    return root / "skills/inferrsi/scripts/inferrsi.py"


def main() -> int:
    if sys.version_info < (3, 10):
        print("InferRSI requires Python 3.10 or newer.", file=sys.stderr)
        return 2
    runtime = _io_path(Path(__file__).resolve().parents[3] / "runtime")
    try:
        manifest_bytes = (runtime / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        payload = (runtime / "payload.zip").read_bytes()
        launcher = (runtime / "launcher.py").read_bytes()
        if (hashlib.sha256(payload).hexdigest() != manifest["payload_sha256"]
                or hashlib.sha256(launcher).hexdigest() != manifest["launcher_sha256"]):
            raise ValueError("Runtime payload or launcher checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            content = verified_files(archive, manifest)
        entry = cache_runtime(manifest_bytes, launcher, content)
        # No wrapper subprocess: the host still owns the foreground CLI process.
        try:
            runpy.run_path(str(entry), run_name="__main__")
        except SystemExit as exit_status:
            return exit_status.code if isinstance(exit_status.code, int) else 1
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"InferRSI plugin bundle is incomplete: {error}. "
              "See the package-integrity and runtime-cache repair steps in the bundled README.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
