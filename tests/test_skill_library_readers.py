import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.cli import main
from inferrsi.knowledge_operations import IdentityError, KnowledgeReader, RevisionConflict
from inferrsi.skill_catalog import (
    get_skill,
    skill_directories,
    skill_directory,
    skill_instructions,
    skill_records,
    skill_reference,
    skill_resource,
)


def _skill(root: Path, relative: str, *, body: bytes = b"Selected body\n") -> Path:
    directory = root / relative
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_bytes(
        f"---\nname: {directory.name}\ndescription: selected procedure\n---\n".encode() + body
    )
    return directory


def _index(root: Path, paths: dict[str, str]) -> None:
    (root / "skill-index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skills": {
                    name: {"path": path, "backend": "common"} for name, path in paths.items()
                },
            }
        ),
        encoding="utf-8",
    )


def _symlink(target: Path, link: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_indexed_selection_reads_only_selected_instructions(tmp_path):
    selected = _skill(tmp_path, "hardware/ascend/selected")
    _skill(tmp_path, "methods/unselected", body=b"\xff\xfe")
    _skill(tmp_path, "en/selected", body=b"not the registered edition")
    (selected / "notes.md").write_text("resource", encoding="utf-8")
    _index(tmp_path, {"selected": "hardware/ascend/selected", "unselected": "methods/unselected"})

    assert skill_directory(tmp_path, "selected") == selected.resolve()
    assert list(skill_directories(tmp_path)) == ["selected", "unselected"]
    assert [record["name"] for record in skill_records(tmp_path)] == ["selected", "unselected"]
    assert skill_instructions(tmp_path, "selected") == "Selected body\n"
    assert get_skill(tmp_path, "selected")["resources"] == ["notes.md"]
    assert skill_resource(tmp_path, "selected", "notes.md") == (selected / "notes.md").resolve()
    # A selected read does not even parse an unrelated skill's frontmatter.
    (tmp_path / "methods/unselected/SKILL.md").write_bytes(b"\xff\xfe")
    assert skill_instructions(tmp_path, "selected") == "Selected body\n"


def test_flat_roots_remain_supported_without_index(tmp_path):
    selected = _skill(tmp_path, "selected")
    assert skill_directories(tmp_path) == {"selected": selected.resolve()}
    assert skill_directory(tmp_path, "selected") == selected.resolve()
    assert skill_instructions(tmp_path, "selected") == "Selected body\n"
    with pytest.raises(ValueError, match="Unknown skill"):
        skill_directory(tmp_path, "unknown")


@pytest.mark.parametrize(
    "record",
    [
        [],
        {"schema_version": True, "skills": {}},
        {"schema_version": 2, "skills": {}},
        {"schema_version": 1, "skills": []},
        {"schema_version": 1, "skills": {"selected": "methods/selected"}},
        {"schema_version": 1, "skills": {"selected": {"path": 1, "backend": "common"}}},
        {"schema_version": 1, "skills": {"selected": {"path": "selected", "backend": []}}},
        {"schema_version": 1, "skills": {"selected": {"path": "selected", "backend": ""}}},
        {"schema_version": 1, "skills": {"selected": {"path": "selected", "backend": "invalid"}}},
    ],
)
def test_malformed_index_is_not_silently_treated_as_flat_root(tmp_path, record):
    _skill(tmp_path, "selected")
    (tmp_path / "skill-index.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="Skill index"):
        skill_directories(tmp_path)
    with pytest.raises(ValueError, match="Skill index"):
        skill_directory(tmp_path, "selected")


@pytest.mark.parametrize(
    "relative",
    ["../selected", "/selected", "C:/selected", "methods\\selected", "./selected", "a//selected"],
)
def test_index_paths_must_be_safe_relative_posix_paths(tmp_path, relative):
    _index(tmp_path, {"selected": relative})
    with pytest.raises(ValueError, match="relative POSIX"):
        skill_directories(tmp_path)


def test_index_preserves_identity_and_rejects_duplicate_fields(tmp_path):
    _skill(tmp_path, "methods/other")
    _index(tmp_path, {"selected": "methods/other"})
    with pytest.raises(ValueError, match="basename"):
        skill_directory(tmp_path, "selected")
    entry = '"selected": {"path": "methods/selected", "backend": "common"}'
    (tmp_path / "skill-index.json").write_text(
        '{"schema_version": 1, "skills": {' + entry + "," + entry + "}}", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Duplicate skill index"):
        skill_directories(tmp_path)


def test_index_rejects_symlink_directory_escape(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = _skill(tmp_path, "outside/selected")
    (root / "hardware").mkdir()
    _symlink(outside, root / "hardware/selected", directory=True)
    _index(root, {"selected": "hardware/selected"})
    with pytest.raises(ValueError, match="inside"):
        skill_directory(root, "selected")


@pytest.mark.parametrize("filename", ["skill-index.json", "SKILL.md"])
def test_index_rejects_symlink_file_escape(tmp_path, filename):
    root = tmp_path / "library"
    selected = _skill(root, "hardware/selected")
    _index(root, {"selected": "hardware/selected"})
    target = root / filename if filename == "skill-index.json" else selected / filename
    outside = tmp_path / "outside.txt"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    _symlink(outside, target)
    with pytest.raises(ValueError, match="inside"):
        skill_directory(root, "selected")


def test_nested_checkout_bundle_preserves_references_cases_and_revision(tmp_path):
    selected = _skill(tmp_path, "hardware/ascend/selected")
    other = _skill(tmp_path, "methods/other")
    notes = other / "notes.md"
    notes.write_text("first", encoding="utf-8")
    reference = "../../../methods/other/notes.md"
    (selected / "metadata.json").write_text(
        json.dumps({"references": [reference]}), encoding="utf-8"
    )
    cases = other / "cases"
    cases.mkdir()
    (cases / "note.md").write_text("observation", encoding="utf-8")
    (cases / "note.json").write_text(
        json.dumps(
            {
                "id": "case.nested",
                "kind": "case",
                "state": "historical_observation",
                "content": "note.md",
                "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
                "applicability": [],
                "limitations": [],
                "attribution": "fixture",
            }
        ),
        encoding="utf-8",
    )
    _index(tmp_path, {"selected": "hardware/ascend/selected", "other": "methods/other"})

    assert skill_reference(tmp_path, "selected", reference) == notes.resolve()
    reader = KnowledgeReader(skill_root=tmp_path)
    bundle = reader.read("selected")
    assert bundle.metadata["entrypoint"] == "hardware/ascend/selected/SKILL.md"
    assert bundle.content["methods/other/notes.md"] == b"first"
    assert "methods/other/notes.md" in bundle.dependencies
    assert reader.read("case.nested").content["note.md"] == b"observation"
    notes.write_text("second", encoding="utf-8")
    with pytest.raises(RevisionConflict):
        reader.resource("selected", "methods/other/notes.md", revision=bundle.revision)
    # The index does not give checkout identities precedence over package identities.
    reader.records()["selected"] = {"id": "selected"}
    with pytest.raises(IdentityError, match="Ambiguous"):
        reader.resolve("selected")


def test_cli_defaults_to_installed_library_and_allows_custom_root(tmp_path, monkeypatch, capsys):
    package = tmp_path / "package"
    library = package / "data/skill_library"
    _skill(library, "hardware/cuda/installed")
    _index(library, {"installed": "hardware/cuda/installed"})
    custom = tmp_path / "custom"
    _skill(custom, "local")
    monkeypatch.setattr("inferrsi.cli.files", lambda name: package)
    monkeypatch.chdir(tmp_path)
    assert main(["skills", "show", "installed"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "installed"
    assert main(["skills", "--root", str(custom), "show", "local"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "local"


def test_package_catalog_and_reader_do_not_require_yaml():
    source = Path(__file__).resolve().parents[1] / "src"
    environment = {**os.environ, "PYTHONPATH": str(source)}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['yaml'] = None\n"
            "from inferrsi.catalog import knowledge_records\n"
            "from inferrsi.knowledge_operations import KnowledgeReader\n"
            "records = knowledge_records()\n"
            "identity = next(r['id'] for r in records if r.get('skill_documents'))\n"
            "assert KnowledgeReader().read(identity).content\n"
            "assert 'inferrsi.skill_catalog' not in sys.modules\n",
        ],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
