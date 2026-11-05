"""Resolve the fixed, local skill snapshot without changing catalog v1 callers."""

from __future__ import annotations

import json
import re

MANIFEST = "_provenance.json"
REPOSITORY = "https://github.com/InferMatrixLab/InferRSI"
REGISTRY = "src/inferrsi/data/skill_library/skill-index.json"


def parse_json(text: str) -> object:
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate packaged skill provenance field: {key}")
            value[key] = item
        return value

    return json.loads(text, object_pairs_hook=unique_object)


def validate_snapshot(snapshot: object) -> dict:
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"schema_version", "repository", "source_revision", "registry"}
        or type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1
        or snapshot["repository"] != REPOSITORY
        or not isinstance(snapshot["source_revision"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", snapshot["source_revision"])
        or not isinstance(snapshot["registry"], dict)
        or set(snapshot["registry"]) != {"path", "sha256"}
        or snapshot["registry"]["path"] != REGISTRY
        or not isinstance(snapshot["registry"]["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["registry"]["sha256"])
    ):
        raise ValueError("Invalid packaged skill provenance manifest")
    return snapshot


def resolve_record(record: dict, snapshot: dict) -> dict:
    """Expand only the supported v2 projection; never follow user-supplied locators."""
    snapshot = validate_snapshot(snapshot)
    if (type(record.get("schema_version")) is not int or record["schema_version"] != 2
            or record.get("index_type") != "packaged-skill"):
        raise ValueError("Unsupported packaged skill projection")
    documents = record.get("skill_documents")
    if (
        not isinstance(documents, dict) or set(documents) != {"original"}
        or not isinstance(documents["original"], str)
        or not documents["original"].startswith("data/skill_library/")
        or not documents["original"].endswith("/SKILL.md")
    ):
        raise ValueError("Invalid packaged skill source document")
    entry = "src/inferrsi/" + documents["original"]
    prefix = entry.removesuffix("SKILL.md")
    hashes = record.get("source_files")
    if (
        not isinstance(hashes, dict) or entry not in hashes
        or any(
            not isinstance(path, str) or not path.startswith(prefix)
            or "\\" in path or any(part in ("", ".", "..") for part in path.split("/"))
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for path, digest in hashes.items()
        )
    ):
        raise ValueError("Invalid packaged skill owner source hashes")
    expected = [{
        "type": "git", "snapshot": MANIFEST, "path": entry,
        "paths": sorted(hashes), "content_sha256": hashes[entry],
    }]
    if record.get("sources") != expected:
        raise ValueError("Packaged skill source disagrees with its owner hashes")
    hashes = dict(sorted({**hashes, REGISTRY: snapshot["registry"]["sha256"]}.items()))
    revision = snapshot["source_revision"]
    return {
        **record,
        "schema_version": 1,
        "sources": [{
            "type": "git", "url": f"{REPOSITORY}/blob/{revision}/{entry}",
            "commit": revision, "paths": list(hashes), "content_sha256": hashes[entry],
        }],
        "source_files": hashes,
    }
