import json
from pathlib import Path

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import get_skill, skill_metadata, skill_resource

ROOT = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
NAME = "audit-flare-session-lifecycle"
RELATIVE = f"repositories/flare-local-inference/{NAME}"
IDENTITY = "inferrsi.cuda.skills.audit_flare_session_lifecycle"
PIN = "bce032c014bae34502ba22d3304fa084d5b40afe"


def test_flare_discovery_preserves_candidate_scope_and_source_identity():
    record = get_knowledge(IDENTITY)
    for query in ("Flare", "transfer-ticket", "recurrent-state"):
        assert record in search_knowledge(query, repo="inferrsi", limit=100)
    assert record["skill_metadata"]["status"] == "candidate"
    assert record["skill_metadata"]["empirical_validation"] == "not_run"
    assert record["verification"]["locally_verified"] is False
    metadata = skill_metadata(ROOT, NAME)
    source = metadata["sources"][0]
    ledger = json.loads(skill_resource(ROOT, NAME, source["identity"]).read_text(
        encoding="utf-8"
    ))
    assert ledger["commit"] == source["commit"] == PIN
    assert ledger["repository"] == source["url"]
    assert ledger["resolved_repository"] == source["resolved_url"]
    assert {entry["path"] for entry in ledger["files"]} == set(source["paths"])
    assert ledger["native_execution"] == "not_run"


def test_flare_package_and_checkout_reads_retain_the_complete_owner():
    reader = KnowledgeReader(skill_root=ROOT)
    checkout = reader.read(NAME)
    package = reader.read(IDENTITY)
    owner = ROOT / RELATIVE
    resources = set(get_skill(ROOT, NAME)["resources"]) | {"SKILL.md"}
    for relative in resources:
        expected = (owner / relative).read_bytes()
        assert checkout.content[f"{RELATIVE}/{relative}"] == expected
        assert package.content[f"data/skill_library/{RELATIVE}/{relative}"] == expected
    assert (owner / "LICENSE").read_bytes() in package.content.values()
    preparation = "references/flare-preparation-boundary.md"
    weight = reader.read("weight-loading-optimization")
    assert weight.content[f"methods/weight-loading-optimization/{preparation}"] == (
        skill_resource(ROOT, "weight-loading-optimization", preparation).read_bytes()
    )
