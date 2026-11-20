"""Read-only, bounded snapshots with independent availability and integrity facts."""

import hashlib
import mimetypes
import stat
from pathlib import Path, PurePosixPath

from ...harness import candidates
from ...infra.artifacts import sha256
from .schema import decode

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


def relative_path(name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or name.startswith("/")
    ):
        raise ValueError("Unsafe delivery source path")
    path = PurePosixPath(name)
    if ".." in path.parts or path.as_posix() != name or name == ".":
        raise ValueError("Unsafe delivery source path")
    return path


class Snapshot:
    def __init__(self, root: Path, observed_at: str):
        self.root = root
        self.observed_at = observed_at
        self.entries = {}
        self.documents = {}
        self.document_names = set()
        self.observations = {}
        self.trees = {}
        self.included = []

    def include(self, other, prefix):
        """Retain references and stability checks for an explicit external input."""
        refs = {}
        for identity, entry in other.entries.items():
            ref = prefix + identity
            if ref in self.entries:
                raise ValueError("Duplicate delivery source identity")
            self.entries[ref] = {**entry, "id": ref,
                                 "location": str(other.path(entry["location"]))}
            refs[identity] = ref
        self.included.append(other)
        return refs

    def path(self, name):
        relative_path(name)
        path = self.root / name
        for parent in (
            self.root,
            *[self.root / Path(*Path(name).parts[:i]) for i in range(1, len(Path(name).parts) + 1)],
        ):
            if parent.is_symlink():
                raise ValueError("Symbolic delivery source path")
        return path

    def file(self, name, role, expected=None, *, document=False):
        path = self.path(name)
        if document:
            self.document_names.add(name)
        identity = "source:" + name
        previous = self.entries.get(identity)
        expected = expected or (previous or {}).get("sha256")
        raw = None
        observed = None
        size = None
        try:
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("Delivery source must be a regular file")
            size = path.stat().st_size
            availability = "available"
            if document and size > MAX_DOCUMENT_BYTES:
                availability = "unreadable"
            elif document:
                raw = path.read_bytes()
                size = len(raw)
                observed = hashlib.sha256(raw).hexdigest()
            else:
                observed = sha256(path)
        except FileNotFoundError:
            availability = "missing"
        except PermissionError:
            availability = "restricted"
        entry = {
            "id": identity,
            "role": role,
            "location": name,
            "location_kind": "source",
            "media_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
            "size_bytes": size,
            "sha256": expected or observed,
            "observed_sha256": observed,
            "source_revision": expected or observed,
            "availability": availability,
            "integrity": ("mismatch" if expected and observed != expected else "verified")
            if observed
            else "not_checked",
            "checked_at": self.observed_at,
            "access": (
                "Document exceeds the 8 MiB read limit; bytes were not read"
                if availability == "unreadable"
                else "Requires the original input directory; no remote fetch was performed"
            ),
        }
        if previous and previous["observed_sha256"] != observed:
            raise SnapshotChanged("Source changed during snapshot")
        if previous and expected and previous["sha256"] != expected:
            # Different frozen references to the same path are a conflict, not last-write-wins.
            entry["integrity"] = "mismatch"
        self.entries[identity] = entry
        self.observations[name] = (availability, observed, size)
        if raw is not None:
            self.documents[name] = raw
        return identity

    def object(self, name, role, expected=None, *, required=False):
        ref = self.file(name, role, expected, document=True)
        raw = self.documents.get(name)
        if raw is not None and self.entries[ref]["integrity"] != "mismatch":
            try:
                value = decode(raw)
                if isinstance(value, dict):
                    return value, ref
            except (ValueError, UnicodeError):
                pass
            self.entries[ref]["integrity"] = "mismatch"
        if required:
            raise ValueError("Required delivery control document is missing or invalid")
        return None, ref

    def candidate(self, name, expected):
        path = self.path(name)
        try:
            members = candidates.members(path)
            actual = candidates.identity(path)
            names = [p.relative_to(self.root).as_posix() for p in members.values()]
            refs = [
                self.file(n, "source_code", expected if path.is_file() else None) for n in names
            ]
            self.trees[name] = actual
            return {
                "path": name,
                "fingerprint": expected,
                "observed_fingerprint": actual,
                "artifact_refs": refs,
                "verified": bool(expected) and actual == expected,
            }
        except (FileNotFoundError, PermissionError):
            pass
        except ValueError:
            # Missing code is a verification gap. Links/unsafe paths are rejected.
            if path.exists() or path.is_symlink():
                raise
        self.trees[name] = None
        ref = self.file(name, "source_code", expected)
        return {
            "path": name,
            "fingerprint": expected,
            "observed_fingerprint": None,
            "artifact_refs": [ref],
            "verified": False,
        }

    def verified(self, refs):
        return bool(refs) and all(self.entries[ref]["integrity"] == "verified" for ref in refs)

    def watch_tree(self, name):
        self.trees[name] = candidates.identity(self.path(name))

    def stable(self):
        """Detect uncoordinated writes, including candidate member-set changes."""
        probe = Snapshot(self.root, self.observed_at)
        for name in self.observations:
            probe.file(name, "snapshot_check", document=name in self.document_names)
        if probe.observations != self.observations:
            return False
        for name, expected in self.trees.items():
            path = probe.path(name)
            try:
                actual = candidates.identity(path)
            except (FileNotFoundError, PermissionError, ValueError):
                actual = None
            if actual != expected:
                return False
        return all(snapshot.stable() for snapshot in self.included)


class SnapshotChanged(ValueError):
    pass


class SnapshotBusy(ValueError):
    pass
