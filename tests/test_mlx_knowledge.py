"""MLX knowledge reads require neither MLX installation nor device execution."""

from pathlib import Path

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import skill_metadata, skill_resource

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
SKILL = "lazy-evaluation-stream-lifetimes"
IDENTITY = "inferrsi.common.skills.lazy_evaluation_stream_lifetimes"


def test_mlx_candidate_preserves_source_state_and_owner_resources():
    metadata = skill_metadata(LIBRARY, SKILL)
    assert metadata["status"] == "candidate"
    assert metadata["empirical_validation"] == "not_run"
    assert metadata["sources"][0]["commit"] == (
        "bff10220c742907f0c68e55ff174aaea56f74e3d"
    )
    resource = skill_resource(LIBRARY, SKILL, "references/source-map.md")
    assert resource.is_relative_to(LIBRARY / "frameworks/mlx" / SKILL)
    assert "TEST-SOURCE" in resource.read_text(encoding="utf-8")


def test_mlx_packaged_guidance_is_discoverable_and_complete():
    record = get_knowledge(IDENTITY)
    assert record in search_knowledge("mlx", repo="inferrsi", limit=100)
    assert record["backend"] == "common"
    assert record["verification"]["locally_verified"] is False
    bundle = KnowledgeReader(skill_root=LIBRARY).read(IDENTITY)
    assert bundle.metadata["kind"] == "knowledge"
    assert any(name.endswith("references/source-map.md") for name in bundle.content)
    assert any(name.endswith("references/execution-lifetime.md") for name in bundle.content)
    assert any(b"source-derived candidate" in content for content in bundle.content.values())
