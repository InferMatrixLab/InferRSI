"""Run outside the checkout after a noneditable [skills] install, PYTHONPATH unset."""

import contextlib
import hashlib
import io
import json
import sys
from importlib.resources import as_file, files
from pathlib import Path

import inferrsi
from inferrsi.catalog import knowledge_records, repository_pack, search_knowledge
from inferrsi.cli import main
from inferrsi.knowledge_operations import KnowledgeReader

assert Path(inferrsi.__file__).resolve().parent.parent.name != "src", (
    "This check requires an installed package"
)
records = knowledge_records()
assert len(records) == 116, "Knowledge is missing from the installation"
assert (
    files("inferrsi")
    .joinpath("data", "repo_packs", "vllm_omni", "knowledge", "README.md")
    .is_file()
)
assert repository_pack("vllm_rlt")["id"] == "vllm_rlt"
assert search_knowledge(repo="vllm_omni", backend="ascend")
assert all(not item["verification"]["locally_verified"] for item in records)
mlx_ids = {
    "mlx.mlx.execution.evaluation_completion",
    "mlx.mlx.execution.cross_stream_dependency",
    "mlx.mlx.execution.post_detachment_buffer_lifetime",
}
mlx_records = search_knowledge(repo="mlx", tier="dependency", backend="mlx", limit=100)
assert {record["id"] for record in mlx_records} == mlx_ids
assert all(record["backend"] == "mlx" for record in mlx_records)
mlx_document = "data/skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md"
mlx_reader = KnowledgeReader()
for record in mlx_records:
    bundle = mlx_reader.read("package:" + record["id"])
    assert mlx_reader.resource(
        "package:" + record["id"], mlx_document, revision=bundle.revision
    ) == files("inferrsi").joinpath(*mlx_document.split("/")).read_bytes()
assert files("inferrsi").joinpath("data/platform_packs/mlx/pack.json").is_file()
skill_index = search_knowledge(repo="inferrsi", limit=100)
assert len(skill_index) == 68, "Missing installed skill abstracts"
assert all(record["index_type"] == "packaged-skill" for record in skill_index)
indexed = KnowledgeReader().read("inferrsi.ascend.skills.ascend_operator_profiling")
assert "data/skill_library/hardware/ascend/ascend-operator-profiling/SKILL.md" in indexed.content
video_diffusion = KnowledgeReader().read(
    "inferrsi.ascend.skills.ascend_video_diffusion_optimization"
)
assert (
    "data/skill_library/hardware/ascend/ascend-video-diffusion-optimization/SKILL.md"
    in video_diffusion.content
)
case_path = (
    "data/skill_library/methods/inference-optimization-casebook/"
    "cases/admission-drain-occupancy.md"
)
assert case_path in indexed.content
assert indexed.dependencies
assert json.loads(indexed.content["record.json"])["skill_metadata"]["license"] == "UNKNOWN"
h3_identity = "inferrsi.common.skills.audit_h3_runtime_residency"
assert any(item["id"] == h3_identity for item in search_knowledge(
    "MiniMax-H3", repo="inferrsi", limit=100
))
h3_bundle = KnowledgeReader().read(h3_identity)
h3_prefix = "data/skill_library/repositories/h3-c/audit-h3-runtime-residency/"
h3_inventory = json.loads(h3_bundle.content[
    h3_prefix + "references/minimax-h3-weight-inventory.json"
])
assert h3_inventory["selections"][0]["totals"]["logical_tensor_elements"] == 69_235_580_593
h3_metadata = json.loads(h3_bundle.content[h3_prefix + "metadata.json"])
assert h3_metadata["status"] == "candidate"
assert h3_metadata["empirical_validation"] == "not_run"
assert h3_metadata["sources"][0]["commit"] == "8974cc055ea9c02fcd14cc27dfda3e1027c05153"
for relative in (
    "SKILL.md", "LICENSE", "references/source-identity.json", "references/source-notes.md",
    "references/phase-residency.md", "references/precision-and-streaming.md",
    "references/validation.md", "references/THIRD_PARTY_NOTICES.md",
    "references/minimax-h3-apple.md",
):
    assert h3_prefix + relative in h3_bundle.content
afd_identity = "inferrsi.cuda.skills.audit_afd_p2p_exchanges"
assert any(item["id"] == afd_identity for item in search_knowledge(
    "AFD", repo="inferrsi", backend="cuda", limit=100
))
afd_bundle = KnowledgeReader().read(afd_identity)
afd_prefix = "data/skill_library/repositories/afd-plugin/audit-afd-p2p-exchanges/"
for relative in ("SKILL.md", "metadata.json", "references/source-notes.md",
                 "references/afd-plugin-LICENSE.md"):
    assert afd_prefix + relative in afd_bundle.content
hopper_identity = "inferrsi.cuda.skills.reason_hopper_kernels"
assert any(item["id"] == hopper_identity for item in search_knowledge(
    "WGMMA", repo="inferrsi", backend="cuda", limit=100
))
hopper_bundle = KnowledgeReader().read(hopper_identity)
hopper_prefix = "data/skill_library/hardware/cuda/reason-hopper-kernels/"
hopper_metadata = json.loads(hopper_bundle.content[hopper_prefix + "metadata.json"])
assert hopper_metadata["status"] == "candidate"
assert hopper_metadata["empirical_validation"] == "not_run"
hopper_inventory = json.loads(hopper_bundle.content[
    hopper_prefix + "references/source-inventory.json"
])
assert hopper_inventory["coverage"]["synthesis_pages"] == 48
assert hopper_inventory["coverage"]["sm90_source_headers"] == 171
assert hopper_inventory["repositories"][0]["kernelwiki_gitlink"]["commit"] == (
    hopper_inventory["repositories"][1]["commit"]
)
for relative in (
    "SKILL.md", "references/sources.md", "references/synchronization.md",
    "references/resources-and-scheduling.md", "references/fp8.md", "references/notices.md",
    "references/licenses/kernelwiki-kda-mit.md", "references/licenses/deepgemm-mit.md",
    "references/licenses/cutlass-bsd.md",
):
    assert hopper_prefix + relative in hopper_bundle.content
# Check installed RLT resources without importing the upstream backend.
rlt_identity = "inferrsi.common.skills.audit_recurrent_kv_finalization"
rlt_bundle = KnowledgeReader().read(rlt_identity)
rlt_prefix = "data/skill_library/repositories/vllm-rlt/audit-recurrent-kv-finalization/"
for relative in (
    "SKILL.md", "metadata.json", "LICENSE", "references/NOTICE.md",
    "references/source-notes.md", "references/source-identity.json",
):
    assert rlt_prefix + relative in rlt_bundle.content
rlt_metadata = json.loads(rlt_bundle.content[rlt_prefix + "metadata.json"])
assert rlt_metadata["status"] == "candidate"
assert rlt_metadata["empirical_validation"] == "not_run"
assert rlt_metadata["sources"][0]["commit"] == "4a350344027960a48384626aa646f1765fda6d4f"
rlt_sources = json.loads(rlt_bundle.content[rlt_prefix + "references/source-identity.json"])
rlt_source_hashes = {item["path"]: item["content_sha256"] for item in rlt_sources["files"]}
for upstream, relative in (("LICENSE", "LICENSE"), ("NOTICE", "references/NOTICE.md")):
    actual = hashlib.sha256(rlt_bundle.content[rlt_prefix + relative]).hexdigest()
    assert actual == rlt_source_hashes[upstream]

assert "yaml" not in sys.modules, "Installed metadata reads must not require the skills extra"
selection_reader = KnowledgeReader()
selection = selection_reader.collect(
    "cpu.stat.local", relevance="cgroupv2", context_bytes=65536, limit=1,
)
assert selection["items"][0]["id"] == "inferrsi.common.skills.cgroup_resource_controls"
assert not selection["context_omissions"]
selection_context = selection["contexts"][0]
selection_core = selection_context["resources"][0]
assert selection_core["path"].endswith("/cgroup-resource-controls/SKILL.md")
assert selection_core["content"].encode() == selection_reader.resource(
    selection_context["ref"], selection_core["path"], revision=selection_context["revision"],
)
assert selection["context_bytes"] <= 65536
assert "yaml" not in sys.modules, "Packaged selection must not require the skills extra"
assert files("inferrsi").joinpath("data", "knowledge_packs", "README.md").is_file()
for tier, count in (("dependency", 6), ("peer", 5)):
    imported = search_knowledge(tier=tier, limit=100)
    assert len(imported) >= count, f"Missing installed {tier} records"
    assert all(item["tier"] == tier for item in imported)
qwen_tts = search_knowledge(
    "Qwen3-TTS", tier="peer", repo="qwen3_tts_engine",
    backend="ascend", scenario="audio.tts", limit=10,
)
assert len(qwen_tts) == 3, "Missing installed Qwen3-TTS peer techniques"
assert all(not record["verification"]["locally_verified"] for record in qwen_tts)
package = files("inferrsi")
library = package.joinpath("data", "skill_library")
for record in skill_index:
    for relative, expected_hash in record["source_files"].items():
        resource = package.joinpath(*relative.removeprefix("src/inferrsi/").split("/"))
        assert resource.is_file(), relative
        data = resource.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == expected_hash, relative
registry = json.loads(library.joinpath("skill-index.json").read_text(encoding="utf-8"))["skills"]
assert len(registry) == 68
for entry in registry.values():
    assert library.joinpath(*entry["path"].split("/"), "SKILL.md").is_file()
router = library.joinpath("workflows", "inference-engine-research")
manifest = json.loads(
    router.joinpath("references", "source-manifest.json").read_text(encoding="utf-8")
)
assert {entry.name for entry in library.iterdir() if entry.is_file()} == {
    "README.md", "skill-index.json",
}
assert not library.joinpath("en").is_dir() and not library.joinpath("zh-CN").is_dir()
assert len(manifest["sources"]) == 5
for source in manifest["sources"]:
    slug = source["skill"]
    repo = slug.replace("-", "_")
    assert repository_pack(repo)["id"] == repo
    imported = [
        item
        for item in search_knowledge(repo=repo, backend="cpu", limit=100)
        if "skill_documents" in item
    ]
    assert len(imported) == 3, f"Missing indexed knowledge for {repo}"
    owner = library.joinpath("repositories", slug)
    assert owner.joinpath("SKILL.md").is_file()
    assert owner.joinpath("LICENSE").is_file()
    assert not owner.joinpath("translations", "zh-CN").is_dir()
    for record in imported:
        assert set(record["skill_documents"]) == {"en"}
        for reference in record["skill_documents"].values():
            assert package.joinpath(*reference.split("/")).is_file(), reference
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert main(["context", imported[0]["id"], "--repo-type", repo, "--backend", "cpu"]) == 0
    assert '"skill_documents"' in output.getvalue()
    assert '"locally_verified": false' in output.getvalue()
assert router.joinpath("SKILL.md").is_file()
assert router.joinpath("references", "overview.md").is_file()
assert not router.joinpath("translations", "zh-CN").is_dir()
strata = library.joinpath("repositories", "strata")
assert strata.joinpath("references", "design-space-analysis.md").is_file()
helper = strata.joinpath("scripts", "summarize_trials.py")
assert helper.is_file()
with as_file(helper) as path:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
ceiling = library.joinpath("methods", "performance-ceiling-analysis")
ceiling_namespace = {}
exec(compile(ceiling.joinpath("scripts", "roofline.py").read_text(encoding="utf-8"),
             "roofline.py", "exec"), ceiling_namespace)
ceiling_example = json.loads(
    ceiling.joinpath("references", "roofline-example.json").read_text(encoding="utf-8")
)
assert ceiling_namespace["analyze"](**ceiling_example)["conditional_roof_flop_per_s"] == 60
assert ceiling.joinpath("references", "roofline-contract.md").is_file()
inference_modules = {"torch", "vllm", "sglang", "sglang_omni", "vllm_omni", "transformers", "mlx"}
assert not inference_modules & sys.modules.keys()
ascend_image = search_knowledge(
    "Qwen-Image-2.1", repo="vllm_omni", backend="ascend", scenario="diffusion.image_generation"
)
assert [item["id"] for item in ascend_image] == [
    "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
]
assert (
    files("inferrsi")
    .joinpath(
        "data",
        "repo_packs",
        "vllm_omni",
        "knowledge",
        "ascend",
        "diffusion",
        "qwen-image-21-eager-t2i.json",
    )
    .is_file()
)
output = io.StringIO()
with contextlib.redirect_stdout(output):
    assert main(["skills", "show", "ascend-operator-profiling"]) == 0
assert json.loads(output.getvalue())["name"] == "ascend-operator-profiling"
output = io.StringIO()
with contextlib.redirect_stdout(output):
    assert main(["skills", "resource", "audit-h3-runtime-residency",
                 "references/phase-residency.md"]) == 0
assert Path(json.loads(output.getvalue())["path"]).is_file()
output = io.StringIO()
with contextlib.redirect_stdout(output):
    assert main([
        "knowledge", "research", "MiniMax-H3", "--framework", "mlx",
        "--target-backend", "metal", "--target-device", "M5 Mac Studio",
        "--target-memory-gib", "64", "--limit", "12",
    ]) == 0
research = json.loads(output.getvalue())
assert research["profile"]["model"] == "MiniMax-H3"
assert research["target_validation"] == "unverified"
assert research["target"]["device"] == "M5 Mac Studio"
assert any(
    item["record"]["id"] == "inferrsi.common.skills.lazy_evaluation_stream_lifetimes"
    for item in research["items"]
)
assert {item["group"] for item in research["queries"]} == {
    "model", "framework", "task", "modality", "mechanism",
}
for key in ("procedure_resource", "worked_example_resource"):
    assert package.joinpath(research[key]).read_text(encoding="utf-8")
for key in ("skill_resource", "inventory_resource"):
    assert package.joinpath(research["profile"][key]).read_text(encoding="utf-8")
assert set(research["profile"]["knowledge_ids"]) <= {
    item["record"]["id"] for item in research["items"]
}
assert not inference_modules & sys.modules.keys()
print(f"Installed package: {inferrsi.__file__}; {len(records)} source-grounded records available.")

splash_notices = files("inferrsi").joinpath(
    "data/skill_library/repositories/splash/THIRD_PARTY_NOTICES"
)
assert splash_notices.is_file(), "Splash third-party notices are missing from the wheel"
assert "The ggml authors" in splash_notices.read_text(encoding="utf-8")

# Document-only candidate remains available without implying native verification.
husky = library.joinpath("repositories", "husky")
assert husky.joinpath("references", "source-availability.json").is_file()
assert husky.joinpath("scripts", "audit_evidence_card.py").is_file()
assert json.loads(husky.joinpath("metadata.json").read_text())["status"] == "candidate"

# Maya retains safe support and unverified-native candidate state in the wheel.
maya = library.joinpath("repositories", "project-maya")
assert maya.joinpath("LICENSE").is_file()
assert maya.joinpath("sub-skills", "model-runtime", "scripts", "audit_runtime_plan.py").is_file()
assert json.loads(maya.joinpath("metadata.json").read_text())["status"] == "candidate"
