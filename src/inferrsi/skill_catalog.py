from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import BinaryIO

try:
    import yaml
except ImportError as exc:  # The base install stays PyYAML-free by contract.
    raise ValueError(
        "Reading checkout skills requires the 'skills' extra (PyYAML); install it "
        "from your InferRSI checkout, replacing the placeholder path: "
        "python -m pip install '<inferrsi-checkout>[skills]'"
    ) from exc

from .catalog import BACKENDS


def _frontmatter(stream: BinaryIO) -> dict:
    if stream.readline().strip() != b"---":
        raise ValueError("SKILL.md must start with YAML frontmatter")
    lines = []
    for line in stream:
        if line.strip() == b"---":
            break
        lines.append(line)
    else:
        raise ValueError("Unclosed SKILL.md frontmatter")
    try:
        record = yaml.safe_load(b"".join(lines).decode("utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid skill YAML: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError("Skill frontmatter must be a mapping")
    return record


def _skill_name(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError(f"Invalid skill name: {name}")


def _directory(root: Path, name: str, relative: str) -> Path:
    _skill_name(name)
    path = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in relative.split("/"))
    ):
        raise ValueError(f"Skill path must be a relative POSIX path: {relative}")
    directory = (root / relative).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("Skill must be inside the selected root")
    if path.name != name or directory.name != name:
        raise ValueError(f"Skill path basename disagrees with its name: {name}")
    if not _entry(directory, "SKILL.md").is_file():
        raise ValueError(f"Unknown skill: {name}")
    return directory


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"Duplicate skill index field: {key}")
        record[key] = value
    return record


def _indexed_directories(root: Path) -> dict[str, Path] | None:
    index = _entry(root, "skill-index.json")
    if not index.exists():
        return None
    record = json.loads(index.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)
    if (
        not isinstance(record, dict)
        or type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
        or not isinstance(record.get("skills"), dict)
    ):
        raise ValueError("Skill index requires schema_version 1 and a skills mapping")
    directories = {}
    paths = set()
    for name, entry in sorted(record["skills"].items()):
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("backend"), str)
            or entry["backend"] not in (*BACKENDS, "common")
        ):
            raise ValueError(f"Skill index requires a path and supported backend: {name}")
        directory = _directory(root, name, entry["path"])
        if directory in paths:
            raise ValueError(f"Duplicate skill index path: {entry['path']}")
        directories[name] = directory
        paths.add(directory)
    return directories


def skill_directories(root: Path) -> dict[str, Path]:
    """Resolve registered skill locations without reading instruction bodies."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Skill root is not a directory: {root}")
    indexed = _indexed_directories(root)
    if indexed is not None:
        return indexed
    return {
        path.parent.name: _directory(root, path.parent.name, path.parent.name)
        for path in sorted(root.glob("*/SKILL.md"))
    }


def skill_directory(root: Path, name: str) -> Path:
    """Resolve one named skill in an indexed library or a legacy flat root."""
    _skill_name(name)
    root = root.resolve()
    indexed = _indexed_directories(root)
    if indexed is None:
        return _directory(root, name, name)
    if name not in indexed:
        raise ValueError(f"Unknown skill: {name}")
    return indexed[name]


def _entry(directory: Path, filename: str) -> Path:
    # The resolved entry file must stay inside the selected skill directory;
    # reject symlinks that point outside it.
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory):
        raise ValueError(f"Skill {filename} must stay inside the selected skill: {directory.name}")
    return path


def _sidecar(directory: Path) -> dict | None:
    # metadata.json shares the directory-boundary loading path with SKILL.md.
    path = _entry(directory, "metadata.json")
    if not path.is_file():
        return None
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"Skill metadata must be a mapping: {directory.name}")
    return metadata


def _references(metadata: dict, name: str) -> list[str]:
    # references must be a list of strings; a string value would degrade
    # membership testing to substring matching.
    references = metadata.get("references", [])
    if not isinstance(references, list) or any(not isinstance(item, str) for item in references):
        raise ValueError(f"Skill references must be a string list: {name}")
    return references


def _strings(record: dict, key: str, name: str) -> None:
    """A declared string list must be strings; [] is a deliberate empty value."""
    if key not in record:
        return
    listed = record[key]
    if not isinstance(listed, list) or any(
        not isinstance(item, str) or not item.strip() for item in listed
    ):
        raise ValueError(f"Skill {key} must be a list of non-empty strings: {name}")


def _applicability(record: dict, name: str) -> None:
    """Conditions a procedure assumes. Descriptive only; never a validation claim."""
    if "applicability" not in record:
        return
    declared = record["applicability"]
    if not isinstance(declared, dict):
        raise ValueError(f"Skill applicability must be a mapping: {name}")
    for key, value in declared.items():
        if isinstance(value, str):
            if not value.strip():
                raise ValueError(f"Skill applicability.{key} is empty: {name}")
        elif isinstance(value, list):
            if not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(
                    f"Skill applicability.{key} must be a non-empty string list: {name}"
                )
        else:
            raise ValueError(f"Skill applicability.{key} must be a string or string list: {name}")


def _effective(directory: Path) -> dict:
    # Read bytes line by line; parse only the frontmatter, never decode the body.
    with _entry(directory, "SKILL.md").open("rb") as stream:
        record = _frontmatter(stream)
    for key in ("name", "description"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Skill requires {key}: {directory.name}")
    if record["name"] != directory.name:
        raise ValueError(f"Skill name disagrees with directory: {directory.name}")
    metadata = _sidecar(directory)
    if metadata is not None:
        for key in record.keys() & metadata.keys():
            if record[key] != metadata[key]:
                raise ValueError(f"Conflicting skill metadata field {key}: {directory.name}")
        if metadata.get("profile") == "local-skill-v1":
            if any(key in metadata for key in ("name", "description")):
                raise ValueError("Local skill name and description belong in SKILL.md")
            if set(record) != {"name", "description"}:
                raise ValueError("Local skill structured fields belong in metadata.json")
        # Only sidecars declare these fields, and JSON cannot express a container
        # cycle; validating the sidecar leaves the bundle normalizer free to report
        # a cyclic legacy frontmatter value against the field that contains it.
        _strings(metadata, "recommendations", directory.name)
        _applicability(metadata, directory.name)
        if "searchspace_not_applicable" in metadata:
            reason = metadata["searchspace_not_applicable"]
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(
                    f"Skill searchspace_not_applicable requires a reason: {directory.name}"
                )
        record.update(metadata)
    _references(record, directory.name)
    if "status" in record and not isinstance(record["status"], str):
        raise ValueError(f"Skill status must be a string: {directory.name}")
    if "tags" in record and (
        not isinstance(record["tags"], list)
        or any(not isinstance(tag, str) for tag in record["tags"])
    ):
        raise ValueError(f"Skill tags must be a string list: {directory.name}")
    return record


def _metadata(directory: Path) -> dict:
    record = _effective(directory)
    return {key: record[key] for key in ("name", "description", "status", "tags") if key in record}


def skill_metadata(root: Path, name: str) -> dict:
    """Effective legacy frontmatter plus sidecar fields, after conflict checks."""
    return _effective(skill_directory(root, name))


def skill_records(root: Path) -> list[dict]:
    """Project metadata only; this projection is not an authoritative matrix."""
    return [_metadata(directory) for directory in skill_directories(root).values()]


def get_skill(root: Path, name: str) -> dict:
    """Read selected metadata and resource names, never resource contents."""
    directory = skill_directory(root, name)
    record = _metadata(directory)
    record["resources"] = [
        path.relative_to(directory).as_posix()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "SKILL.md"
    ]
    return record


def skill_instructions(root: Path, name: str) -> str:
    """Load selected instructions. Reading does not authorize their commands."""
    directory = skill_directory(root, name)
    _metadata(directory)
    with _entry(directory, "SKILL.md").open("rb") as stream:
        _frontmatter(stream)
        return stream.read().decode("utf-8").lstrip("\r\n")


def skill_resource(root: Path, name: str, resource: str) -> Path:
    """Resolve one explicitly selected resource inside its skill directory."""
    directory = skill_directory(root, name)
    path = (directory / resource).resolve()
    if not path.is_relative_to(directory) or path == directory / "SKILL.md":
        raise ValueError("Resource must be inside the selected skill; use show for instructions")
    if not path.is_file():
        raise ValueError(f"Unknown skill resource: {resource}")
    return path


def skill_reference(root: Path, name: str, reference: str) -> Path:
    """Resolve a declared checkout reference without escaping the skills root."""
    directory = skill_directory(root, name)
    if reference not in _references(_effective(directory), directory.name):
        raise ValueError(f"Undeclared skill reference: {reference}")
    if "\\" in reference or Path(reference).is_absolute():
        raise ValueError("Reference must use a relative POSIX path")
    path = (directory / reference).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Reference must stay inside the skills root")
    if not path.is_file():
        raise ValueError(f"Missing skill reference: {reference}")
    return path
