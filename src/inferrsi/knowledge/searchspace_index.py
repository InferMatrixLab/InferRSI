"""Read a matrix coordinate snapshot for an InferRSI source checkout."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .skill_catalog import _entry, skill_directories

LIBRARY = Path("src/inferrsi/knowledge/data/skill_library")
CATALOG = LIBRARY / "skill-index.json"
MATRIX = Path("docs/searchspace-matrix.md")
INDEX = Path("docs/searchspace-index.json")

RESOURCES = {"1": "Accelerator", "2": "RAM/Host", "3": "SSD", "4": "Network", "5": "OS"}
STAGES = ("Observe", "Profile", "Diagnose", "Configure", "Optimize", "Verify")
STATES = ("covered", "supplementary", "unknown", "not-applicable", "conflict")


class SearchspaceSourceMismatch(ValueError):
    """The artifact or lookup is for a different source identity."""


class StaleSearchspaceIndex(ValueError):
    """The artifact does not correspond to this checkout's current sources."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_digest(root: Path, paths: Iterable[Path]) -> str:
    """Hash inputs in repository-relative POSIX path order on every host."""
    digest = hashlib.sha256()
    relative = {path: path.relative_to(root).as_posix() for path in paths}
    for path in sorted(relative, key=relative.__getitem__):
        digest.update(relative[path].encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def _source_paths() -> dict[str, str]:
    return {
        "matrix_path": MATRIX.as_posix(),
        "catalog_path": CATALOG.as_posix(),
        "skill_root": LIBRARY.as_posix(),
    }


def coordinate_inputs(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Fingerprint the matrix, registry and all files supplying Skill metadata."""
    root = root.resolve()
    matrix = root / MATRIX
    catalog = root / CATALOG
    sources = {**_source_paths(), "matrix_sha256": _sha256(matrix)}
    registry_bytes = catalog.read_bytes()
    sources["catalog_sha256"] = hashlib.sha256(registry_bytes).hexdigest()
    directories = skill_directories(root / LIBRARY)
    registry = json.loads(registry_bytes)["skills"]
    paths = {name: f"{registry[name]['path']}/SKILL.md" for name in directories}
    metadata = []
    for name, directory in directories.items():
        entrypoint = root / LIBRARY / paths[name]
        metadata.append(entrypoint)
        if _entry(directory, "metadata.json").is_file():
            metadata.append(entrypoint.with_name("metadata.json"))
    sources["metadata_sha256"] = input_digest(root, metadata)
    return sources, paths


@dataclass(frozen=True)
class SearchspaceEntry:
    path: str
    state: str
    coordinates: frozenset[tuple[str, str]]
    exclusion_reason: str | None = None

    def matches(self, resource: str, stage: str) -> bool:
        """Match a declared pair. Missing, supplementary and excluded pairs miss."""
        return (resource, stage) in self.coordinates


@dataclass(frozen=True)
class SearchspaceIndex:
    _skill_root: Path
    _entries: Mapping[str, SearchspaceEntry]

    def entry(self, *, skill_root: Path, skill_id: str, path: str) -> SearchspaceEntry:
        """Look up an identity qualified by its Skill root and relative SKILL.md path."""
        entry = self._entries.get(skill_id)
        if skill_root.resolve() != self._skill_root or entry is None or path != entry.path:
            raise SearchspaceSourceMismatch(f"Skill is outside this SearchSpace: {skill_id}")
        return entry


def _load_entry(row: object, path: str) -> SearchspaceEntry:
    if not isinstance(row, dict) or row.get("path") != path:
        raise StaleSearchspaceIndex(f"SearchSpace path disagrees with the Skill registry: {path}")
    state, pairs, reason = row.get("state"), row.get("coordinates"), row.get("exclusion_reason")
    if (
        state not in STATES or not isinstance(pairs, list)
        or bool(pairs) != (state == "covered")
        or (reason is not None and (not isinstance(reason, str) or not reason.strip()))
        or (reason is not None) != (state in ("not-applicable", "conflict"))
        or any(
            not isinstance(pair, list) or len(pair) != 2
            or pair[0] not in RESOURCES.values() or pair[1] not in STAGES
            for pair in pairs
        )
    ):
        raise ValueError(f"Invalid SearchSpace index entry: {path}")
    return SearchspaceEntry(path, state, frozenset(tuple(pair) for pair in pairs), reason)


def load_searchspace_index(checkout: Path) -> SearchspaceIndex:
    """Read and verify a generated index against its canonical checkout sources."""
    root = checkout.resolve()
    artifact = json.loads((root / INDEX).read_bytes())
    if not isinstance(artifact, dict) or type(artifact.get("schema_version")) is not int:
        raise ValueError("Invalid SearchSpace index")
    if artifact["schema_version"] != 1:
        raise ValueError("Unsupported SearchSpace index schema")
    source = artifact.get("source")
    if not isinstance(source, dict) or any(
        source.get(key) != path for key, path in _source_paths().items()
    ):
        raise SearchspaceSourceMismatch("SearchSpace index names different canonical sources")
    try:
        current, paths = coordinate_inputs(root)
    except (FileNotFoundError, ValueError) as exc:
        raise StaleSearchspaceIndex("SearchSpace sources are missing or invalid") from exc
    if source != current:
        raise StaleSearchspaceIndex("SearchSpace matrix, registry or Skill metadata changed")
    entries = artifact.get("skills")
    if not isinstance(entries, dict) or entries.keys() != paths.keys():
        raise StaleSearchspaceIndex("SearchSpace skills disagree with the Skill registry")
    loaded = {name: _load_entry(entries[name], path) for name, path in paths.items()}
    return SearchspaceIndex((root / LIBRARY).resolve(), MappingProxyType(loaded))
