import json
from pathlib import Path

import pytest

from inferrsi.skill_catalog import skill_directory, skill_records, skill_reference

ROOT = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"


def test_local_profiles_preserve_core_and_structured_ownership():
    records = skill_records(ROOT)
    normalized = []
    for record in records:
        sidecar = skill_directory(ROOT, record["name"]) / "metadata.json"
        if not sidecar.exists():
            continue
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if metadata.get("profile") != "local-skill-v1":
            continue
        normalized.append(record["name"])
        assert "name" not in metadata and "description" not in metadata
        assert metadata["status"] == record["status"]
        assert metadata["kind"] == "skill"
        for readset in metadata["provenance_readsets"]:
            assert (sidecar.parent / readset).is_file()
    assert len(normalized) == 53


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
    reference = "../inference-optimization-casebook/cases/admission-drain-occupancy.md"
    first = skill_reference(ROOT, "inference-benchmark-design", reference)
    second = skill_reference(ROOT, "dense-performance-evidence", reference)
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
