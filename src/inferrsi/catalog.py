"""Read-only package-data catalog. Knowledge text is never executable."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

REPO_TYPES = ("vllm", "vllm_omni", "afd_plugin", "vllm_rlt", "strata", "sglang", "sglang_omni")
# Learning scope does not imply that a repository has a runnable target adapter.
# Legacy repository-pack records retain their contribution tier; an independent
# peer card can describe a different learning use case for the same source repo.
KNOWLEDGE_SCOPES = {
    "contribution": (*REPO_TYPES, "vllm_ascend", "inferrsi"),
    "dependency": (
        "flashinfer", "flashattention", "pytorch", "triton", "diffusers", "transformers"
    ),
    "peer": (
        "sglang", "tensorrt_llm", "lmdeploy", "xdit", "cache_dit",
        "qwen3_tts_engine", "minicpmo_single_gpu_engine",
    ),
}
KNOWLEDGE_REPOS = tuple(
    dict.fromkeys(repo for repos in KNOWLEDGE_SCOPES.values() for repo in repos)
)
BACKENDS = ("cpu", "cuda", "rocm", "ascend")
SCENARIO_ALIASES = {
    "diffusion.t2i": "diffusion.image_generation",
    "diffusion.t2v": "diffusion.video_generation",
}


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


def knowledge_records() -> list[dict[str, Any]]:
    data = files("inferrsi").joinpath("data")
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
            for parts, item in _walk(knowledge):
                if not item.name.endswith(".json"):
                    continue
                record = json.loads(item.read_text(encoding="utf-8"))
                _validate_record(record, repo, parts, tier)
                if record["id"] in seen:
                    raise ValueError(f"Duplicate knowledge ID: {record['id']}")
                seen.add(record["id"])
                records.append(record)
    return records


def search_knowledge(
    query: str = "",
    *,
    repo: str | None = None,
    tier: str | None = None,
    backend: str | None = None,
    scenario: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if tier is not None and tier not in KNOWLEDGE_SCOPES:
        raise ValueError(f"Unknown knowledge tier: {tier}")
    scenario = SCENARIO_ALIASES.get(scenario, scenario)
    tokens = re.findall(r"[\w.-]+", query.casefold())
    scored = []
    for record in knowledge_records():
        if tier and record.get("tier", "contribution") != tier:
            continue
        if repo and record["repo"] != repo:
            continue
        if backend and record["backend"] not in (backend, "common"):
            continue
        if scenario:
            declared = record.get("scenario", "")
            if declared != scenario and not (
                declared.endswith(".*") and scenario.startswith(declared[:-1])
            ):
                continue
        document = json.dumps(record, ensure_ascii=False).casefold()
        if any(token not in document for token in tokens):
            continue
        score = sum(document.count(token) for token in tokens)
        scored.append((score, record["id"], record))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:limit]]


def get_knowledge(record_id: str) -> dict[str, Any]:
    for record in knowledge_records():
        if record["id"] == record_id:
            return record
    raise ValueError(f"Unknown knowledge ID: {record_id}")


def repository_pack(repo_type: str) -> dict[str, Any]:
    if repo_type not in REPO_TYPES:
        raise ValueError(f"Unknown repository type: {repo_type}")
    path = files("inferrsi").joinpath("data", "repo_packs", repo_type, "pack.json")
    return json.loads(path.read_text(encoding="utf-8"))
