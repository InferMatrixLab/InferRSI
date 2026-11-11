import json

from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.observability.campaign_records import create_campaign
from inferrsi.observability.knowledge_capture import capture_context, verify_capture

BASELINE_CUE = "reproducible diffusion baseline correctness fixed seed end to end benchmark"


def test_campaign_search_returns_portable_methods_and_records_counts(tmp_path):
    create_campaign(tmp_path, "diffusion")
    path, _ = capture_context(tmp_path, context_id="first", reader=KnowledgeReader(),
                              relevance=BASELINE_CUE, limit=2, context_bytes=14000)
    document, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert [item["title"] for item in document["items"]] == [
        "inference-benchmark-design", "video-diffusion-optimization",
    ]
    assert document["selection"]["method"] == "task-lexical-v1"
    assert document["selection"]["matched_count"] > document["selection"]["returned_count"] == 2
    assert document["context_omissions"][0]["reason"] == "context_limit"
    assert document["contexts"][0]["resources"][0]["path"].endswith(
        "video-diffusion-optimization/SKILL.md"
    )


def test_campaign_backend_routes_to_repository_evidence_and_can_be_overridden(tmp_path):
    create_campaign(tmp_path, "target", backend="cuda")
    reader = KnowledgeReader()
    path, _ = capture_context(tmp_path, context_id="cuda", reader=reader,
                              relevance="MiniMax H3 QK RMSNorm RoPE fusion", limit=3)
    doc, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert doc["request"]["backend"] == "cuda"
    assert all(item["backend"] in ("cuda", "common") for item in doc["items"])
    ctx = next(c for c in doc["contexts"] if c["ref"].endswith("minimax_h3_qk_norm_rope"))
    resource, = ctx["resources"]
    assert resource["role"] == "record"
    assert json.loads(resource["content"])["scenario"] == "diffusion.video_generation"
    assert resource["content"].encode() == reader.resource(
        ctx["ref"], resource["path"], revision=ctx["revision"]
    )
    path, _ = capture_context(tmp_path, context_id="ascend", reader=reader, backend="ascend",
                              relevance="Ascend video diffusion NPU optimization", limit=1)
    doc, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert doc["items"][0]["title"] == "ascend-video-diffusion-optimization"


def test_workload_scenario_discovers_skills_and_compatible_engine_records():
    reader = KnowledgeReader()
    options = {"relevance": BASELINE_CUE, "relevance_method": "task-lexical-v1",
               "backend": "cuda", "scenario": "diffusion.t2i", "limit": 8}
    items = reader.collect(**options)["items"]
    ids = [i["id"] for i in items]
    portable = "inferrsi.common.skills.video_diffusion_optimization"
    assert portable in ids
    assert "vllm_omni.common.diffusion.measurement_and_profiling" in ids
    assert all(i["scenario"] in ("skills.discovery", "diffusion.*", "diffusion.image_generation")
               and i["backend"] in ("cuda", "common") for i in items)
    assert reader.collect(ids=[portable], **options)["omissions"] == [
        {"id": portable, "reason": "filters"}
    ]
