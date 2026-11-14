from __future__ import annotations

import re
from typing import Any

# One shared snapshot keeps the repository-wide source revision and registry digest out of
# per-owner records, so a one-owner edit regenerates only that owner's record.
# LIBRARY is the repository path of the corpus at the pinned source_revision.
# After the K02 move and the explicit re-pin, this agrees with the current checkout
# path src/inferrsi/knowledge/data/skill_library. skill_documents.original and
# wheel bundle keys stay at the package-relative prefix data/skill_library/.
MANIFEST = "_provenance.json"
REPOSITORY = "https://github.com/InferMatrixLab/InferRSI"
LIBRARY = "src/inferrsi/knowledge/data/skill_library"
BUNDLE_LIBRARY = "data/skill_library"
REGISTRY = f"{LIBRARY}/skill-index.json"
STORED_SCHEMA = 2


def source_entry(original: str) -> str:
    """Return the git path of a skill entry at the pinned source revision.

    ``skill_documents.original`` is the package-relative bundle key
    ``data/skill_library/<category>/<name>/SKILL.md``, not the checkout path.
    """
    prefix = BUNDLE_LIBRARY + "/"
    if not isinstance(original, str) or not original.startswith(prefix):
        raise ValueError(f"Invalid skill document path: {original!r}")
    return f"{LIBRARY}/{original[len(prefix):]}"


def manifest(revision: str, registry_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": REPOSITORY,
        "source_revision": revision,
        "registry": {"path": REGISTRY, "sha256": registry_sha256},
    }


def _snapshot(value: Any) -> tuple[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "repository", "source_revision", "registry"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["repository"] != REPOSITORY
        or not isinstance(value["source_revision"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", value["source_revision"])
    ):
        raise ValueError("Invalid knowledge source snapshot")
    registry = value["registry"]
    if (
        not isinstance(registry, dict)
        or set(registry) != {"path", "sha256"}
        or registry["path"] != REGISTRY
        or not isinstance(registry["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", registry["sha256"])
    ):
        raise ValueError("Invalid knowledge source snapshot registry")
    return value["source_revision"], registry["sha256"]


def compact(record: dict[str, Any]) -> dict[str, Any]:
    """Store a generated schema-v1 record without its snapshot-wide fields."""
    stored = {key: value for key, value in record.items() if key != "sources"}
    stored["schema_version"] = STORED_SCHEMA
    stored["source_files"] = {
        path: digest for path, digest in record["source_files"].items() if path != REGISTRY
    }
    return stored


def resolve(stored: dict[str, Any], snapshot: Any) -> dict[str, Any]:
    """Rebuild the public schema-v1 record from a stored record and the shared snapshot."""
    revision, registry_sha256 = _snapshot(snapshot)
    if stored.get("schema_version") != STORED_SCHEMA or "sources" in stored:
        raise ValueError("Stored skill record is not a schema-v2 projection")
    files = stored.get("source_files")
    documents = stored.get("skill_documents")
    if (
        not isinstance(files, dict) or REGISTRY in files
        or not isinstance(documents, dict) or not isinstance(documents.get("original"), str)
    ):
        raise ValueError(f"Invalid stored skill record: {stored.get('id')}")
    entry = source_entry(documents["original"])
    if entry not in files:
        raise ValueError(f"Stored skill record lacks its entry hash: {stored.get('id')}")
    hashes = dict(sorted({**files, REGISTRY: registry_sha256}.items()))
    source = {
        "type": "git",
        "url": f"{REPOSITORY}/blob/{revision}/{entry}",
        "commit": revision,
        "paths": list(hashes),
        "content_sha256": hashes[entry],
    }
    record = {}
    for key, value in stored.items():
        record[key] = 1 if key == "schema_version" else value
        if key == "origin":
            record["sources"] = [source]
    if "sources" not in record:
        raise ValueError(f"Stored skill record lacks origin: {stored.get('id')}")
    record["source_files"] = hashes
    return record
