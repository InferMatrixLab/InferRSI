from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shutil
import sqlite3
from collections.abc import Container
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from ._knowledge_errors import MissingSkillsExtra
from ._skill_selection import (
    FIND_RELEVANCE,
    INLINE_PAGE_BYTES,
    candidate_contexts,
    context_view,
    declared_skill_references,
    indexed_skill,
    record_context,
    skill_procedure,
    text_page,
    validate_relevance_method,
)
from .catalog import (
    KNOWLEDGE_SCOPES,
    SCENARIO_ALIASES,
    _catalog_corpus,
    knowledge_records,
    lookup_record,
)
from .ranking_policy import DEFAULT_RANKING_POLICY, RankingPolicy

if TYPE_CHECKING:
    from .knowledge_find import Document

AUTHORITIES = ("package", "checkout", "store")
IDENTITY = r"[a-z0-9][a-z0-9._-]*"


class RevisionConflict(ValueError):
    pass


class UnavailableRevision(RevisionConflict):
    """The authority does not retain the requested revision."""


class IdentityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(f"Unsafe bundle path: {value}")
    return value


def _resource_candidates(value: str, body: str):
    yield value
    target = value.partition("#")[0]
    if not target or target.startswith("/") or "\\" in target or ":" in target:
        raise ValueError(f"Unsafe bundle path: {value}")
    directory = posixpath.dirname(safe_path(body))
    yield safe_path(posixpath.normpath(posixpath.join(directory, target)))
    if target != value:
        yield target


def resolve_resource_key(value: str, body: str, members: Container[str]) -> str:
    """Resolve a bundle key or a local Markdown link against an already opened body."""
    for path in _resource_candidates(value, body):
        if path in members:
            return safe_path(path)
    raise ValueError(f"Unknown resource: {value}")


def case_resource_path(root: Path, record_path: Path, resource: object) -> Path:
    """Resolve a resource a case record names, refusing anything outside `root`.

    `read` loads a case through this check, and `find` locates a case body for
    ranking through it too, so a body that one would refuse is never treated as
    readable by the other.
    """
    if not isinstance(resource, str):
        raise ValueError("Case resource must be a relative POSIX path")
    safe_path(resource)
    if resource == "case.json":
        raise ValueError("Case resource collides with its case.json record")
    path = record_path.parent / resource
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Case resource escapes the skills root: {resource}")
    return path


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _normalized(value: object, field: str, ancestors: frozenset[int] = frozenset()) -> object:
    # Bundle identity is JSON, so YAML scalars without a JSON form are rejected
    # here instead of failing inside revision serialization.
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        # A YAML alias can make a container its own descendant. Only the active path
        # is tracked, so the same object shared by sibling fields stays accepted.
        identity = id(value)
        if identity in ancestors:
            raise ValueError(
                f"Field {field} contains a reference cycle: {type(value).__name__}"
            )
        ancestors = ancestors | {identity}
        if isinstance(value, list):
            return [
                _normalized(item, f"{field}[{index}]", ancestors)
                for index, item in enumerate(value)
            ]
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Field {field} has a non-string key: {key!r}")
            result[key] = _normalized(item, f"{field}.{key}" if field else key, ancestors)
        return result
    raise ValueError(
        f"Field {field or '<metadata>'} cannot be represented in the bundle identity: "
        f"{type(value).__name__}"
    )


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sources(records: list[dict]) -> list[dict]:
    result = []
    for record in records:
        source = dict(record)
        kind = source.get("type")
        if kind in ("source", "source_code", "technical_document") and "commit" in source:
            source["original_type"] = kind
            kind = "git"
        if kind is None and "commit" in source:
            kind = "git"
        if kind not in ("git", "paper", "document", "internal", "unknown"):
            # Legacy types keep their original label; nothing is inferred from them.
            source["original_type"] = kind
            kind = "unknown"
        source["type"] = kind
        if kind == "git":
            commit = source.get("commit")
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{7,40}", commit):
                raise ValueError("Git source requires a real commit or explicit historical prefix")
            source["revision_precision"] = "full" if len(commit) == 40 else "prefix"
        elif kind == "paper":
            if not source.get("id") or "version" not in source:
                raise ValueError("Paper source requires ID and explicit version (null if unknown)")
            if "commit" in source:
                raise ValueError("Paper versions are not Git commits")
        elif kind == "document":
            if not source.get("url") or not any(k in source for k in ("version", "sha256")):
                raise ValueError("Document source requires URL and version or snapshot identity")
        elif kind == "internal":
            if not source.get("artifact") or not any(k in source for k in ("issue", "run")):
                raise ValueError("Internal source requires artifact and issue/run identity")
        result.append(source)
    return result


@dataclass(frozen=True)
class Bundle:
    metadata: dict
    content: dict[str, bytes]
    dependencies: dict[str, str]

    def __post_init__(self) -> None:
        # Normalize once at ingestion so manifest, revision and views agree.
        object.__setattr__(self, "metadata", _normalized(self.metadata, "metadata"))

    def manifest(self) -> dict:
        record = self.metadata
        if not isinstance(record.get("id"), str) or not re.fullmatch(IDENTITY, record["id"]):
            raise ValueError("Invalid bundle identity")
        if record.get("kind") not in ("skill", "knowledge", "case"):
            raise ValueError("Invalid bundle kind")
        for field in (
            "sources",
            "applicability",
            "state",
            "limitations",
            "attribution",
            "entrypoint",
        ):
            if field not in record:
                raise ValueError(f"Missing normalized field: {field}")
        for field in ("state", "entrypoint"):
            if not isinstance(record[field], str) or not record[field]:
                raise ValueError(f"Normalized {field} must be a nonempty string")
        if not isinstance(record["limitations"], list):
            raise ValueError("Normalized limitations must be a list")
        if not isinstance(record["sources"], list) or not record["sources"]:
            raise ValueError("Bundle requires sources, including explicit unknown provenance")
        _sources(record["sources"])
        for path, data in self.content.items():
            safe_path(path)
            if not isinstance(data, bytes):
                raise ValueError("Bundle content must be bytes")
        if record["entrypoint"] not in self.content:
            raise ValueError("Missing entrypoint in complete bundle")
        for required in record.get("required_resources", []):
            # Present string keys already passed the content path validation.
            if isinstance(required, str) and required in self.content:
                continue
            if safe_path(required) not in self.content:
                raise ValueError(f"Missing required resource: {required}")
        resources = {path: _hash(data) for path, data in sorted(self.content.items())}
        for dependency, revision in self.dependencies.items():
            safe_path(dependency)
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
                raise ValueError("Dependency requires a resolved content revision")
            if dependency in self.content:
                actual = "sha256:" + resources[dependency]
            else:
                members = {
                    path: digest
                    for path, digest in resources.items()
                    if path.startswith(dependency + "/")
                }
                if not members:
                    raise ValueError(f"Missing dependency: {dependency}")
                actual = "sha256:" + _hash(_json(members))
            if actual != revision:
                raise RevisionConflict(f"Dependency bytes disagree with revision: {dependency}")
        return {
            "metadata": record,
            "resources": resources,
            "dependencies": dict(sorted(self.dependencies.items())),
        }

    @property
    def revision(self) -> str:
        return "sha256:" + _hash(_json(self.manifest()))

    def view(self, *, material: bool = False) -> dict:
        manifest = self.manifest()
        result = {
            **self.metadata,
            "revision": "sha256:" + _hash(_json(manifest)),
            "resources": manifest["resources"],
            "dependencies": manifest["dependencies"],
        }
        if material:
            path = self.metadata["entrypoint"]
            data = self.content[path]
            if self.metadata["kind"] == "skill":
                data, locator = skill_procedure(path, data)
                if locator:
                    result["content_view"] = {
                        **locator, "sha256": _hash(data),
                        "source_sha256": manifest["resources"][path],
                    }
            result["content"] = data.decode("utf-8")
        return result


def _store_document(reference: str, bundle: Bundle) -> Document:
    from .knowledge_find import Document, _flatten

    metadata = bundle.metadata
    identity = metadata["id"]
    title = _flatten(metadata.get("title", identity))
    summary = _flatten(metadata.get("summary"))
    entrypoint = metadata["entrypoint"]
    return Document(
        identity=identity,
        kind="record" if metadata["kind"] == "knowledge" else metadata["kind"],
        state=metadata["state"],
        path=entrypoint,
        title=title,
        summary=summary,
        qualified=reference,
        backend=metadata.get("backend"),
        fields={
            "title": f"{title} {identity.replace('.', ' ')}",
            "summary": summary,
            "tags": _flatten(metadata.get("tags")),
            "findings": _flatten(metadata.get("findings")),
            "applicability": _flatten(metadata.get("applicability")),
            "body": bundle.content[entrypoint].decode("utf-8"),
        },
    )


INCIDENTAL = ("__pycache__", ".DS_Store")


def _tree(
    node, prefix: str, *, root: Path | None = None, ancestors: frozenset[Path] = frozenset()
) -> dict[str, bytes]:
    if isinstance(node, Path):
        # A junction or symlink resolves away from where it appears; every descended
        # directory must still land inside the root that owns this walk.
        directory = node.resolve()
        if root is None:
            root = directory
        if directory in ancestors:
            raise ValueError(f"Resource cycle inside the skills root: {prefix}")
        ancestors = ancestors | {directory}
    result = {}
    for child in sorted(node.iterdir(), key=lambda p: p.name):
        # Record/config/build inputs have independent owners. Only skill resources enter this pin.
        if prefix == "data/skill_library" and child.name in {"records", "config", "_compiled"}:
            continue
        if child.name in INCIDENTAL or child.name.endswith(".pyc"):
            continue
        path = safe_path(f"{prefix}/{child.name}")
        if isinstance(child, Path) and child.is_symlink():
            raise ValueError(f"Symlink resource is not supported: {path}")
        if child.is_dir():
            if isinstance(child, Path) and root is not None and not child.resolve().is_relative_to(
                root
            ):
                raise ValueError(f"Resource escapes the skills root: {path}")
            result.update(_tree(child, path, root=root, ancestors=ancestors))
        else:
            result[path] = child.read_bytes()
    return result


def _service_scope(record):
    editions = record.get("skill_documents", {})
    primary = editions.get("original") or "record.json"
    owner = posixpath.dirname(primary)
    declared = set(editions.values())
    if owner:
        declared.update(posixpath.normpath(posixpath.join(owner, link))
                        for link in declared_skill_references(record.get("skill_metadata", {})))
    return primary, owner, declared


def _service_node(root, path):
    parts = safe_path(path).split("/")
    if not path.startswith("data/skill_library/") or parts[2] in {"records", "config", "_compiled"}:
        raise ValueError(f"Unavailable service knowledge resource: {path}")
    if any(part in INCIDENTAL or part.endswith(".pyc") for part in parts):
        raise ValueError(f"Unavailable service knowledge resource: {path}")
    node = root
    for part in parts:
        node = node.joinpath(part)
        if isinstance(node, Path) and node.is_symlink():
            raise ValueError(f"Symbolic knowledge resource: {path}")
    return node


def service_resources(record):
    """Capture the exact owner and declared files this service hit can subsequently read."""
    root = files("inferrsi").joinpath("knowledge")
    _, owner, declared = _service_scope(record)
    resources = {"record.json": _json(record)}
    if owner:
        resources.update(_tree(_service_node(root, owner), owner))
    for path in sorted(declared):
        if path not in resources:
            node = _service_node(root, path)
            if node.is_file():
                resources[path] = node.read_bytes()
    return resources


def service_body(record, resource=None, *, source_root=None):
    """Open one resource from the installed package or an already retained service source."""
    primary, owner, declared = _service_scope(record)
    root = files("inferrsi").joinpath("knowledge") if source_root is None else source_root
    requested = primary if resource is None else resource
    for path in _resource_candidates(requested, primary):
        if path == "record.json":
            return path, _json(record), {}
        if not path.startswith("data/skill_library/") or (
            path not in declared and not (owner and path.startswith(owner + "/"))
        ):
            continue
        node = _service_node(root, path)
        if node.is_file():
            raw = node.read_bytes()
            data, locator = (raw, {}) if resource is not None else skill_procedure(path, raw)
            return path, data, locator
    raise ValueError(f"Unknown resource: {requested}")


def _character_bytes(raw, start):
    end = start + 1
    while end < len(raw) and raw[end] & 0xc0 == 0x80:
        end += 1
    return end - start


def read_page(view, requested, *, source_hash=None, source_ranges=None):
    """Slice the UTF-8 material view; offsets always refer to the same pinned view."""
    if "content" not in view:
        if requested is not None:
            raise ValueError("--byte-range requires --material or --resource")
        return
    content = view["content"]
    raw = content.encode("utf-8")
    if requested is None:
        if len(raw) <= INLINE_PAGE_BYTES:
            serialized = json.dumps(content, ensure_ascii=False).encode("utf-8")
            if len(serialized) <= INLINE_PAGE_BYTES:
                return
        requested = (0, INLINE_PAGE_BYTES)
    start, length = requested
    if start < 0 or length < 1 or start > len(raw) or (start == len(raw) and start != 0):
        raise ValueError("--byte-range requires a valid start byte and a positive length")
    if start < len(raw) and raw[start] & 0xc0 == 0x80:
        raise ValueError("--byte-range must start at a UTF-8 character boundary")
    text, stop = text_page(raw, start, length)
    if stop == start and start < len(raw):
        raise ValueError(f"--byte-range needs at least {_character_bytes(raw, start)} bytes "
                         "for the next UTF-8 character")
    # Put the continuation coordinates before a potentially long stdout body.
    del view["content"]
    view["content_range"] = {
        "start": start, "end": stop, "total_bytes": len(raw),
        "first_line": raw.count(b"\n", 0, start) + 1,
    }
    if stop < len(raw):
        view["next_byte_range"] = [stop, max(length, _character_bytes(raw, stop))]
    if source_hash is not None or source_ranges is not None:
        # A Skill procedure omits frontmatter. Map the selected view bytes back
        # onto the already pinned source ranges, including pages crossing a gap.
        original = view.get("content_view", {})
        ranges, offset = [], 0
        for lo, hi in original.get("source_byte_ranges", source_ranges or [(0, len(raw))]):
            begin, end = max(start - offset, 0), min(stop - offset, hi - lo)
            if begin < end:
                ranges.append([lo + begin, lo + end])
            offset += hi - lo
        view["content_view"] = {"locator": "byte-range", "source_byte_ranges": ranges}
        if source_hash is not None:
            view["content_view"].update(source_sha256=source_hash,
                                        sha256=_hash(raw[start:stop]))
    view["content"] = text


def _retain_service_sources(destination, selections):
    """Publish only complete, byte-consistent source sets before their search receipt."""
    temporary = destination.with_name("." + destination.name)
    temporary.mkdir(parents=True)
    try:
        for record, document in selections:
            resources = service_resources(record)
            primary = record.get("skill_documents", {}).get("original") or "record.json"
            if document.kind == "skill":
                if (primary != "data/skill_library/" + document.path
                        or record["skill_metadata"]["name"] != document.identity
                        or record["backend"] != document.backend):
                    raise ValueError(
                        "Knowledge ownership changed while finding material; run Find again"
                    )
                raw = resources[primary].decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                body, _ = skill_procedure(primary, raw.encode("utf-8"))
                if body.decode("utf-8") != document.fields["body"]:
                    raise ValueError("Knowledge changed while finding material; run Find again")
            directory = temporary / record["id"]
            for path, content in resources.items():
                target = directory / safe_path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                target.chmod(target.stat().st_mode & ~0o222)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _find_service(query, destination, *, kinds, backend, repo, tier, scenario,
                  limit, explain, policy):
    from .knowledge_find import rank

    if not query:
        raise ValueError("Service-reuse Find requires a question")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    records = knowledge_records(file_fingerprints=False)
    scenario = SCENARIO_ALIASES.get(scenario, scenario)

    def matches(record):
        skill = record.get("index_type") == "packaged-skill"
        declared = record.get("scenario", "")
        applicable = (not scenario or declared == scenario
                      or (skill and declared == "skills.discovery")
                      or (declared.endswith(".*") and scenario.startswith(declared[:-1])))
        return (("skill" if skill else "record") in kinds
                and (not backend or record["backend"] in ("common", backend))
                and (not tier or record.get("tier", "contribution") == tier)
                and (not repo or record["repo"] == repo)
                and applicable)

    records = [record for record in records if matches(record)]
    corpus, records = _catalog_corpus(records, file_fingerprints=False)
    _, _, ranked = rank(query, corpus, policy)
    items = []
    selections = []
    for score, _, index, components in ranked[:limit]:
        record = records[index]
        selections.append((record, corpus.documents[index]))
        ref = "package:" + record["id"]
        revision = record["sources"][0]["commit"]
        path = record.get("skill_documents", {}).get("original") or "record.json"
        items.append({
            "id": record["id"], "authority": "package", "title": record["title"],
            "kind": "skill" if record.get("index_type") == "packaged-skill" else "record",
            "repo": record["repo"], "tier": record.get("tier", "contribution"),
            "backend": record["backend"], "scenario": record["scenario"],
            "score": round(score, 2), "material_ref": ref, "revision": revision,
            "body_resource": path, "material_read_args": ["read", ref, "--revision", revision],
            **({"matched": components} if explain else {}),
        })
    _retain_service_sources(destination, selections)
    return {"query": query, "matched": len(ranked), "no_match": not ranked, "items": items,
            "ranking_policy": policy.configuration(), "sources": ["package"]}


def _read_service_hit(source_root, hit, resource):
    metadata = source_root / "record.json"
    if metadata.is_symlink():
        raise ValueError("Symbolic retained knowledge record")
    record = json.loads(metadata.read_bytes())
    if record.get("id") != hit["id"] or record["sources"][0]["commit"] != hit["revision"]:
        raise ValueError("The retained source does not match this Find")
    primary = hit["body_resource"]
    path, data, locator = service_body(record, resource, source_root=source_root)
    ref, revision = hit["material_ref"], hit["revision"]
    selected = {"path": path, "role": "core" if path == primary else "reference",
                "content": data.decode("utf-8"), **locator}
    context = {"ref": ref, "revision": revision, "resources": [selected],
               "content_bytes": len(data), "omissions": [], "sources": record["sources"]}
    view = {"ref": ref, "id": hit["id"], "revision": revision, "entrypoint": primary,
            "content_resource": path, "content": selected["content"], "sources": record["sources"]}
    if resource is not None and path != resource:
        view["body_resource"] = primary
    if locator:
        view["content_view"] = locator
    return view, context


def _read_local_hit(source, hit, resource):
    ref, bundle = source.read_resolved(hit["material_ref"], revision=hit["revision"])
    view = bundle.view()
    body = hit["body_resource"]
    path = resolve_resource_key(body if resource is None else resource, body, bundle.content)
    if resource is not None and path != resource:
        view["body_resource"] = body
    raw = bundle.content[path]
    data, locator = skill_procedure(path, raw) if resource is None else (raw, {})
    content = data.decode("utf-8")
    digest = view["resources"][path]
    role = "reference" if path != hit["body_resource"] else (
        "record" if path == "record.json" else "core"
    )
    delivered = {"path": path, "role": role, "sha256": digest, "content": content}
    if locator:
        location = {**locator, "source_sha256": digest, "sha256": _hash(data)}
        delivered.update(location)
        view["content_view"] = location
    context = {"ref": ref, "revision": view["revision"], "resources": [delivered],
               "sources": view["sources"], "content_bytes": len(data), "omissions": []}
    view.pop("resources")
    view.pop("required_resources", None)
    view.update(ref=ref, content=content, content_resource=path)
    return view, context


class KnowledgeReader:
    def __init__(self, *, skill_root: Path | None = None, store=None):
        self.skill_root = skill_root.resolve() if skill_root is not None else None
        if store is not None and store.skill_root != self.skill_root:
            raise ValueError("Store must reserve identities from the same checkout")
        self.store = store
        self._records: dict[str, dict] | None = None
        self._opened_records: dict[str, dict | None] = {}
        self._library: tuple[dict[str, bytes], str] | None = None

    def find(
        self, query: str, *, kinds=("case", "skill", "record"), backend=None, repo=None,
        tier=None, scenario=None, revisions=None,
        retained_source=None,
        limit=5, explain=False, ranking_policy=DEFAULT_RANKING_POLICY, searchspace_index=None,
        **options,
    ) -> dict:
        """Find within a scoped catalog or retain the pinned service source bytes."""
        from .knowledge_find import find, load_corpus

        if not kinds or set(kinds) - {"case", "skill", "record"}:
            raise ValueError("--kinds takes a subset of case,skill,record")
        if retained_source is not None:
            return _find_service(
                query, retained_source, kinds=kinds, backend=backend, repo=repo, tier=tier,
                scenario=scenario, limit=limit, explain=explain, policy=ranking_policy,
            )
        corpus = load_corpus(
            self.skill_root, kinds=kinds, backend=backend, repo=repo, tier=tier, scenario=scenario,
            searchspace_index=searchspace_index, store=self.store, revisions=revisions,
        )
        return find(query, corpus, limit=limit, explain=explain, backend=backend,
                    ranking_policy=ranking_policy, **options)

    def read_hit(self, hit: dict, *, resource=None, byte_range=None,
                 retained_source=None) -> tuple[dict, dict]:
        """Read one selected body or linked resource and report the exact returned page."""
        if retained_source is not None:
            view, context = _read_service_hit(retained_source, hit, resource)
        else:
            from .knowledge_find import installed_skill_root

            source = (KnowledgeReader(skill_root=installed_skill_root())
                      if "--installed-library" in hit["material_read_args"]
                      and self.skill_root is None else self)
            view, context = _read_local_hit(source, hit, resource)
        delivered, = context["resources"]
        read_page(
            view, byte_range, source_hash=delivered.get("source_sha256", delivered.get("sha256")),
            source_ranges=delivered.get("source_byte_ranges"),
        )
        if "content_range" in view:
            delivered.update(content=view["content"], content_range=view["content_range"])
            delivered.update(view.get("content_view", {}))
            context["content_bytes"] = len(view["content"].encode("utf-8"))
        return view, context

    def records(self) -> dict[str, dict]:
        """Installed catalog records, read once per reader (one package snapshot)."""
        if self._records is None:
            self._records = {record["id"]: record for record in knowledge_records()}
        return self._records

    def record(self, identity: str) -> dict | None:
        """Read one validated owner, honoring an already-loaded or supplied catalog."""
        if self._records is not None:
            return self._records.get(identity)
        if identity not in self._opened_records:
            self._opened_records[identity] = lookup_record(identity)
        return self._opened_records[identity]

    def _skill_library(self) -> tuple[dict[str, bytes], str]:
        if self._library is None:
            # K02 moved the physical corpus under the Knowledge module. The bundle
            # key prefix stays "data/skill_library" so resource keys, dependency
            # keys and pinned record hashes keep their existing values.
            root = files("inferrsi").joinpath("knowledge", "data", "skill_library")
            library = _tree(root, "data/skill_library")
            digest = _hash(_json({path: _hash(data) for path, data in sorted(library.items())}))
            self._library = (library, "sha256:" + digest)
        return self._library

    def owners(self) -> dict[str, list[str]]:
        """Map each public ID to every authority that owns it."""
        result: dict[str, list[str]] = {}
        for identity in self.records():
            result.setdefault(identity, []).append("package")
        for identity in self._checkout_identities():
            result.setdefault(identity, []).append("checkout")
        if self.store is not None:
            for identity in self.store.identities():
                result.setdefault(identity, []).append("store")
        return result

    def _checkout_identities(self) -> list[str]:
        if self.skill_root is None:
            return []
        # Enumeration reads registered names. Collect validates metadata per item.
        from .skill_catalog import skill_directories

        directories = skill_directories(self.skill_root)
        identities = [*directories, *self._cases(directories)]
        if len(set(identities)) != len(identities):
            raise IdentityError("collision", "Duplicate identity inside the checkout")
        return identities

    def identities(self) -> list[str]:
        return sorted(f"{a}:{i}" for i, authorities in self.owners().items() for a in authorities)

    def resolve(self, reference: str, owners: dict[str, list[str]] | None = None) -> str:
        """Return the qualified `authority:id`; ambiguity is an error, never precedence."""
        authority, qualified, identity = reference.rpartition(":")
        if not re.fullmatch(IDENTITY, identity) or (qualified and authority not in AUTHORITIES):
            raise IdentityError("invalid_identity", f"Invalid identity: {reference}")
        if owners is not None:
            found = owners.get(identity, [])
        else:
            found = []
            if (not qualified or authority == "package") and self.record(identity) is not None:
                found.append("package")
            if ((not qualified or authority == "checkout")
                    and identity in self._checkout_identities()):
                found.append("checkout")
            if (not qualified or authority == "store") and self.store is not None:
                if identity in self.store.identities():
                    found.append("store")
        if qualified:
            if authority not in found:
                raise IdentityError("unknown_identity", f"Unknown identity: {reference}")
            return reference
        if not found:
            raise IdentityError("unknown_identity", f"Unknown identity: {identity}")
        if len(found) > 1:
            choices = ", ".join(f"{a}:{identity}" for a in found)
            raise IdentityError(
                "ambiguous_identity", f"Ambiguous identity {identity}; qualify one of: {choices}"
            )
        return f"{found[0]}:{identity}"

    def cases(self) -> dict[str, Path]:
        """Case identities owned by this checkout's registered skills.

        The discovery `read` and `collect` resolve against, exposed so a caller
        ranking cases cannot drift from the rule that decides whether they open.
        """
        return self._cases()

    def _cases(self, directories: dict[str, Path] | None = None) -> dict[str, Path]:
        result = {}
        if self.skill_root is not None:
            from .skill_catalog import skill_directories

            if directories is None:
                directories = skill_directories(self.skill_root)
            for directory in directories.values():
                for path in sorted(directory.glob("cases/*.json")):
                    if path.is_symlink() or not path.resolve().is_relative_to(self.skill_root):
                        raise ValueError("Case must stay inside the selected skills root")
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if record.get("kind") == "case":
                        identity = record["id"]
                        if not isinstance(identity, str) or not re.fullmatch(IDENTITY, identity):
                            raise ValueError(f"Invalid case identity in {path.name}: {identity!r}")
                        if identity in result:
                            raise ValueError(f"Duplicate case identity: {identity}")
                        result[identity] = path
        return result

    def read(self, reference: str, *, revision: str | None = None) -> Bundle:
        _, bundle = self.read_resolved(reference, revision=revision)
        return bundle

    def read_resolved(self, reference: str, *, revision: str | None = None) -> tuple[str, Bundle]:
        """Read a bundle and return the qualified reference used for that read."""
        qualified = self.resolve(reference)
        return qualified, self._read(qualified, revision)

    def read_decision_card(
        self, reference: str, *, revision: str, finding: str | None = None,
        max_bytes: int | None = None, compact: bool = False,
    ) -> dict:
        """Read the L1 projection of one atom at the requested content revision."""
        from .decision_cards import project_decision_card

        if not revision:
            raise ValueError("L1 requires an exact --revision")
        try:
            resolved = self.read_resolved(reference, revision=revision)
            return project_decision_card(
                resolved, reference=reference if ":" in reference else resolved[0],
                revision=revision, finding=finding,
                max_bytes=max_bytes, compact=compact,
            )
        except (IdentityError, UnavailableRevision) as exc:
            if isinstance(exc, IdentityError) and exc.code != "unknown_identity":
                raise
            return {"ref": reference, "revision": revision, "status": "unavailable_revision",
                    "detail": str(exc)}

    def _read(self, qualified: str, revision: str | None) -> Bundle:
        authority, _, identity = qualified.partition(":")
        if authority == "store":
            return self.store.read(identity, revision=revision)
        bundle = self._checkout(identity) if authority == "checkout" else self._knowledge(identity)
        if revision is not None and bundle.revision != revision:
            raise UnavailableRevision(
                f"Revision unavailable in this snapshot: {qualified} at {revision}"
            )
        return bundle

    def _checkout(self, identity: str) -> Bundle:
        cases = self._cases()
        if identity in cases:
            path = cases[identity]
            original = path.read_bytes()
            record = json.loads(original.decode("utf-8"))
            if record.get("id") != identity or record.get("kind") != "case":
                raise ValueError(f"Case identity changed during read: {identity}")
            for field in ("references", "dependencies"):
                if field in record:
                    raise ValueError(f"Case {field} are not supported; declare required_resources")
            declared = record.get("required_resources", [])
            if not isinstance(declared, list) or any(not isinstance(p, str) for p in declared):
                raise ValueError("Case required_resources must be a string list")
            if len(set(declared)) != len(declared):
                raise ValueError("Case required_resources must not repeat a path")
            relative = record["content"]
            required = [relative, "case.json", *(p for p in declared if p != relative)]
            content = {"case.json": original}
            for resource in [relative, *required[2:]]:
                resource_path = case_resource_path(self.skill_root, path, resource)
                if not resource_path.is_file():
                    raise ValueError(f"Missing case resource: {resource}")
                content[resource] = (
                    original if resource_path == path else resource_path.read_bytes()
                )
            return Bundle(
                {
                    **record,
                    "entrypoint": relative,
                    "sources": _sources(record["sources"]),
                    "required_resources": required,
                },
                content,
                {},
            )
        return self._skill(identity)

    def _knowledge(self, identity: str) -> Bundle:
        record = self.record(identity)
        if record is None:
            raise IdentityError("unknown_identity", f"Unknown knowledge ID: {identity}")
        content = {"record.json": _json(record)}
        dependencies = {}
        if record.get("skill_documents"):
            # The whole imported library is one explicit dependency so bilingual
            # references and licenses stay a complete closure.
            library, digest = self._skill_library()
            content.update(library)
            dependencies["data/skill_library"] = digest
            documents = record["skill_documents"]
            if not isinstance(documents, dict):
                raise ValueError(f"skill_documents must map editions to paths: {identity}")
            for target in documents.values():
                if not isinstance(target, str) or safe_path(target) not in library:
                    raise ValueError(f"Missing declared skill document: {target}")
        return Bundle(
            {
                "id": identity,
                "kind": "knowledge",
                "entrypoint": "record.json",
                "origin": record.get("origin", ["external"]),
                "sources": _sources(record["sources"]),
                "applicability": record.get("applicability", {}),
                "state": record["status"],
                "limitations": record.get("limitations", [])
                + [
                    "Imported guidance; reading does not validate or execute it.",
                    "Historical revisions require the matching installed snapshot "
                    "or a retained store.",
                ],
                "attribution": record["sources"],
                "verification": record["verification"],
                "tier": record.get("tier", "contribution"),
                "repo": record["repo"],
                "backend": record["backend"],
                "scenario": record["scenario"],
                "title": record["title"],
                "skill_documents": record.get("skill_documents", {}),
                "required_resources": sorted(content),
            },
            content,
            dependencies,
        )

    def _skill(self, identity: str) -> Bundle:
        from .skill_catalog import _effective, _reference_path, skill_directory

        root = self.skill_root
        directory = skill_directory(root, identity)
        metadata = _effective(directory)
        prefix = directory.relative_to(root).as_posix()
        content = _tree(directory, prefix, root=root)
        dependencies = {}
        for reference in metadata.get("references", []):
            path = _reference_path(root, directory, reference)
            key = path.relative_to(root).as_posix()
            content[key] = path.read_bytes()
            dependencies[key] = "sha256:" + _hash(content[key])
        return Bundle(
            {
                "id": identity,
                "kind": "skill",
                "entrypoint": f"{prefix}/SKILL.md",
                "title": metadata["description"],
                "origin": metadata.get("origin", ["unknown"]),
                "sources": _sources(metadata.get("sources", []))
                or [
                    {
                        "type": "unknown",
                        "note": "Legacy provenance remains in procedure/readsets",
                    }
                ],
                "applicability": metadata.get("applicability", {}),
                "state": metadata.get("status", "unspecified"),
                "limitations": metadata.get("limitations", [])
                + [
                    "Checkout-only local skill; no automatic execution or promotion.",
                    "Only declared references are required; "
                    "other cross-skill links are navigation.",
                    "Historical revisions require a matching checkout or a retained store.",
                ],
                "attribution": metadata.get("sources", []),
                "empirical_validation": metadata.get("empirical_validation", "unknown"),
                "required_resources": sorted(content),
            },
            content,
            dependencies,
        )

    def resource(self, identity: str, path: str, *, revision: str) -> bytes:
        safe_path(path)
        bundle = self.read(identity, revision=revision)
        if path not in bundle.content:
            raise ValueError(f"Unknown resource: {path}")
        return bundle.content[path]

    def pack_find_hits(self, hits, *, cue, limit, context_bytes, max_bytes=None, revisions=None,
                       ranking_policy=DEFAULT_RANKING_POLICY):
        """Pack the complete bodies of already ranked pins, then their relevant attachments."""
        fixed = revisions or {}
        pins = {hit["material_ref"]: fixed.get(hit["material_ref"], hit["revision"])
                for hit in hits}
        if type(context_bytes) is not int or context_bytes < 0:
            raise ValueError("A candidate context requires a nonnegative byte limit")
        return self.collect(
            ids=list(pins), revisions=pins, limit=limit, relevance=cue if pins else None,
            max_bytes=max_bytes, context_bytes=context_bytes, ranking_policy=ranking_policy,
            _found_bodies={hit["material_ref"]: hit["body_resource"] for hit in hits},
        )

    def collect(
        self,
        query: str | None = "",
        *,
        ids: list[str] | None = None,
        revisions: dict[str, str] | None = None,
        kind: str | None = None,
        repo: str | None = None,
        tier: str | None = None,
        backend: str | None = None,
        scenario: str | None = None,
        limit: int = 10,
        max_bytes: int | None = None,
        material: bool = False,
        relevance: str | None = None,
        relevance_method: str | None = None,
        ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
        context_bytes: int | None = None,
        decision_cards: dict[str, str | None] | None = None,
        _found_bodies: dict[str, str] | None = None,
    ) -> dict:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 1):
            raise ValueError("max_bytes must be a positive integer")
        if ids is not None and (
            not isinstance(ids, list) or any(not isinstance(identity, str) for identity in ids)
        ):
            raise ValueError("ids must be a list of identity strings")
        if kind not in (None, "skill", "knowledge", "case"):
            raise ValueError("Unknown content kind")
        validate_relevance_method(relevance_method)
        if query is not None and not isinstance(query, str):
            raise ValueError("query must be a string or None")
        if (query and query.strip()) or (relevance is not None and not ids):
            raise ValueError("Use find(query, load_corpus(...)) to search for material. "
                             "Collect uses relevance only for attachments of explicit IDs.")
        if relevance is not None and (
            not isinstance(relevance, str) or not re.search(r"\w", relevance)
        ):
            raise ValueError("relevance requires at least one word")
        if context_bytes is not None and (type(context_bytes) is not int
                                          or context_bytes < (1 if _found_bodies is None else 0)):
            raise ValueError("context_bytes must be a positive integer")
        if revisions is None:
            revisions = {}
        if not isinstance(revisions, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in revisions.items()
        ):
            raise ValueError("revisions must map identity strings to revision strings")
        if ids is not None and len(set(ids)) != len(ids):
            raise ValueError("Duplicate requested identity")
        if decision_cards is not None and not isinstance(decision_cards, dict):
            raise ValueError("decision_cards must map qualified refs to a finding or None")
        if decision_cards:
            if not ids or context_bytes is None:
                raise ValueError("Decision cards require explicit ids and context_bytes")
            for ref, finding in decision_cards.items():
                if not isinstance(ref, str) or ref not in ids or ":" not in ref:
                    raise ValueError("Decision cards require an explicitly selected qualified ref")
                if not revisions.get(ref, "").strip():
                    raise ValueError(f"Decision card requires an exact revision for {ref}")
                if finding is not None and (not isinstance(finding, str) or not finding.strip()):
                    raise ValueError("A finding must be a nonempty selector")
        owners = self.owners()
        requested = ids if ids is not None else sorted(
            f"{authority}:{identity}" for identity, values in owners.items() for authority in values
        )

        def qualified(reference: str) -> str | None:
            # Revision keys may use any spelling the API accepts for an identity.
            try:
                return self.resolve(reference, owners)
            except IdentityError:
                return None

        selected_refs = {qualified(reference) for reference in requested} if revisions else set()
        pinned: dict[str, str] = {}
        for reference, revision in revisions.items():
            target = qualified(reference)
            if target is None or target not in selected_refs:
                raise ValueError(
                    f"Revision requested for an unselected identity: {reference}"
                )
            if pinned.setdefault(target, revision) != revision:
                raise ValueError(f"Conflicting revisions for the same identity: {reference}")
            pinned[target] = revision
        collisions = sorted(i for i, authorities in owners.items() if len(authorities) > 1)
        if tier is not None and tier not in KNOWLEDGE_SCOPES:
            raise ValueError(f"Unknown knowledge tier: {tier}")
        scenario = SCENARIO_ALIASES.get(scenario, scenario)
        package_filters = any(value is not None for value in (repo, tier, scenario, backend))

        def matches(metadata: dict, authority: str) -> bool:
            declared = metadata.get("scenario")
            declared = declared if isinstance(declared, str) else ""
            return not (
                (kind and metadata.get("kind") != kind)
                or (package_filters and authority != "package")
                or (repo and metadata.get("repo") != repo)
                or (tier and metadata.get("tier", "contribution") != tier)
                or (backend and metadata.get("backend") not in (backend, "common"))
                or not (
                    scenario is None
                    or declared == scenario
                    or (declared.endswith(".*") and scenario.startswith(declared[:-1]))
                )
            )

        excluded = {
            "ranking_scope": 0, "filters": 0, "query": 0, "zero_score": 0,
            "item_limit": 0, "material_bytes": 0,
        }
        considered = len(requested)
        omitted = []
        cases = self._cases() if kind else {}
        selected, seen = [], set()
        used = 0
        contexts, context_omissions, found_entries = [], [], []
        delivered_bundles: dict[str, tuple[str, Bundle]] = {}
        context_used = 0
        matched_count = 0

        def select(reference: str, bundle: Bundle, view: dict) -> None:
            nonlocal used, context_used, matched_count
            packaged = view["authority"] == "package"
            record = (
                self.records().get(view["id"], {})
                if packaged and context_bytes is not None else {}
            )
            is_skill = record.get("index_type") == "packaged-skill"
            matched_count += 1
            # Normal Bundle views were serialized while computing their revision.
            # Preserve custom subclasses' serialization/error behavior below.
            if type(bundle) is Bundle and len(selected) >= limit:
                excluded["item_limit"] += 1
                omitted.append({"id": reference, "reason": "output_limit"})
                return
            size = len(_json(view))
            if len(selected) >= limit or (max_bytes is not None and used + size > max_bytes):
                excluded["item_limit" if len(selected) >= limit else "material_bytes"] += 1
                omitted.append({"id": reference, "reason": "output_limit"})
                return
            selected.append(view)
            used += size
            if context_bytes is None:
                return
            if _found_bodies is not None:
                found_entries.append((view, record, bundle.content, _found_bodies[view["ref"]]))
                return
            pinned_item = ids is not None and view["ref"] in pinned
            checkout_context = (
                view["authority"] == "checkout" and view["kind"] in ("case", "skill")
                and pinned_item
            )
            if not ((packaged and (is_skill or pinned_item)) or checkout_context):
                context_omissions.append({"ref": view["ref"], "reason": "unsupported_context"})
                return
            try:
                available = context_bytes - context_used
                if is_skill:
                    index = indexed_skill(record, view, bundle.content)
                    context, omission = context_view(
                        index, view, bundle.content, relevance, available, ranking_policy,
                    )
                else:
                    context, omission = record_context(record, view, bundle.content, available)
            except (ValueError, KeyError, TypeError) as exc:
                context_omissions.append({
                    "ref": view["ref"], "reason": "index_unavailable", "detail": str(exc),
                })
                return
            if omission is not None:
                context_omissions.append(omission)
            else:
                contexts.append(context)
                context_used += context["content_bytes"]
                if decision_cards and view["ref"] in decision_cards:
                    delivered_bundles[view["ref"]] = (view["ref"], bundle)

        for reference in requested:
            try:
                qualified = self.resolve(reference, owners)
                if qualified in seen:
                    raise IdentityError("duplicate_identity", f"Already selected: {qualified}")
                seen.add(qualified)
                authority, _, identity = qualified.partition(":")
                # Cheap metadata checks first, before loading bundle resources.
                if authority == "package":
                    early = {**self.records()[identity], "kind": "knowledge"}
                elif authority == "checkout":
                    early = {"kind": "case" if identity in cases else "skill"}
                else:
                    early = None
                if early is not None and not matches(early, authority):
                    excluded["filters"] += 1
                    if ids is not None:
                        omitted.append({"id": reference, "reason": "filters"})
                    continue
                bundle = self._read(qualified, pinned.get(qualified))
                view = {**bundle.view(material=material), "authority": authority, "ref": qualified}
                # A Case selected by Find still includes its ranked title in the
                # material-size limit when its exact pin is assembled later.
                if _found_bodies is not None and view["kind"] == "case":
                    view.setdefault("title", identity.removeprefix("case."))
            except IdentityError as exc:
                omitted.append({"id": reference, "reason": exc.code, "detail": str(exc)})
                continue
            except RevisionConflict as exc:
                omitted.append(
                    {"id": reference, "reason": "unavailable_revision", "detail": str(exc)}
                )
                continue
            except MissingSkillsExtra:
                # The install cannot parse any checkout skill, not just this one.
                # As an omission it would return `no_match`, which reads as
                # "nothing found" rather than "install the skills extra".
                raise
            except (ValueError, KeyError, TypeError, AttributeError, OSError, sqlite3.Error) as exc:
                omitted.append({"id": reference, "reason": "invalid", "detail": str(exc)})
                continue
            if not matches(view, authority):
                excluded["filters"] += 1
                if ids is not None:
                    omitted.append({"id": reference, "reason": "filters"})
                continue
            select(reference, bundle, view)
        if found_entries:
            contexts, context_omissions, context_used = candidate_contexts(
                found_entries, relevance, context_bytes, ranking_policy,
            )
        result = {
            "items": selected,
            "omissions": omitted,
            "no_match": not selected,
            "collisions": collisions,
            "material_bytes": used,
            "limitations": [
                "Items follow explicit ID order or inventory identity order.",
                "max_bytes bounds item payloads, not omission/control metadata.",
                "Read references must be resolved with their returned exact revision.",
            ],
        }
        if relevance is not None:
            result["selection"] = {
                "method": FIND_RELEVANCE, "cue": relevance,
                "scope": "context-resources", "ranking_applied": False,
            }
        if context_bytes is not None:
            result.update({
                "contexts": contexts, "context_omissions": context_omissions,
                "context_bytes": context_used,
                "context_budget": {
                    "max_bytes": context_bytes, "accounting": "utf8-resource-content",
                    "excludes": "provenance, omission and control metadata",
                },
            })
            if decision_cards:
                from .decision_cards import project_decision_card

                cards = []
                for ref in ids:
                    if ref not in decision_cards:
                        continue
                    finding = decision_cards[ref]
                    entry = {"ref": ref, "revision": pinned[ref]}
                    if finding is not None:
                        entry["finding"] = finding
                    if ref not in delivered_bundles:
                        cards.append({**entry, "status": "no_body"})
                        continue
                    try:
                        projection = project_decision_card(
                            delivered_bundles[ref], reference=ref, revision=pinned[ref],
                            finding=finding, max_bytes=context_bytes - context_used,
                        )
                    except (ValueError, KeyError, TypeError):
                        cards.append({**entry, "status": "unavailable",
                                      "reason": "invalid_decision_source_or_finding"})
                        continue
                    cards.append({**entry, **projection})
                    if "card" in projection:
                        context_used += projection["card_bytes"]
                result["decision_cards"] = cards
                result["context_bytes"] = context_used
                result["context_budget"].update(
                    accounting="utf8-resource-content-and-canonical-l1",
                    excludes="provenance and control metadata outside resource and card payloads",
                )
        from .retrieval import observation

        selection = result.get("selection", {})
        if selection:
            selection["ranking_policy"] = ranking_policy.receipt()
        result["retrieval"] = observation(
            entrypoint="collect", request={
                "query": query, "relevance": relevance, "relevance_method": relevance_method,
                "ids": ids, "revisions": revisions, "kind": kind, "repo": repo, "tier": tier,
                "backend": backend, "scenario": scenario, "limit": limit,
                "max_bytes": max_bytes, "context_bytes": context_bytes,
                **({"decision_cards": dict(decision_cards)} if decision_cards else {}),
                "sources": ["package"] + (["checkout"] if self.skill_root else [])
                           + (["store"] if self.store is not None else []),
            }, selection={
                "method": selection.get("method"),
                "scope": selection.get("scope"),
                **({"ranking_policy": selection["ranking_policy"]} if selection else {}),
                "ranking_applied": False,
                "state": "explicit_ids" if ids is not None else "not_requested",
                "tie_break": None,
            }, items=[{"ref": item["ref"], "revision": item["revision"], "rank": n}
                      for n, item in enumerate(selected, 1)],
            counts={
                "considered": considered, "matched": matched_count,
                "returned": len(selected), "excluded": excluded,
            },
            assembly="not_requested" if context_bytes is None else "performed",
        )
        return result
