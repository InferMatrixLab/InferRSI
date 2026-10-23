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
    assert "inferrsi.common.skills.lazy_evaluation_stream_lifetimes" in identities
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


def test_h3_packaged_resources_cover_complete_selections_and_consistent_accounting():
    result = research_knowledge("MiniMax-H3")
    package = files("inferrsi")
    for key in ("procedure_resource", "worked_example_resource"):
        assert package.joinpath(result[key]).read_text(encoding="utf-8")
    inventory = json.loads(package.joinpath(
        "data/skill_library/workflows/inference-engine-research/references/"
        "minimax-h3-weight-inventory.json"
    ).read_text(encoding="utf-8"))
    assert len(inventory["selections"]) == 2
    for selection in inventory["selections"]:
        assert {component["role"] for component in selection["components"]} == {
            "denoiser", "text_encoder", "video_vae", "audio_vae",
        }
        paths = [path for component in selection["components"] for path in component["files"]]
        assert len(paths) == len(set(paths))
        assert set(selection["header_sha256"]) == set(paths)
        for field in ("logical_tensor_elements", "file_bytes"):
            assert selection["totals"][field] == sum(
                component[field] for component in selection["components"]
            )
        for component in selection["components"]:
            if "packed_u32_elements" in component:
                assert component["logical_tensor_elements"] == (
                    component["dense_elements"] + 4 * component["packed_u32_elements"]
                )
                assert component["quant_scale_bias_elements_excluded_from_logical_count"] > 0
            elif "elements_by_dtype" in component:
                assert component["logical_tensor_elements"] == sum(
                    component["elements_by_dtype"].values()
                )


@pytest.mark.parametrize("memory", [0, -1, math.inf, math.nan])
def test_target_memory_must_be_positive_and_finite(memory):
    with pytest.raises(ValueError, match="memory"):
        research_knowledge("MiniMax-H3", target_memory_gib=memory)


def test_public_cli_exposes_model_profile_and_keeps_filters(capsys):
    assert main([
        "knowledge", "research", "minimax-h3", "--framework", "mlx",
        "--target-backend", "metal", "--target-memory-gib", "64", "--limit", "12",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["profile"]["model"] == "MiniMax-H3"
    assert result["profile"]["sources"]
    assert any(
        item["record"]["id"] == "inferrsi.common.skills.lazy_evaluation_stream_lifetimes"
        for item in result["items"]
    )
    assert main([
        "knowledge", "research", "MiniMax-H3", "--repo-type", "vllm_rlt",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["no_match"] is True
    with pytest.raises(SystemExit) as error:
        main(["knowledge", "research", "MiniMax-H3", "--target-memory-gib", "-1"])
    assert error.value.code == 2


@pytest.mark.parametrize("model,kwargs", [("", {}), ("Example", {"frameworks": [" "]}),
                                         ("Example", {"limit": 0})])
def test_invalid_research_inputs_fail_explicitly(model, kwargs):
    with pytest.raises(ValueError):
        research_knowledge(model, **kwargs)
