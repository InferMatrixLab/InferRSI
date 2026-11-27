"""Collect migration checks for selectors and budgeted optional resources."""

import hashlib

import pytest

from inferrsi.knowledge._skill_selection import indexed_skill
from inferrsi.knowledge._source_snapshot import source_entry
from inferrsi.knowledge.knowledge_operations import KnowledgeReader, _hash, _json


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
            source_entry(path): _hash(data)
            for path, data in library.items() if path.startswith(prefix) or path == registry_path
        }
    reader = KnowledgeReader()
    reader._records = records
    reader._library = library, "sha256:" + _hash(_json({
        path: _hash(data) for path, data in sorted(library.items())
    }))
    return reader


@pytest.mark.parametrize(("options", "message"), [
    ({"relevance_method": "weighted-lexical-v1"}, "Omit the method or use 'find-lexical-v1'"),
    ({"relevance_method": "weighted-raw-string-v1", "relevance": "cue"}, "find-lexical-v1"),
    ({"relevance_method": "task-lexical-v1", "ids": ["owner"]}, "find-lexical-v1"),
    ({"relevance_method": "unknown"}, "Unsupported relevance_method"),
    ({"relevance_method": []}, "Unsupported relevance_method"),
    ({"query": "filtered", "relevance": "cue"}, "Use find"),
    ({"query": "filtered", "ids": ["owner"]}, "Use find"),
])
def test_retired_selectors_and_ambiguous_inputs_fail_before_reader_access(
    monkeypatch, options, message,
):
    reader = KnowledgeReader()

    def unexpected_access():
        raise AssertionError("invalid request accessed owners")

    monkeypatch.setattr(reader, "owners", unexpected_access)
    with pytest.raises(ValueError, match=message):
        reader.collect(**options)


def test_optional_context_uses_find_and_required_files_keep_atomic_exact_bytes():
    reader = synthetic_reader({"owner": {
        "title": "n", "core": "Core é", "references": ["refs.md"],
        "resources": {"refs.md": "Required", "LICENSE": "Legal", "a.md": "\n", "b.md": "n"},
    }})
    identity, = reader.records()
    bundle = reader.read(identity)
    view = {**bundle.view(), "authority": "package"}
    _, required, _ = indexed_skill(reader.records()[identity], view, bundle.content)
    required_bytes = sum(len(bundle.content[path]) for path in required)
    too_small = reader.collect(ids=[identity], relevance="n", context_bytes=required_bytes - 1)
    assert not too_small["contexts"]
    assert too_small["context_omissions"][0]["reason"] == "context_limit"

    no_cue = reader.collect(ids=[identity], context_bytes=required_bytes + 1)
    assert no_cue["contexts"][0]["resources"][-1]["path"].endswith("/a.md")
    for budget in (required_bytes, required_bytes + 1, required_bytes + 2):
        result = reader.collect(
            ids=[identity], revisions={identity: bundle.revision},
            relevance="n", context_bytes=budget,
        )
        assert result["items"] == no_cue["items"]
        assert result["selection"]["ranking_applied"] is False
        context, = result["contexts"]
        assert context["revision"] == bundle.revision
        resources = context["resources"]
        assert [r["path"] for r in resources[:len(required)]] == required
        for resource in resources:
            data = reader.resource(identity, resource["path"], revision=context["revision"])
            assert resource["content"].encode() == data
            assert resource["sha256"] == hashlib.sha256(data).hexdigest()
        omissions = {r["path"].rsplit("/", 1)[-1]: r["reason"] for r in context["omissions"]}
        assert omissions["a.md"] == "not_relevant"
        if budget == required_bytes:
            assert omissions["b.md"] == "context_limit"
            assert context["content_bytes"] == required_bytes
        else:
            assert resources[-1]["path"].endswith("/b.md")
            assert context["content_bytes"] == required_bytes + 1
