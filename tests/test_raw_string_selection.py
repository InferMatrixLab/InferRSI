"""Ordinary synthetic compatibility controls, not a retrieval-quality benchmark."""

import copy
import hashlib
import json

import pytest

from inferrsi._skill_selection import (
    indexed_skill,
    lexical_score,
    raw_string_lexical_score,
    skill_score,
)
from inferrsi.cli import main
from inferrsi.knowledge_operations import KnowledgeReader, _hash, _json
from inferrsi.knowledge_store import KnowledgeStore

RAW = "weighted-raw-string-v1"
LEGACY = "weighted-lexical-v1"


def synthetic_reader(entries):
    """Exercise the real package adapter using a complete in-memory test library."""
    registry_path = "data/skill_library/skill-index.json"
    registry = {"schema_version": 1, "skills": {}}
    library, records = {}, {}
    for name, fields in entries.items():
        path = f"methods/{name}"
        prefix = f"data/skill_library/{path}/"
        registry["skills"][name] = {"path": path, "backend": "common"}
        library[prefix + "SKILL.md"] = fields.get("core", "").encode()
        for relative, text in fields.get("resources", {}).items():
            library[prefix + relative] = text.encode()
        identity = f"inferrsi.common.skills.{name.replace('-', '_')}"
        records[identity] = {
            "id": identity, "title": fields.get("title", ""),
            "summary": fields.get("summary", ""), "tags": fields.get("tags", []),
            "applicability": fields.get("applicability", {}),
            "sources": [{"type": "internal", "issue": "test", "artifact": "synthetic"}],
            "status": "candidate", "verification": "synthetic-only", "repo": "inferrsi",
            "backend": "common", "scenario": "skills.discovery", "tier": "contribution",
            "index_type": "packaged-skill", "skill_documents": {"original": prefix + "SKILL.md"},
            "skill_metadata": {"name": name, "references": fields.get("references", [])},
        }
    library[registry_path] = _json(registry)
    for record in records.values():
        prefix = record["skill_documents"]["original"].removesuffix("SKILL.md")
        record["source_files"] = {
            "src/inferrsi/" + path: _hash(data)
            for path, data in library.items() if path.startswith(prefix) or path == registry_path
        }
    reader = KnowledgeReader()
    reader._records = records
    reader._library = library, "sha256:" + _hash(_json({
        path: _hash(data) for path, data in sorted(library.items())
    }))
    return reader


def without_method(result):
    value = copy.deepcopy(result)
    value.get("selection", {}).pop("method", None)
    return value


@pytest.mark.parametrize("value", [None, True, 13.5, ["\n\t", None], {"n": "\r"}])
def test_nonstring_values_retain_exact_legacy_json_matching(value):
    cue = "n t r null true 13 5"
    assert raw_string_lexical_score(cue, [(2, value)]) == lexical_score(cue, [(2, value)])


def test_raw_string_matching_does_not_change_the_legacy_helper():
    assert raw_string_lexical_score("n t", [(4, "\n\t")]) == 0
    assert lexical_score("n t", [(4, "\n\t")]) == 8
    assert raw_string_lexical_score("n t", [(4, r"\n\t")]) == 8
    assert raw_string_lexical_score("RUN run STRASSE", [(3, "running Straße")]) == 6


def test_skill_adapter_keeps_field_weights_and_combined_nonstring_metadata():
    record = {"title": "n", "summary": "n", "tags": ["\n"], "applicability": {}}
    assert skill_score("n N", record, b"n", method=RAW) == 10
    assert skill_score("n N", record, b"n") == 10
    with pytest.raises(ValueError, match="Unknown relevance method"):
        skill_score("n", record, b"n", method="unknown")


def test_opt_in_changes_only_raw_string_owner_ranking_and_positive_admission():
    reader = synthetic_reader({
        "a-phantom": {"title": "\n", "summary": "\n", "core": "\n"},
        "b-hit": {"title": "n"}, "c-hit": {"title": "n"},
    })
    legacy = reader.collect(relevance="n")
    assert legacy == reader.collect(relevance="n", relevance_method=LEGACY)
    assert [r["title"] for r in legacy["items"]] == ["\n", "n", "n"]
    raw = reader.collect(relevance="n", relevance_method=RAW)
    expected = ["inferrsi.common.skills.b_hit", "inferrsi.common.skills.c_hit"]
    assert [r["id"] for r in raw["items"]] == expected
    assert raw["selection"] == {
        "method": RAW, "cue": "n", "scope": "generated-packaged-skills", "ranking_applied": True,
    }
    assert reader.collect(relevance="n", relevance_method=RAW, limit=1)["items"] == raw["items"][:1]
    assert reader.collect() == reader.collect(relevance_method=LEGACY)


@pytest.mark.parametrize("options", [
    {"query": "missing"}, {"query": "synthetic n"},
    {"kind": "skill"}, {"repo": "vllm"}, {"backend": "cpu"},
    {"tier": "peer"}, {"scenario": "diffusion.t2i"}, {"material": True},
])
def test_query_and_filters_preserve_ordinary_semantics(options):
    reader = synthetic_reader({"item": {"title": "running", "core": "n"}})
    legacy = reader.collect(relevance="n", **options)
    raw = reader.collect(relevance="n", relevance_method=RAW, **options)
    assert without_method(raw) == without_method(legacy)


def test_explicit_ids_keep_membership_order_aliases_revisions_and_item_budgets():
    reader = synthetic_reader({"a": {"title": "\n"}, "b": {"title": "n"}})
    a, b = sorted(reader.records())
    options = {"ids": [b, a, "package:" + a], "relevance": "absent", "material": True}
    legacy = reader.collect(**options)
    raw = reader.collect(**options, relevance_method=RAW)
    assert without_method(raw) == without_method(legacy)
    assert [r["id"] for r in raw["items"]] == [b, a]
    assert raw["selection"]["ranking_applied"] is False
    for extra in (
        {"limit": 1}, {"max_bytes": len(_json(raw["items"][0]))},
        {"revisions": {a: reader.read(a).revision}}, {"revisions": {a: "sha256:" + "0" * 64}},
    ):
        assert without_method(reader.collect(**options, **extra, relevance_method=RAW)) == (
            without_method(reader.collect(**options, **extra))
        )


@pytest.mark.parametrize("explicit", [False, True])
def test_context_required_hashes_atomic_budgets_and_optional_legacy_order(explicit):
    reader = synthetic_reader({"owner": {
        "title": "n", "core": "Core é", "references": ["refs.md"],
        "resources": {"refs.md": "Required", "LICENSE": "Legal", "a.md": "\n", "b.md": "n"},
    }})
    identity, = reader.records()
    bundle = reader.read(identity)
    view = {**bundle.view(), "authority": "package"}
    _, required, _ = indexed_skill(reader.records()[identity], view, bundle.content)
    required_bytes = sum(len(bundle.content[path]) for path in required)
    options = {"relevance": "n"}
    if explicit:
        options["ids"] = [identity]
    for budget in (required_bytes - 1, required_bytes, required_bytes + 1, required_bytes + 2):
        legacy = reader.collect(**options, context_bytes=budget)
        raw = reader.collect(**options, context_bytes=budget, relevance_method=RAW)
        assert without_method(raw) == without_method(legacy)
        if budget < required_bytes:
            assert not raw["contexts"]
            assert raw["context_omissions"][0]["reason"] == "context_limit"
            continue
        context, = raw["contexts"]
        assert context["revision"] == bundle.revision
        assert context["content_bytes"] == budget
        resources = context["resources"]
        assert [r["path"] for r in resources[:len(required)]] == required
        for resource in resources:
            data = reader.resource(identity, resource["path"], revision=context["revision"])
            assert resource["content"].encode() == data
            assert resource["sha256"] == hashlib.sha256(data).hexdigest()
        if budget > required_bytes:
            # JSON's newline contribution must still admit the optional a.md first.
            assert resources[len(required)]["path"].endswith("/a.md")


@pytest.mark.parametrize("options", [
    {"relevance_method": RAW}, {"relevance_method": "unknown"},
    {"relevance": "n", "relevance_method": "unknown"},
    {"relevance": "n", "relevance_method": None},
    {"relevance": "n", "relevance_method": []},
    {"relevance": "!!!", "relevance_method": RAW},
])
def test_method_validation_happens_before_reader_access(monkeypatch, options):
    reader = KnowledgeReader()

    def unexpected_access():
        raise AssertionError("invalid request accessed owners")

    monkeypatch.setattr(reader, "owners", unexpected_access)
    with pytest.raises(ValueError):
        reader.collect(**options)


def test_raw_method_keeps_fail_closed_index_validation():
    reader = synthetic_reader({"owner": {"title": "n"}})
    identity, = reader.records()
    reader.records()[identity]["source_files"] = {}
    result = reader.collect(relevance="n", relevance_method=RAW)
    assert result["no_match"]
    assert result["omissions"][0]["reason"] == "index_unavailable"


def test_cli_and_store_delegate_the_explicit_method(monkeypatch, capsys, tmp_path):
    reader = synthetic_reader({"owner": {"title": "n"}})
    monkeypatch.setattr("inferrsi.cli._knowledge_reader", lambda args: reader)
    assert main(["collect", "--relevance", "n", "--relevance-method", RAW, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["selection"]["method"] == RAW
    with pytest.raises(SystemExit):
        main(["collect", "--relevance", "n", "--relevance-method", "unknown"])
    with pytest.raises(SystemExit) as error:
        main(["collect", "--relevance-method", RAW])
    assert error.value.code == 2
    store = KnowledgeStore(tmp_path, skill_root=None)
    monkeypatch.setattr(store, "reader", lambda: reader)
    assert store.collect(relevance="n", relevance_method=RAW) == reader.collect(
        relevance="n", relevance_method=RAW
    )
