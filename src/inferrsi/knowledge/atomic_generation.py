"""Open one immutable installed Knowledge generation and resolve only its exact pins."""

from __future__ import annotations

import hashlib
import json
import marshal
import os
import sys
from importlib.util import MAGIC_NUMBER, source_hash
from pathlib import Path, PurePosixPath
from uuid import uuid4

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


def _install_cache_sources(files: dict[str, str]) -> dict[str, tuple[str, int]]:
    """Map installer cache paths to the sealed source and optimization level."""
    tag = sys.implementation.cache_tag
    sources = {}
    if tag is not None:
        for name in files:
            path = PurePosixPath(name)
            if path.suffix == ".py":
                cache = path.parent / "__pycache__"
                for level, suffix in enumerate(("", ".opt-1", ".opt-2")):
                    cache_name = (cache / f"{path.stem}.{tag}{suffix}.pyc").as_posix()
                    if cache_name not in files:
                        sources[cache_name] = (name, level)
    return sources


def _cache_filename(payload: bytes, offset: int) -> str:
    # Read only the framed filename string. Never deserialize installer bytecode.
    if not 0 <= offset < len(payload):
        raise ValueError("Missing cache filename")
    tag = chr(payload[offset] & 0x7f)
    if tag in "zZ":
        width = 1
    elif tag in "aAut":
        width = 4
    else:
        raise ValueError("Invalid cache filename tag")
    start = offset + 1 + width
    end = start + int.from_bytes(payload[offset + 1:start], "little")
    if start > len(payload) or end > len(payload):
        raise ValueError("Truncated cache filename")
    return payload[start:end].decode("utf-8", errors="surrogatepass")


def _matches_install_cache(data: bytes, source: bytes, optimization: int) -> bool:
    if len(data) <= 16 or data[:4] != MAGIC_NUMBER:
        return False
    flags = int.from_bytes(data[4:8], "little")
    if flags == 0:
        if int.from_bytes(data[12:16], "little") != (len(source) & 0xffffffff):
            return False
    elif flags not in (1, 3) or data[8:16] != source_hash(source):
        return False

    payload = data[16:]
    # pip can compile in a staging directory. Locate the filename field by
    # compiling trusted bytes with a short ASCII marker, then compare the
    # complete payload against a fresh compile using the recorded filename.
    marker = f"<inferrsi-{uuid4().hex}>"
    try:
        probe = marshal.dumps(compile(source, marker, "exec", dont_inherit=True,
                                      optimize=optimization))
        marker_bytes = marker.encode("ascii")
        offset = probe.find(marker_bytes) - 2
        if _cache_filename(probe, offset) != marker:
            return False
        filename = _cache_filename(payload, offset)
        compiled = compile(source, filename, "exec", dont_inherit=True, optimize=optimization)
        return marshal.dumps(compiled) == payload
    except (SyntaxError, ValueError):
        return False


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
        files = inventory(root)
        cache_sources = _install_cache_sources(seal["files"]) if allow_install_cache else {}
        caches = {path: files.pop(path) for path in files.keys() & cache_sources.keys()}
        if {path: digest(data) for path, data in files.items()} != seal["files"]:
            raise ValueError("Installed Knowledge and skills differ from the sealed generation")
        for path, data in caches.items():
            source, optimization = cache_sources[path]
            if not _matches_install_cache(data, files[source], optimization):
                raise ValueError(f"Installed Python cache differs from sealed source: {path}")
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
