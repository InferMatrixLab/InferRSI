"""Read-only package-data catalog. Knowledge text is never executable."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.resources import files
from typing import Any

from ..resources.repository_packs import REPO_TYPES
from ._skill_view import skill_views

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


def knowledge_records(
    *, file_fingerprints: bool = True, include_skill_views: bool = True,
) -> list[dict[str, Any]]:
    root = files("inferrsi").joinpath("knowledge", "data", "skill_library")
    records = []
    authored = root.joinpath("records")
    for item in sorted(authored.iterdir(), key=lambda p: p.name):
        if item.name == "README.md":
            continue
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
        records.append(record)
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
    if limit < 1:
        raise ValueError("limit must be positive")
    if tier is not None and tier not in KNOWLEDGE_SCOPES:
        raise ValueError(f"Unknown knowledge tier: {tier}")
    scenario = SCENARIO_ALIASES.get(scenario, scenario)
    tokens = re.findall(r"[\w.-]+", query.casefold())
    scored = []
    records = knowledge_records()
    excluded = {"tier": 0, "repo": 0, "backend": 0, "scenario": 0, "query": 0}
    explanations = {}
    for record in records:
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
        document = json.dumps(record, ensure_ascii=False).casefold()
        if any(token not in document for token in tokens):
            excluded["query"] += 1
            continue
        score = sum(document.count(token) for token in tokens)
        if explain:
            explanations[record["id"]] = [
                {"term": token, "occurrences": document.count(token)} for token in tokens]
        scored.append((score, record["id"], record))
    scored.sort(key=lambda item: (-item[0], item[1]))
    items = [item[2] for item in scored[:limit]]
    if not explain:
        return items
    from .retrieval import observation

    return {"items": items, "retrieval": observation(
        entrypoint="knowledge search",
        request={"query": query, "repo": repo, "tier": tier, "backend": backend,
                 "scenario": scenario, "limit": limit, "sources": ["package"]},
        selection={"method": "catalog-occurrences-v1", "scope": "package-records",
                   "ranking_applied": True, "state": "applied", "tie_break": "id_ascending"},
        items=[{"ref": "package:" + identity, "rank": rank, "score": score,
                "revision": "catalog-sha256:" + hashlib.sha256(json.dumps(
                    record, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                "components": explanations[identity]}
               for rank, (score, identity, record) in enumerate(scored[:limit], 1)],
        counts={"considered": len(records), "matched": len(scored), "returned": len(items),
                "excluded": {**excluded, "item_limit": max(0, len(scored) - limit)}},
        assembly="not_requested",
    )}


def get_knowledge(record_id: str) -> dict[str, Any]:
    for record in knowledge_records():
        if record["id"] == record_id:
            return record
    raise ValueError(f"Unknown knowledge ID: {record_id}")
