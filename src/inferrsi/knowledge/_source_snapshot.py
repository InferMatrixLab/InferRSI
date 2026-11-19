from __future__ import annotations

import re
from typing import Any

# The build pin names the source corpus; installed bundle keys remain package-relative.
MANIFEST = "_provenance.json"
REPOSITORY = "https://github.com/InferMatrixLab/InferRSI"
LIBRARY = "src/inferrsi/knowledge/data/skill_library"
BUNDLE_LIBRARY = "data/skill_library"
REGISTRY = f"{LIBRARY}/skill-index.json"


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
