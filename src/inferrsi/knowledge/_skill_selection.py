from __future__ import annotations

import hashlib
import json
import posixpath
import re

from ._source_snapshot import source_entry
from .catalog import _skill_search_source, packaged_skill_id

FIND_RELEVANCE = "find-lexical-v1"
TASK_STOP_WORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"})

_BACKEND_TERMS = {
    "cuda": {"cuda", "nvidia"},
    "rocm": {"rocm", "amd"},
    "ascend": {"ascend", "cann"},
    "musa": {"musa", "mthreads"},
    "mlx": {"mlx"},
    "cpu": {"cpu"},
}


class SkillIndexError(ValueError):
    pass


def validate_relevance_method(method: str | None) -> None:
    if method not in (None, FIND_RELEVANCE):
        raise ValueError(
            f"Unsupported relevance_method {method!r}. "
            f"Omit the method or use {FIND_RELEVANCE!r} with one query or relevance cue."
        )


def named_backends(terms: set[str]) -> set[str]:
    return {backend for backend, names in _BACKEND_TERMS.items() if names & terms}


def indexed_skill(
    record: dict, view: dict, content: dict[str, bytes],
) -> tuple[str, list[str], list[str]]:
    """Validate the existing projection against this exact canonical bundle."""
    registry_path = "data/skill_library/skill-index.json"
    registry = json.loads(content[registry_path])
    name = record["skill_metadata"]["name"]
    entry = registry["skills"][name]
    prefix = f"data/skill_library/{entry['path']}/"
    core = prefix + "SKILL.md"
    expected_id = packaged_skill_id(name, entry["backend"])
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
        source_entry(path): digest
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


def record_context(record: dict, view: dict, content: dict[str, bytes], available: int) -> tuple:
    """Deliver whole files, including the declared closure of a Case."""
    paths = {view["entrypoint"]: "record" if view["kind"] == "knowledge" else "core"}
    omissions = [
        {"path": path, "reason": "linked_document"}
        for path in dict.fromkeys(record.get("skill_documents", {}).values())
    ]
    if view["kind"] == "case":
        for path in view.get("required_resources", ()):
            paths.setdefault(path, "reference")
        # The checkout Bundle exposes the case card both as case.json and, when
        # declared, under its authored filename. Deliver the named copy once.
        if "case.json" in paths and any(
            path != "case.json" and path.endswith(".json")
            and content[path] == content["case.json"] for path in paths
        ):
            del paths["case.json"]
            omissions.append({"path": "case.json", "reason": "duplicate_resource"})
    required_bytes = sum(len(content[path]) for path in paths)
    if required_bytes > available:
        return None, {"ref": view["ref"], "reason": "context_limit",
                      "required_bytes": required_bytes, "available_bytes": available}
    return {
        "ref": view["ref"], "revision": view["revision"], "content_bytes": required_bytes,
        "resources": [
            {"path": path, "sha256": view["resources"][path], "role": role,
             "locator": "whole-resource", "content": content[path].decode("utf-8")}
            for path, role in paths.items()
        ],
        "omissions": omissions,
        "sources": view["sources"], "attribution": view["attribution"],
        "limitations": view["limitations"],
    }, None


def skill_procedure(path: str, raw: bytes) -> tuple[bytes, dict]:
    """Select the instruction bytes of a single-file skill for a budgeted context."""
    if posixpath.basename(path) != "SKILL.md":
        return raw, {}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, {}  # The caller handles non-UTF8 optional resources.
    procedure, metadata = _skill_search_source(text)
    if metadata is None:
        return raw, {}
    data = procedure.encode("utf-8")
    # The projection removes one contiguous block. These half-open UTF-8 byte
    # ranges reconstruct the delivered bytes from the exact pinned file.
    start = next((i for i, (a, b) in enumerate(zip(raw, data)) if a != b), len(data))
    end = start + len(raw) - len(data)
    return data, {"locator": "skill-procedure", "source_byte_ranges": [[0, start], [end, len(raw)]]}


def context_view(
    index: tuple[str, list[str], list[str]], view: dict, content: dict[str, bytes],
    cue: str | None, available: int,
) -> tuple[dict | None, dict | None]:
    core, required, optional = index
    selected = {path: skill_procedure(path, content[path]) for path in [*required, *optional]}
    required_bytes = sum(len(selected[path][0]) for path in required)
    if required_bytes > available:
        return None, {
            "ref": view["ref"], "reason": "context_limit",
            "required_bytes": required_bytes, "available_bytes": available,
        }

    resources, omissions = [], []
    used = 0

    def include(path: str) -> None:
        nonlocal used
        data, locator = selected[path]
        resource = {
            "path": path, "sha256": view["resources"][path], "locator": "whole-resource",
            "role": "core" if path == core else "reference",
            "content": data.decode("utf-8"),
        }
        if locator:
            resource.update(**locator, source_sha256=view["resources"][path],
                            sha256=hashlib.sha256(data).hexdigest())
        resources.append(resource)
        used += len(data)

    for path in required:
        include(path)
    candidates = {}
    for path in optional:
        if (
            posixpath.basename(path) == "metadata.json"
            or posixpath.splitext(path)[1].lower() not in (".md", ".json", ".txt", ".csv")
        ):
            omissions.append({"path": path, "reason": "not_context_resource"})
            continue
        try:
            candidates[path] = selected[path][0].decode("utf-8")
        except UnicodeDecodeError:
            omissions.append({"path": path, "reason": "not_utf8"})
            continue
    paths = list(candidates)
    if cue and candidates:
        from .knowledge_find import Corpus, Document, rank

        documents = [
            Document(
                identity=path, kind="record", state="unspecified", path=path,
                title=posixpath.basename(path), summary="",
                fields={"title": posixpath.basename(path), "body": text},
            )
            for path, text in candidates.items()
        ]
        _, _, ranked = rank(cue, Corpus(documents))
        paths = [documents[index].identity for _, _, index, _ in ranked]
        matched = set(paths)
        omissions.extend(
            {"path": path, "reason": "not_relevant"}
            for path in candidates if path not in matched
        )
    for path in paths:
        if used + len(selected[path][0]) > available:
            omissions.append({"path": path, "reason": "context_limit"})
            continue
        include(path)
    return {
        "ref": view["ref"], "revision": view["revision"], "resources": resources,
        "content_bytes": used, "omissions": omissions,
        "sources": view["sources"], "attribution": view["attribution"],
        "limitations": view["limitations"] + [
            "For a skill-procedure, concatenate the reported half-open byte ranges of its source.",
            "Follow omitted or other linked resources through the exact owner revision.",
        ],
    }, None
