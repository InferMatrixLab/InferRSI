from __future__ import annotations

import json
import posixpath
import re


class SkillIndexError(ValueError):
    pass


def words(cue: str) -> set[str]:
    return set(re.findall(r"\w+", cue.casefold()))


def lexical_score(cue: str, fields: list[tuple[int, object]]) -> int:
    tokens = words(cue)
    return sum(
        weight * sum(token in json.dumps(value, ensure_ascii=False).casefold() for token in tokens)
        for weight, value in fields
    )


def indexed_skill(record: dict, view: dict, content: dict[str, bytes]) -> tuple:
    """Validate the existing projection against this exact canonical bundle."""
    registry_path = "data/skill_library/skill-index.json"
    registry = json.loads(content[registry_path])
    name = record["skill_metadata"]["name"]
    entry = registry["skills"][name]
    prefix = f"data/skill_library/{entry['path']}/"
    core = prefix + "SKILL.md"
    expected_id = f"inferrsi.{entry['backend']}.skills.{name.replace('-', '_')}"
    if (
        registry["schema_version"] != 1
        or view["authority"] != "package"
        or record["id"] != view["id"]
        or record["id"] != expected_id
        or record["backend"] != entry["backend"]
        or record["skill_documents"] != {"original": core}
        or posixpath.basename(entry["path"]) != name
    ):
        raise SkillIndexError("Packaged skill identity disagrees with the registry")
    expected = {
        "src/inferrsi/" + path: digest
        for path, digest in view["resources"].items()
        if path.startswith(prefix) or path == registry_path
    }
    if record["source_files"] != expected:
        raise SkillIndexError("Stale packaged skill projection; rebuild with build_skill_index.py")

    required = [core]
    metadata = record["skill_metadata"]
    notices = [
        source["third_party_notices"]
        for source in metadata.get("sources", []) if "third_party_notices" in source
    ]
    for relative in [
        *metadata.get("references", []), *metadata.get("provenance_readsets", []), *notices,
    ]:
        path = posixpath.normpath(prefix + relative)
        if "\\" in relative or not path.startswith("data/skill_library/") or path not in content:
            raise SkillIndexError(f"Unavailable declared skill reference: {relative}")
        if path not in required:
            required.append(path)
    for path in sorted(content):
        if path.startswith(prefix) and re.search(
            r"(?:^|[-_])(?:LICENSE|NOTICES?)(?:\.[^.]+)?$",
            posixpath.basename(path), re.IGNORECASE,
        ) and path not in required:
            required.append(path)
    for resource in list(required):
        directory = posixpath.dirname(resource)
        while directory.startswith("data/skill_library/"):
            license_path = directory + "/LICENSE"
            if license_path in content and license_path not in required:
                required.append(license_path)
            directory = posixpath.dirname(directory)
    optional = sorted(
        path for path in content
        if path.startswith(prefix) and path not in required
    )
    return core, required, optional


def skill_score(cue: str, record: dict, core: bytes) -> int:
    return lexical_score(cue, [
        (4, record["title"]),
        (3, record["summary"]),
        (2, [record.get("tags", []), record.get("applicability", {})]),
        (1, core.decode("utf-8")),
    ])


def context_view(
    record: dict, view: dict, content: dict[str, bytes], cue: str, available: int
) -> tuple[dict | None, dict | None]:
    core, required, optional = indexed_skill(record, view, content)
    required_bytes = sum(len(content[path]) for path in required)
    if required_bytes > available:
        return None, {
            "ref": view["ref"], "reason": "context_limit",
            "required_bytes": required_bytes, "available_bytes": available,
        }

    resources, omissions = [], []
    used = 0

    def include(path: str) -> None:
        nonlocal used
        resources.append({
            "path": path, "sha256": view["resources"][path], "locator": "whole-resource",
            "role": "core" if path == core else "reference",
            "content": content[path].decode("utf-8"),
        })
        used += len(content[path])

    for path in required:
        include(path)
    candidates = []
    for path in optional:
        if (
            posixpath.basename(path) == "metadata.json"
            or posixpath.splitext(path)[1].lower() not in (".md", ".json", ".txt", ".csv")
        ):
            omissions.append({"path": path, "reason": "not_context_resource"})
            continue
        try:
            text = content[path].decode("utf-8")
        except UnicodeDecodeError:
            omissions.append({"path": path, "reason": "not_utf8"})
            continue
        score = lexical_score(cue, [(2, path.rpartition("/")[2]), (1, text)])
        if words(cue) and score == 0:
            omissions.append({"path": path, "reason": "not_relevant"})
            continue
        candidates.append((score, path))
    for _, path in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if used + len(content[path]) > available:
            omissions.append({"path": path, "reason": "context_limit"})
            continue
        include(path)
    return {
        "ref": view["ref"], "revision": view["revision"], "resources": resources,
        "content_bytes": used, "omissions": omissions,
        "sources": view["sources"], "attribution": view["attribution"],
        "limitations": view["limitations"] + [
            "Selected resources are complete files; this view is not a standalone Bundle.",
            "Follow omitted or other linked resources through the exact owner revision.",
        ],
    }, None
