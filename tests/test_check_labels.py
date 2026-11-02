import json
from pathlib import Path

import pytest

from tools import check_labels as check

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / ".github/labels.json").read_text(encoding="utf-8"))
LIVE = [{"name": entry["name"], "description": entry["description"]} for entry in MANIFEST]


def entry(name, group=None, description="Meaning"):
    return {"name": name, "group": group or name.split(":")[0], "description": description}


def write_lines(path, labels):
    path.write_text("".join(json.dumps(label) + "\n" for label in labels), encoding="utf-8")
    return str(path)


def test_repository_manifest_is_valid():
    assert check.manifest_problems(MANIFEST) == []


def test_templates_and_configs_reference_only_listed_labels():
    references = check.referenced_labels(ROOT)
    assert references[".github/ISSUE_TEMPLATE/scoped-task.md"] == ["kind:task"]
    assert references[".github/ISSUE_TEMPLATE/campaign-acceptance.yml"] == ["kind:acceptance"]
    assert references["tools/skill_eval_auto_config.json"] == ["skill-eval:execute"]
    assert check.drift(MANIFEST, LIVE, references) == []


@pytest.mark.parametrize("bad, message", [
    (entry("bug", group="kind"), "form <group>:<value>"),
    (entry("kind:bug", group="type"), "form <group>:<value>"),
    (entry("kind:bug", description=""), "description must have"),
    (entry("kind:bug", description="x" * 101), "description must have"),
    ({"name": "kind:bug", "group": "kind"}, "exactly name, group and description"),
])
def test_invalid_manifest_entries_are_reported(bad, message):
    [problem] = check.manifest_problems([bad])
    assert message in problem


def test_duplicate_names_are_reported():
    assert check.manifest_problems([entry("kind:bug"), entry("kind:bug")]) == [
        "kind:bug: listed more than once"
    ]


def test_drift_reports_missing_extra_changed_and_unlisted_references():
    manifest = [entry("kind:bug"), entry("status:proposed", description="Waiting")]
    repository = [{"name": "status:proposed", "description": None},
                  {"name": "bug", "description": "Something isn't working"}]
    assert check.drift(manifest, repository, {"form.yml": ["kind:bug", "acceptance"]}) == [
        "kind:bug: in labels.json, missing from the repository",
        "bug: in the repository, missing from labels.json",
        "status:proposed: repository description differs from labels.json",
        "acceptance: referenced by form.yml, missing from labels.json",
    ]


def test_template_and_config_label_forms(tmp_path):
    templates = tmp_path / ".github/ISSUE_TEMPLATE"
    templates.mkdir(parents=True)
    (templates / "task.md").write_bytes(
        b"---\r\nname: Task\r\nlabels: kind:task, area:process\r\n---\r\n\r\n## Goal\r\n---\r\n")
    (templates / "form.yml").write_text(
        "name: Form\nlabels:\n  - kind:acceptance\nbody: []\n", encoding="utf-8")
    (templates / "config.yml").write_text("blank_issues_enabled: false\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/skill_eval_auto_config.json").write_text(
        json.dumps({"label": "skill-eval:execute"}), encoding="utf-8")
    (tmp_path / "tools/skill_eval_other_config.json").write_text("{}", encoding="utf-8")
    assert check.referenced_labels(tmp_path) == {
        ".github/ISSUE_TEMPLATE/form.yml": ["kind:acceptance"],
        ".github/ISSUE_TEMPLATE/task.md": ["kind:task", "area:process"],
        "tools/skill_eval_auto_config.json": ["skill-eval:execute"],
    }


def test_markdown_template_without_front_matter_fails(tmp_path):
    templates = tmp_path / ".github/ISSUE_TEMPLATE"
    templates.mkdir(parents=True)
    (templates / "task.md").write_text("## Goal\n", encoding="utf-8")
    with pytest.raises(ValueError, match="front matter"):
        check.referenced_labels(tmp_path)


def test_main_passes_silently_when_repository_matches(tmp_path, capsys):
    assert check.main([write_lines(tmp_path / "labels.jsonl", LIVE)]) == 0
    assert capsys.readouterr().out == ""


def test_main_reports_each_drift_line_and_fails(tmp_path, capsys):
    live = LIVE[1:] + [{"name": "::error::x", "description": None}]
    assert check.main([write_lines(tmp_path / "labels.jsonl", live)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[:2] == [
        f"label drift: {MANIFEST[0]['name']}: in labels.json, missing from the repository",
        "label drift: ::error::x: in the repository, missing from labels.json",
    ]
    assert "labels.json" in out[2] and len(out) == 3
