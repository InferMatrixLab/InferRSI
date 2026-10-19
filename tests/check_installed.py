"""Run after a noneditable install with PYTHONPATH unset."""

import contextlib
import io
import json
import sys
from importlib.resources import as_file, files
from pathlib import Path

import inferrsi
from inferrsi.catalog import knowledge_records, repository_pack, search_knowledge
from inferrsi.cli import main

assert Path(inferrsi.__file__).resolve().parent.parent.name != "src", (
    "This check requires an installed package"
)
records = knowledge_records()
assert len(records) >= 10, "Knowledge is missing from the installation"
assert (
    files("inferrsi")
    .joinpath("data", "repo_packs", "vllm_omni", "knowledge", "README.md")
    .is_file()
)
assert repository_pack("vllm_rlt")["id"] == "vllm_rlt"
assert search_knowledge(repo="vllm_omni", backend="ascend")
assert all(not item["verification"]["locally_verified"] for item in records)
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
manifest = json.loads(library.joinpath("source-manifest.json").read_text(encoding="utf-8"))
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
    for language in ("en", "zh-CN"):
        assert library.joinpath(language, slug, "SKILL.md").is_file()
        assert library.joinpath(language, slug, "LICENSE").is_file()
    for record in imported:
        for reference in record["skill_documents"].values():
            assert package.joinpath(*reference.split("/")).is_file(), reference
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert main(["context", imported[0]["id"], "--repo-type", repo, "--backend", "cpu"]) == 0
    assert '"skill_documents"' in output.getvalue()
    assert '"locally_verified": false' in output.getvalue()
for language in ("en", "zh-CN"):
    assert library.joinpath(language, "inference-engine-research", "SKILL.md").is_file()
    helper = library.joinpath(language, "strata", "scripts", "summarize_trials.py")
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
print(f"Installed package: {inferrsi.__file__}; {len(records)} source-grounded records available.")
