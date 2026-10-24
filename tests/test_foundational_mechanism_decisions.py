import hashlib
from pathlib import Path

import pytest

from inferrsi.knowledge_operations import KnowledgeReader

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
GUIDE = "methods/optimization-search-policy/references/foundational-mechanism-decisions.md"

# 这些 golden IDs 只检查 retrieval 合同，不模拟 method selector。
CASES = [
    (
        "S1",
        "diagnose-vllm-admission-pressure",
        "skill",
        "candidate",
        "repositories/vllm/diagnose-vllm-admission-pressure/SKILL.md",
        "inferrsi.common.skills.diagnose_vllm_admission_pressure",
    ),
    (
        "S2",
        "assess-serving-preemption",
        "skill",
        "candidate",
        "methods/assess-serving-preemption/SKILL.md",
        "inferrsi.common.skills.assess_serving_preemption",
    ),
    (
        "C1",
        "audit-vllm-kv-lifetimes",
        "skill",
        "candidate",
        "repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md",
        "inferrsi.common.skills.audit_vllm_kv_lifetimes",
    ),
    (
        "C2",
        "case.qwen-b300-rejected-directions",
        "case",
        "historical_observation",
        "methods/inference-optimization-casebook/cases/qwen-b300-rejected-directions.md",
        "inferrsi.common.skills.inference_optimization_casebook",
    ),
    (
        "P1",
        "choose-parallel-training-plan",
        "skill",
        "candidate",
        "methods/choose-parallel-training-plan/SKILL.md",
        "inferrsi.common.skills.choose_parallel_training_plan",
    ),
    (
        "P2",
        "audit-afd-p2p-exchanges",
        "skill",
        "candidate",
        "repositories/afd-plugin/audit-afd-p2p-exchanges/SKILL.md",
        "inferrsi.cuda.skills.audit_afd_p2p_exchanges",
    ),
]


@pytest.fixture(scope="module")
def reader():
    reader = KnowledgeReader(skill_root=LIBRARY)
    checkout = reader.read("checkout:optimization-search-policy")
    package = reader.read("package:inferrsi.common.skills.optimization_search_policy")
    assert checkout.metadata["state"] == "candidate"
    assert checkout.metadata["empirical_validation"] == "not_run"
    assert package.metadata["kind"] == "knowledge"
    assert package.metadata["state"] == "imported"
    assert checkout.dependencies
    for reference in checkout.dependencies:
        assert reference in checkout.content
    for reference, key in (
        ("checkout:optimization-search-policy", GUIDE),
        (
            "package:inferrsi.common.skills.optimization_search_policy",
            "data/skill_library/" + GUIDE,
        ),
    ):
        bundle = checkout if reference.startswith("checkout:") else package
        data = reader.resource(reference, key, revision=bundle.revision)
        assert data == (LIBRARY / GUIDE).read_bytes()
        assert hashlib.sha256(data).hexdigest() == bundle.view()["resources"][key]
    return reader


@pytest.mark.parametrize(
    "case_id,identity,kind,state,path,package_id", CASES, ids=[case[0] for case in CASES]
)
def test_curated_owner_material_contract(reader, case_id, identity, kind, state, path, package_id):
    reference = f"checkout:{identity}"
    assert reference in reader.identities()
    result = reader.collect(ids=[reference], kind=kind, material=True)
    assert not result["no_match"] and not result["omissions"]
    assert [item["ref"] for item in result["items"]] == [reference]
    item = result["items"][0]
    assert item["kind"] == kind
    bundle = reader.read(reference, revision=item["revision"])
    view = bundle.view()
    assert view["state"] == state
    assert view["sources"] and view["applicability"] and view["limitations"]
    key = Path(path).name if kind == "case" else path
    data = reader.resource(reference, key, revision=item["revision"])
    assert data == bundle.content[key] == (LIBRARY / path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == view["resources"][key]
    package_ref = f"package:{package_id}"
    package = reader.read(package_ref)
    package_key = "data/skill_library/" + path
    assert reader.resource(package_ref, package_key, revision=package.revision) == data
    assert package.view()["resources"][package_key] == hashlib.sha256(data).hexdigest()
    if case_id == "C1":
        tier = reader.read("checkout:kv-tier-management")
        tier_key = "repositories/lmcache/kv-tier-management/SKILL.md"
        assert tier.metadata["state"] == "candidate"
        assert reader.resource(
            "checkout:kv-tier-management", tier_key, revision=tier.revision
        ) == (LIBRARY / tier_key).read_bytes()


def test_required_unavailable_revision_is_not_substituted(reader):
    reference = "checkout:optimization-search-policy"
    result = reader.collect(
        ids=[reference],
        revisions={reference: "sha256:" + "0" * 64},
        kind="skill",
        material=True,
    )
    assert result["no_match"] and result["items"] == []
    assert len(result["omissions"]) == 1
    omission = result["omissions"][0]
    assert omission["id"] == reference
    assert omission["reason"] == "unavailable_revision"
    assert reference in omission["detail"]
    assert "sha256:" + "0" * 64 in omission["detail"]
