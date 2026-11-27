"""Open one immutable installed Knowledge generation and resolve only its exact pins."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath

from .atomic_composition import AtomPin
from .knowledge_operations import Bundle, UnavailableRevision, _json, safe_path

PUBLIC_TASKS = frozenset({
    "task-day-0", "task-performance", "task-debug", "task-accuracy", "task-version-alignment",
    "task-derived-engine", "task-independent-engine",
})
SEAL = "knowledge/generation.json"
FORMAT = 2


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def filesystem_root(root: Path) -> Path:
    """Use absolute filesystem paths that accommodate deep installed resources on Windows."""
    absolute = Path(root).absolute()
    if os.name != "nt":
        return absolute
    name = str(absolute)
    if name.startswith(("\\\\?\\", "\\\\.\\")):
        return absolute
    if name.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + name[2:])
    return Path("\\\\?\\" + name)


def directory_skill_path(metadata: dict, name: str) -> str:
    entry = PurePosixPath(safe_path(metadata["entrypoint"]))
    relative = PurePosixPath(safe_path(name)).relative_to(entry.parent)
    return f"skills/{safe_path(metadata['id'])}/{relative.as_posix()}"


def owned_path(root: Path, name: str) -> Path:
    """Resolve a portable resource within its owner, rejecting links and Windows junctions."""
    path = root
    for part in safe_path(name).split("/"):
        path = path / part
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"Linked generation resource: {name}")
    return path


def inventory(root: Path, *, exclude: frozenset[str] = frozenset()) -> dict[str, bytes]:
    result = {}
    for family in ("knowledge", "skills"):
        directory = owned_path(root, family)
        if not directory.is_dir():
            raise ValueError(f"Missing generation directory: {family}")
        for path in directory.rglob("*"):
            name = path.relative_to(root).as_posix()
            owned_path(root, name)
            if path.is_file() and name != SEAL and name not in exclude:
                result[name] = path.read_bytes()
    return result


def _install_cache_paths(files: dict[str, str]) -> frozenset[str]:
    """Return cache paths the wheel installer may add for sealed Python sources."""
    tag = sys.implementation.cache_tag
    paths = set()
    if tag is not None:
        for name in files:
            path = PurePosixPath(name)
            if path.suffix == ".py":
                cache = path.parent / "__pycache__"
                for optimization in ("", ".opt-1", ".opt-2"):
                    paths.add((cache / f"{path.stem}.{tag}{optimization}.pyc").as_posix())
    return frozenset(paths.difference(files))


class InstalledGeneration:
    """An internally consistent snapshot, optionally pinned by its caller's release record."""

    def __init__(
        self, root: Path, *, expected: str | None = None, allow_install_cache: bool = True,
    ):
        root = filesystem_root(root).resolve(strict=True)
        seal = json.loads(owned_path(root, SEAL).read_bytes())
        generation = seal.pop("generation")
        if seal.get("format") != FORMAT or generation != "sha256:" + digest(_json(seal)):
            raise ValueError("Invalid Knowledge generation seal")
        if expected is not None and expected != generation:
            raise UnavailableRevision(f"Requested generation is unavailable: {expected}")
        cache_paths = _install_cache_paths(seal["files"]) if allow_install_cache else frozenset()
        files = inventory(root, exclude=cache_paths)
        if {path: digest(data) for path, data in files.items()} != seal["files"]:
            raise ValueError("Installed Knowledge and skills differ from the sealed generation")
        self.generation = generation
        self._catalog = seal["entries"]
        self._skills = seal["skills"]
        self._bundles = {}
        exports = {}
        for ref, entry in self._catalog.items():
            pin = AtomPin(ref, entry["revision"])
            path = safe_path(entry["manifest"])
            manifest = json.loads(files[path])
            metadata = manifest["metadata"]
            skill = metadata.get("composition", {}).get("skill")
            if skill == {"directory_entry": True}:
                content = {name: files[directory_skill_path(metadata, name)]
                           for name in manifest["resources"]}
            else:
                content = {name: files[path.removesuffix(".json") + "/" + safe_path(name)]
                           for name in manifest["resources"]}
            bundle = Bundle(manifest["metadata"], content, manifest["dependencies"])
            if (ref.partition(":")[2] != bundle.metadata["id"] or bundle.manifest() != manifest
                    or bundle.revision != pin.revision):
                raise ValueError(f"Installed Bundle differs from its catalog entry: {ref}")
            self._bundles[pin] = bundle
            if skill is not None:
                name = metadata["id"] if skill == {"directory_entry": True} else skill["name"]
                if name in exports or f"skills/{name}/SKILL.md" not in files:
                    raise ValueError(f"Invalid host skill export: {name}")
                exports[name] = ref
        if exports != self._skills or PUBLIC_TASKS - exports.keys():
            raise ValueError("Installed skill catalog differs from the public composition exports")
        self._release_pinned = expected is not None

    @property
    def release_pinned(self) -> bool:
        """Whether this installation matched a generation ID supplied by the caller."""
        return self._release_pinned

    def source_range_verified(self, pin: AtomPin) -> bool:
        entry = self._catalog.get(pin.ref, {})
        return (self.release_pinned and entry.get("revision") == pin.revision
                and entry.get("source_range_verified") is True)

    @property
    def catalog(self) -> dict:
        return {ref: dict(entry) for ref, entry in self._catalog.items()}

    @property
    def skills(self) -> dict[str, str]:
        """Generated host skill name to its owning composition."""
        return dict(self._skills)

    @property
    def tasks(self) -> dict[str, str]:
        return {name: self._skills[name] for name in sorted(PUBLIC_TASKS)}

    def read_resolved(self, reference: str, *, revision: str) -> tuple[str, Bundle]:
        pin = AtomPin(reference, revision)
        if pin not in self._bundles:
            raise UnavailableRevision(f"Revision unavailable in {self.generation}: {pin.ref}")
        bundle = self._bundles[pin]
        return pin.ref, Bundle(bundle.metadata, dict(bundle.content), dict(bundle.dependencies))
