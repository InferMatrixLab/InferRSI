"""Read a matrix coordinate snapshot for an InferRSI source checkout."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ._knowledge_errors import MissingSkillsExtra
from .skill_catalog import _effective, _entry, skill_directories

LIBRARY = Path("src/inferrsi/knowledge/data/skill_library")
CATALOG = LIBRARY / "skill-index.json"
MATRIX = Path("docs/searchspace-matrix.md")
INDEX = Path("docs/searchspace-index.json")

RESOURCES = {"1": "Accelerator", "2": "RAM/Host", "3": "SSD", "4": "Network", "5": "OS"}
STAGES = ("Observe", "Profile", "Diagnose", "Configure", "Optimize", "Verify")
STATES = ("covered", "supplementary", "unknown", "not-applicable", "conflict")


# The five SearchSpace resource layers are a maintained contract. A renamed
# heading fails generation instead of silently relabelling coverage.
LAYERS = {
    "1": "Graphics Card / Accelerator",
    "2": "RAM / Host Memory",
    "3": "SSD / Storage",
    "4": "Communication Card / Network",
    "5": "OS / System",
}
HEADING = re.compile(r"^## ([1-5]) · (.+)$")
LINK = re.compile(r"\(([^()\s]*/skill_library/[^()\s]+/SKILL\.md)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
CANDIDATE_LINK = r"\[(?P<label>[^\[\]\n]+)\]\((?P<target>[^()\s]+)\)"
CANDIDATE_TOKEN = re.compile(rf"{CANDIDATE_LINK}|`[^`\n]+`|[^\s]")

# An owner states this for a dimension that genuinely does not apply, so the
# view can tell it apart from a field nobody has analyzed yet.
NOT_APPLICABLE = "not-applicable"


def cells(line):
    body = line.strip()[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [part.strip() for part in body.split("|")]


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


def references(root, path, registered, *, canonical_paths=None):
    """Skill ids a document mentions, plus links whose target does not exist.

    Each mention keeps the heading, the first cell and, when the heading is a
    supplementary ``| Resource | Stage |`` table, the resource cell as well.
    Pass canonical paths when mentions must come from the registered source.
    """
    found, dead = {}, []
    headers, heading = {}, None
    linked_skills = None if canonical_paths is None else {
        f"../{LIBRARY.as_posix()}/{canonical_path}": name
        for name, canonical_path in canonical_paths.items()
    }
    for line in (root / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line.rstrip()
            continue
        if not heading or not line.lstrip().startswith("|"):
            continue
        parts = cells(line)
        if all(set(part) <= set("-: ") for part in parts):
            continue
        if parts[0] in ("Resource", "Lifecycle step"):
            headers[heading] = parts[0] == "Resource"
            continue
        joined = " | ".join(parts)
        mentions = {name for name in registered if f"`{name}`" in joined}
        for target in LINK.findall(joined):
            if linked_skills is not None:
                if target in linked_skills:
                    mentions.add(linked_skills[target])
                continue
            resolved = (root / "docs" / target).resolve()
            if not resolved.is_file():
                dead.append((str(path), target))
                continue
            mentions.add(resolved.parent.name)
        resource = parts[0] if headers.get(heading) else None
        for name in mentions:
            found.setdefault(name, []).append((heading, parts[0], resource))
    return found, dead


def _strip_bold(text):
    return BOLD.sub(r"\1", text)


def _split(text):
    return [token.strip() for token in _strip_bold(text).split(" / ") if token.strip()]


# Layer labels as the matrices spell them. Compounding a label such as
# "Accelerator / RAM / Host" must be matched by whole names, longest first:
# "RAM / Host" itself contains the separator, and bare "RAM"/"SSD" occur in
# compound cells such as "RAM / Accelerator / SSD".
LAYER_LABELS = {
    "Graphics Card / Accelerator": "1",
    "Communication Card / Network": "4",
    "RAM / Host Memory": "2",
    "Accelerator": "1",
    "RAM / Host": "2",
    "SSD / Storage": "3",
    "Communication / Network": "4",
    "OS / System": "5",
    "Host": "2",
    "RAM": "2",
    "SSD": "3",
}


def _layer_numbers(text):
    """Resource layers named by a cell, longest label first."""
    remaining = _strip_bold(text)
    found = []
    for label in sorted(LAYER_LABELS, key=len, reverse=True):
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(label)}(?![A-Za-z])")
        if not pattern.search(remaining):
            continue
        number = LAYER_LABELS[label]
        if number not in found:
            found.append(number)
        remaining = pattern.sub(" ", remaining)
    return found


def layer_refs(found):
    """Resource layer -> (stages, supplementary headings), in document order.

    A numbered layer section states coverage. A supplementary ``Resource``
    table states source-derived guidance for one skill; it is kept distinct so
    the view never reports a guidance mapping as a missing layer or vice versa.
    """
    layers = {}
    for heading, stage, resource in found:
        match = HEADING.match(heading)
        if match:
            number, name = match.groups()
            if name != LAYERS[number]:
                raise ValueError(f"SearchSpace layer {number} renamed: {name}")
            stages = layers.setdefault(number, ([], []))[0]
            for token in _split(stage):
                if token not in stages:
                    stages.append(token)
            continue
        if resource is None:
            continue
        for number in _layer_numbers(resource):
            _, sections = layers.setdefault(number, ([], []))
            if heading[3:] not in sections:
                sections.append(heading[3:])
    return {number: (stages, sections) for number, (stages, sections) in layers.items()}


def _candidate_ids(cell, paths):
    """Read candidate declarations at the head of comma/semicolon-separated entries."""
    first, depth = True, 0
    for token in CANDIDATE_TOKEN.finditer(cell):
        value = token[0]
        if value == "(":
            depth += 1
        elif depth:
            if value == ")":
                depth -= 1
        elif value in (",", ";"):
            first = True
        elif first:
            first = False
            if value.startswith("`") and value[1:-1] in paths:
                yield value[1:-1]
            elif (name := token["label"]) in paths:
                if token["target"] == f"../{LIBRARY.as_posix()}/{paths[name]}":
                    yield name


def _coordinate_pairs(root, paths):
    """Project only the contiguous lifecycle table under each numbered layer."""
    pairs, seen = defaultdict(set), set()
    layer, header = None, None
    for line in (root / MATRIX).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            match = HEADING.match(line.rstrip())
            layer, header = (match[1] if match else None), None
            if match and match[2] != LAYERS[layer]:
                raise ValueError(f"SearchSpace layer {layer} renamed: {match[2]}")
        if not layer or not line.lstrip().startswith("|"):
            header = None
            continue
        row = cells(line)
        if row[0] == "Lifecycle step":
            if row.count("Candidate Skills") != 1 or layer in seen:
                raise ValueError(f"Invalid SearchSpace detail table header in layer {layer}")
            header = (len(row), row.index("Candidate Skills"))
            seen.add(layer)
        elif header and not all(set(part) <= set("-: ") for part in row):
            stages = _split(row[0])
            if len(row) != header[0] or not stages or any(stage not in STAGES for stage in stages):
                raise ValueError(f"Invalid SearchSpace detail table row in layer {layer}: {row[0]}")
            for name in _candidate_ids(row[header[1]], paths):
                pairs[name].update((layer, stage) for stage in stages)
    if seen != LAYERS.keys():
        raise ValueError("SearchSpace matrix is missing a numbered detail table")
    return pairs


def layer_state(row):
    if row["layer_exclusion"]:
        return "conflict" if row["layers"] else NOT_APPLICABLE
    if not row["layers"]:
        return "unknown"
    if all(
        not stages and sections for stages, sections in row["layers"].values()
    ):
        return "supplementary"
    return "covered"


def project_coordinate_entries(root: Path, paths: Mapping[str, str]) -> dict[str, dict]:
    """Project canonical rows for generation and verification."""
    pairs = _coordinate_pairs(root, paths)
    mentions, _ = references(root, MATRIX, paths, canonical_paths=paths)
    rows = {}
    for name, path in paths.items():
        guidance = [ref for ref in mentions.get(name, []) if not HEADING.match(ref[0])]
        layers = layer_refs(guidance)
        coordinates = sorted(pairs.get(name, ()))
        for layer, stage in coordinates:
            layers.setdefault(layer, ([], []))[0].append(stage)
        directory = (root / LIBRARY / Path(path).parent).resolve()
        reason = _effective(directory).get("searchspace_not_applicable")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError(f"Skill searchspace_not_applicable requires a reason: {name}")
        state = layer_state({"layers": layers, "layer_exclusion": reason})
        row = {
            "path": path,
            "state": state,
            "coordinates": [[RESOURCES[layer], stage] for layer, stage in coordinates]
            if state == "covered" else [],
        }
        if reason:
            row["exclusion_reason"] = reason

        rows[name] = row
    return rows


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
    matrix_sha256: str

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
    try:
        expected = project_coordinate_entries(root, paths)
        still_current = (current, paths) == coordinate_inputs(root)
    except MissingSkillsExtra:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise StaleSearchspaceIndex("SearchSpace sources are missing or invalid") from exc
    if not still_current:
        raise StaleSearchspaceIndex("SearchSpace sources changed during verification")
    if entries != expected:
        raise StaleSearchspaceIndex("SearchSpace entries disagree with canonical sources")
    return SearchspaceIndex(
        (root / LIBRARY).resolve(), MappingProxyType(loaded), current["matrix_sha256"],
    )


@dataclass(frozen=True)
class SearchspaceCoordinate:
    """One query coordinate bound to a verified checkout index."""

    index: SearchspaceIndex
    resource: str
    stage: str

    @property
    def skill_root(self) -> Path:
        return self.index._skill_root

    def matches(self, *, skill_root: Path, skill_id: str, path: str) -> bool:
        try:
            entry = self.index.entry(skill_root=skill_root, skill_id=skill_id, path=path)
        except SearchspaceSourceMismatch:
            return False
        return entry.matches(self.resource, self.stage)

    def view(self) -> dict:
        return {
            "resource": self.resource,
            "stage": self.stage,
            "source": {"matrix_path": MATRIX.as_posix(), "matrix_sha256": self.index.matrix_sha256},
        }


def load_searchspace_coordinate(
    skill_root: Path | None, resource: str, stage: str,
) -> SearchspaceCoordinate:
    """Resolve an explicit Find filter from the checkout that owns its Skills."""
    if resource not in RESOURCES.values() or stage not in STAGES:
        raise ValueError(
            f"--searchspace-coordinate requires RESOURCE ({', '.join(RESOURCES.values())}) "
            f"and STAGE ({', '.join(STAGES)})"
        )
    root = skill_root.resolve() if skill_root is not None else None
    if root is None or root.parts[-len(LIBRARY.parts):] != LIBRARY.parts:
        raise ValueError(
            "--searchspace-coordinate requires an explicit --skill-root pointing to "
            f"{LIBRARY.as_posix()} in a matching InferRSI checkout"
        )
    checkout = root.parents[len(LIBRARY.parts) - 1]
    regenerate = "Run `python tools/build_skill_coverage.py --searchspace-index` in that checkout."
    try:
        index = load_searchspace_index(checkout)
    except MissingSkillsExtra:
        raise
    except FileNotFoundError as exc:
        raise ValueError(
            f"SearchSpace index unavailable at {checkout / INDEX}. {regenerate}"
        ) from exc
    except SearchspaceSourceMismatch as exc:
        raise ValueError(f"Foreign SearchSpace index: {exc}. {regenerate}") from exc
    except StaleSearchspaceIndex as exc:
        raise ValueError(f"Stale SearchSpace index: {exc}. {regenerate}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid SearchSpace index: {exc}. {regenerate}") from exc
    return SearchspaceCoordinate(index, resource, stage)
