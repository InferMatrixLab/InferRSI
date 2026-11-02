"""Static checks for the PyTorch v2.15 and TorchNPU repo-to-skill distillation."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "src/inferrsi/data/skill_library"
PT = "31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457"
NP = "54e365d3e3614299bccd17f06916544c3880c9fc"
SHA256 = re.compile(r"[0-9a-f]{64}")

SKILLS = {
    "frameworks/pytorch/pytorch-inference-operating-graph": PT,
    "frameworks/pytorch/pytorch-dispatcher-and-custom-ops": PT,
    "frameworks/pytorch/pytorch-sdpa-backend-selection": PT,
    "frameworks/pytorch/pytorch-caching-allocator-and-streams": PT,
    "frameworks/pytorch/pytorch-inference-profiler": PT,
    "frameworks/pytorch/pytorch-aot-inductor-inference": PT,
    "hardware/ascend/torchnpu-inference-operating-graph": NP,
    "hardware/ascend/torchnpu-graph-capture": NP,
    "hardware/ascend/torchnpu-privateuse1-dispatch": NP,
    "hardware/ascend/torchnpu-streams-and-events": NP,
    "hardware/ascend/torchnpu-hccl-process-groups": NP,
    "hardware/ascend/torchnpu-profiler-and-compile": NP,
}


def test_distillation_stays_candidate_and_pins_full_file_hashes():
    for relative, commit in SKILLS.items():
        directory = LIBRARY / relative
        body = (directory / "SKILL.md").read_text(encoding="utf-8")
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        readset = json.loads(
            (directory / "references" / "readset.json").read_text(encoding="utf-8")
        )
        assert metadata["status"] == "candidate"
        assert metadata["empirical_validation"] == "not_run"
        assert "not_run" in body
        assert commit in body
        assert readset["revision"] == commit
        assert readset["empirical_validation"] == "not_run"
        assert readset["files"]
        for item in readset["files"]:
            assert item["url"].startswith("https://")
            assert f"/blob/{commit}/" in item["url"]
            assert SHA256.fullmatch(item["sha256"])
            assert re.fullmatch(r"[0-9a-f]{40}", item["blob"])
        # Refusal of a measured gain may use the word; a numeric rate may not.
        assert "tokens/s" not in body.lower()
        assert not re.search(r"\d+(\.\d+)?\s*%\s*(faster|speedup)", body, re.I)


def test_cudagraph_document_hash_matches_existing_compiler_card():
    card_path = (
        ROOT / "src/inferrsi/data/knowledge_packs/dependency/pytorch/cuda/compiler"
        / "cudagraph-shapes-and-lifetimes.json"
    )
    card = json.loads(card_path.read_text(encoding="utf-8"))
    previous = next(
        source["content_sha256"]
        for source in card["sources"]
        if source["url"].endswith("torch.compiler_cudagraph_trees.md")
    )
    readset_path = (
        LIBRARY / "frameworks/pytorch/pytorch-aot-inductor-inference/references/readset.json"
    )
    readset = json.loads(readset_path.read_text(encoding="utf-8"))
    current = next(
        item["sha256"]
        for item in readset["files"]
        if item["path"].endswith("torch.compiler_cudagraph_trees.md")
    )
    assert current == previous == "0dbfcef13ad6baea52c6e989eaf6561440c02a26a6ef667da850439d3a88c6a5"


def test_torch_npu_cards_remain_imported_and_unverified():
    from inferrsi.catalog import KNOWLEDGE_SCOPES, search_knowledge

    assert "torch_npu" in KNOWLEDGE_SCOPES["dependency"]
    records = search_knowledge(repo="torch_npu", tier="dependency", limit=20)
    assert {record["id"] for record in records} == {
        "torch_npu.ascend.compiler.npugraph_capture_contract",
        "torch_npu.ascend.execution.privateuse1_backend_alias",
    }
    assert all(record["status"] == "imported" for record in records)
    assert all(record["verification"]["locally_verified"] is False for record in records)
