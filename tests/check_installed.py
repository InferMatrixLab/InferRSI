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
assert len(records) == 91, "Knowledge is missing from the installation"
assert (
    files("inferrsi")
    .joinpath("data", "repo_packs", "vllm_omni", "knowledge", "README.md")
    .is_file()
)
assert repository_pack("vllm_rlt")["id"] == "vllm_rlt"
assert search_knowledge(repo="vllm_omni", backend="ascend")
assert all(not item["verification"]["locally_verified"] for item in records)
skill_index = search_knowledge(repo="inferrsi", limit=100)
assert len(skill_index) == 49, "Missing installed skill abstracts"
assert all(record["index_type"] == "packaged-skill" for record in skill_index)
indexed = KnowledgeReader().read("inferrsi.ascend.skills.ascend_operator_profiling")
assert "data/skill_library/hardware/ascend/ascend-operator-profiling/SKILL.md" in indexed.content
case_path = (
    "data/skill_library/methods/inference-optimization-casebook/"
    "cases/admission-drain-occupancy.md"
)
assert case_path in indexed.content
assert indexed.dependencies
assert json.loads(indexed.content["record.json"])["skill_metadata"]["license"] == "UNKNOWN"
assert "yaml" not in sys.modules, "Installed metadata reads must not require the skills extra"
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
assert len(registry) == 49
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
inference_modules = {"torch", "vllm", "sglang", "sglang_omni", "vllm_omni", "transformers"}
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
assert not inference_modules & sys.modules.keys()
print(f"Installed package: {inferrsi.__file__}; {len(records)} source-grounded records available.")
