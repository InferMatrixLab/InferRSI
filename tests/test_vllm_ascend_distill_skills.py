from pathlib import Path

import pytest

from inferrsi.catalog import search_knowledge
from inferrsi.skill_catalog import skill_instructions, skill_metadata, skill_resource

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"


@pytest.mark.parametrize(
    ("query", "expected_skill_id"),
    [
        # Query 1: ACLGraph capture/replay runtime contract
        (
            "ACLGraph capture replay",
            "inferrsi.ascend.skills.ascend_aclgraph_capture_replay",
        ),
        (
            "vLLM-Ascend ACLGraph",
            "inferrsi.ascend.skills.ascend_aclgraph_capture_replay",
        ),
        # Query 2: Model adaptation and FP8 checkpoint onboarding
        (
            "FP8 checkpoint",
            "inferrsi.ascend.skills.ascend_model_adaptation",
        ),
        # Query 3: KV replication with Tensor Parallelism
        (
            "KV replication TP",
            "inferrsi.ascend.skills.ascend_model_adaptation",
        ),
        # Query 4: Multimodal feature validation
        (
            "multimodal feature validation",
            "inferrsi.ascend.skills.ascend_model_adaptation",
        ),
    ],
)
def test_batch1_skills_are_discoverable_for_representative_queries(
    query, expected_skill_id
):
    results = search_knowledge(query, repo="inferrsi", backend="ascend", limit=5)
    skill_ids = [item["id"] for item in results]
    assert expected_skill_id in skill_ids, (
        f"Query {query!r} expected {expected_skill_id} in {skill_ids}"
    )


def test_aclgraph_skill_metadata_and_contracts():
    meta = skill_metadata(LIBRARY, "ascend-aclgraph-capture-replay")
    assert meta["status"] == "candidate"
    assert meta["empirical_validation"] == "not_run"
    assert "references/source-notes.md" in meta["provenance_readsets"]

    notes = skill_resource(
        LIBRARY, "ascend-aclgraph-capture-replay", "references/source-notes.md"
    ).read_text(encoding="utf-8")
    assert "8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf" in notes
    assert "acl_graph.py" in notes

    inst = skill_instructions(LIBRARY, "ascend-aclgraph-capture-replay")
    assert "cudagraph_capture_sizes" in inst
    assert "ENPU" in inst


def test_model_adaptation_skill_metadata_and_contracts():
    meta = skill_metadata(LIBRARY, "ascend-model-adaptation")
    assert meta["status"] == "candidate"
    assert meta["empirical_validation"] == "not_run"
    assert "references/source-notes.md" in meta["provenance_readsets"]

    notes = skill_resource(
        LIBRARY, "ascend-model-adaptation", "references/source-notes.md"
    ).read_text(encoding="utf-8")
    assert "bc8115ed7fdc7e500320b5de70742ef049b4c1a2" in notes
    assert "Three-Tier Responsibility" in notes

    inst = skill_instructions(LIBRARY, "ascend-model-adaptation")
    assert "--load-format dummy" in inst
    assert "weight_scale_inv" in inst
    assert "tp_size > num_key_value_heads" in inst
