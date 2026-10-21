"""CLI contracts for the collect / read / resource knowledge commands."""

import contextlib
import io
import json
import tempfile
from pathlib import Path

import pytest

from inferrsi.cli import main
from inferrsi.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge_store import KnowledgeStore

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "src/inferrsi/data/skill_library"
SOURCE = "calibrate-serving-simulation"
LOCAL = f"{SOURCE}-local"


def run_cli(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


def run_cli_error(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit) as error:
            main(list(argv))
    assert error.value.code == 2
    return stderr.getvalue()


def local_candidate(source: Bundle) -> Bundle:
    return Bundle(
        {
            **source.metadata,
            "id": LOCAL,
            "state": "candidate",
            "derived_from": [{"ref": f"checkout:{SOURCE}", "revision": source.revision}],
        },
        dict(source.content),
        dict(source.dependencies),
    )


def test_collect_defaults_to_package_with_query_and_limit():
    code, stdout, _ = run_cli("collect", "Qwen", "--limit", "3", "--json")
    assert code == 0
    envelope = json.loads(stdout)
    assert envelope["items"] and len(envelope["items"]) <= 3
    assert all(item["authority"] == "package" for item in envelope["items"])


def test_collect_reports_explicit_no_match_with_omission_reason():
    code, stdout, _ = run_cli("collect", "--id", "not-a-real-id", "--json")
    assert code == 0
    envelope = json.loads(stdout)
    assert envelope["no_match"]
    assert envelope["omissions"][0]["reason"] == "unknown_identity"


def test_collect_selects_explicit_checkout_identity():
    code, stdout, _ = run_cli(
        "collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS)
    )
    assert code == 0
    line = stdout.strip().splitlines()[0].split("\t")
    assert line[0] == f"checkout:{SOURCE}"
    assert line[1].startswith("sha256:")


def test_read_returns_bundle_view_and_rejects_wrong_revision():
    code, stdout, _ = run_cli("read", SOURCE, "--skill-root", str(SKILLS), "--material")
    assert code == 0
    view = json.loads(stdout)
    assert view["id"] == SOURCE
    assert view["revision"].startswith("sha256:")
    assert view["content"]
    stderr = run_cli_error(
        "read", SOURCE, "--revision", f"sha256:{'0' * 64}", "--skill-root", str(SKILLS)
    )
    assert "unavailable" in stderr


def test_resource_writes_exact_bytes_of_requested_revision():
    bundle = KnowledgeReader(skill_root=SKILLS).read(SOURCE)
    entrypoint = bundle.metadata["entrypoint"]
    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory) / "entry.md"
        code, stdout, _ = run_cli(
            "resource",
            SOURCE,
            entrypoint,
            "--revision",
            bundle.revision,
            "--skill-root",
            str(SKILLS),
            "--output",
            str(destination),
        )
        assert code == 0
        assert destination.read_bytes() == bundle.content[entrypoint]
        assert json.loads(stdout)["resource"] == str(destination.resolve())


def test_store_source_requires_existing_database_and_reads_candidates(tmp_path):
    workspace = tmp_path / "store"
    workspace.mkdir()
    source = KnowledgeReader(skill_root=SKILLS).read(SOURCE)
    revision = KnowledgeStore(workspace, skill_root=SKILLS).create(local_candidate(source))
    code, stdout, _ = run_cli(
        "collect",
        "--id",
        f"store:{LOCAL}",
        "--skill-root",
        str(SKILLS),
        "--store",
        str(workspace),
        "--json",
    )
    assert code == 0
    item = json.loads(stdout)["items"][0]
    assert (item["authority"], item["revision"]) == ("store", revision)
    code, stdout, _ = run_cli(
        "read",
        f"store:{LOCAL}",
        "--revision",
        revision,
        "--skill-root",
        str(SKILLS),
        "--store",
        str(workspace),
    )
    assert code == 0
    assert json.loads(stdout)["id"] == LOCAL
    empty = tmp_path / "empty"
    empty.mkdir()
    stderr = run_cli_error("read", LOCAL, "--store", str(empty))
    assert "existing database" in stderr
    assert list(empty.iterdir()) == []


def test_ambiguous_identity_error_names_qualified_choices(tmp_path):
    package_id = KnowledgeReader().identities()[0].partition(":")[2]
    cases = tmp_path / "owner" / "cases"
    cases.mkdir(parents=True)
    (tmp_path / "owner" / "SKILL.md").write_text(
        "---\nname: owner\ndescription: test\n---\nBody", encoding="utf-8"
    )
    (cases / "note.md").write_text("observation", encoding="utf-8")
    (cases / "note.json").write_text(
        json.dumps(
            {
                "id": package_id,
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
    stderr = run_cli_error("read", package_id, "--skill-root", str(tmp_path))
    assert "Ambiguous" in stderr
    assert f"package:{package_id}" in stderr and f"checkout:{package_id}" in stderr


def test_store_skill_root_reservation_is_enforced(tmp_path):
    workspace = tmp_path / "store"
    workspace.mkdir()
    source = KnowledgeReader(skill_root=SKILLS).read(SOURCE)
    KnowledgeStore(workspace, skill_root=SKILLS).create(local_candidate(source))
    stderr = run_cli_error("read", LOCAL, "--store", str(workspace))
    assert "reserves the skills checkout" in stderr


def test_malformed_revision_pairs_are_input_errors():
    for pair in ("REV", "ID=", "=REV"):
        stderr = run_cli_error("collect", "--revision", pair)
        assert "ID=REV" in stderr
    stderr = run_cli_error("collect", "--revision", "a=sha256:x", "--revision", "a=sha256:y")
    assert "Duplicate revision request" in stderr


def test_collect_material_appears_in_text_and_json_modes():
    code, stdout, _ = run_cli("collect", "Qwen", "--limit", "1", "--material")
    assert code == 0
    assert "--- begin content package:" in stdout
    assert "--- end content package:" in stdout
    _, json_stdout, _ = run_cli("collect", "Qwen", "--limit", "1", "--material", "--json")
    envelope = json.loads(json_stdout)
    assert envelope["items"][0]["content"]


def _escaped(value: str) -> str:
    # Independent reimplementation of the CLI's one-line-per-item escaping.
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def test_collect_text_lines_match_the_json_envelope():
    code, stdout, _ = run_cli("collect", "Qwen", "--limit", "2")
    assert code == 0
    _, json_stdout, _ = run_cli("collect", "Qwen", "--limit", "2", "--json")
    items = json.loads(json_stdout)["items"]
    assert len(items) >= 1
    # Item lines are the ones whose second field is the content revision.
    lines = [line for line in stdout.splitlines() if line.split("\t")[1].startswith("sha256:")]
    assert len(lines) == len(items)
    for line, item in zip(lines, items):
        fields = line.split("\t")
        assert fields[0] == item["ref"]
        assert fields[1] == item["revision"]
        assert fields[2] == item["kind"]
        assert fields[3] == _escaped(item["state"])
        if "applicability" in item:
            value = item["applicability"]
            applicability = (
                _escaped(value)
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, sort_keys=True)
            )
        else:
            applicability = "-"
        assert fields[4] == applicability


def test_collect_reports_no_match_omissions_and_collisions_in_text_mode(tmp_path):
    code, stdout, _ = run_cli("collect", "definitely-no-such-knowledge-anywhere")
    assert code == 0
    assert stdout.strip() == (
        "no_match\tnothing selected from the requested sources; "
        "use --json for the full envelope"
    )
    code, stdout, _ = run_cli("collect", "--id", "not-a-real-id")
    assert code == 0
    assert "not-a-real-id\tomitted\tunknown_identity" in stdout
    package_id = KnowledgeReader().identities()[0].partition(":")[2]
    cases = tmp_path / "owner" / "cases"
    cases.mkdir(parents=True)
    (tmp_path / "owner" / "SKILL.md").write_text(
        "---\nname: owner\ndescription: test\n---\nBody", encoding="utf-8"
    )
    (cases / "note.md").write_text("observation", encoding="utf-8")
    (cases / "note.json").write_text(
        json.dumps(
            {
                "id": package_id,
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
    code, stdout, _ = run_cli("collect", "--id", package_id, "--skill-root", str(tmp_path))
    assert code == 0
    assert f"{package_id}\tcollision\towned by multiple authorities" in stdout
    assert f"{package_id}\tomitted\tambiguous_identity" in stdout


def test_collect_limit_and_max_bytes_surface_output_limit_omissions():
    code, stdout, _ = run_cli("collect", "--limit", "1")
    assert code == 0
    envelope = json.loads(run_cli("collect", "--limit", "1", "--json")[1])
    assert len(envelope["items"]) == 1
    assert any(omission["reason"] == "output_limit" for omission in envelope["omissions"])
    code, stdout, _ = run_cli("collect", "--max-bytes", "1")
    assert code == 0
    assert "no_match\t" in stdout
    envelope = json.loads(run_cli("collect", "--max-bytes", "1", "--json")[1])
    assert not envelope["items"]
    assert all(omission["reason"] == "output_limit" for omission in envelope["omissions"])
    assert envelope["material_bytes"] == 0


def test_unsafe_resource_path_is_an_input_error(tmp_path):
    bundle = KnowledgeReader(skill_root=SKILLS).read(SOURCE)
    stderr = run_cli_error(
        "resource",
        SOURCE,
        "../escape.md",
        "--revision",
        bundle.revision,
        "--skill-root",
        str(SKILLS),
        "--output",
        str(tmp_path / "out.md"),
    )
    assert "Unsafe bundle path" in stderr


def test_collect_escapes_control_characters_to_keep_one_line_per_item(tmp_path):
    state = "two\tlines\nbroken"
    cases = tmp_path / "owner" / "cases"
    cases.mkdir(parents=True)
    (tmp_path / "owner" / "SKILL.md").write_text(
        "---\nname: owner\ndescription: test\n---\nBody", encoding="utf-8"
    )
    (cases / "note.md").write_text("observation", encoding="utf-8")
    (cases / "note.json").write_text(
        json.dumps(
            {
                "id": "escape-check",
                "kind": "case",
                "state": state,
                "content": "note.md",
                "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
                "applicability": [],
                "limitations": [],
                "attribution": "fixture",
            }
        ),
        encoding="utf-8",
    )
    code, stdout, _ = run_cli("collect", "--id", "escape-check", "--skill-root", str(tmp_path))
    assert code == 0
    item_lines = [
        line for line in stdout.splitlines() if line.split("\t")[1].startswith("sha256:")
    ]
    assert len(item_lines) == 1
    fields = item_lines[0].split("\t")
    assert len(fields) == 5
    assert fields[3] == "two\\tlines\\nbroken"


class _Missing:
    pass


_MISSING = _Missing()


def _case_root(tmp_path: Path, identity: str, applicability) -> Path:
    cases = tmp_path / "owner" / "cases"
    cases.mkdir(parents=True)
    (tmp_path / "owner" / "SKILL.md").write_text(
        "---\nname: owner\ndescription: test\n---\nBody",
        encoding="utf-8",
    )
    (cases / "note.md").write_text("observation", encoding="utf-8")
    record = {
        "id": identity,
        "kind": "case",
        "state": "historical_observation",
        "content": "note.md",
        "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
        "limitations": [],
        "attribution": "fixture",
    }
    if applicability is not _MISSING:
        record["applicability"] = applicability
    (cases / "note.json").write_text(json.dumps(record), encoding="utf-8")
    return tmp_path


def test_collect_projects_recorded_applicability_including_empty_values():
    # An empty list/object/string is a RECORDED value and must render literally;
    # only an absent field may collapse to the "-" marker. A bundle without
    # applicability is rejected upstream as invalid, so it never reaches projection.
    tmp = Path(tempfile.mkdtemp())
    for index, (value, expected) in enumerate((([], "[]"), ({}, "{}"), ("", ""))):
        root = _case_root(tmp / f"case{index}", "shape-check", value)
        code, text, _ = run_cli("collect", "--id", "shape-check", "--skill-root", str(root))
        assert code == 0, text
        line = next(
            entry for entry in text.splitlines() if entry.startswith("checkout:shape-check")
        )
        assert line.split(chr(9))[4] == expected


def test_collect_omission_escapes_control_characters_in_invalid_id():
    tab, newline = chr(9), chr(10)
    code, text, _ = run_cli("collect", "--id", f"bad{tab}id{newline}injected")
    assert code == 0
    lines = text.splitlines()
    omitted = [line for line in lines if chr(9) + "omitted" + chr(9) in line]
    assert len(omitted) == 1
    # the invalid id stays on one line and never leaks a raw newline that could
    # forge a separate record or a no_match marker
    assert not any(line == "injected" for line in lines)
    assert "injected" in omitted[0]
