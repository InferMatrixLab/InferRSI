"""Research discovery broadens queries without qualifying engines or hardware."""

import json
import math
from importlib.resources import files

import pytest

from inferrsi import catalog
from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.cli import main
from inferrsi.research import research_knowledge


def test_h3_retrieves_framework_and_task_knowledge_with_source_boundaries():
    result = research_knowledge(
        "MiniMax-H3", frameworks=["mlx"], target_backend="metal",
        target_device="M5 Mac Studio", target_memory_gib=64, limit=12,
    )
    queries = {(item["group"], item["query"]) for item in result["queries"]}
    assert ("model", "MiniMax-H3") in queries
    assert ("framework", "mlx") in queries
    assert ("task", "diffusion") in queries
    assert ("modality", "video") in queries
    assert ("modality", "audio") in queries
    assert any(group == "mechanism" for group, _ in queries)
    items = result["items"]
    identities = [item["record"]["id"] for item in items]
    assert len(identities) == len(set(identities)) <= 12
    # Corpus additions can reorder matches; the independent framework query still contributes.
    framework_first = search_knowledge("mlx", limit=1)[0]["id"]
    assert any(
        item["record"]["id"] == framework_first
        and {"group": "framework", "query": "mlx"} in item["matched_queries"]
        for item in items
    )
    assert set(result["profile"]["knowledge_ids"]) <= set(identities)
    assert any("diffusion" in item["record"]["scenario"] for item in items)
    assert any(
        match["group"] == "modality" and match["query"] == "video"
        for item in items for match in item["matched_queries"]
    )
    for item in items:
        assert item["record"] == get_knowledge(item["record"]["id"])
        assert item["record"]["verification"]["locally_verified"] is False
    assert result["target"]["memory_gib"] == 64
    assert result["target"]["backend"] == "metal"
    assert result["target_validation"] == "unverified"
    assert "metal" not in catalog.BACKENDS
    assert {part["role"] for part in result["components"]} == {
        "denoiser", "text_encoder", "video_vae", "audio_vae",
    }
    assert result["profile"]["input_modalities"] == ["text", "image", "video", "audio"]
    assert result["profile"]["output_modalities"] == ["video", "audio"]


def test_independent_queries_are_unioned_fairly_and_exact_search_is_unchanged(monkeypatch):
    records = [
        {"id": name, "repo": "vllm_omni", "backend": "common", "scenario": "diffusion.*",
         "summary": summary}
        for name, summary in (
            ("a-model", "ExampleModel"),
            ("b-framework", "mlx"),
            ("c-task", "diffusion"),
            ("d-modality", "video"),
            ("e-mechanism", "offload"),
            ("f-overlap", "ExampleModel mlx diffusion video offload"),
        )
    ]
    monkeypatch.setattr(catalog, "knowledge_records", lambda: records)
    exact = search_knowledge("ExampleModel mlx diffusion video offload")
    assert [record["id"] for record in exact] == ["f-overlap"]
    result = research_knowledge(
        "ExampleModel", frameworks=["mlx", "MLX"], tasks=["diffusion"],
        modalities=["video"], mechanisms=["offload"], limit=6,
    )
    assert len(result["queries"]) == 5  # same-dimension duplicates are case insensitive
    assert {item["record"]["id"] for item in result["items"]} == {
        record["id"] for record in records
    }
    overlap = next(item for item in result["items"] if item["record"]["id"] == "f-overlap")
    assert len(overlap["matched_queries"]) == 5
    assert search_knowledge("ExampleModel mlx diffusion video offload") == exact
    limited = research_knowledge(
        "ExampleModel", frameworks=["mlx"], tasks=["diffusion"],
        modalities=["video"], mechanisms=["offload"], limit=5,
    )
    assert len(limited["items"]) == 5
    assert {item["record"]["id"] for item in limited["items"]} == {
        "a-model", "b-framework", "c-task", "d-modality", "e-mechanism",
    }


def test_query_attribution_survives_the_shared_output_limit(monkeypatch):
    records = [
        {"id": "model", "summary": "SyntheticModel mlx"},
        {"id": "framework", "summary": "mlx mlx"},
    ]
    monkeypatch.setattr(catalog, "knowledge_records", lambda: records)
    result = research_knowledge("SyntheticModel", frameworks=["mlx"], limit=1)
    assert result["items"] == [{
        "record": records[0],
        "matched_queries": [
            {"group": "model", "query": "SyntheticModel"},
            {"group": "framework", "query": "mlx"},
        ],
    }]
    assert [query["matches"] for query in result["queries"]] == [1, 2]


def test_research_retains_all_package_filters_and_no_match():
    result = research_knowledge(
        "MiniMax-H3", frameworks=["mlx"], repo="vllm_omni", tier="contribution",
        backend="ascend", scenario="diffusion.t2v", limit=100,
    )
    assert result["items"]
    allowed = {
        item["id"] for item in search_knowledge(
            repo="vllm_omni", tier="contribution", backend="ascend",
            scenario="diffusion.video_generation", limit=100,
        )
    }
    assert {item["record"]["id"] for item in result["items"]} <= allowed
    assert result["filters"]["backend"] == "ascend"
    assert any(item["matches"] == 0 for item in result["queries"])
    empty = research_knowledge("MiniMax-H3", repo="vllm_rlt")
    assert empty["items"] == []
    assert empty["no_match"] is True


def test_unknown_model_never_invents_tasks_or_components():
    result = research_knowledge("UnknownSyntheticModel")
    assert [(item["group"], item["query"]) for item in result["queries"]] == [
        ("model", "UnknownSyntheticModel"),
    ]
    assert result["profile"] is None
    assert result["components"] == []
    assert result["warnings"]
    explicit = research_knowledge(
        "UnknownSyntheticModel", tasks=["diffusion"], modalities=["video"]
    )
    assert {item["group"] for item in explicit["queries"]} == {"model", "task", "modality"}


@pytest.mark.parametrize("alias", ["MiniMax-H3", "minimax h3", "MiniMax_H3"])
def test_model_profile_links_packaged_resources_at_the_repository_owner(alias):
    result = research_knowledge(alias)
    package = files("inferrsi")
    profile = result["profile"]
    assert profile["model"] == "MiniMax-H3"
    assert package.joinpath(result["procedure_resource"]).read_text(encoding="utf-8")
    assert result["worked_example_resource"] == profile["worked_example_resource"]
    for key in ("skill_resource", "worked_example_resource", "inventory_resource"):
        resource = profile[key]
        assert resource.startswith("data/skill_library/repositories/h3-c/")
        assert package.joinpath(resource).read_text(encoding="utf-8")
    record = get_knowledge(profile["knowledge_ids"][0])
    assert record["skill_documents"]["original"] == profile["skill_resource"]


@pytest.mark.parametrize("memory", [0, -1, math.inf, math.nan])
def test_target_memory_must_be_positive_and_finite(memory):
    with pytest.raises(ValueError, match="memory"):
        research_knowledge("MiniMax-H3", target_memory_gib=memory)


def test_public_cli_exposes_model_profile_and_keeps_filters(capsys):
    assert main([
        "knowledge", "research", "minimax-h3", "--framework", "mlx",
        "--target-backend", "metal", "--target-device", "M5 Mac Studio",
        "--target-memory-gib", "64", "--limit", "12",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"]["model"] == "MiniMax-H3"
    assert result["profile"]["sources"]
    assert result["target"]["device"] == "M5 Mac Studio"
    assert result["target_validation"] == "unverified"
    framework_first = search_knowledge("mlx", limit=1)[0]["id"]
    assert any(
        item["record"]["id"] == framework_first
        and {"group": "framework", "query": "mlx"} in item["matched_queries"]
        for item in result["items"]
    )
    assert main([
        "knowledge", "research", "MiniMax-H3", "--repo-type", "vllm_rlt",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["no_match"] is True
    with pytest.raises(SystemExit) as error:
        main(["knowledge", "research", "MiniMax-H3", "--target-memory-gib", "-1"])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        main(["knowledge", "research", "MiniMax-H3", "--backend", "metal"])
    assert error.value.code == 2


@pytest.mark.parametrize("model,kwargs", [("", {}), ("Example", {"frameworks": [" "]}),
                                         ("Example", {"limit": 0})])
def test_invalid_research_inputs_fail_explicitly(model, kwargs):
    with pytest.raises(ValueError):
        research_knowledge(model, **kwargs)
