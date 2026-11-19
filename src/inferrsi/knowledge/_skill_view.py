"""Expand catalog views from the packaged library without Git or optional YAML."""

import hashlib
import json
import re
from pathlib import PurePosixPath

from . import _source_snapshot

REPOSITORY = _source_snapshot.REPOSITORY
COMPILED = "_compiled"
INPUTS = "inputs.json"


DEFAULT_RECOMMENDATIONS = [
    "Read the pinned SKILL.md and its prerequisites before choosing this procedure.",
    "Read the packaged references and owner-local cases alongside the procedure.",
]


def recommendations(metadata: dict) -> list[str]:
    """Owner-supplied procedure advice, or generic navigation when absent.

    A declared empty list means the owner states there is no procedure-specific
    advice; it is not the same as an absent field and does not fall back.
    """
    if "recommendations" in metadata:
        return list(metadata["recommendations"])
    return list(DEFAULT_RECOMMENDATIONS)


def skill_views(root, *, file_fingerprints=True):
    """The only compiled inputs are YAML headers and immutable source hashes."""
    built = root.joinpath(COMPILED)
    snapshot = json.loads(built.joinpath(_source_snapshot.MANIFEST).read_bytes())
    revision, registry_hash = _source_snapshot._snapshot(snapshot)
    raw = root.joinpath("skill-index.json").read_bytes()
    if file_fingerprints and hashlib.sha256(raw).hexdigest() != registry_hash:
        raise ValueError("Skill registry disagrees with its pinned snapshot")
    registry = json.loads(raw)
    if registry.get("schema_version") != 1 or not isinstance(registry.get("skills"), dict):
        raise ValueError("Invalid packaged skill registry")
    entries = registry["skills"]
    inputs = json.loads(built.joinpath(INPUTS).read_bytes())
    if not isinstance(inputs, dict) or entries.keys() != inputs.keys():
        raise ValueError("Compiled skill IDs disagree with registry")
    for name, registration in entries.items():
        relative = registration["path"]
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or path.name != name or "\\" in relative:
            raise ValueError(f"Invalid registered skill path: {relative}")
        directory = f"{_source_snapshot.LIBRARY}/{relative}"
        owner = root.joinpath(*path.parts)
        data = inputs[name]
        if (not isinstance(data, dict) or set(data) != {"header", "files"}
                or not isinstance(data["header"], dict) or not isinstance(data["files"], dict)):
            raise ValueError(f"Invalid compiled inputs for {name}")
        metadata = dict(data["header"])
        if metadata.get("name") != name or not metadata.get("description"):
            raise ValueError(f"Invalid compiled header for {name}")
        fingerprints = data["files"]
        if "SKILL.md" not in fingerprints:
            raise ValueError(f"Missing entry fingerprint for {name}")
        for key, digest in fingerprints.items():
            if (not key or key.startswith("/") or "\\" in key
                    or any(p in {"", ".", ".."} for p in key.split("/"))
                    or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                raise ValueError(f"Invalid source fingerprint for {name}: {key}")
        sidecar = owner.joinpath("metadata.json")
        if sidecar.is_file() != ("metadata.json" in fingerprints):
            raise ValueError(f"Skill metadata and snapshot disagree for {name}")
        if sidecar.is_file():
            raw = sidecar.read_bytes()
            if (file_fingerprints
                    and hashlib.sha256(raw).hexdigest() != fingerprints["metadata.json"]):
                raise ValueError(f"Stale skill metadata for {name}")
            metadata.update(json.loads(raw))
        backend = registration["backend"]
        state = metadata.get("status", "unspecified")
        entry = directory + "/SKILL.md"
        hashes = {}
        if file_fingerprints:
            hashes = dict(sorted({
                _source_snapshot.REGISTRY: registry_hash,
                **{f"{directory}/{k}": v for k, v in fingerprints.items()},
            }.items()))
        paths = list(hashes)
        yield {
            "schema_version": 1,
            "id": f"inferrsi.{backend}.skills.{name.replace('-', '_')}",
            "title": name,
            "repo": "inferrsi",
            "tier": "contribution",
            "backend": backend,
            "component": "skills",
            "scenario": "skills.discovery",
            "status": "imported",
            "summary": metadata["description"],
            "tags": metadata.get("tags", []),
            "origin": metadata.get("origin", ["unknown"]),
            "sources": ([{
                "type": "git",
                "url": f"{REPOSITORY}/blob/{revision}/{entry}",
                "commit": revision,
                "paths": paths,
                "content_sha256": hashes[entry],
            }] if file_fingerprints else [{
                "type": "git", "commit": revision, "url": f"{REPOSITORY}/tree/{revision}",
            }]),
            "index_type": "packaged-skill",
            "skill_documents": {
                "original": f"data/skill_library/{relative}/SKILL.md",
            },
            "checkout_ref": f"checkout:{name}",
            "source_files": hashes,
            "skill_metadata": metadata,
            "applicability": metadata.get("applicability", {}),
            "recommendations": recommendations(metadata),
            "limitations": [
                "This generated abstract points to the complete packaged skill; "
                "external evidence and upstream repositories remain source links.",
                "The imported status describes this index, not the original skill; "
                f"its declared status is {state}.",
                "Reading or indexing does not authorize execution, validate efficacy, "
                "promote a candidate or grant a license.",
                "The backend categorizes the procedure's hardware dependency; it does not "
                "certify compatibility, and skills.discovery is a discovery scenario.",
                *metadata.get("limitations", []),
            ],
            "verification": {"locally_verified": False, "evidence_level": "guidance"},
        }
