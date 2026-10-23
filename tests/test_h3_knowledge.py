"""h3.c knowledge delivery preserves source identity and unverified scope."""

import hashlib
import json
import re
from pathlib import Path

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.cli import main
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import get_skill, skill_metadata, skill_resource

ROOT = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
NAME = "audit-h3-runtime-residency"
OWNER = ROOT / "repositories/h3-c" / NAME
IDENTITY = "inferrsi.common.skills.audit_h3_runtime_residency"
COMMIT = "8974cc055ea9c02fcd14cc27dfda3e1027c05153"
PREFIX = f"data/skill_library/repositories/h3-c/{NAME}/"
CHECKOUT_PREFIX = f"repositories/h3-c/{NAME}/"
INVENTORY = "references/minimax-h3-weight-inventory.json"
INVENTORY_SHA256 = "fbaacaeec340d3ce893556ee864405a0746af4d13530a38cb3d5aa9d60929271"


def test_h3_model_and_repository_queries_discover_the_registered_candidate(capsys):
    record = get_knowledge(IDENTITY)
    for query in ("MiniMax-H3", "h3.c", "AdaLN SSD"):
        assert record in search_knowledge(query, repo="inferrsi", limit=100)
    assert record["status"] == "imported"
    assert record["skill_metadata"]["status"] == "candidate"
    assert record["skill_metadata"]["empirical_validation"] == "not_run"
    assert record["verification"]["locally_verified"] is False
    assert record["skill_documents"] == {"original": PREFIX + "SKILL.md"}
    assert main(["skills", "--root", str(ROOT), "show", NAME]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["name"] == NAME
    assert INVENTORY in selected["resources"]
    assert main(["skills", "--root", str(ROOT), "resource", NAME, INVENTORY]) == 0
    assert Path(json.loads(capsys.readouterr().out)["path"]) == OWNER / INVENTORY


def test_h3_checkout_and_package_reads_preserve_complete_owner_resources():
    reader = KnowledgeReader(skill_root=ROOT)
    local = reader.read(NAME)
    packaged = reader.read(IDENTITY)
    assert local.metadata["kind"] == "skill"
    assert packaged.metadata["kind"] == "knowledge"
    resources = set(get_skill(ROOT, NAME)["resources"]) | {"SKILL.md"}
    for relative in resources:
        expected = (OWNER / relative).read_bytes()
        assert local.content[CHECKOUT_PREFIX + relative] == expected
        assert packaged.content[PREFIX + relative] == expected
    expected = (OWNER / INVENTORY).read_bytes()
    assert reader.resource(NAME, CHECKOUT_PREFIX + INVENTORY, revision=local.revision) == expected
    assert reader.resource(
        IDENTITY, PREFIX + INVENTORY, revision=packaged.revision
    ) == expected
    assert local.metadata["state"] == "candidate"
    assert local.metadata["sources"][0]["commit"] == COMMIT
    assert local.metadata["sources"][0]["revision_precision"] == "full"
    assert all(source["type"] != "unknown" for source in local.metadata["sources"])


def test_h3_source_readset_and_retained_notices_have_one_owner():
    metadata = skill_metadata(ROOT, NAME)
    primary = metadata["sources"][0]
    identity = json.loads(skill_resource(ROOT, NAME, primary["identity"]).read_text(
        encoding="utf-8"
    ))
    assert identity["commit"] == primary["commit"] == COMMIT
    assert identity["repository"] == primary["url"] == "https://github.com/antirez/h3.c"
    assert identity["native_execution"] == "not_run"
    entries = identity["files"]
    assert len(entries) == len({entry["path"] for entry in entries})
    assert {entry["path"] for entry in entries} == set(primary["paths"])
    for entry in entries:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["git_blob"])
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert entry["bytes"] > 0
    assert metadata["license"] == "MIT"
    assert "Salvatore Sanfilippo" in (OWNER / "LICENSE").read_text(encoding="utf-8")
    notices = skill_resource(ROOT, NAME, primary["third_party_notices"])
    assert "Liu Liu" in notices.read_text(encoding="utf-8")
    documents = [source for source in metadata["sources"] if source["type"] == "document"]
    assert len(documents) == 2
    assert all(source["license"] == "UNKNOWN" for source in documents)
    assert all(source["readset"] == INVENTORY for source in documents)


def test_h3_retained_header_evidence_preserves_exact_bytes_and_full_component_totals():
    data = (OWNER / INVENTORY).read_bytes()
    # Frozen prior JSON-header evidence: deliberate future reinspection needs
    # new source revisions/digests, not a silent rewrite of this observation.
    assert hashlib.sha256(data).hexdigest() == INVENTORY_SHA256
    selections = json.loads(data)["selections"]
    expected = (
        ("MiniMaxAI/MiniMax-H3", 29, 69_235_580_593, 144_016_376_436),
        ("appautomaton/minimax-h3-base-8bit-mlx", 4, 61_631_247_232, 72_905_799_600),
    )
    for selection, (repository, count, elements, size) in zip(selections, expected, strict=True):
        assert selection["repository"] == repository
        assert selection["totals"] == {"logical_tensor_elements": elements, "file_bytes": size}
        components = selection["components"]
        assert {component["role"] for component in components} == {
            "denoiser", "text_encoder", "video_vae", "audio_vae",
        }
        assert sum(item["logical_tensor_elements"] for item in components) == elements
        assert sum(item["file_bytes"] for item in components) == size
        paths = [path for item in components for path in item["files"]]
        assert len(paths) == len(set(paths)) == count
        assert set(paths) == set(selection["header_sha256"])
        assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (
            selection["header_sha256"].values()
        ))
    for component in selections[1]["components"][:2]:
        assert component["logical_tensor_elements"] == (
            component["packed_u32_elements"] * 4 + component["dense_elements"]
        )
