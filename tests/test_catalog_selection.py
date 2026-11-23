import json
import os
import shutil

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


@pytest.mark.parametrize("change", ["same_stat", "add", "remove"])
def test_cached_snapshot_detects_unselected_resource_changes(catalog, change):
    resource = catalog.skill_root / "beta" / "LICENSE"
    resource.write_text("first")
    snapshot = catalog.snapshot(kinds=("skill",))
    if change == "same_stat":
        before = resource.stat()
        resource.write_text("other")
        os.utime(resource, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == "add":
        (resource.parent / "new.md").write_text("new dependency")
    else:
        resource.unlink()
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")],
                         kinds=("skill",), expansion_depth=0)
    assert error.value.code == "stale_snapshot"


def test_cached_snapshot_detects_new_owner_and_scope_changes(catalog):
    old = catalog.snapshot(kinds=("skill",))
    skill(catalog.skill_root, "gamma", "New owner")
    current = catalog.snapshot(kinds=("skill",))
    assert current["snapshot_id"] != old["snapshot_id"]
    assert "checkout:gamma" in {c["ref"] for c in current["cards"]}
    assert catalog.snapshot(kinds=("case",))["cards"] == []


@pytest.mark.parametrize("name", ["observation.pyc", ".DS_Store", "__pycache__/notes.txt"])
def test_explicit_case_resources_are_checked_even_with_incidental_names(catalog, name):
    cases = catalog.skill_root / "beta" / "cases"
    resource = cases / name
    resource.parent.mkdir(parents=True)
    resource.write_text("first observation")
    record = {
        "id": "case.explicit", "kind": "case", "state": "historical_observation",
        "content": name, "sources": [{"type": "unknown"}], "applicability": [],
        "limitations": [], "attribution": "fixture",
    }
    (cases / "explicit.json").write_text(json.dumps(record))
    snapshot = catalog.snapshot()
    card = next(c for c in snapshot["cards"] if c["ref"] == "checkout:case.explicit")
    assert "unreadable" not in card
    resource.write_text("other observation")
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")],
                         expansion_depth=0)
    assert error.value.code == "stale_snapshot"


def test_authored_record_symlink_target_changes_are_not_cached(tmp_path, monkeypatch):
    import shutil

    from inferrsi.knowledge import catalog as records
    from inferrsi.knowledge import knowledge_find, knowledge_operations

    package = tmp_path / "package"
    library = package / "knowledge" / "data" / "skill_library"
    shutil.copytree(knowledge_find.installed_skill_root(), library)
    path = library / "records" / "xdit.cuda.diffusion.parallelism_freshness_and_topology.json"
    target = tmp_path / "external-record.json"
    target.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    for module in (records, knowledge_find, knowledge_operations):
        monkeypatch.setattr(module, "files", lambda _: package)
    catalog = CatalogSelection()
    snapshot = catalog.snapshot(kinds=("record",))
    record = json.loads(target.read_text())
    record["summary"] += " Changed external source."
    target.write_text(json.dumps(record))
    current = catalog.snapshot(kinds=("record",))
    assert current["snapshot_id"] != snapshot["snapshot_id"]
    assert current == CatalogSelection().snapshot(kinds=("record",))
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [], kinds=("record",))
    assert error.value.code == "stale_snapshot"


def test_source_changes_during_delivery_reject_cached_snapshot(catalog, monkeypatch):
    snapshot = catalog.snapshot(kinds=("skill",))
    original = catalog._context

    def changing_read(*args):
        result = original(*args)
        (catalog.skill_root / "beta" / "NOTICE").write_text("changed during read")
        return result

    monkeypatch.setattr(catalog, "_context", changing_read)
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")],
                         kinds=("skill",), expansion_depth=0)
    assert error.value.code == "stale_snapshot"


def test_source_changes_during_build_are_not_published(catalog, monkeypatch):
    original = catalog._build

    def changing_build(**scope):
        result = original(**scope)
        skill(catalog.skill_root, "gamma", "Added during build")
        return result

    monkeypatch.setattr(catalog, "_build", changing_build)
    with pytest.raises(SelectionError) as error:
        catalog.snapshot(kinds=("skill",))
    assert error.value.code == "stale_snapshot"


def test_cached_snapshot_checks_store_revisions(catalog):
    import tempfile
    from pathlib import Path

    from inferrsi.knowledge.knowledge_operations import Bundle
    from inferrsi.knowledge.knowledge_store import KnowledgeStore

    source = catalog._reader().read("checkout:beta")
    metadata = {**source.metadata, "id": "stored-beta", "state": "candidate"}
    with tempfile.TemporaryDirectory() as directory:
        catalog.store = KnowledgeStore(Path(directory), skill_root=catalog.skill_root)
        initial = catalog.snapshot(kinds=("skill",))
        revision = catalog.store.create(Bundle(metadata, source.content, source.dependencies))
        snapshot = catalog.snapshot(kinds=("skill",))
        assert snapshot["snapshot_id"] != initial["snapshot_id"]
        content = {**source.content, "beta/SKILL.md": source.content["beta/SKILL.md"] + b" new"}
        catalog.store.update(Bundle(metadata, content, source.dependencies), expected=revision,
                             reason="updated source", evidence=[])
        with pytest.raises(SelectionError) as error:
            catalog.complete(snapshot["snapshot_id"], [selection("store:stored-beta")],
                             kinds=("skill",))
        assert error.value.code == "stale_snapshot"


def test_returned_prompt_and_context_do_not_poison_later_reads(catalog):
    snapshot = catalog.snapshot(kinds=("skill",))
    expected = snapshot["snapshot_id"]
    snapshot["cards"][0]["revision"] = "caller-modified"
    snapshot["references"].clear()
    result = catalog.complete(expected, [selection("checkout:alpha")], kinds=("skill",))
    result["contexts"][0]["sources"][0]["note"] = "caller-modified"
    assert catalog.snapshot(kinds=("skill",))["snapshot_id"] == expected
    again = catalog.complete(expected, [selection("checkout:alpha")], kinds=("skill",))
    assert "caller-modified" not in json.dumps(again)


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


@pytest.mark.parametrize("field", ["engine_version", "dependency_version"])
def test_only_literal_release_versions_produce_match_or_conflict(field):
    for ambiguous in ("1.4.x", "1.X", "1.*", ">=1.4", "latest", "1.0-2.0"):
        for source, task in [(ambiguous, "1.4.2"), ("1.4.2", ambiguous)]:
            assert compare_conditions({field: source}, {field: task})["verdict"] == "unknown"
    assert compare_conditions({field: "1.4.2"}, {field: "1.4.3"})["verdict"] == "conflict"
    for exact in ("1.4.2", "v1.4.2-rc.1", "2.6.0+cu124"):
        assert compare_conditions({field: exact}, {field: exact})["verdict"] == "match"


def test_record_backend_agrees_in_card_and_judgment():
    catalog = CatalogSelection()
    ref = "package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
    scope = {"kinds": ("record",)}
    snapshot = catalog.snapshot(**scope)
    card = next(card for card in snapshot["cards"] if card["ref"] == ref)
    assert card["conditions"]["backend"] == "ascend"
    for backend, purpose, verdict in (("cuda", "conclusion", "conflict"),
                                      ("cuda", "method", "analogue"),
                                      ("ascend", "conclusion", "match")):
        result = catalog.complete(snapshot["snapshot_id"], [selection(ref, purpose=purpose)],
                                  conditions={"backend": backend}, expansion_depth=0, **scope)
        judgment, = result["judgments"]
        assert judgment["verdict"] == verdict
        assert judgment["comparisons"][0]["locator"] == "backend"
        assert judgment["verification"]["locally_verified"] is False


@pytest.mark.parametrize("sidecar", [False, True])
def test_flat_skill_backend_in_scope_and_judgment(tmp_path, sidecar):
    folder = skill(tmp_path, "alpha", metadata={"backend": "ascend"} if sidecar else None)
    if not sidecar:
        core = folder / "SKILL.md"
        core.write_text(core.read_text().replace("name: alpha", "name: alpha\nbackend: ascend"))
    scope = {"kinds": ("skill",), "backend": "ascend"}
    catalog = CatalogSelection(skill_root=tmp_path)
    snapshot = catalog.snapshot(**scope)
    card, = snapshot["cards"]
    assert card["conditions"]["backend"] == "ascend"
    result = catalog.complete(snapshot["snapshot_id"], [selection(card["ref"])],
                              conditions={"backend": "cuda"}, **scope)
    judgment, = result["judgments"]
    assert judgment["verdict"] == "conflict"
    locator = "metadata.json#backend" if sidecar else "SKILL.md#backend"
    assert judgment["comparisons"][0]["locator"] == locator


def test_cache_scan_error_uses_current_reader_inputs(catalog, monkeypatch):
    from pathlib import Path

    unrelated = catalog.skill_root / "scratch.log"
    unrelated.write_bytes(b"unregistered")
    scope = {"kinds": ("skill",)}
    old = catalog.snapshot(**scope)
    read_bytes = Path.read_bytes

    def denied(path):
        if path == unrelated:
            raise PermissionError("unreadable unregistered file")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    assert catalog.complete(old["snapshot_id"], [selection("checkout:alpha")],
                            expansion_depth=0, **scope)["contexts"]
    note = catalog.skill_root / "alpha" / "amendment.md"
    note.write_text("updated material")
    with pytest.raises(SelectionError) as err:
        catalog.complete(old["snapshot_id"], [selection("checkout:alpha")], **scope)
    assert err.value.code == "stale_snapshot"


def test_optional_link_parse_failure_preserves_neighbors_and_fallback(catalog):
    path = catalog.skill_root / "alpha" / "SKILL.md"
    path.write_text(path.read_text() + "\n[unfinished link](https://[draft)")
    scope = {"kinds": ("skill",)}
    snapshot = catalog.snapshot(**scope)
    result = catalog.complete(snapshot["snapshot_id"], [selection("checkout:alpha")], **scope)
    assert {item["ref"] for item in result["contexts"]} == {"checkout:alpha", "checkout:beta"}
    assert any(p.get("stop") == "unresolved" and p["via"].get("reason") == "invalid_url"
               for p in result["retrieval"]["assembly"]["paths"])
    fallback = prepare_catalog_selection(catalog, "Beta", token_budget=1, **scope)
    assert fallback["status"] == "fallback" and fallback["fallback"]["items"]


def test_direct_checkout_closure_budget_and_revision(tmp_path):
    metadata = {"sources": [{"type": "unknown", "third_party_notices": "../NOTICE.txt"}],
                "provenance_readsets": ["../evidence/notes.md"]}
    skill(tmp_path, "demo", "Procedure", metadata)
    (tmp_path / "evidence").mkdir()
    for path in ("NOTICE.txt", "LICENSE", "evidence/notes.md", "evidence/LICENSE"):
        (tmp_path / path).write_text("source " + path)
    catalog = CatalogSelection(skill_root=tmp_path)
    scope = {"kinds": ("skill",)}
    ref = "checkout:demo"
    snapshot = catalog.snapshot(**scope)
    result = catalog.complete(snapshot["snapshot_id"], [selection(ref)], expansion_depth=0, **scope)
    context, = result["contexts"]
    assert {r["path"] for r in context["resources"]} == {
        "demo/SKILL.md", "demo/metadata.json", "NOTICE.txt", "LICENSE",
        "evidence/notes.md", "evidence/LICENSE",
    }
    size = sum(len(r["content"].encode()) for r in context["resources"])
    limited = catalog.complete(snapshot["snapshot_id"], [selection(ref)], context_bytes=size - 1,
                               expansion_depth=0, **scope)
    assert limited["contexts"] == []
    assert limited["omissions"][0]["scope"] == "entry"
    assert limited["omissions"][0]["required_bytes"] == size
    (tmp_path / "NOTICE.txt").write_text("changed notice")
    with pytest.raises(SelectionError, match="Sources changed"):
        catalog.complete(snapshot["snapshot_id"], [selection(ref)], **scope)
    (tmp_path / "NOTICE.txt").unlink()
    fresh = catalog.snapshot(**scope)
    assert fresh["cards"][0]["unreadable"]


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
    limited = catalog.complete(snapshot["snapshot_id"], [selection(ref)], expansion_bytes=1)
    assert limited["contexts"][0]["ref"] == ref
    omission = next(o for o in limited["omissions"] if o["reason"] == "context_limit")
    assert omission["scope"] == "resource" and omission["ref"] == ref
    assert omission["path"] == omission["via"]["path"]


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
    assert confirmed["assessments"][0]["claim"] == "A method"
    assert confirmed["assessments"][0]["reason"] == "Source analogy only"
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

    def unavailable(*args, **kwargs):
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


@pytest.fixture
def package_library(tmp_path, monkeypatch):
    from inferrsi.knowledge import catalog as records
    from inferrsi.knowledge import knowledge_find, knowledge_operations

    package = tmp_path / "package"
    library = package / "knowledge/data/skill_library"
    shutil.copytree(knowledge_find.installed_skill_root(), library)
    for module in (records, knowledge_find, knowledge_operations):
        monkeypatch.setattr(module, "files", lambda _: package)
    return library


@pytest.mark.parametrize("invalid", ["binary", "metadata"])
def test_optional_resource_failure_preserves_other_selections(package_library, invalid):
    owner = package_library / "systems/engines/vllm/sub-skills/operation-performance"
    if invalid == "binary":
        (owner / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    else:
        (owner / "metadata.json").write_text("{", encoding="utf-8")
    catalog = CatalogSelection()
    snapshot = catalog.snapshot(kinds=("record",))
    refs = ["package:vllm.common.llm.bounded_serving_measurement",
            "package:vllm.common.llm.runtime_and_kv_ownership"]
    result = catalog.complete(snapshot["snapshot_id"], [selection(ref) for ref in refs],
                              kinds=("record",), expansion_bytes=1000000)
    assert [c["ref"] for c in result["contexts"]] == refs
    omission, = result["omissions"]
    assert omission["scope"] == "resource" and omission["ref"] == refs[0]
    assert omission["reason"] == "invalid_resource"
    assert omission["path"].endswith("operation-performance/SKILL.md")
    # No partial closure or byte charge survives the failed expansion.
    assert [r["path"] for r in result["contexts"][0]["resources"]] == ["record.json"]
    delivered = [p for p in result["retrieval"]["assembly"]["paths"]
                 if p.get("status") == "delivered" and p.get("via")]
    assert len(delivered) == 1 and delivered[0]["via"]["from"] == refs[1]
    assert result["retrieval"]["assembly"]["expansion_bytes"] == delivered[0]["bytes"]


def test_optional_resource_revision_conflict_rejects_entire_snapshot(monkeypatch):
    from inferrsi.knowledge.knowledge_operations import RevisionConflict

    catalog = CatalogSelection()
    snapshot = catalog.snapshot(kinds=("record",))

    def changed(*args, **kwargs):
        raise RevisionConflict("Changed during optional read")

    monkeypatch.setattr(catalog, "_reference_context", changed)
    ref = "package:vllm.common.llm.bounded_serving_measurement"
    with pytest.raises(SelectionError) as error:
        catalog.complete(snapshot["snapshot_id"], [selection(ref)], kinds=("record",))
    assert error.value.code == "stale_snapshot"


def test_expansion_deduplicates_required_closure_before_budgeting(package_library):
    path = package_library / "records/vllm.common.llm.bounded_serving_measurement.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    extra = "data/skill_library/systems/engines/vllm/sub-skills/extend-validate/SKILL.md"
    record["skill_documents"]["other"] = extra
    path.write_text(json.dumps(record), encoding="utf-8")
    catalog = CatalogSelection()
    snapshot = catalog.snapshot(kinds=("record",))
    ref = "package:vllm.common.llm.bounded_serving_measurement"

    def complete(budget):
        return catalog.complete(snapshot["snapshot_id"], [selection(ref)],
                                kinds=("record",), expansion_bytes=budget)

    result = complete(1000000)
    context, = result["contexts"]
    resources = {r["path"]: r for r in context["resources"]}
    assert len(resources) == len(context["resources"])
    assert extra in resources
    assert "data/skill_library/systems/engines/vllm/LICENSE" in resources
    size = sum(len(r["content"].encode()) for p, r in resources.items() if p != "record.json")
    assert result["retrieval"]["assembly"]["expansion_bytes"] == size
    exact = complete(size)
    assert not exact["omissions"]
    assert exact["contexts"] == result["contexts"]
    limited = complete(size - 1)
    omission, = limited["omissions"]
    assert omission["scope"] == "resource" and omission["path"] == extra
    assert omission["reason"] == "context_limit"
    assert not any(r["path"] == extra for r in limited["contexts"][0]["resources"])
    assert omission["required_bytes"] == omission["available_bytes"] + 1
