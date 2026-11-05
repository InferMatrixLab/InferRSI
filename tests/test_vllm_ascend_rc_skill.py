import re
from pathlib import Path

import pytest

from inferrsi.catalog import search_knowledge
from inferrsi.skill_catalog import skill_instructions, skill_metadata, skill_resource

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
NAME = "vllm-ascend"


@pytest.mark.parametrize(("query", "route"), [
    ("v0.27.1rc1 plugin registration", "plugin-registration.md"),
    ("MiniMax-M3 FP8", "minimax-cache.md"),
    ("DeepSeek-V4-Flash DSpark", "dspark-pd.md"),
])
def test_release_skill_is_discoverable_and_its_routes_ship(query, route):
    results = search_knowledge(query, repo="inferrsi", backend="ascend", limit=3)
    assert any(item["id"] == "inferrsi.ascend.skills.vllm_ascend" for item in results)
    relative = f"references/{route}"
    assert f"]({relative})" in skill_instructions(LIBRARY, NAME)
    assert "](sources.md)" in skill_resource(LIBRARY, NAME, relative).read_text()


def test_release_skill_distinguishes_source_coverage_from_native_validation():
    metadata = skill_metadata(LIBRARY, NAME)
    assert metadata["status"] == "candidate" and metadata["empirical_validation"] == "not_run"
    source, = metadata["sources"]
    notes = skill_resource(LIBRARY, NAME, source["readset"]).read_text()
    prefix = f'{source["url"]}/blob/{source["commit"]}/'
    assert set(re.findall(re.escape(prefix) + r"([^#]+)#L\d+\)", notes)) == set(source["paths"])
    assert "outside this RC's declared scope" in skill_instructions(LIBRARY, NAME)
