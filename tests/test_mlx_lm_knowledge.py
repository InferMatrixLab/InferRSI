from pathlib import Path

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import skill_metadata, skill_resource

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
SKILL = "generation-cache-lifecycle"
IDENTITY = "inferrsi.common.skills.generation_cache_lifecycle"


def test_mlx_lm_candidate_preserves_source_and_application_owner():
    metadata = skill_metadata(LIBRARY, SKILL)
    assert metadata["status"] == "candidate"
    assert metadata["empirical_validation"] == "not_run"
    assert metadata["sources"][0]["commit"] == (
        "ab7f7048dc341ced2d84b1887eeb17d60b0d1b02"
    )
    resource = skill_resource(LIBRARY, SKILL, "references/cache-stop.md")
    assert resource.is_relative_to(LIBRARY / "repositories/mlx-lm" / SKILL)
    assert "LRUPromptCache" in resource.read_text(encoding="utf-8")


def test_mlx_lm_packaged_guidance_keeps_resources_and_unverified_state():
    record = get_knowledge(IDENTITY)
    assert record in search_knowledge("mlx-lm", repo="inferrsi", limit=100)
    assert record["backend"] == "common"
    assert record["verification"]["locally_verified"] is False
    bundle = KnowledgeReader(skill_root=LIBRARY).read(IDENTITY)
    assert bundle.metadata["kind"] == "knowledge"
    for resource in ("source-map.md", "generation-batch.md", "cache-stop.md", "validation.md"):
        assert any(name.endswith(f"references/{resource}") for name in bundle.content)
    assert any(b"cooperative" in content for content in bundle.content.values())
