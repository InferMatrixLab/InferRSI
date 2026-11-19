import json
import shutil

import pytest

from inferrsi.apps.campaign import capture_context, create_campaign, verify_capture
from inferrsi.knowledge.knowledge_find import find, installed_skill_root, load_corpus
from inferrsi.knowledge.knowledge_operations import KnowledgeReader

BASELINE_CUE = "reproducible diffusion baseline correctness fixed seed end to end benchmark"


def test_campaign_search_returns_portable_methods_and_records_counts(tmp_path):
    create_campaign(tmp_path, "diffusion", backend="cuda")
    path, _ = capture_context(tmp_path, context_id="first", reader=KnowledgeReader(),
                              relevance=BASELINE_CUE, limit=2, context_bytes=14000)
    document, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert [item["title"] for item in document["items"]] == [
        "inference-benchmark-design", "video-diffusion-optimization",
    ]
    assert document["selection"]["method"] == "find-lexical-v1"
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
    options = {"relevance": BASELINE_CUE, "backend": "cuda",
               "scenario": "diffusion.t2i", "limit": 8}
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


@pytest.mark.parametrize(("backend", "case"), [
    ("cuda", "qwen-ascend-rejected-directions"),
    ("ascend", "qwen-b300-rejected-directions"),
])
def test_find_filters_cases_to_the_campaign_backend(tmp_path, backend, case):
    create_campaign(tmp_path, "target", backend=backend)
    path, _ = capture_context(
        tmp_path, context_id="r1", reader=KnowledgeReader(), kind="case",
        relevance=case.replace("-", " "), limit=5,
    )
    capture, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert capture["items"]
    assert all(item["ref"] != f"checkout:case.{case}" for item in capture["items"])
    counts = capture["retrieval"]["counts"]
    assert counts["excluded"]["filters"] > 0
    assert counts["considered"] == (
        counts["matched"] + sum(
            counts["excluded"][name] for name in ("filters", "ranking_scope", "zero_score")
        )
    )


def test_find_with_custom_library_keeps_packaged_projections(tmp_path):
    create_campaign(tmp_path, "target")
    library = tmp_path / "custom"
    library.mkdir()
    path, _ = capture_context(
        tmp_path, context_id="r1", reader=KnowledgeReader(skill_root=library),
        relevance="cgroupv2", limit=1,
    )
    capture, state = verify_capture(path.read_bytes())
    assert state == "verified"
    item, = capture["items"]
    assert item["ref"] == "package:inferrsi.common.skills.cgroup_resource_controls"


def test_find_preserves_required_case_readset(tmp_path):
    create_campaign(tmp_path, "target")
    path, _ = capture_context(
        tmp_path, context_id="r1", reader=KnowledgeReader(), kind="case",
        relevance="vllm gdn source contract", limit=1,
    )
    capture, state = verify_capture(path.read_bytes())
    assert state == "verified"
    context, = capture["contexts"]
    assert context["ref"] == "checkout:case.vllm-gdn-source-contract"
    resource = next(
        item for item in context["resources"] if item["path"] == "vllm-gdn-causal-conv-contract.md"
    )
    assert resource["content"].encode("utf-8") == KnowledgeReader(
        skill_root=installed_skill_root()
    ).resource(context["ref"], resource["path"], revision=context["revision"])


def test_find_collection_uses_the_case_only_corpus():
    query = "cache per-step masks ran out of device memory"
    discovery = find(query, load_corpus(kinds=("case",)), limit=3)
    delivery = KnowledgeReader().collect(
        query, kind="case", relevance_method="find-lexical-v1", limit=3,
    )
    observed = delivery["retrieval"]
    assert [(item["ref"], item["score"]) for item in observed["items"]] == [
        (f"checkout:{item['id']}", item["score"]) for item in discovery["items"]
    ]
    assert observed["counts"]["considered"] == discovery["corpus_size"]
    assert observed["counts"]["excluded"]["filters"] == 0


def test_find_collection_does_not_repeat_custom_skills_as_package_projections(tmp_path):
    library = tmp_path / "copy"
    shutil.copytree(installed_skill_root(), library)
    reader = KnowledgeReader(skill_root=library)
    result = reader.collect(
        "weight loading optimization", relevance_method="find-lexical-v1", limit=6,
    )
    refs = {item["ref"] for item in result["items"]}
    assert "checkout:weight-loading-optimization" in refs
    assert "package:inferrsi.common.skills.weight_loading_optimization" not in refs


def test_find_does_not_infer_case_backend_from_applicability(tmp_path):
    owner = tmp_path / "owner"
    cases = owner / "cases"
    cases.mkdir(parents=True)
    (owner / "SKILL.md").write_text(
        "---\nname: owner\ndescription: Local test\n---\nCore", encoding="utf-8",
    )
    (cases / "body.md").write_text("B300 queue tuning.", encoding="utf-8")
    (cases / "case.json").write_text(json.dumps({
        "id": "case.legacy-b300",
        "kind": "case",
        "content": "body.md",
        "state": "candidate",
        "applicability": ["A B300 run"],
        "sources": [{"type": "internal", "issue": "test", "artifact": "case"}],
        "limitations": [],
        "attribution": [],
    }), encoding="utf-8")
    reader = KnowledgeReader(skill_root=tmp_path)
    options = {"kind": "case", "relevance_method": "find-lexical-v1"}
    result = reader.collect("B300", **options)
    assert [item["ref"] for item in result["items"]] == ["checkout:case.legacy-b300"]
    scoped = reader.collect("B300", backend="cuda", **options)
    assert scoped["no_match"]
    counts = scoped["retrieval"]["counts"]
    assert counts["considered"] == 1
    assert counts["excluded"]["ranking_scope"] == 1
    assert counts["excluded"]["filters"] == 0
