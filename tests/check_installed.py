"""Run after a noneditable install with PYTHONPATH unset."""

from importlib.resources import files
from pathlib import Path

import omnirsi
from omnirsi.catalog import knowledge_records, repository_pack, search_knowledge

assert Path(omnirsi.__file__).resolve().parent.parent.name != "src", (
    "This check requires an installed package"
)
records = knowledge_records()
assert len(records) >= 10, "Knowledge is missing from the installation"
assert (
    files("omnirsi").joinpath("data", "repo_packs", "vllm_omni", "knowledge", "README.md").is_file()
)
assert repository_pack("vllm_rlt")["id"] == "vllm_rlt"
assert search_knowledge(repo="vllm_omni", backend="ascend")
assert all(not item["verification"]["locally_verified"] for item in records)
ascend_image = search_knowledge(
    "Qwen-Image-2.1", repo="vllm_omni", backend="ascend", scenario="diffusion.image_generation"
)
assert [item["id"] for item in ascend_image] == [
    "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
]
assert (
    files("omnirsi")
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
print(f"Installed package: {omnirsi.__file__}; {len(records)} source-grounded records available.")
