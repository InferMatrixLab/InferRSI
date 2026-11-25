"""Read-only model-aware discovery; target annotations are not runtime support."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from importlib.resources import files

from .catalog import _catalog_corpus, _scoped_records
from .knowledge_find import rank
from .ranking_policy import DEFAULT_RANKING_POLICY, RankingPolicy

PROCEDURE = (
    "data/skill_library/workflows/research/inference-engine-research/"
    "references/model-aware-preparation.md"
)


def _profile(model: str) -> dict | None:
    config = files("inferrsi").joinpath("knowledge", "data", "skill_library", "config")
    root = config.joinpath("research_profiles")
    for resource in sorted(root.iterdir(), key=lambda path: path.name):
        if resource.name.endswith(".json"):
            profile = json.loads(resource.read_text(encoding="utf-8"))
            if model.casefold() in {name.casefold() for name in profile["aliases"]}:
                return profile
    return None


def research_knowledge(
    model: str,
    *,
    frameworks: Sequence[str] = (),
    tasks: Sequence[str] = (),
    modalities: Sequence[str] = (),
    mechanisms: Sequence[str] = (),
    repo: str | None = None,
    tier: str | None = None,
    backend: str | None = None,
    scenario: str | None = None,
    limit: int = 10,
    target_backend: str | None = None,
    target_device: str | None = None,
    target_memory_gib: float | None = None,
    ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
) -> dict:
    """Union separate research queries, preserving every package filter and record.

    Round-robin selection gives each query a turn before another result from the
    same query. It is discovery ordering, not an engine or evidence-quality rank.
    """
    if not model.strip():
        raise ValueError("model must be nonempty")
    if limit < 1:
        raise ValueError("limit must be positive")
    if target_memory_gib is not None and (
        not math.isfinite(target_memory_gib) or target_memory_gib <= 0
    ):
        raise ValueError("target memory must be positive and finite GiB")
    model = model.strip()
    profile = _profile(model)
    defaults = profile or {}
    groups = {
        "model": [model, *([profile["model"]] if profile else [])],
        "framework": frameworks,
        "task": [*defaults.get("tasks", []), *tasks],
        "modality": [*defaults.get("modalities", []), *modalities],
        "mechanism": [*defaults.get("mechanisms", []), *mechanisms],
    }
    filters = {"repo": repo, "tier": tier, "backend": backend, "scenario": scenario}
    queries, streams, matches = [], [], {}
    scoped, _ = _scoped_records(**filters)
    corpus, document_records = _catalog_corpus(scoped)
    # Retain every query's matches before capping the union so overlapping
    # records keep all their query attributions.
    for group, terms in groups.items():
        seen = set()
        for term in terms:
            term = term.strip()
            if not term:
                raise ValueError(f"{group} query must be nonempty")
            if term.casefold() in seen:
                continue
            seen.add(term.casefold())
            query = {"group": group, "query": term}
            _, _, scored = rank(term, corpus, ranking_policy)
            records = [document_records[index] for _, _, index, _ in scored]
            queries.append({**query, "matches": len(records)})
            streams.append(records)
            for record in records:
                matches.setdefault(record["id"], []).append(query)
    selected = {}
    for position in range(max((len(stream) for stream in streams), default=0)):
        for stream in streams:
            if position < len(stream):
                record = stream[position]
                selected.setdefault(record["id"], record)
                if len(selected) == limit:
                    break
        if len(selected) == limit:
            break
    return {
        "model": model,
        "ranking_policy": ranking_policy.receipt(),
        "profile": profile,
        "queries": queries,
        "filters": filters,
        "items": [
            {"record": record, "matched_queries": matches[identity]}
            for identity, record in selected.items()
        ],
        "no_match": not selected,
        "target": {
            "backend": target_backend, "device": target_device, "memory_gib": target_memory_gib,
        },
        "target_validation": "unverified",
        "components": defaults.get("components", []),
        "procedure_resource": PROCEDURE,
        "worked_example_resource": defaults.get("worked_example_resource"),
        "warnings": [] if profile else [
            "No packaged model profile: supply --task/--modality and verify the full component "
            "inventory from the selected checkpoint before judging feasibility."
        ],
        "limitations": [
            "Each query uses Find's lexical ranking over installed package records eligible "
            "under the scope filters. Other sources require separate discovery.",
            "Mechanism queries are research leads, not claims of model/backend support. "
            "Retain each record's applicability, source revision and verification state.",
            "Target annotations do not inspect hardware or add a runtime backend. Full weight "
            "inventory, engine/format compatibility, peak residency and quality need evidence "
            "under the linked preparation procedure; no engine is selected or executed.",
        ],
    }
