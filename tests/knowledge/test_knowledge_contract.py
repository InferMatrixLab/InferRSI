import json
import os
import re
from pathlib import Path

import pytest

from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.skill_catalog import (
    skill_directories,
    skill_directory,
    skill_metadata,
    skill_records,
    skill_reference,
)

ROOT = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/data/skill_library"


def test_local_profiles_preserve_core_and_structured_ownership():
    records = skill_records(ROOT)
    normalized = []
    for record in records:
        directory = skill_directory(ROOT, record["name"])
        assert not (directory / "metadata.json").exists()
        metadata = skill_metadata(ROOT, record["name"])
        if metadata.get("profile") != "local-skill-v1":
            continue
        normalized.append(record["name"])
        assert metadata["name"] == record["name"] and metadata["description"]
        assert metadata["status"] == record["status"]
        assert metadata["kind"] == "skill"
        for readset in metadata["provenance_readsets"]:
            assert (directory / readset).is_file()
    assert len(normalized) == 78


def test_local_profiles_omit_fields_that_equal_reader_defaults():
    # Readers default absent sources/references to [] and applicability to {};
    # a stored empty or placeholder value would only repeat that default.
    placeholder = {"scope": "See procedure prerequisites and counter-signals"}
    for record in skill_records(ROOT):
        directory = skill_directory(ROOT, record["name"])
        assert not (directory / "metadata.json").exists()
        metadata = skill_metadata(ROOT, record["name"])
        assert metadata.get("sources") != [], record["name"]
        assert metadata.get("references") != [], record["name"]
        assert metadata.get("applicability") != placeholder, record["name"]


def _case_records():
    for directory in skill_directories(ROOT).values():
        for path in sorted(directory.glob("cases/*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("kind") == "case":
                yield path, record


def test_case_documents_cite_their_record_without_copying_digests():
    cases = list(_case_records())
    assert len(cases) == 7
    for path, record in cases:
        body = (path.parent / record["content"]).read_text(encoding="utf-8")
        # The JSON record is the single home for source identities and digests;
        # pinned source URLs stay in the prose as citations.
        assert f"]({path.name})" in body, path.name
        prose = re.sub(r"https://\S+", "", body)
        assert not re.search(r"\b(?:[0-9a-f]{40}|[0-9a-f]{64})\b", prose), path.name
        for source in record["sources"]:
            for key in ("url", "evidence_url", "issue"):
                if key in source:
                    assert source[key] in body, (path.name, key)


def test_case_document_links_resolve_inside_the_delivered_bundle():
    reader = KnowledgeReader(skill_root=ROOT)
    for path, record in _case_records():
        bundle = reader.read(record["id"])
        body = bundle.content[bundle.metadata["entrypoint"]].decode("utf-8")
        links = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", body)
        local = [link for link in links if "://" not in link]
        assert path.name in local, path.name
        for link in local:
            data = reader.resource(record["id"], link, revision=bundle.revision)
            assert data == (path.parent / link).read_bytes(), (path.name, link)


def test_contradictory_legacy_metadata_fails(tmp_path):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: selected\ndescription: test\nstatus: candidate\n---\nProcedure\n"
    )
    (directory / "metadata.json").write_text('{"status":"active"}')
    with pytest.raises(ValueError, match="Conflicting.*status"):
        skill_records(tmp_path)


def test_two_real_consumers_resolve_one_authoritative_case():
    def read_case(owner):
        directory = skill_directory(ROOT, owner)
        case = skill_directory(ROOT, "inference-optimization-casebook") / "cases"
        relative = os.path.relpath(case / "admission-drain-occupancy.md", directory)
        return skill_reference(ROOT, owner, Path(relative).as_posix())

    first = read_case("inference-benchmark-design")
    second = read_case("dense-performance-evidence")
    assert first == second
    assert "## Observation" in first.read_text(encoding="utf-8")
    assert "## Interpretation" in first.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="Undeclared"):
        skill_reference(ROOT, "inference-benchmark-design", "../../README.md")


@pytest.mark.parametrize("reference", ["../../outside.md", "missing.md"])
def test_declared_reference_escape_and_missing_dependency_fail(tmp_path, reference):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text("---\nname: selected\ndescription: test\n---\n")
    (directory / "metadata.json").write_text(json.dumps({"references": [reference]}))
    with pytest.raises(ValueError, match="inside|Missing"):
        skill_reference(tmp_path, "selected", reference)


@pytest.mark.parametrize("references", ["private-notes.md", None, ["notes.md", 3], {"notes.md": 1}])
def test_malformed_references_fail_listing_and_resolution(tmp_path, references):
    # Regression: references that is not a string list is rejected by both
    # listing and reference resolution.
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text("---\nname: selected\ndescription: test\n---\n")
    (directory / "metadata.json").write_text(json.dumps({"references": references}))
    with pytest.raises(ValueError, match="references"):
        skill_records(tmp_path)
    with pytest.raises(ValueError, match="references"):
        skill_reference(tmp_path, "selected", "notes.md")


def test_string_references_never_authorize_substring_paths(tmp_path):
    # Regression: a string references value used to degrade membership
    # testing to substring matching.
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text("---\nname: selected\ndescription: test\n---\n")
    (directory / "notes.md").write_text("private\n", encoding="utf-8")
    (directory / "metadata.json").write_text(json.dumps({"references": "private-notes.md"}))
    with pytest.raises(ValueError, match="references"):
        skill_reference(tmp_path, "selected", "notes.md")
