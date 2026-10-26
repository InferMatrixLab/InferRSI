"""Knowledge contracts only: no agent/model efficacy or accelerator execution."""

import json
import shutil
from pathlib import Path

import pytest

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader, RevisionConflict
from inferrsi.skill_catalog import skill_reference

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "src/inferrsi/data/skill_library"
OWNER = "methods/optimization-search-policy"
IDENTITY = "inferrsi.common.skills.optimization_search_policy"
NEW_CASES = (
    "sarathi-chunk-budget",
    "paged-kv-allocation",
    "prefix-reuse-locality",
    "distserve-phase-placement",
    "cuda-copy-overlap",
)


def test_case_identity_sources_and_existing_observation_are_preserved():
    reader = KnowledgeReader(skill_root=ROOT)
    for slug in NEW_CASES:
        bundle = reader.read(f"case.{slug}")
        assert bundle.metadata["state"] == "candidate"
        assert bundle.metadata["empirical_validation"] == "not_run"
        assert bundle.metadata["origin"] == ["external"]
        assert bundle.metadata["applicability"] and bundle.metadata["limitations"]
        assert bundle.metadata["attribution"]
        assert all(source["version"] for source in bundle.metadata["sources"])
        assert all(source["type"] in {"paper", "document"}
                   for source in bundle.metadata["sources"])
        assert bundle.content[f"{slug}.md"] == (ROOT / OWNER / "cases" / f"{slug}.md").read_bytes()
        assert bundle.view()["revision"] == bundle.revision

    # One historical ID and its original evidence remain with the original owner.
    existing = reader.read("case.admission-drain-occupancy")
    assert existing.metadata["state"] == "historical_observation"
    assert "Campaign INCONCLUSIVE" in existing.metadata["limitations"]
    reference = "../inference-optimization-casebook/cases/admission-drain-occupancy.md"
    assert skill_reference(ROOT, "optimization-search-policy", reference) == skill_reference(
        ROOT, "inference-benchmark-design", reference,
    )


def test_checkout_reference_closure_and_source_drift(tmp_path):
    library = tmp_path / "library"
    shutil.copytree(ROOT, library)
    reader = KnowledgeReader(skill_root=library)
    bundle = reader.read("optimization-search-policy")
    expected = {
        f"{OWNER}/references/foundational-mechanism-decisions.md",
        f"{OWNER}/references/foundational-sources.md",
        "methods/assess-serving-preemption/references/source-notes.md",
        "methods/inference-optimization-casebook/cases/admission-drain-occupancy.json",
        "repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md",
        "repositories/lmcache/kv-tier-management/SKILL.md",
        "repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md",
    }
    assert expected <= bundle.content.keys()
    case = reader.read("case.prefix-reuse-locality")
    path = library / OWNER / "cases/prefix-reuse-locality.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["sources"][0]["version"] = "fixture-changed-version"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(RevisionConflict):
        reader.read("case.prefix-reuse-locality", revision=case.revision)
    with pytest.raises(RevisionConflict):
        reader.read("optimization-search-policy", revision=bundle.revision)


def test_packaged_discovery_and_complete_bounded_context():
    assert IDENTITY in {r["id"] for r in search_knowledge("whole-system", repo="inferrsi")}
    record = get_knowledge(IDENTITY)
    assert not record["verification"]["locally_verified"]
    assert record["skill_metadata"]["empirical_validation"] == "not_run"
    reader = KnowledgeReader()
    # A context budget must not silently drop prerequisites or counterexamples.
    small = reader.collect(ids=[IDENTITY], context_bytes=1)
    assert not small["contexts"]
    omission, = small["context_omissions"]
    assert omission["reason"] == "context_limit"
    result = reader.collect(ids=[IDENTITY], context_bytes=omission["required_bytes"])
    assert not result["context_omissions"]
    context, = result["contexts"]
    resources = {r["path"]: r["content"] for r in context["resources"]}
    prefix = f"data/skill_library/{OWNER}/"
    assert prefix + "references/foundational-mechanism-decisions.md" in resources
    for slug in NEW_CASES:
        for suffix in ("md", "json"):
            path = prefix + f"cases/{slug}.{suffix}"
            assert resources[path].encode() == reader.resource(
                IDENTITY, path, revision=context["revision"],
            )


@pytest.mark.parametrize("fixture", json.loads(
    (Path(__file__).parent / "fixtures/foundational_selection.json").read_text(encoding="utf-8")
), ids=lambda fixture: fixture["name"])
def test_frozen_method_selection_or_abstention(fixture):
    # Actual lexical Collect, not a fixture-only router or an LLM grader.
    result = KnowledgeReader().collect(
        relevance=fixture["cue"], backend=fixture.get("backend"),
        repo="inferrsi", limit=3,
    )
    identities = {item["id"] for item in result["items"]}
    if fixture["expected"] is None:
        assert result["no_match"] and not identities
    else:
        assert fixture["expected"] in identities
    assert not (set(fixture["excluded"]) & identities)


def test_missing_measurement_and_training_boundaries_reach_the_reader():
    # Text availability is the contract; this does not prove an agent obeys it.
    bundle = KnowledgeReader(skill_root=ROOT).read("optimization-search-policy")
    guide = bundle.content[f"{OWNER}/references/foundational-mechanism-decisions.md"].decode()
    core = bundle.content[f"{OWNER}/SKILL.md"].decode()
    assert "abstain and request\n   measurement" in guide
    assert "apply only to training" in guide
    assert "not an automatic stall detector" in core
