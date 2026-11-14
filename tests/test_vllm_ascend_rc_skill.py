import json
import re
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.catalog import search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import skill_instructions, skill_metadata, skill_resource

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/knowledge/data/skill_library"
NAME = "vllm-ascend"


@pytest.mark.parametrize(("query", "route"), [
    ("v0.27.1rc1 plugin registration", "plugin-registration.md"),
    ("MiniMax-M3 FP8", "minimax-cache.md"),
    ("DeepSeek-V4-Flash DSpark", "dspark-pd.md"),
    ("Kimi K3", "model-performance.md"),
    ("GLM5.3", "model-performance.md"),
    ("v0.27.1rc1 fusion performance", "fused-operators.md"),
    ("DSA-CP FlashComm1 Fused-MC2", "communication-config.md"),
])
def test_release_skill_is_discoverable_and_its_routes_ship(query, route):
    results = search_knowledge(query, repo="inferrsi", backend="ascend", limit=3)
    assert any(item["id"] == "inferrsi.ascend.skills.vllm_ascend" for item in results)
    relative = f"references/{route}"
    assert f"]({relative})" in skill_instructions(LIBRARY, NAME)
    body = skill_resource(LIBRARY, NAME, relative).read_text()
    assert re.search(r"\]\((sources|history-scope)\.md\)", body)


def test_release_skill_distinguishes_source_coverage_from_native_validation():
    metadata = skill_metadata(LIBRARY, NAME)
    assert metadata["status"] == "candidate" and metadata["empirical_validation"] == "not_run"
    source, = metadata["sources"]
    notes = skill_resource(LIBRARY, NAME, source["readset"]).read_text()
    prefix = f'{source["url"]}/blob/{source["commit"]}/'
    assert set(re.findall(re.escape(prefix) + r"([^#]+)#L\d+\)", notes)) == set(source["paths"])
    assert "outside this RC's declared scope" in skill_instructions(LIBRARY, NAME)

def history_module():
    path = skill_resource(LIBRARY, NAME, "scripts/screen_history.py")
    return SimpleNamespace(**runpy.run_path(str(path)))


def test_history_screen_combines_messages_paths_and_patch_evidence():
    module = history_module()
    assert module.classify("Support GLM5.3", [], False) == ["priority-models"]
    assert module.classify("Support GLM4.7", [], False) == []
    assert module.classify("Generic fix", ["vllm_ascend/models/deepseek_v4/model.py"],
                           False) == ["deepseek-v4-dspark"]
    assert module.classify("Generic optimization", [], True) == ["fusion"]


def test_history_screen_reads_git_objects_without_changing_checkout(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True)

    git("init")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    source = tmp_path / "vllm_ascend" / "operator.py"
    source.parent.mkdir()
    source.write_text("def fused_operation(): pass\n")
    git("add", ".")
    git("commit", "-m", "Introduce an operator")
    pin = git("rev-parse", "HEAD").strip()
    source.write_text("uncommitted work\n")
    before = git("status", "--porcelain")
    result = history_module().inventory(tmp_path, pin)
    assert result["reachable_commits"] == result["candidate_commits"] == 1
    record, = result["commits"]
    assert record["commit"] == pin
    assert record["runtime_patch_match"] is True
    assert record["topics"] == ["fusion"]
    assert git("status", "--porcelain") == before


def test_archived_history_preserves_separate_screening_and_semantic_levels():
    archive = Path(__file__).resolve().parents[1] / (
        "docs/reviews/vllm-ascend-0271rc1/history-inventory.json"
    )
    inventory = json.loads(archive.read_text())
    commits = inventory["commits"]
    assert len({row["commit"] for row in commits}) == inventory["candidate_commits"]
    assert inventory["candidate_commits"] <= inventory["reachable_commits"]
    for topic, count in inventory["topic_counts"].items():
        assert count == sum(topic in row["topics"] for row in commits)
    reviewed = skill_resource(LIBRARY, NAME, "references/history-reviewed.json").read_text()
    inspected = set(re.findall(r'"commit": "([a-f0-9]{40})"', reviewed))
    assert inspected <= {row["commit"] for row in commits}
    assert inventory["commit"] == skill_metadata(LIBRARY, NAME)["sources"][0]["commit"]


def test_history_screen_rejects_incomplete_history(monkeypatch, tmp_path):
    module = history_module()
    monkeypatch.setitem(
        module.inventory.__globals__, "git", lambda *args: "true\n"
    )
    with pytest.raises(ValueError, match="non-shallow"):
        module.inventory(tmp_path, "HEAD")


def test_runtime_reader_keeps_full_history_outside_the_bundle():
    bundle = KnowledgeReader().read("inferrsi.ascend.skills.vllm_ascend")
    assert all("history-inventory.json" not in key for key in bundle.content)
    prefix = "data/skill_library/repositories/vllm-ascend/"
    for relative in ("references/history-reviewed.json", "scripts/screen_history.py"):
        assert bundle.content[prefix + relative] == skill_resource(
            LIBRARY, NAME, relative
        ).read_bytes()
    record = json.loads(bundle.content["record.json"])
    assert all("history-inventory.json" not in path for path in record["sources"][0]["paths"])


def test_every_instruction_route_retains_a_readset_link():
    routes = re.findall(r"\]\((references/[^)]+\.md)\)", skill_instructions(LIBRARY, NAME))
    for route in set(routes) - {"references/sources.md"}:
        body = skill_resource(LIBRARY, NAME, route).read_text()
        assert re.search(r"\]\((sources|history-scope)\.md\)", body), route
