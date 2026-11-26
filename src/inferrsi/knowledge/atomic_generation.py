"""Open one immutable installed Knowledge generation and resolve only its exact pins."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

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


def owned_path(root: Path, name: str) -> Path:
    """Resolve a portable resource within its owner, rejecting links and Windows junctions."""
    path = root
    for part in safe_path(name).split("/"):
        path = path / part
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"Linked generation resource: {name}")
    return path


def inventory(root: Path) -> dict[str, bytes]:
    result = {}
    for family in ("knowledge", "skills"):
        directory = owned_path(root, family)
        if not directory.is_dir():
            raise ValueError(f"Missing generation directory: {family}")
        for path in directory.rglob("*"):
            name = path.relative_to(root).as_posix()
            owned_path(root, name)
            if path.is_file() and name != SEAL:
                result[name] = path.read_bytes()
    return result


class InstalledGeneration:
    """A verified snapshot. An open reader keeps its bytes across later installations."""

    def __init__(self, root: Path, *, expected: str | None = None):
        root = Path(root).resolve(strict=True)
        seal = json.loads(owned_path(root, SEAL).read_bytes())
        generation = seal.pop("generation")
        if seal.get("format") != FORMAT or generation != "sha256:" + digest(_json(seal)):
            raise ValueError("Invalid Knowledge generation seal")
        if expected is not None and expected != generation:
            raise UnavailableRevision(f"Requested generation is unavailable: {expected}")
        files = inventory(root)
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
            content = {name: files[path.removesuffix(".json") + "/" + safe_path(name)]
                       for name in manifest["resources"]}
            bundle = Bundle(manifest["metadata"], content, manifest["dependencies"])
            if (ref.partition(":")[2] != bundle.metadata["id"] or bundle.manifest() != manifest
                    or bundle.revision != pin.revision):
                raise ValueError(f"Installed Bundle differs from its catalog entry: {ref}")
            self._bundles[pin] = bundle
            skill = bundle.metadata.get("composition", {}).get("skill")
            if skill is not None:
                name = skill["name"]
                if name in exports or f"skills/{name}/SKILL.md" not in files:
                    raise ValueError(f"Invalid host skill export: {name}")
                exports[name] = ref
        if exports != self._skills or PUBLIC_TASKS - exports.keys():
            raise ValueError("Installed skill catalog differs from the public composition exports")

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
