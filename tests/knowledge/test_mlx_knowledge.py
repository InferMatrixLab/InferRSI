from pathlib import Path

import pytest

from inferrsi.knowledge.catalog import get_knowledge
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.skill_catalog import skill_metadata, skill_resource
from tests.knowledge._catalog_find import find_package_records

LIBRARY = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/data/skill_library"


@pytest.mark.parametrize(
    ("skill", "owner", "commit", "resource", "marker"),
    [
        (
            "lazy-evaluation-stream-lifetimes", "frameworks/mlx",
            "bff10220c742907f0c68e55ff174aaea56f74e3d", "source-map.md", "TEST-SOURCE",
        ),
        (
            "generation-cache-lifecycle", "engines/mlx-lm",
            "ab7f7048dc341ced2d84b1887eeb17d60b0d1b02", "cache-stop.md", "LRUPromptCache",
        ),
    ],
    ids=["mlx", "mlx-lm"],
)
def test_mlx_candidate_preserves_source_state_and_owner_resources(
    skill, owner, commit, resource, marker
):
    metadata = skill_metadata(LIBRARY, skill)
    assert metadata["status"] == "candidate"
    assert metadata["empirical_validation"] == "not_run"
    assert metadata["sources"][0]["commit"] == commit
    path = skill_resource(LIBRARY, skill, f"references/{resource}")
    assert path.is_relative_to(LIBRARY / "systems" / owner / skill)
    assert marker in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("query", "identity", "resources", "marker"),
    [
        (
            "mlx", "inferrsi.common.skills.lazy_evaluation_stream_lifetimes",
            ("source-map.md", "execution-lifetime.md"), b"source-derived candidate",
        ),
        (
            "mlx-lm", "inferrsi.common.skills.generation_cache_lifecycle",
            ("source-map.md", "generation-batch.md", "cache-stop.md", "validation.md"),
            b"cooperative",
        ),
    ],
    ids=["mlx", "mlx-lm"],
)
def test_mlx_packaged_guidance_is_discoverable_and_complete(query, identity, resources, marker):
    record = get_knowledge(identity)
    assert record in find_package_records(query, repo="inferrsi", limit=100)
    assert record["backend"] == "common"
    assert record["verification"]["locally_verified"] is False
    bundle = KnowledgeReader(skill_root=LIBRARY).read(identity)
    assert bundle.metadata["kind"] == "knowledge"
    for resource in resources:
        assert any(name.endswith(f"references/{resource}") for name in bundle.content)
    assert any(marker in content for content in bundle.content.values())
