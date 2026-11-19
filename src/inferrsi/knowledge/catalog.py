"""Read-only package-data catalog. Knowledge text is never executable."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.resources import files
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


def knowledge_records(*, file_fingerprints: bool = True) -> list[dict[str, Any]]:
    data = files("inferrsi").joinpath("knowledge", "data")
    records = []
    seen = set()
    for tier, repos in KNOWLEDGE_SCOPES.items():
        for repo in repos:
            knowledge = (
                data.joinpath("repo_packs", repo, "knowledge")
                if tier == "contribution"
                else data.joinpath("knowledge_packs", tier, repo)
            )
            if not knowledge.is_dir():
                continue
            snapshot = knowledge.joinpath(_source_snapshot.MANIFEST)
            snapshot = (
                json.loads(snapshot.read_text(encoding="utf-8")) if snapshot.is_file() else None
            )
            for parts, item in _walk(knowledge):
                if not item.name.endswith(".json") or parts == (_source_snapshot.MANIFEST,):
                    continue
                record = json.loads(item.read_text(encoding="utf-8"))
                # Generated skill records store schema v2; readers always receive schema v1.
                # A pack with a snapshot holds only generated records.
                if isinstance(record, dict) and record.get("schema_version") == (
                    _source_snapshot.STORED_SCHEMA
                ):
                    if snapshot is None:
                        raise ValueError(f"Knowledge record lacks its source snapshot: {repo}")
                    if file_fingerprints:
                        record = _source_snapshot.resolve(record, snapshot)
                    else:
                        revision = snapshot.get("source_revision")
                        if not isinstance(revision, str) or not re.fullmatch(
                            r"[0-9a-f]{40}", revision
                        ):
                            raise ValueError("Knowledge source commit is unavailable")
                        record = {
                            **record,
                            "schema_version": 1,
                            "sources": [
                                {
                                    "type": "git",
                                    "commit": revision,
                                    "url": _source_snapshot.REPOSITORY + "/tree/" + revision,
                                }
                            ],
                        }
                elif snapshot is not None:
                    raise ValueError(
                        f"Source-snapshot pack holds a record that is not schema "
                        f"{_source_snapshot.STORED_SCHEMA}: {repo}/{'/'.join(parts)}"
                    )
                if not file_fingerprints:
                    record = without_file_fingerprints(record)
                _validate_record(record, repo, parts, tier)
                if record["id"] in seen:
                    raise ValueError(f"Duplicate knowledge ID: {record['id']}")
                seen.add(record["id"])
                records.append(record)
    return records


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


def get_knowledge(record_id: str) -> dict[str, Any]:
    for record in knowledge_records():
        if record["id"] == record_id:
            return record
    raise ValueError(f"Unknown knowledge ID: {record_id}")
