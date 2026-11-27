import hashlib
import json
import shutil

import pytest

from inferrsi.apps.workflows.campaign import capture_context, create_campaign, verify_capture
from inferrsi.knowledge.knowledge_find import find, installed_skill_root, load_corpus
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from tests.apps.test_codex_knowledge_search import _cli

BASELINE_CUE = "reproducible diffusion baseline correctness fixed seed end to end benchmark"


def _scoped(root, query, *flags):
    _, output = _cli(root, "find", query, "--session", str(root),
                     "--no-external", *flags)
    found = json.loads(output)
    doc, state = verify_capture((root / found["reference"]["path"]).read_bytes())
    assert state == "verified"
    return found, doc


def test_campaign_search_returns_portable_methods_and_records_counts(tmp_path):
    create_campaign(tmp_path, "diffusion", backend="cuda")
    found, doc = _scoped(tmp_path, BASELINE_CUE, "--limit", "2")
    assert found["matched"] > len(found["items"]) == len(doc["items"]) == 2
    assert [h["material_ref"] for h in found["items"]] == [
        "package:inferrsi.common.skills.inference_benchmark_design",
        "package:inferrsi.common.skills.video_diffusion_optimization",
    ]
    for hit in found["items"]:
        _, opened = _cli(tmp_path, *hit["read_args"])
        assert len(json.loads(opened)["content"].encode()) == hit["next_read_content_bytes"]


def test_campaign_backend_routes_to_repository_evidence_and_can_be_overridden(tmp_path):
    create_campaign(tmp_path, "target", backend="cuda")
    found, doc = _scoped(tmp_path, "MiniMax H3 QK RMSNorm RoPE fusion", "--limit", "3")
    assert doc["request"]["backend"] == "cuda"
    hit = next(h for h in found["items"] if h["material_ref"].endswith("minimax_h3_qk_norm_rope"))
    _, output = _cli(tmp_path, *hit["read_args"])
    opened = json.loads(output)
    assert json.loads(opened["content"])["scenario"] == "diffusion.video_generation"
    assert opened["content"].encode() == KnowledgeReader().resource(
        opened["ref"], opened["content_resource"], revision=opened["revision"],
    )
    other, _ = _scoped(tmp_path, "Ascend video diffusion NPU optimization",
                       "--backend", "ascend", "--limit", "1")
    assert other["items"][0]["material_ref"].endswith(".skills.ascend_video_diffusion_optimization")


def test_workload_scenario_discovers_skills_and_compatible_engine_records():
    scope = {"backend": "cuda", "scenario": "diffusion.t2i"}
    found = find(BASELINE_CUE, load_corpus(**scope), limit=8, pin_material=True)
    refs = {hit["material_ref"] for hit in found["items"]}
    portable = "package:inferrsi.common.skills.video_diffusion_optimization"
    assert {portable, "package:vllm_omni.common.diffusion.measurement_and_profiling"} <= refs
    assert KnowledgeReader().collect(ids=[portable], **scope)["omissions"] == [
        {"id": portable, "reason": "filters"}
    ]


@pytest.mark.parametrize(("backend", "case"), [
    ("cuda", "qwen-ascend-rejected-directions"),
    ("ascend", "qwen-b300-rejected-directions"),
])
def test_find_filters_cases_to_the_campaign_backend(tmp_path, backend, case):
    create_campaign(tmp_path, "target", backend=backend)
    found, doc = _scoped(tmp_path, case.replace("-", " "), "--kinds", "case", "--limit", "5")
    assert doc["request"]["backend"] == backend
    assert found["items"] and found["corpus_size"] >= found["matched"] >= len(found["items"])
    assert all(item["material_ref"] != f"checkout:case.{case}" for item in found["items"])


def test_find_with_custom_library_keeps_packaged_projections(tmp_path):
    create_campaign(tmp_path, "target")
    library = tmp_path / "custom"
    library.mkdir()
    found, _ = _scoped(tmp_path, "cgroupv2", "--skill-root", str(library), "--limit", "1")
    item, = found["items"]
    assert item["material_ref"] == "package:inferrsi.common.skills.cgroup_resource_controls"
    with pytest.raises(ValueError, match="Package catalog filters"):
        load_corpus(library, repo="inferrsi")


def test_find_preserves_required_case_readset(tmp_path):
    create_campaign(tmp_path, "target")
    found, _ = _scoped(tmp_path, "vllm gdn source contract", "--kinds", "case", "--limit", "1")
    hit, = found["items"]
    ref = hit["material_ref"]
    reader = KnowledgeReader(skill_root=installed_skill_root())
    path, _ = capture_context(tmp_path, context_id="snapshot", reader=reader, ids=[ref],
                              revisions={ref: hit["revision"]})
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
    result = find(query, load_corpus(kinds=("case",)), limit=3, pin_material=True)
    reader = KnowledgeReader(skill_root=installed_skill_root())
    packed = reader.pack_find_hits(result["items"], cue=query, limit=3, context_bytes=65536)
    assert [(item["ref"], item["revision"]) for item in packed["items"]] == [
        (hit["material_ref"], hit["revision"]) for hit in result["items"]
    ]
    assert all(item["kind"] == "case" for item in packed["items"])


def test_find_collection_does_not_repeat_custom_skills_as_package_projections(tmp_path):
    library = tmp_path / "copy"
    shutil.copytree(installed_skill_root(), library)
    hits = find("weight loading optimization", load_corpus(library), limit=6)["items"]
    material = {hit["read_args"][1] for hit in hits}
    assert "checkout:weight-loading-optimization" in material
    assert "package:inferrsi.common.skills.weight_loading_optimization" not in material


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
    result = find("B300", load_corpus(tmp_path, kinds=("case",)), pin_material=True)
    assert [item["material_ref"] for item in result["items"]] == ["checkout:case.legacy-b300"]
    scoped = find("B300", load_corpus(tmp_path, kinds=("case",), backend="cuda"))
    assert scoped["no_match"] and scoped["corpus_size"] == 0


def test_task_skills_are_explicitly_readable_but_never_ranked_into_campaign(tmp_path):
    create_campaign(tmp_path, "routing")
    reader = KnowledgeReader()
    tasks = ("inference_task_router", "task_day_0", "task_performance", "task_debug",
             "task_accuracy", "task_version_alignment", "task_derived_engine",
             "task_independent_engine")
    task_refs = {f"package:inferrsi.common.skills.{task}" for task in tasks}
    cue = "inference-task-router day-0 model onboarding performance accuracy"
    options = {"context_bytes": 65536, "limit": 135, "repo": "inferrsi", "kind": "knowledge"}
    ranked, _ = _scoped(tmp_path, cue, "--repo-type", "inferrsi", "--limit", "135")
    assert ranked["items"] and ranked["matched"] <= ranked["corpus_size"]
    assert task_refs.isdisjoint(item["material_ref"] for item in ranked["items"])
    refs = sorted(task_refs)
    path, _ = capture_context(tmp_path, context_id="explicit", reader=reader, ids=refs,
                              **{**options, "context_bytes": 1024 * 1024})
    exact, state = verify_capture(path.read_bytes())
    assert state == "verified"
    assert {item["ref"] for item in exact["items"]} == task_refs
    assert {item["ref"] for item in exact["contexts"]} == task_refs
    for context in exact["contexts"]:
        core = next(resource for resource in context["resources"] if resource["role"] == "core")
        assert core["locator"] == "skill-procedure"
        source = reader.resource(context["ref"], core["path"], revision=context["revision"])
        delivered = core["content"].encode("utf-8")
        assert hashlib.sha256(source).hexdigest() == core["source_sha256"]
        assert hashlib.sha256(delivered).hexdigest() == core["sha256"]
        assert b"".join(source[a:b] for a, b in core["source_byte_ranges"]) == delivered
    for item in exact["items"]:
        pinned = reader.read(item["ref"], revision=item["revision"])
        assert pinned.metadata["id"] == item["ref"].split(":")[1]
