import json
from pathlib import Path

import pytest

from tools import check_labels as check

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / ".github/labels.json").read_text(encoding="utf-8"))
EXTERNAL = json.loads((ROOT / ".github/external-labels.json").read_text(encoding="utf-8"))
EXTERNAL_NAMES = {entry["name"] for entry in EXTERNAL}
LIVE = [{"name": entry["name"], "description": entry["description"]} for entry in MANIFEST]


def entry(name, group=None, description="Meaning"):
    return {"name": name, "group": group or name.split(":")[0], "description": description}


def write_lines(path, labels):
    path.write_text("".join(json.dumps(label) + "\n" for label in labels), encoding="utf-8")
    return str(path)


def test_repository_manifest_is_valid():
    assert check.manifest_problems(MANIFEST) == []


def test_repository_external_list_is_valid():
    assert check.external_problems(EXTERNAL, MANIFEST) == []


def test_templates_and_configs_reference_only_listed_labels():
    references = check.referenced_labels(ROOT)
    assert references[".github/ISSUE_TEMPLATE/scoped-task.md"] == ["kind:task"]
    assert references[".github/ISSUE_TEMPLATE/campaign-acceptance.yml"] == ["kind:acceptance"]
    assert references["tools/skill_eval_auto_config.json"] == ["skill-eval:execute"]
    assert check.drift(MANIFEST, LIVE, references, EXTERNAL_NAMES) == []


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


@pytest.mark.parametrize("bad, message", [
    ({"name": "bot-reviewed"}, "exactly name and owner"),
    ({"name": "bot-reviewed", "owner": "a", "note": "b"}, "exactly name and owner"),
    ({"name": "", "owner": "a"}, "nonempty string"),
    ({"name": "   ", "owner": "a"}, "nonempty string"),
    ({"name": None, "owner": "a"}, "nonempty string"),
    ({"name": "bot-reviewed", "owner": "  "}, "owner must name the app"),
])
def test_invalid_external_entries_are_reported(bad, message):
    [problem] = check.external_problems([bad], [])
    assert message in problem


@pytest.mark.parametrize("name", [["a", "b"], {"a": 1}, 7])
def test_an_unhashable_or_nonstring_external_name_is_reported_not_raised(name):
    # An unusable name must not reach the duplicate/overlap sets and crash the check.
    [problem] = check.external_problems([{"name": name, "owner": "app"}], [entry("kind:bug")])
    assert "name must be a nonempty string" in problem


def test_external_duplicates_and_overlap_with_the_manifest_are_reported():
    external = [{"name": "bot-reviewed", "owner": "app"}, {"name": "bot-reviewed", "owner": "app"},
                {"name": "kind:bug", "owner": "app"}]
    assert check.external_problems(external, [entry("kind:bug")]) == [
        "bot-reviewed: listed more than once",
        "kind:bug: external labels cannot also be in labels.json",
    ]


def test_drift_reports_missing_extra_changed_and_unlisted_references():
    manifest = [entry("kind:bug"), entry("status:proposed", description="Waiting")]
    repository = [{"name": "status:proposed", "description": None},
                  {"name": "bug", "description": "Something isn't working"}]
    assert check.drift(manifest, repository, {"form.yml": ["kind:bug", "acceptance"]}, set()) == [
        "kind:bug: in labels.json, missing from the repository",
        "bug: in the repository, missing from labels.json",
        "status:proposed: repository description differs from labels.json",
        "acceptance: referenced by form.yml, missing from labels.json",
    ]


def test_drift_accepts_an_external_label_in_the_repository():
    manifest = [entry("kind:bug")]
    repository = [{"name": "kind:bug", "description": "Meaning"},
                  {"name": "bot-reviewed", "description": None}]
    assert check.drift(manifest, repository, {}, {"bot-reviewed"}) == []
    # Absence is also accepted: an outside app owns whether the label exists.
    assert check.drift(manifest, repository[:1], {}, {"bot-reviewed"}) == []


def test_drift_still_rejects_a_template_reference_to_an_external_label():
    manifest = [entry("kind:bug")]
    repository = [{"name": "kind:bug", "description": "Meaning"},
                  {"name": "bot-reviewed", "description": None}]
    assert check.drift(manifest, repository, {"form.yml": ["bot-reviewed"]},
                       {"bot-reviewed"}) == [
        "bot-reviewed: referenced by form.yml, missing from labels.json",
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
    live = LIVE + [{"name": name, "description": None} for name in sorted(EXTERNAL_NAMES)]
    assert check.main([write_lines(tmp_path / "labels.jsonl", live)]) == 0
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
