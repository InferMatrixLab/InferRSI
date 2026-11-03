import json
from pathlib import Path

import pytest

from inferrsi.cli import main
from inferrsi.skill_catalog import (
    get_skill,
    skill_directories,
    skill_instructions,
    skill_metadata,
    skill_records,
    skill_reference,
    skill_resource,
)

PROJECT = Path(__file__).resolve().parents[1]


def _symlink(target: Path, link: Path) -> None:
    # Symlink creation needs Developer Mode or admin rights on Windows;
    # skip instead of failing where the platform refuses.
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_checkout_catalog_is_metadata_only():
    root = PROJECT / "src/inferrsi/data/skill_library"
    records = skill_records(root)
    assert len(records) == len(skill_directories(root))
    assert len(records) >= 32
    assert len({record["name"] for record in records}) == len(records)
    assert all(set(record) <= {"name", "description", "status", "tags"} for record in records)
    inherited = next(record for record in records if record["name"] == "claim-contract")
    assert set(inherited) == {"name", "description", "status", "tags"}
    casebook = next(
        record for record in records if record["name"] == "inference-optimization-casebook"
    )
    assert casebook["name"] == "inference-optimization-casebook"


def test_listing_never_decodes_instruction_body_or_resources(tmp_path):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_bytes(
        b"---\nname: selected\ndescription: >\n  Folded YAML\n  description\n---\n\xff\xfe"
    )
    (directory / "resource.bin").write_bytes(b"\xff\xfe")
    assert skill_records(tmp_path) == [
        {"name": "selected", "description": "Folded YAML description\n"}
    ]
    assert get_skill(tmp_path, "selected")["resources"] == ["resource.bin"]


def test_explicit_selection_and_resource_resolution(tmp_path, capsys):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: selected\ndescription: "Read: exactly one"\n---\n# Selected body\n',
        encoding="utf-8",
        newline="\n",
    )
    references = directory / "references"
    references.mkdir()
    resource = references / "notes.md"
    resource.write_text("Resource content stays on demand.\n", encoding="utf-8")
    other = tmp_path / "unselected"
    other.mkdir()
    (other / "SKILL.md").write_bytes(b"\xff\xfe")
    assert skill_instructions(tmp_path, "selected") == "# Selected body\n"
    assert main(["skills", "--root", str(tmp_path), "show", "selected"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["instructions"] == "# Selected body\n"
    assert record["resources"] == ["references/notes.md"]
    assert "does not authorize" in record["authority"]
    assert "Resource content" not in json.dumps(record)
    assert main(
        ["skills", "--root", str(tmp_path), "resource", "selected", "references/notes.md"]
    ) == 0
    assert Path(json.loads(capsys.readouterr().out)["path"]) == resource.resolve()
    assert skill_resource(tmp_path, "selected", "references/notes.md") == resource.resolve()
    with pytest.raises(ValueError, match="inside"):
        skill_resource(tmp_path, "selected", "../unselected/SKILL.md")
    with pytest.raises(ValueError, match="Unknown"):
        skill_resource(tmp_path, "selected", "missing.md")


def test_instruction_symlink_escape_rejected(tmp_path):
    # Regression: the skill directory stays inside the selected root, but
    # SKILL.md symlinks to an outside file. The outside file must not be
    # named SKILL.md under a root-level directory, or the listing glob
    # would match it as its own skill.
    directory = tmp_path / "selected"
    directory.mkdir()
    outside = tmp_path / "outside" / "stolen.md"
    outside.parent.mkdir()
    outside.write_text(
        "---\nname: selected\ndescription: test\n---\n# Outside body\n",
        encoding="utf-8",
        newline="\n",
    )
    _symlink(outside, directory / "SKILL.md")
    with pytest.raises(ValueError, match="inside"):
        skill_records(tmp_path)
    with pytest.raises(ValueError, match="inside"):
        skill_instructions(tmp_path, "selected")
    with pytest.raises(ValueError, match="inside"):
        get_skill(tmp_path, "selected")


def test_metadata_symlink_escape_rejected(tmp_path):
    # Regression: metadata.json symlinks outside; listing and reference
    # resolution must both reject it.
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: selected\ndescription: test\n---\n", encoding="utf-8", newline="\n"
    )
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"status": "candidate", "references": []}))
    _symlink(outside, directory / "metadata.json")
    with pytest.raises(ValueError, match="inside"):
        skill_records(tmp_path)
    with pytest.raises(ValueError, match="inside"):
        skill_reference(tmp_path, "selected", "notes.md")


def test_cli_list(capsys):
    root = PROJECT / "src/inferrsi/data/skill_library"
    assert main(["skills", "--root", str(root), "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == skill_records(root)


@pytest.mark.parametrize("name", ["../claim-contract", "unknown", "Claim-Contract", ""])
def test_selection_rejects_invalid_or_unknown_names(name):
    with pytest.raises(ValueError):
        get_skill(PROJECT / "src/inferrsi/data/skill_library", name)


@pytest.mark.parametrize(
    "frontmatter",
    [
        "name: selected\n",
        "---\nname: selected\n",
        "---\n- selected\n---\n",
        "---\nname: other\ndescription: test\n---\n",
        "---\nname: selected\ndescription: test\ntags: string\n---\n",
        "---\nname: selected\ndescription: [broken\n---\n",
    ],
)
def test_frontmatter_boundary_validation(tmp_path, frontmatter):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text(frontmatter, encoding="utf-8")
    with pytest.raises(ValueError):
        skill_records(tmp_path)


@pytest.mark.parametrize(
    "sidecar",
    [
        # recommendations must be a list of non-empty strings
        '{"recommendations": "Read this first."}',
        '{"recommendations": [""]}',
        '{"recommendations": [1]}',
        '{"recommendations": null}',
        # applicability must be a mapping of strings or non-empty string lists
        '{"applicability": []}',
        '{"applicability": {"scope": ""}}',
        '{"applicability": {"prerequisites": ["a", 2]}}',
        '{"applicability": {"hardware": []}}',
        '{"applicability": {"prerequisites": 3}}',
        '{"searchspace_not_applicable": ""}',
        '{"searchspace_not_applicable": "  "}',
        '{"searchspace_not_applicable": null}',
        '{"searchspace_not_applicable": []}',
        '{"searchspace_not_applicable": {"reason": "process only"}}',
    ],
)
def test_recommendation_and_applicability_shape_is_validated(tmp_path, sidecar):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: selected\ndescription: test\n---\n', encoding="utf-8"
    )
    (directory / "metadata.json").write_text(sidecar, encoding="utf-8")
    with pytest.raises(ValueError):
        skill_records(tmp_path)


def test_explicit_empty_recommendations_is_a_statement_not_a_shape_error(tmp_path):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        '---\nname: selected\ndescription: test\n---\n', encoding="utf-8"
    )
    (directory / "metadata.json").write_text(
        '{"recommendations": [], "applicability": {"hardware": "not-applicable"}}',
        encoding="utf-8",
    )
    record = skill_records(tmp_path)[0]
    assert record["name"] == "selected"
    assert skill_metadata(tmp_path, "selected")["recommendations"] == []
    assert skill_metadata(tmp_path, "selected")["applicability"] == {
        "hardware": "not-applicable"
    }
