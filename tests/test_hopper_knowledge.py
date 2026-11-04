"""Hopper knowledge discovery and retained provenance, without GPU qualification."""

import json
import re
from collections import Counter
from pathlib import Path

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import get_skill, skill_metadata, skill_reference, skill_resource

ROOT = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
NAME = "reason-hopper-kernels"
OWNER = ROOT / "hardware/cuda" / NAME
IDENTITY = "inferrsi.cuda.skills.reason_hopper_kernels"
PREFIX = f"data/skill_library/hardware/cuda/{NAME}/"
CHECKOUT_PREFIX = f"hardware/cuda/{NAME}/"


def test_hopper_discovery_keeps_cuda_scope_and_unverified_candidate_state():
    record = get_knowledge(IDENTITY)
    for query in ("Hopper", "KernelWiki", "WGMMA", "FP8"):
        assert record in search_knowledge(query, repo="inferrsi", backend="cuda", limit=100)
    assert record not in search_knowledge(repo="inferrsi", backend="ascend", limit=100)
    assert record not in search_knowledge(repo="inferrsi", backend="cpu", limit=100)
    assert record["status"] == "imported"
    assert record["skill_metadata"]["status"] == "candidate"
    assert record["skill_metadata"]["empirical_validation"] == "not_run"
    assert record["verification"]["locally_verified"] is False
    assert record["skill_metadata"]["applicability"]["architectures"] == ["sm90", "sm90a"]


def test_hopper_package_and_checkout_retain_resources_and_declared_dependencies():
    reader = KnowledgeReader(skill_root=ROOT)
    local = reader.read(NAME)
    packaged = reader.read(IDENTITY)
    for relative in set(get_skill(ROOT, NAME)["resources"]) | {"SKILL.md"}:
        expected = (OWNER / relative).read_bytes()
        assert local.content[CHECKOUT_PREFIX + relative] == expected
        assert packaged.content[PREFIX + relative] == expected
    for reference in skill_metadata(ROOT, NAME)["references"]:
        assert skill_reference(ROOT, NAME, reference).is_file()
    assert all(source["type"] != "unknown" for source in local.metadata["sources"])


def test_hopper_inventory_preserves_gitlink_scope_and_source_dispositions():
    metadata = skill_metadata(ROOT, NAME)
    inventory = json.loads(skill_resource(
        ROOT, NAME, "references/source-inventory.json"
    ).read_text(encoding="utf-8"))
    kda, wiki = inventory["repositories"]
    assert kda["kernelwiki_gitlink"] == {
        "path": "skills/KernelWiki", "mode": "160000", "commit": wiki["commit"],
    }
    assert [source["commit"] for source in metadata["sources"][:2]] == [
        kda["commit"], wiki["commit"],
    ]
    assert inventory["empirical_validation"] == "not_run"
    assert inventory["classification_only_not_hardware_validation"]
    coverage = inventory["coverage"]
    synthesis = inventory["synthesis_inventory"]
    sources = inventory["sm90_source_inventory"]
    assert len({item["path"] for item in synthesis}) == len(synthesis) == 48
    assert Counter(item["disposition"] for item in synthesis) == coverage[
        "synthesis_dispositions"
    ]
    assert len({item["path"] for item in sources}) == len(sources) == 171
    assert coverage["source_headers_screened"] == sum(
        coverage["source_headers_by_directory"].values()
    ) == 2217
    assert sum(item["inspection"] != "frontmatter only" for item in sources) == 9
    for item in synthesis:
        assert re.fullmatch(r"[0-9a-f]{40}", item["git_blob"])
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        if "distilled_to" in item:
            assert skill_resource(ROOT, NAME, item["distilled_to"]).is_file()
    assert wiki["license"] == metadata["license"] == "UNKNOWN"
    for source in inventory["direct_upstream_readset"]:
        assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
        assert all(item["kernelwiki_bytes_match"] for item in source["files"]
                   if "kernelwiki_path" in item)
    assert all(not source["bytes_retained_in_package"] for source in (
        inventory["versioned_document_readset"]
    ))
