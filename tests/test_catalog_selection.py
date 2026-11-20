import json

import pytest

from inferrsi.apps.knowledge import prepare_catalog_selection, select_catalog_evidence
from inferrsi.knowledge.catalog_selection import (
    CatalogSelection,
    SelectionError,
    compare_conditions,
)
from inferrsi.knowledge.knowledge_find import load_documents


def skill(root, name, body="", metadata=None):
    folder = root / name
    folder.mkdir(exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test {name}\n---\n{body}", encoding="utf-8"
    )
    if metadata:
        (folder / "metadata.json").write_text(json.dumps(metadata))
    return folder


def selection(ref, **extra):
    return {"ref": ref, "reason": "Relevant mechanism", "questions": [], **extra}


@pytest.fixture
def catalog(tmp_path):
    skill(tmp_path, "alpha", "Alpha [beta](../beta/SKILL.md) [web](https://example.org)")
    skill(tmp_path, "beta", "Beta [alpha](../alpha/SKILL.md) [lost](missing.md)")
    return CatalogSelection(skill_root=tmp_path)


def test_complete_catalog_and_cross_directory_reads():
    catalog = CatalogSelection()
    snapshot = catalog.snapshot()
    assert sum(snapshot["counts"].values()) == len(load_documents())
    assert {"case", "skill", "record"} == set(snapshot["counts"])
    assert not any(c["id"].startswith("task-") for c in snapshot["cards"])
    chosen = [
        next(c for c in snapshot["cards"] if c["kind"] == kind)
        for kind in ("skill", "case", "record")
    ]
    result = catalog.complete(
        snapshot["snapshot_id"],
        [selection(c["ref"]) for c in chosen],
        context_bytes=1000000,
        expansion_depth=0,
    )
    assert len(result["contexts"]) == 3
    assert not result["omissions"]
    assert all(c["resources"] for c in result["contexts"])
    assert all(i["agent_read"] == "unknown" for i in result["retrieval"]["items"])


def test_selection_validation_and_empty(catalog):
    snapshot = catalog.snapshot(kinds=("skill",))
    assert catalog.complete(snapshot["snapshot_id"], [], kinds=("skill",))["contexts"] == []
    with pytest.raises(SelectionError, match="qualified"):
        catalog.complete(snapshot["snapshot_id"], [selection("alpha")], kinds=("skill",))
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [selection("checkout:outside")], kinds=("skill",))
    assert error.value.code == "outside_snapshot"
    with pytest.raises(SelectionError, match="Repeated"):
        catalog.complete(
            snapshot["snapshot_id"], [selection("checkout:alpha")] * 2, kinds=("skill",)
        )


def test_stale_required_resource_and_selection(catalog):
    dependency = catalog.skill_root / "alpha" / "required.md"
    dependency.write_text("first")
    snapshot = catalog.snapshot()
    dependency.write_text("second")
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")])
    assert error.value.code == "stale_snapshot"


def test_expansion_cycles_limits_and_required_budget(catalog):
    snapshot = catalog.snapshot()
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], expansion_depth=5
    )
    assert [c["ref"] for c in result["contexts"]] == ["checkout:alpha", "checkout:beta"]
    reasons = {p.get("stop") for p in result["retrieval"]["assembly"]["paths"]}
    assert {"external_pointer", "unresolved", "cycle_or_duplicate"} <= reasons
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], expansion_items=0
    )
    assert len(result["contexts"]) == 1
    assert any(p.get("stop") == "item_budget" for p in result["retrieval"]["assembly"]["paths"])
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], context_bytes=1
    )
    assert result["contexts"] == []
    assert result["omissions"]
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], expansion_bytes=1
    )
    assert len(result["contexts"]) == 1
    assert result["omissions"]


@pytest.mark.parametrize(
    "declared,task,purpose,verdict",
    [
        ({"dtype": "BF16"}, {"dtype": "bf16"}, "conclusion", "match"),
        ({}, {"dtype": "bf16"}, "conclusion", "unknown"),
        ({"dtype": "bf16"}, {"dtype": None}, "conclusion", "unknown"),
        ({"dtype": "W8A8"}, {"dtype": "BF16"}, "conclusion", "conflict"),
        ({"dtype": "W8A8"}, {"dtype": "BF16"}, "method", "analogue"),
        ({"engine_version": ">=1.0"}, {"engine_version": "1.1"}, "conclusion", "unknown"),
        ({"hardware": "Measured on NPU"}, {"hardware": "NPU"}, "conclusion", "unknown"),
        ({"dtype": ["bf16", "fp16"]}, {"dtype": "fp16"}, "conclusion", "match"),
        ({"backend": "common"}, {"backend": "ascend"}, "method", "unknown"),
    ],
)
def test_condition_rules(declared, task, purpose, verdict):
    assert compare_conditions(declared, task, purpose=purpose)["verdict"] == verdict


def test_model_seam_and_budget_fallback(catalog):
    calls = []

    def selector(prompt):
        calls.append(prompt)
        return {
            "snapshot_id": prompt["catalog"]["snapshot_id"],
            "selections": [selection("checkout:alpha")],
        }

    result = select_catalog_evidence(
        catalog, "beta", selector, model="fixture-selector", token_budget=1000000, kinds=("skill",)
    )
    assert len(calls) == 1
    assert len(calls[0]["catalog"]["cards"]) == 2
    assert len(result["contexts"]) == 2
    result = select_catalog_evidence(
        catalog, "alpha", selector, model="fixture-selector", token_budget=1, kinds=("skill",)
    )
    assert result["status"] == "fallback"
    assert result["reason"] == "catalog_over_budget"
    assert result["fallback"]["items"]
    assert len(calls) == 1
    assert "prompt" not in result


def test_filters_record_all_exclusions(catalog):
    snapshot = catalog.snapshot(kinds=("skill",))
    assert snapshot["scope"]["considered"] == (
        len(snapshot["cards"]) + sum(snapshot["scope"]["excluded"].values())
    )
    assert snapshot["counts"] == {"skill": 2}


def test_counter_accounts_for_entire_input(catalog):
    seen = []

    def count(text):
        seen.append(text)
        return len(text)

    result = prepare_catalog_selection(
        catalog,
        "question",
        token_budget=100000,
        token_counter=count,
        tokenizer="fixture-chars",
        kinds=("skill",),
    )
    assert "question" in seen[0] and "instructions" in seen[0]
    assert result["accounting"]["input_tokens"] >= len(seen[-1])


def test_store_path_cannot_shadow_checkout_and_metadata_survives(catalog, tmp_path):
    # The store must be outside the checkout's protected parent.
    import tempfile

    from inferrsi.knowledge.knowledge_operations import Bundle
    from inferrsi.knowledge.knowledge_store import KnowledgeStore

    with tempfile.TemporaryDirectory() as directory:
        store = KnowledgeStore(__import__("pathlib").Path(directory), skill_root=catalog.skill_root)
        source = catalog._reader().read("checkout:beta")
        metadata = {
            **source.metadata,
            "id": "beta-copy",
            "state": "candidate",
            "applicability": {"dtype": "bf16"},
            "limitations": ["Source warning"],
        }
        store.create(Bundle(metadata, source.content, source.dependencies))
        catalog.store = store
        snapshot = catalog.snapshot(kinds=("skill",))
        card = next(c for c in snapshot["cards"] if c["ref"] == "store:beta-copy")
        assert card["conditions"] == {"dtype": "bf16"}
        assert "Source warning" in card["limitations"]
        edges = snapshot["references"]["checkout:alpha"]
        assert next(e for e in edges if e["kind"] == "entry")["ref"] == "checkout:beta"
        result = prepare_catalog_selection(catalog, "Beta", token_budget=1, kinds=("skill",))
        assert result["fallback"]["corpus_size"] == 3
        assert "beta-copy" in [i["id"] for i in result["fallback"]["items"]]


def test_query_version_is_not_silently_dropped(catalog):
    body = catalog.skill_root / "alpha" / "SKILL.md"
    body.write_text(body.read_text().replace("../beta/SKILL.md", "../beta/SKILL.md?revision=old"))
    snapshot = catalog.snapshot()
    result = catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")])
    assert [c["ref"] for c in result["contexts"]] == ["checkout:alpha"]
    assert any(
        p.get("stop") == "unsupported_version_or_query"
        for p in result["retrieval"]["assembly"]["paths"]
    )


def test_direct_skill_required_resources_are_atomic(catalog):
    required = catalog.skill_root / "alpha" / "LICENSE"
    required.write_text("Required attribution " * 100)
    snapshot = catalog.snapshot()
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], context_bytes=500
    )
    assert result["contexts"] == []
    assert result["omissions"][0]["required_bytes"] > 500
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], expansion_depth=0
    )
    assert any(r["path"] == "alpha/LICENSE" for r in result["contexts"][0]["resources"])


def test_record_declared_skill_link_reads_complete_resources():
    catalog = CatalogSelection()
    snapshot = catalog.snapshot()
    ref = "package:vllm.common.llm.bounded_serving_measurement"
    edges = snapshot["references"][ref]
    assert any(e["source_path"].startswith("record.json#skill_documents") for e in edges)
    result = catalog.complete(snapshot["snapshot_id"], [selection(ref)], expansion_bytes=1000000)
    paths = {r["path"] for c in result["contexts"] for r in c["resources"]}
    assert any(p.endswith("operation-performance/SKILL.md") for p in paths)
    assert any(p.endswith("commands-and-measurements.md") for p in paths)
    assert any(p.endswith("LICENSE") for p in paths)


def test_post_read_assessment_rejects_invented_quotes(catalog):
    from inferrsi.apps.knowledge import confirm_catalog_evidence

    snapshot = catalog.snapshot()
    result = catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")])
    context = result["contexts"][0]
    assessment = dict(
        ref=context["ref"],
        revision=context["revision"],
        path="alpha/SKILL.md",
        quote="Alpha",
        claim="A method",
        reason="Source analogy only",
        validation_step="Replay on target",
        verdict="analogue",
        missing=["hardware"],
    )
    confirmed = confirm_catalog_evidence(result, [assessment])
    assert confirmed["assessments"][0]["source_verification_upgraded"] is False
    with pytest.raises(ValueError, match="quote"):
        confirm_catalog_evidence(result, [{**assessment, "quote": "invented passage"}])


@pytest.mark.parametrize("ref", [[], {}, None, 42])
def test_invalid_id_types_are_recoverable(catalog, ref):
    snapshot = catalog.snapshot(kinds=("skill",))
    with pytest.raises(SelectionError):
        catalog.complete(snapshot["snapshot_id"], [selection(ref)], kinds=("skill",))


def test_linked_procedure_declared_closure_not_optional_navigation(catalog):
    from inferrsi.knowledge.knowledge_operations import Bundle

    metadata = {
        "references": ["../required.md"],
        "provenance_readsets": ["../evidence.md"],
        "sources": [{"third_party_notices": "../NOTICE.txt"}],
    }
    body = "---\nname: linked\ndescription: test\nmetadata:\n  inferrsi: |\n    " + json.dumps(
        metadata
    )
    body += "\n---\nProcedure [optional](../missing.md)"
    original = catalog._reader().read("checkout:alpha")
    bundle = Bundle(
        original.metadata,
        {
            **original.content,
            "linked/SKILL.md": body.encode(),
            "required.md": b"mandatory",
            "evidence.md": b"provenance",
            "NOTICE.txt": b"attribution",
        },
        {},
    )

    class Reader:
        def read(self, ref, revision):
            assert revision == bundle.revision
            return bundle

    context, omission = catalog._reference_context(
        Reader(), "checkout:alpha", "linked/SKILL.md", bundle.revision, 10000
    )
    assert omission is None
    assert {"required.md", "evidence.md", "NOTICE.txt"} <= {r["path"] for r in context["resources"]}
    context, omission = catalog._reference_context(
        Reader(), "checkout:alpha", "linked/SKILL.md", bundle.revision, 1
    )
    assert context is None and omission["reason"] == "context_limit"


def test_missing_optional_parser_keeps_visible_unreadable_cards(catalog, monkeypatch):
    from inferrsi.knowledge._knowledge_errors import MissingSkillsExtra
    from inferrsi.knowledge.knowledge_operations import KnowledgeReader

    def unavailable(*args):
        raise MissingSkillsExtra("Install skills extra")

    monkeypatch.setattr(KnowledgeReader, "_skill", unavailable)
    snapshot = catalog.snapshot(kinds=("skill",))
    assert len(snapshot["cards"]) == 2
    assert all(c["unreadable"]["reason"] == "MissingSkillsExtra" for c in snapshot["cards"])
    result = catalog.complete(
        snapshot["snapshot_id"], [selection("checkout:alpha")], kinds=("skill",)
    )
    assert not result["contexts"]
    assert result["omissions"][0]["reason"] == "unreadable"
