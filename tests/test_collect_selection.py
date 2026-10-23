import hashlib
import json
from pathlib import Path

import pytest

from inferrsi._skill_selection import lexical_score
from inferrsi.cli import main
from inferrsi.knowledge_operations import Bundle, KnowledgeReader, _hash, _json
from inferrsi.knowledge_store import KnowledgeStore

ROOT = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"
CGROUP = "inferrsi.common.skills.cgroup_resource_controls"
H3 = "inferrsi.common.skills.audit_h3_runtime_residency"
AFD = "inferrsi.cuda.skills.audit_afd_p2p_exchanges"


@pytest.mark.parametrize(("cue", "query", "identity", "first"), [
    ("cgroupv2", "", CGROUP, True),
    ("MiniMax-H3 AdaLN SSD", "", H3, False),
    ("P2pNccl", "", AFD, True),
    ("DLRover replica recovery", "",
     "inferrsi.common.skills.checkpoint_recovery_consistency", False),
    ("cgroupv2", "cpu.stat.local", CGROUP, False),
])
def test_frozen_offline_pilot(cue, query, identity, first):
    result = KnowledgeReader().collect(query, relevance=cue, context_bytes=65536, limit=3)
    identities = [item["id"] for item in result["items"]]
    assert identity in identities
    if first:
        assert identities[0] == identity
    assert not [o for o in result["omissions"] if o["reason"] == "index_unavailable"]
    assert result["context_bytes"] <= 65536


def test_no_match_and_query_remains_token_and_substring_matching():
    reader = KnowledgeReader()
    assert reader.collect(relevance="floristry orchid")["no_match"]
    item = reader.read(CGROUP)
    assert "cpu.stat.local" not in json.dumps(item.metadata).casefold()
    assert "cpu.stat.local" in item.content["record.json"].decode()
    result = reader.collect("cpu.stat.local", relevance="cgroupv2")
    assert result["items"][0]["id"] == CGROUP
    assert reader.collect("cpu.stat.local impossibleword", relevance="cgroupv2")["no_match"]
    assert reader.collect("stat.loc", relevance="cgroupv2")["items"][0]["id"] == CGROUP


def test_existing_item_payload_and_material_accounting_are_unchanged():
    reader = KnowledgeReader()
    old = reader.collect(ids=[CGROUP], material=True)
    assert set(old) == {
        "items", "omissions", "no_match", "collisions", "material_bytes", "limitations",
    }
    new = reader.collect(ids=[CGROUP], material=True, context_bytes=65536)
    assert new["items"] == old["items"]
    assert new["material_bytes"] == old["material_bytes"] == len(_json(old["items"][0]))
    assert json.loads(new["items"][0]["content"])["id"] == CGROUP
    assert new["contexts"][0]["resources"][0]["path"].endswith("/SKILL.md")
    assert new["contexts"][0]["omissions"] == [{
        "path": "data/skill_library/hardware/host/cgroup-resource-controls/metadata.json",
        "reason": "not_context_resource",
    }]
    assert "contexts" not in reader.collect(ids=[CGROUP], relevance="unrelated")


def test_explicit_membership_order_aliases_and_revisions_are_preserved():
    reader = KnowledgeReader(skill_root=ROOT)
    ids = [H3, CGROUP, f"package:{CGROUP}", "cgroup-resource-controls"]
    revision = reader.read(H3).revision
    result = reader.collect(
        ids=ids, revisions={H3: revision}, relevance="orchid", context_bytes=65536
    )
    assert [item["ref"] for item in result["items"]] == [
        f"package:{H3}", f"package:{CGROUP}", "checkout:cgroup-resource-controls",
    ]
    assert result["omissions"] == [{"id": f"package:{CGROUP}", "reason": "duplicate_identity",
                                       "detail": f"Already selected: package:{CGROUP}"}]
    assert result["selection"]["ranking_applied"] is False
    assert result["context_omissions"][-1]["reason"] == "unsupported_context"
    wrong = reader.collect(ids=[H3], revisions={H3: "sha256:" + "0" * 64}, relevance="H3")
    assert wrong["omissions"][0]["reason"] == "unavailable_revision"
    with pytest.raises(ValueError, match="Duplicate"):
        reader.collect(ids=[H3, H3], relevance="H3")


def test_filters_stay_package_only_and_precede_ranking():
    reader = KnowledgeReader(skill_root=ROOT)
    assert reader.collect(relevance="P2pNccl", backend="ascend")["no_match"]
    assert reader.collect(relevance="P2pNccl", tier="peer")["no_match"]
    assert reader.collect(relevance="cgroupv2", kind="skill")["no_match"]
    assert reader.collect(relevance="cgroupv2", repo="vllm")["no_match"]
    assert reader.collect(relevance="cgroupv2", scenario="diffusion.t2i")["no_match"]
    result = reader.collect(
        relevance="cgroupv2", kind="knowledge", repo="inferrsi", tier="contribution",
        backend="cpu", scenario="skills.discovery",
    )
    assert result["items"][0]["id"] == CGROUP


def test_weighted_presence_and_identity_ties_are_deterministic():
    assert lexical_score("MATCH match", [(4, "match match"), (1, "match")]) == 5
    reader = KnowledgeReader()
    all_items = reader.collect(relevance="candidate", limit=100)["items"]
    # With no title/description/tag occurrence, these owners share the core-only score.
    tied = []
    for item in all_items:
        record = reader.records()[item["id"]]
        if "candidate" not in json.dumps([
            record["title"], record["summary"], record["tags"], record["applicability"],
        ]).casefold():
            tied.append(item["ref"])
    assert len(tied) > 1 and tied == sorted(tied)
    assert reader.collect(relevance="candidate", limit=1)["items"] == all_items[:1]


def test_context_keeps_complete_core_prerequisites_provenance_and_exact_bytes():
    reader = KnowledgeReader()
    result = reader.collect(ids=[AFD], context_bytes=65536)
    assert not result["context_omissions"]
    context = result["contexts"][0]
    item = result["items"][0]
    assert (context["ref"], context["revision"]) == (item["ref"], item["revision"])
    assert context["sources"] == item["sources"]
    paths = {r["path"] for r in context["resources"]}
    assert "data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md" in paths
    assert "data/skill_library/methods/inference-benchmark-design/SKILL.md" in paths
    assert any(path.endswith("/references/source-notes.md") for path in paths)
    for resource in context["resources"]:
        actual = reader.resource(context["ref"], resource["path"], revision=context["revision"])
        assert resource["content"].encode() == actual
        assert resource["sha256"] == hashlib.sha256(actual).hexdigest()
        assert resource["locator"] == "whole-resource"
    assert context["content_bytes"] == result["context_bytes"] == sum(
        len(r["content"].encode()) for r in context["resources"]
    )
    assert item["entrypoint"] == "record.json" and item["dependencies"]
    assert len(item["resources"]) > len(context["resources"])


def test_both_budgets_skip_oversized_items_and_fit_later_smaller_items():
    reader = KnowledgeReader()
    small = reader.collect(ids=[CGROUP], material=True, context_bytes=65536)
    core_bytes = small["context_bytes"]
    core = small["contexts"][0]["resources"][0]["content"]
    assert len(core.encode()) > len(core)
    result = reader.collect(ids=[H3, CGROUP], context_bytes=core_bytes)
    assert [context["ref"] for context in result["contexts"]] == [f"package:{CGROUP}"]
    assert result["context_omissions"][0]["ref"] == f"package:{H3}"
    assert result["context_omissions"][0]["reason"] == "context_limit"
    assert result["context_bytes"] == core_bytes
    assert len(result["items"]) == 2
    item_budget = small["material_bytes"]
    result = reader.collect(ids=[H3, CGROUP], material=True, max_bytes=item_budget,
                            context_bytes=65536)
    assert [item["id"] for item in result["items"]] == [CGROUP]
    assert result["omissions"] == [{"id": H3, "reason": "output_limit"}]
    tiny = reader.collect(ids=[CGROUP], context_bytes=1)
    assert tiny["items"] and not tiny["contexts"] and tiny["context_bytes"] == 0


def test_source_drift_and_cross_owner_mapping_never_fall_back():
    for change in ("source", "mapping", "resource", "registry_missing"):
        reader = KnowledgeReader()
        original = reader.read(CGROUP).revision
        record = reader.records()[CGROUP]
        if change == "source":
            record["source_files"][next(iter(record["source_files"]))] = "0" * 64
        elif change == "mapping":
            record["skill_documents"] = reader.records()[H3]["skill_documents"]
        else:
            library = dict(reader._skill_library()[0])
            if change == "resource":
                core = record["skill_documents"]["original"]
                library[core] += b"\nChanged instructions.\n"
            else:
                del library["data/skill_library/skill-index.json"]
            digest = _hash(_json({p: _hash(data) for p, data in sorted(library.items())}))
            reader._library = library, "sha256:" + digest
        result = reader.collect("cpu.stat.local", relevance="cgroupv2")
        assert result["no_match"]
        assert any(o["reason"] == "index_unavailable" for o in result["omissions"])
        explicit = reader.collect(ids=[CGROUP], context_bytes=65536)
        assert explicit["items"] and not explicit["contexts"]
        assert explicit["context_omissions"][0]["reason"] == "index_unavailable"
        assert reader.collect(ids=[CGROUP], revisions={CGROUP: original})["omissions"][0][
            "reason"
        ] == "unavailable_revision"


def test_store_delegates_but_copied_package_metadata_cannot_gain_context(tmp_path):
    source = KnowledgeReader().read(CGROUP)
    store = KnowledgeStore(tmp_path, skill_root=None)
    store.create(Bundle({**source.metadata, "id": "local-cgroup", "state": "candidate"},
                        dict(source.content), dict(source.dependencies)))
    result = store.collect(ids=["store:local-cgroup", CGROUP], context_bytes=65536)
    assert [item["authority"] for item in result["items"]] == ["store", "package"]
    assert [c["ref"] for c in result["contexts"]] == [f"package:{CGROUP}"]
    assert result["context_omissions"] == [
        {"ref": "store:local-cgroup", "reason": "unsupported_context"},
    ]
    filtered = store.collect(ids=["store:local-cgroup"], repo="inferrsi", context_bytes=65536)
    assert filtered["omissions"] == [{"id": "store:local-cgroup", "reason": "filters"}]


def test_h3_readsets_are_mandatory_even_without_lexical_overlap():
    result = KnowledgeReader().collect(ids=[H3], relevance="orchid", context_bytes=65536)
    assert not result["context_omissions"]
    paths = {r["path"] for r in result["contexts"][0]["resources"]}
    prefix = "data/skill_library/repositories/h3-c/audit-h3-runtime-residency/"
    for path in ("SKILL.md", "LICENSE", "references/source-notes.md",
                 "references/source-identity.json", "references/minimax-h3-weight-inventory.json"):
        assert prefix + path in paths


def test_parent_owner_license_is_mandatory_and_budgeted_for_cross_skill_references():
    identity = "inferrsi.common.skills.audit_vllm_kv_lifetimes"
    license_path = "data/skill_library/repositories/vllm/LICENSE"
    reader = KnowledgeReader()
    for owner in (identity, AFD):
        result = reader.collect(ids=[owner], context_bytes=100000)
        assert not result["context_omissions"]
        context = result["contexts"][0]
        license_resource, = [r for r in context["resources"] if r["path"] == license_path]
        expected = reader.resource(context["ref"], license_path, revision=context["revision"])
        assert license_resource["content"].encode() == expected
        assert license_resource["sha256"] == hashlib.sha256(expected).hexdigest()
    bundle = reader.read(identity)
    core = bundle.metadata["skill_documents"]["original"]
    limited = reader.collect(ids=[identity], context_bytes=len(bundle.content[core]))
    assert not limited["contexts"]
    omission = limited["context_omissions"][0]
    assert omission["reason"] == "context_limit"
    assert omission["required_bytes"] >= (
        len(bundle.content[core]) + len(bundle.content[license_path])
    )


def test_optimized_request_preserves_identity_collisions(tmp_path):
    owner = tmp_path / "owner"
    cases = owner / "cases"
    cases.mkdir(parents=True)
    (owner / "SKILL.md").write_text("---\nname: owner\ndescription: Local test\n---\nCore")
    (cases / "note.md").write_text("Local case")
    (cases / "case.json").write_text(json.dumps({
        "id": CGROUP, "kind": "case", "content": "note.md", "state": "candidate",
        "sources": [{"type": "internal", "issue": "test", "artifact": "local-case"}],
        "applicability": {}, "limitations": [], "attribution": [],
    }))
    result = KnowledgeReader(skill_root=tmp_path).collect(
        ids=[CGROUP, f"package:{CGROUP}", f"checkout:{CGROUP}"],
        relevance="cgroupv2", context_bytes=65536,
    )
    assert result["collisions"] == [CGROUP]
    assert result["omissions"][0]["reason"] == "ambiguous_identity"
    assert [item["authority"] for item in result["items"]] == ["package", "checkout"]
    assert [c["ref"] for c in result["contexts"]] == [f"package:{CGROUP}"]


@pytest.mark.parametrize("options", [
    {"relevance": ""}, {"relevance": " -- "}, {"relevance": 3},
    {"context_bytes": 0}, {"context_bytes": -1}, {"context_bytes": 1.5},
])
def test_invalid_opt_ins_fail_at_request_boundary(options):
    with pytest.raises(ValueError):
        KnowledgeReader().collect(**options)


def test_cli_exposes_context_in_json_and_text(capsys):
    args = ["collect", "--id", CGROUP, "--relevance", "cgroupv2", "--context-bytes", "65536"]
    assert main([*args, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["contexts"][0]["resources"][0]["role"] == "core"
    assert main(args) == 0
    assert "--- begin context package:" in capsys.readouterr().out
    assert main(["collect", "--id", CGROUP, "--context-bytes", "1"]) == 0
    assert "context_omitted\tcontext_limit" in capsys.readouterr().out
