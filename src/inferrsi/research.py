"""Read-only model-aware discovery; target annotations are not runtime support."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from importlib.resources import files

from .catalog import knowledge_records, search_knowledge

PROCEDURE = (
    "data/skill_library/workflows/inference-engine-research/"
    "references/model-aware-preparation.md"
)


def _profile(model: str) -> dict | None:
    root = files("inferrsi").joinpath("data", "research_profiles")
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
    # Retrieve every scoped match before applying the shared output limit; an
    # early per-query limit would lose attribution for overlapping records.
    catalog_size = max(1, len(knowledge_records()))
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
            records = search_knowledge(term, **filters, limit=catalog_size)
            queries.append({**query, "matches": len(records)})
            streams.append(records)
            for record in records:
                matches.setdefault(record["id"], []).append(query)
    selected = {}
    for rank in range(max((len(stream) for stream in streams), default=0)):
        for stream in streams:
            if rank < len(stream):
                record = stream[rank]
                selected.setdefault(record["id"], record)
                if len(selected) == limit:
                    break
        if len(selected) == limit:
            break
    return {
        "model": model,
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
            "Queries search installed package records only; empty results do not rule out "
            "external sources. Existing token-AND search and scope filters are unchanged.",
            "Mechanism queries are research leads, not claims of model/backend support. "
            "Retain each record's applicability, source revision and verification state.",
            "Target annotations do not inspect hardware or add a runtime backend. Full weight "
            "inventory, engine/format compatibility, peak residency and quality need evidence "
            "under the linked preparation procedure; no engine is selected or executed.",
        ],
    }
