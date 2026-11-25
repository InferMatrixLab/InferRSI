import hashlib
import json
from pathlib import Path

import pytest

from inferrsi.knowledge._skill_selection import FIND_RELEVANCE
from inferrsi.knowledge.knowledge_operations import Bundle, KnowledgeReader, _hash, _json
from inferrsi.knowledge.knowledge_store import KnowledgeStore

ROOT = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/data/skill_library"
CGROUP = "inferrsi.common.skills.cgroup_resource_controls"
H3 = "inferrsi.common.skills.audit_h3_runtime_residency"
AFD = "inferrsi.cuda.skills.audit_afd_p2p_exchanges"


@pytest.mark.parametrize(("cue", "identity"), [
    ("cgroupv2", CGROUP),
    ("MiniMax-H3 AdaLN SSD", H3),
    ("P2pNccl", AFD),
    ("DLRover replica recovery", "inferrsi.common.skills.checkpoint_recovery_consistency"),
    ("cgroupv2 cpu.stat.local", CGROUP),
])
def test_find_discovery_returns_known_material_with_a_context_budget(cue, identity):
    result = KnowledgeReader().collect(relevance=cue, context_bytes=65536, limit=3)
    assert result["items"][0]["id"] == identity
    assert not [o for o in result["omissions"] if o["reason"] == "index_unavailable"]
    assert result["context_bytes"] <= 65536


def test_default_query_and_relevance_use_the_same_find_ranking():
    reader = KnowledgeReader()
    assert reader.collect(relevance="floristry orchid")["no_match"]
    cue = "前缀缓存"
    result = reader.collect(cue, limit=3)
    explicit = reader.collect(relevance=cue, relevance_method=FIND_RELEVANCE, limit=3)
    assert result["items"] == explicit["items"]
    assert result["selection"] == explicit["selection"]
    assert result["items"][0]["id"] == "sglang.cuda.llm.hierarchical_prefix_cache"
    assert result["retrieval"]["calls"] == ["collect", "find"]
    assert result["retrieval"]["items"] == explicit["retrieval"]["items"]


def test_existing_item_payload_and_material_accounting_are_unchanged():
    reader = KnowledgeReader()
    old = reader.collect(ids=[CGROUP], material=True)
    assert set(old) == {
        "items", "omissions", "no_match", "collisions", "material_bytes", "limitations",
        "retrieval",
    }
    new = reader.collect(ids=[CGROUP], material=True, context_bytes=65536)
    assert new["items"] == old["items"]
    assert new["material_bytes"] == old["material_bytes"] == len(_json(old["items"][0]))
    assert json.loads(new["items"][0]["content"])["id"] == CGROUP
    assert new["contexts"][0]["resources"][0]["path"].endswith("/SKILL.md")
    assert new["contexts"][0]["omissions"] == []
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
    assert reader.collect(relevance="cgroupv2", repo="vllm")["no_match"]
    assert reader.collect(relevance="cgroupv2", kind="skill")["items"][0]["id"] == CGROUP
    assert reader.collect(relevance="cgroupv2", scenario="diffusion.t2i")[
        "items"
    ][0]["scenario"] == "skills.discovery"
    assert reader.collect(ids=[CGROUP], scenario="diffusion.t2i")["omissions"] == [
        {"id": CGROUP, "reason": "filters"},
    ]
    result = reader.collect(
        relevance="cgroupv2", kind="knowledge", repo="inferrsi", tier="contribution",
        backend="cpu", scenario="skills.discovery",
    )
    assert result["items"][0]["id"] == CGROUP


def test_inventory_without_a_cue_uses_identity_order():
    reader = KnowledgeReader()
    result = reader.collect(limit=3)
    assert [item["ref"] for item in result["items"]] == reader.identities()[:3]
    assert result["retrieval"]["calls"] == ["collect"]
    assert not result["retrieval"]["selection"]["ranking_applied"]
    assert reader.collect(limit=3, relevance_method=FIND_RELEVANCE)["items"] == result["items"]


def test_context_keeps_complete_core_prerequisites_provenance_and_exact_bytes():
    reader = KnowledgeReader()
    bounded = reader.collect(ids=[AFD], context_bytes=65536)
    assert bounded["items"] and not bounded["contexts"]
    omission, = bounded["context_omissions"]
    assert omission["reason"] == "context_limit"
    assert omission["available_bytes"] == 65536 < omission["required_bytes"]
    result = reader.collect(ids=[AFD], context_bytes=omission["required_bytes"])
    assert not result["context_omissions"]
    context = result["contexts"][0]
    item = result["items"][0]
    assert (context["ref"], context["revision"]) == (item["ref"], item["revision"])
    assert context["sources"] == item["sources"]
    paths = {r["path"] for r in context["resources"]}
    assert "data/skill_library/systems/engines/vllm/audit-vllm-kv-lifetimes/SKILL.md" in paths
    assert "data/skill_library/playbooks/measurement/inference-benchmark-design/SKILL.md" in paths
    assert any(path.endswith("/references/source-notes.md") for path in paths)
    for resource in context["resources"]:
        actual = reader.resource(context["ref"], resource["path"], revision=context["revision"])
        delivered = resource["content"].encode()
        assert resource["sha256"] == hashlib.sha256(delivered).hexdigest()
        if resource["path"].endswith("/SKILL.md") and b"  inferrsi: |" in actual:
            import yaml

            assert resource["locator"] == "skill-procedure"
            assert resource["source_sha256"] == hashlib.sha256(actual).hexdigest()
            first, second = resource["source_byte_ranges"]
            assert first[0] == 0 < first[1] < second[0] < second[1] == len(actual)
            assert actual[:first[1]] + actual[second[0]:] == delivered
            original_header, original_body = actual.split(b"---", 2)[1:]
            header, body = delivered.split(b"---", 2)[1:]
            expected = yaml.safe_load(original_header)
            del expected["metadata"]["inferrsi"]
            if not expected["metadata"]:
                del expected["metadata"]
            assert yaml.safe_load(header) == expected
            assert body == original_body
        else:
            assert resource["locator"] == "whole-resource"
            assert delivered == actual
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
        result = reader.collect("cgroupv2")
        assert result["no_match"]
        assert any(o["reason"] == "index_unavailable" for o in result["omissions"])
        explicit = reader.collect(ids=[CGROUP], context_bytes=65536)
        assert explicit["items"] and not explicit["contexts"]
        assert explicit["context_omissions"][0]["reason"] == "index_unavailable"
        assert reader.collect(ids=[CGROUP], revisions={CGROUP: original})["omissions"][0][
            "reason"
        ] == "unavailable_revision"


def test_store_delegates_but_copied_package_metadata_cannot_gain_context(tmp_path, monkeypatch):
    source = KnowledgeReader().read(CGROUP)
    store = KnowledgeStore(tmp_path, skill_root=None)
    candidate = Bundle({**source.metadata, "id": "local-cgroup", "state": "candidate"},
                       dict(source.content), dict(source.dependencies))
    old = store.create(candidate)
    result = store.collect(ids=["store:local-cgroup", CGROUP], context_bytes=65536)
    assert [item["authority"] for item in result["items"]] == ["store", "package"]
    assert [c["ref"] for c in result["contexts"]] == [f"package:{CGROUP}"]
    assert result["context_omissions"] == [
        {"ref": "store:local-cgroup", "reason": "unsupported_context"},
    ]
    filtered = store.collect(ids=["store:local-cgroup"], repo="inferrsi", context_bytes=65536)
    assert filtered["omissions"] == [{"id": "store:local-cgroup", "reason": "filters"}]
    current = store.update(
        Bundle({**candidate.metadata, "limitations": ["updated"]},
               candidate.content, candidate.dependencies),
        expected=old, reason="Revise the candidate", evidence=[],
    )
    assert current != old
    history = KnowledgeStore(tmp_path, skill_root=None, read_only=True)
    read = history.read
    calls = []

    def count_reads(identity, *, revision):
        calls.append((identity, revision))
        return read(identity, revision=revision)

    monkeypatch.setattr(history, "read", count_reads)
    ref = "store:local-cgroup"
    result = history.collect(ids=[ref], revisions={ref: old}, decision_cards={ref: None},
                             context_bytes=65536)
    assert calls == [("local-cgroup", old)]
    assert result["items"][0]["revision"] == old
    assert result["context_omissions"] == [{"ref": ref, "reason": "unsupported_context"}]
    assert result["contexts"] == [] and result["context_bytes"] == 0
    assert result["decision_cards"] == [{"ref": ref, "revision": old, "status": "no_body"}]


def test_h3_readsets_are_mandatory_even_without_lexical_overlap():
    result = KnowledgeReader().collect(ids=[H3], relevance="orchid", context_bytes=65536)
    assert not result["context_omissions"]
    paths = {r["path"] for r in result["contexts"][0]["resources"]}
    prefix = "data/skill_library/systems/engines/h3-c/audit-h3-runtime-residency/"
    for path in ("SKILL.md", "LICENSE", "references/source-notes.md",
                 "references/source-identity.json", "references/minimax-h3-weight-inventory.json"):
        assert prefix + path in paths


def test_parent_owner_license_is_mandatory_and_budgeted_for_cross_skill_references():
    identity = "inferrsi.common.skills.audit_vllm_kv_lifetimes"
    license_path = "data/skill_library/systems/engines/vllm/LICENSE"
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
    context, = reader.collect(ids=[identity], context_bytes=100000)["contexts"]
    core_resource, = (entry for entry in context["resources"] if entry["path"] == core)
    core_size = len(core_resource["content"].encode())
    limited = reader.collect(ids=[identity], context_bytes=core_size)
    assert not limited["contexts"]
    omission = limited["context_omissions"][0]
    assert omission["reason"] == "context_limit"
    assert omission["required_bytes"] >= (
        core_size + len(bundle.content[license_path])
    )


@pytest.mark.parametrize(("identity", "cue", "path"), [
    (AFD, "P2pNccl", "data/skill_library/systems/engines/afd-plugin/"
     "audit-afd-p2p-exchanges/references/afd-plugin-LICENSE.md"),
    (H3, "orchid", "data/skill_library/systems/engines/h3-c/"
     "audit-h3-runtime-residency/references/THIRD_PARTY_NOTICES.md"),
])
def test_retained_legal_resources_ignore_relevance_and_use_atomic_budget(identity, cue, path):
    reader = KnowledgeReader()
    bundle = reader.read(identity)
    assert cue.casefold() not in (path + bundle.content[path].decode()).casefold()
    result = reader.collect(ids=[identity], relevance=cue, context_bytes=100000)
    assert not result["context_omissions"]
    context = result["contexts"][0]
    resource, = [item for item in context["resources"] if item["path"] == path]
    assert resource["content"].encode() == bundle.content[path]
    assert resource["sha256"] == hashlib.sha256(bundle.content[path]).hexdigest()
    assert path not in {item["path"] for item in context["omissions"]}
    assert context["content_bytes"] == sum(
        len(item["content"].encode()) for item in context["resources"]
    )
    required_bytes = context["content_bytes"]
    limited = reader.collect(ids=[identity], relevance=cue, context_bytes=required_bytes - 1)
    assert not limited["contexts"] and limited["context_bytes"] == 0
    assert limited["context_omissions"][0]["reason"] == "context_limit"
    assert limited["context_omissions"][0]["required_bytes"] == required_bytes


def test_missing_declared_notice_is_explicitly_unavailable():
    reader = KnowledgeReader()
    reader.records()[H3]["skill_metadata"]["sources"][0]["third_party_notices"] = (
        "references/missing-notice.md"
    )
    result = reader.collect(ids=[H3], context_bytes=100000)
    assert result["items"] and not result["contexts"]
    assert result["context_omissions"][0]["reason"] == "index_unavailable"


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
    from inferrsi.apps.cli import main

    args = ["collect", "--id", CGROUP, "--relevance", "cgroupv2", "--context-bytes", "65536"]
    assert main([*args, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["contexts"][0]["resources"][0]["role"] == "core"
    assert main(args) == 0
    assert "--- begin context package:" in capsys.readouterr().out
    assert main(["collect", "--id", CGROUP, "--context-bytes", "1"]) == 0
    assert "context_omitted\tcontext_limit" in capsys.readouterr().out


@pytest.fixture
def pinned_skills(tmp_path):
    reader = KnowledgeReader(skill_root=tmp_path)
    pins = {}
    for name in ("alpha", "beta"):
        owner = tmp_path / name
        owner.mkdir()
        declaration = json.dumps({"recommendations": [f"{name} 的建议"]}, ensure_ascii=False)
        (owner / "SKILL.md").write_bytes((
            f"---\nname: {name}\ndescription: Measure latency.\n---\n{name} 正文\n"
        ).encode())
        (owner / "metadata.json").write_bytes(declaration.encode())
        ref = f"checkout:{name}"
        pins[ref] = reader.read(ref).revision
    return reader, pins


def test_collect_delivers_all_bodies_before_whole_utf8_cards(pinned_skills):
    reader, pins = pinned_skills
    first, second = pins
    options = {"ids": list(pins), "revisions": pins}
    default = reader.collect(**options, context_bytes=10000)
    empty = reader.collect(**options, context_bytes=10000, decision_cards={})
    assert _json(empty) == _json(default)
    assert "decision_cards" not in default
    assert "decision_cards" not in default["retrieval"]["request"]
    requested = {second: None, first: None}
    single = reader.read_decision_card(first, revision=pins[first])
    payload = json.dumps(single["card"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert "建议" in payload and len(payload.encode()) > len(payload)
    body_bytes = sum(len(r["content"].encode()) for c in default["contexts"]
                     for r in c["resources"])
    exact_budget = body_bytes + len(payload.encode())
    exact = reader.collect(**options, decision_cards=requested, context_bytes=exact_budget)
    fit, omitted = exact["decision_cards"]
    assert exact["contexts"] == default["contexts"] and len(exact["contexts"]) == 2
    assert fit == single
    assert omitted["ref"] == second and omitted["status"] == "over_budget"
    assert omitted["max_bytes"] == 0 and "card" not in omitted
    assert exact["context_bytes"] == exact_budget
    short = reader.collect(**options, decision_cards={first: None}, context_bytes=exact_budget - 1)
    failure, = short["decision_cards"]
    assert short["contexts"] == default["contexts"] and short["context_bytes"] == body_bytes
    assert failure["status"] == "over_budget" and "card" not in failure
    assert failure["card_bytes"] == len(payload.encode()) == failure["max_bytes"] + 1
    later_bytes = reader.read_decision_card(second, revision=pins[second])["card_bytes"]
    later = reader.collect(**options, decision_cards=requested,
                           context_bytes=body_bytes + later_bytes)
    skipped, delivered = later["decision_cards"]
    assert skipped["status"] == "over_budget" and delivered["card"]["ref"] == second
    assert later["context_bytes"] == body_bytes + later_bytes


def test_collect_projects_from_the_delivered_bundle(pinned_skills, tmp_path, monkeypatch):
    reader, pins = pinned_skills
    first, second = pins
    fresh = reader._read
    calls = []

    def replace_after_read(ref, revision):
        assert ref not in calls, "L1 reopened a selected bundle"
        calls.append(ref)
        bundle = fresh(ref, revision)
        if ref == first:
            (tmp_path / "alpha" / "metadata.json").write_bytes(b'{"recommendations":["new"]}')
        return bundle

    with monkeypatch.context() as patch:
        patch.setattr(reader, "_read", replace_after_read)
        result = reader.collect(ids=list(pins), revisions=pins, context_bytes=10000,
                                decision_cards={first: None})
    assert calls == [first, second]
    entry, = result["decision_cards"]
    assert entry["revision"] == result["contexts"][0]["revision"] == pins[first]
    assert entry["card"]["decision"]["recommendation"] == ["alpha 的建议"]
    assert entry["source_resource"] == "alpha/metadata.json"
    assert result["contexts"][0]["resources"][0]["path"] == entry["body_resource"]
    result = reader.collect(ids=list(pins), revisions=pins, context_bytes=10000,
                            decision_cards={first: None, second: None})
    missing, valid = result["decision_cards"]
    assert missing == {"ref": first, "revision": pins[first], "status": "no_body"}
    assert result["omissions"][0]["reason"] == "unavailable_revision"
    assert valid["card"]["ref"] == second and [c["ref"] for c in result["contexts"]] == [second]


def test_collect_decision_card_requires_explicit_membership_and_pin(pinned_skills):
    reader, pins = pinned_skills
    first, second = pins
    pairs = [
        ({"ids": [first], "decision_cards": {"alpha": None}}, "qualified ref"),
        ({"ids": [first], "decision_cards": {second: None}}, "qualified ref"),
        ({"ids": [first], "decision_cards": {"package:alpha": None}}, "qualified ref"),
        ({"ids": [first], "decision_cards": {first: None}}, "exact revision"),
        ({"decision_cards": {first: None}}, "explicit ids"),
        ({"ids": [first], "revisions": pins, "decision_cards": {first: ""}}, "selector"),
    ]
    for options, message in pairs:
        with pytest.raises(ValueError, match=message):
            reader.collect(context_bytes=10000, **options)
    with pytest.raises(ValueError, match="context_bytes"):
        reader.collect(ids=list(pins), revisions=pins, decision_cards={first: None})
    result = reader.collect(ids=list(pins), revisions=pins, decision_cards={first: None},
                            context_bytes=1)
    missing, = result["decision_cards"]
    assert missing == {"ref": first, "revision": pins[first], "status": "no_body"}
    assert result["context_omissions"][0]["reason"] == "context_limit"


def test_collect_cli_pins_one_original_case_finding(capsys):
    from inferrsi.apps.cli import main

    reader = KnowledgeReader(skill_root=ROOT)
    ref = "checkout:case.qwen-ascend-rejected-directions"
    revision = reader.read(ref).revision
    args = ["collect", "--installed-library", "--id", ref, "--revision", f"{ref}={revision}",
            "--context-bytes", "1000000"]
    selector = "case.json#/findings/1"
    assert main([*args, "--decision-card", f"{ref}={selector}", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    card, = result["decision_cards"]
    expected = reader.read_decision_card(ref, revision=revision, finding=selector)
    assert card == {**expected, "finding": selector}
    original = json.loads(reader.resource(ref, card["source_resource"], revision=revision))
    assert card["card"]["declared"]["finding"] == original["findings"][1]
    for wrong in (ref, f"{ref}=id:no-such-finding"):
        assert main([*args, "--decision-card", wrong, "--json"]) == 0
        rejected = json.loads(capsys.readouterr().out)
        assert rejected["contexts"] == result["contexts"]
        failure, = rejected["decision_cards"]
        assert failure["status"] == "unavailable" and "card" not in failure
    with pytest.raises(SystemExit) as duplicate:
        main([*args, "--decision-card", ref, "--decision-card", ref])
    assert duplicate.value.code == 2
    assert "Duplicate decision card request" in capsys.readouterr().err
