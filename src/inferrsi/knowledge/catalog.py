"""Read-only package-data catalog. Knowledge text is never executable."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.resources import files
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from ..resources.repository_packs import REPO_TYPES
from . import _source_snapshot
from .retrieval import observation

if TYPE_CHECKING:
    from .knowledge_find import Corpus

# Learning scope does not imply that a repository has a runnable target adapter.
# Legacy repository-pack records retain their contribution tier; an independent
# peer card can describe a different learning use case for the same source repo.
KNOWLEDGE_SCOPES = {
    "contribution": (*REPO_TYPES, "vllm_ascend", "inferrsi"),
    "dependency": (
        "flashinfer", "flashattention", "pytorch", "triton", "diffusers", "transformers", "mlx"
    ),
    "peer": (
        "sglang", "tensorrt_llm", "lmdeploy", "xdit", "cache_dit", "qwen3_tts_engine", "deepinfer"
    ),
}
KNOWLEDGE_REPOS = tuple(
    dict.fromkeys(repo for repos in KNOWLEDGE_SCOPES.values() for repo in repos)
)
BACKENDS = ("cpu", "cuda", "rocm", "ascend", "mlx")
SCENARIO_ALIASES = {
    "diffusion.t2i": "diffusion.image_generation",
    "diffusion.t2v": "diffusion.video_generation",
}


def packaged_skill_id(name: str, backend: str) -> str:
    """Return the stable catalog ID for a skill registered by name and backend."""
    return f"inferrsi.{backend}.skills.{name.replace('-', '_')}"


def _walk(root, prefix=()):
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        parts = (*prefix, child.name)
        if child.is_dir():
            yield from _walk(child, parts)
        else:
            yield parts, child


def _validate_record(
    record: dict, repo: str, parts: tuple[str, ...], tier: str = "contribution"
) -> None:
    required = ("id", "title", "repo", "backend", "component", "scenario", "status", "summary")
    if not isinstance(record, dict) or any(
        not isinstance(record.get(key), str) or not record[key].strip() for key in required
    ):
        raise ValueError(f"Incomplete knowledge record: {repo}/{'/'.join(parts)}")
    if record.get("schema_version") != 1:
        raise ValueError(f"Unsupported knowledge schema: {record['id']}")
    # Existing schema-v1 records retain their IDs and default to contribution.
    if record.get("tier", "contribution") != tier:
        raise ValueError(f"Knowledge tier disagrees with path: {record['id']}")
    if len(parts) != 3:
        raise ValueError("Knowledge path must be BACKEND/COMPONENT/ENTRY.json")
    backend, component, filename = parts
    if backend not in (*BACKENDS, "common"):
        raise ValueError(f"Unknown knowledge backend: {backend}")
    if (record["repo"], record["backend"], record["component"]) != (repo, backend, component):
        raise ValueError(f"Knowledge scope disagrees with path: {record['id']}")
    expected_id = f"{repo}.{backend}.{component}.{filename[:-5].replace('-', '_')}"
    if record["id"] != expected_id:
        raise ValueError(f"Knowledge ID disagrees with path: {record['id']}")
    if not record["scenario"].startswith(component + "."):
        raise ValueError(f"Knowledge scenario disagrees with component: {record['id']}")
    sources = record.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"Knowledge has no source: {record['id']}")
    for source in sources:
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("url"), str)
            or not source["url"].startswith("https://")
            or not isinstance(source.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", source["commit"])
        ):
            raise ValueError(f"Knowledge requires source attribution and revision: {record['id']}")
    verification = record.get("verification", {})
    if not isinstance(verification, dict) or not isinstance(
        verification.get("locally_verified"), bool
    ):
        raise ValueError(f"Knowledge requires an explicit verification state: {record['id']}")
    if record["status"] == "imported" and verification["locally_verified"]:
        raise ValueError(f"Imported knowledge must state locally_verified=false: {record['id']}")


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


def skill_views(root, *, file_fingerprints=True, record_id: str | None = None):
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
    if not isinstance(inputs, dict) or (record_id is None and entries.keys() != inputs.keys()):
        raise ValueError("Compiled skill IDs disagree with registry")
    for name, registration in entries.items():
        if record_id is not None and packaged_skill_id(name, registration["backend"]) != record_id:
            continue
        relative = registration["path"]
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or path.name != name or "\\" in relative:
            raise ValueError(f"Invalid registered skill path: {relative}")
        directory = f"{_source_snapshot.LIBRARY}/{relative}"
        owner = root.joinpath(*path.parts)
        data = inputs.get(name)
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
            "id": packaged_skill_id(name, backend),
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


def _authored_record(item) -> dict:
    if not item.is_file() or not item.name.endswith(".json"):
        raise ValueError(f"Unexpected authored knowledge resource: {item.name}")
    parts = item.name[:-5].split(".", 3)
    if len(parts) != 4:
        raise ValueError(f"Invalid knowledge filename: {item.name}")
    repo, backend, component, entry = parts
    record = json.loads(item.read_bytes())
    if not isinstance(record, dict) or record.get("index_type") == "packaged-skill":
        raise ValueError(f"Invalid authored knowledge record: {item.name}")
    tier = record.get("tier", "contribution")
    if repo not in KNOWLEDGE_SCOPES.get(tier, ()):
        raise ValueError(f"Knowledge tier disagrees with repository scope: {item.name}")
    _validate_record(record, repo, (backend, component, entry + ".json"), tier)
    if item.name != record["id"] + ".json":
        raise ValueError(f"Knowledge ID disagrees with filename: {item.name}")
    return record


def knowledge_records(
    *, file_fingerprints: bool = True, include_skill_views: bool = True,
) -> list[dict[str, Any]]:
    root = files("inferrsi").joinpath("knowledge", "data", "skill_library")
    records = []
    authored = root.joinpath("records")
    for item in sorted(authored.iterdir(), key=lambda p: p.name):
        if item.is_file() and (
            item.name in {"README.md", ".DS_Store"}
            or item.name.casefold() in {"desktop.ini", "thumbs.db"}
        ):
            continue
        records.append(_authored_record(item))
    if include_skill_views:
        for view in skill_views(root, file_fingerprints=file_fingerprints):
            parts = (view["backend"], "skills", view["title"] + ".json")
            _validate_record(view, "inferrsi", parts)
            records.append(view)
    order = {(tier, repo): (t, r) for t, (tier, repos) in enumerate(KNOWLEDGE_SCOPES.items())
             for r, repo in enumerate(repos)}
    records.sort(key=lambda row: (
        order[row.get("tier", "contribution"), row["repo"]], row["id"]
    ))
    if len({row["id"] for row in records}) != len(records):
        raise ValueError("Duplicate knowledge ID")
    return records if file_fingerprints else without_file_fingerprints(records)


def without_file_fingerprints(value):
    """Project source attribution without computing or validating file identities."""
    if isinstance(value, dict):
        return {key: without_file_fingerprints(item) for key, item in value.items()
                if key != "source_files" and not any(
                    part in key.lower() for part in ("sha256", "fingerprint", "digest"))}
    if isinstance(value, list):
        return [without_file_fingerprints(item) for item in value]
    return value


def _scoped_records(
    *,
    repo: str | None = None,
    tier: str | None = None,
    backend: str | None = None,
    scenario: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if tier is not None and tier not in KNOWLEDGE_SCOPES:
        raise ValueError(f"Unknown knowledge tier: {tier}")
    scenario = SCENARIO_ALIASES.get(scenario, scenario)
    eligible = []
    excluded = {"tier": 0, "repo": 0, "backend": 0, "scenario": 0}
    for record in knowledge_records():
        if tier and record.get("tier", "contribution") != tier:
            excluded["tier"] += 1
            continue
        if repo and record["repo"] != repo:
            excluded["repo"] += 1
            continue
        if backend and record["backend"] not in (backend, "common"):
            excluded["backend"] += 1
            continue
        if scenario:
            declared = record.get("scenario", "")
            if declared != scenario and not (
                declared.endswith(".*") and scenario.startswith(declared[:-1])
            ):
                excluded["scenario"] += 1
                continue
        eligible.append(record)
    return eligible, excluded


def _catalog_corpus(records: list[dict[str, Any]]) -> tuple[Corpus, list[dict[str, Any]]]:
    from .knowledge_find import Corpus, installed_skill_projection, load_documents

    by_id = {record["id"]: record for record in records}
    kinds = ("record",)
    if any(record.get("index_type") == "packaged-skill" for record in records):
        kinds = ("skill", "record")
    documents, document_records = [], []
    for document in load_documents(kinds=kinds, records=records):
        record = (
            by_id[document.identity] if document.kind == "record"
            else installed_skill_projection(document, by_id)
        )
        if record is not None:
            # Keep the native identity and source state for Find's ties. The
            # corresponding record supplies the exact package ID and payload.
            documents.append(document)
            document_records.append(record)
    return Corpus(documents), document_records


def search_knowledge(
    query: str = "",
    *,
    repo: str | None = None,
    tier: str | None = None,
    backend: str | None = None,
    scenario: str | None = None,
    limit: int = 10,
    explain: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List exact package records, using Find when a text query is supplied."""
    if limit < 1:
        raise ValueError("limit must be positive")
    records, excluded = _scoped_records(repo=repo, tier=tier, backend=backend, scenario=scenario)
    ranking = bool(query.strip())
    if ranking:
        from .knowledge_find import rank

        corpus, document_records = _catalog_corpus(records)
        _, _, scored = rank(query, corpus)
        matches = [
            (document_records[index], score, components) for score, _, index, components in scored
        ]
    else:
        matches = [
            (record, None, None) for record in sorted(records, key=lambda record: record["id"])
        ]

    returned = matches[:limit]
    items = [record for record, _, _ in returned]
    if not explain:
        return items
    from ._skill_selection import FIND_RELEVANCE

    observed = []
    for position, (record, score, components) in enumerate(returned, 1):
        data = json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        item = {"ref": "package:" + record["id"], "rank": position,
                "revision": "catalog-sha256:" + hashlib.sha256(data).hexdigest()}
        if score is not None:
            item.update(score=round(score, 2), components=components)
        observed.append(item)
    retrieval = observation(
        entrypoint="knowledge search",
        request={"query": query, "repo": repo, "tier": tier, "backend": backend,
                 "scenario": SCENARIO_ALIASES.get(scenario, scenario), "limit": limit,
                 "sources": ["package"]},
        selection={
            "method": FIND_RELEVANCE if ranking else None, "scope": "package-records",
            "ranking_applied": ranking, "state": "applied" if ranking else "not_requested",
            "tie_break": "state_then_id_then_ref" if ranking else None,
        },
        items=observed,
        counts={
            "considered": len(records) + sum(excluded.values()),
            "matched": len(matches), "returned": len(items),
            "excluded": {**excluded, "query": len(records) - len(matches),
                         "item_limit": len(matches) - len(items)},
        },
        assembly="not_requested",
    )
    if ranking:
        retrieval["calls"].append("find")
    return {"items": items, "retrieval": retrieval}


def lookup_record(record_id: str) -> dict | None:
    """Validate a single package owner without parsing unrelated records or skill sidecars."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", record_id):
        return None
    root = files("inferrsi").joinpath("knowledge", "data", "skill_library")
    item = root.joinpath("records", record_id + ".json")
    record = _authored_record(item) if item.is_file() else None
    if re.fullmatch(r"inferrsi\.[a-z0-9]+\.skills\.[a-z0-9_]+", record_id):
        for view in skill_views(root, record_id=record_id):
            if record is not None:
                raise ValueError(f"Duplicate knowledge ID: {record_id}")
            _validate_record(view, "inferrsi", (view["backend"], "skills", view["title"] + ".json"))
            record = view
    return record


def get_knowledge(record_id: str) -> dict[str, Any]:
    record = lookup_record(record_id)
    if record is None:
        raise ValueError(f"Unknown knowledge ID: {record_id}")
    return record
