"""CLI contracts for the collect / read / resource knowledge commands."""

import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge.knowledge_operations import Bundle, KnowledgeReader
from inferrsi.knowledge.knowledge_store import KnowledgeStore

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "src/inferrsi/knowledge/data/skill_library"
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


def read_pages(*argv):
    pages = []
    received = 0
    while True:
        code, stdout, stderr = run_cli(*argv)
        assert code == 0, stderr
        page = json.loads(stdout)
        if pages:
            assert page["ref"] == pages[0]["ref"]
            assert page["revision"] == pages[0]["revision"]
        pages.append(page)
        argv = page.get("next_read_args")
        if span := page.get("content_range"):
            assert span["start"] == received
            received += len(page["content"].encode("utf-8"))
            assert span["end"] == received
            assert bool(argv) == (received < span["total_bytes"])
        if not argv:
            return pages
        assert span and span["end"] > span["start"]


def test_enter_rejects_a_primary_with_no_instructions(tmp_path):
    owner = tmp_path / "task-accuracy"
    owner.mkdir()
    (owner / "metadata.json").write_text(
        '{"discovery_role":"task-entry","tags":["primary-task"]}', encoding="utf-8"
    )
    (owner / "SKILL.md").write_text(
        "---\nname: task-accuracy\ndescription: Missing body\n---\n", encoding="utf-8"
    )
    error = run_cli_error("skills", "--root", str(tmp_path), "enter", "task-accuracy")
    assert "requires frontmatter and instructions" in error


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


def test_collect_inventory_defaults_to_package_with_limit():
    code, stdout, stderr = run_cli("collect", "--limit", "3", "--json")
    assert code == 0 and not stderr
    envelope = json.loads(stdout)
    assert len(envelope["items"]) == 3
    assert all(item["authority"] == "package" for item in envelope["items"])
    assert not envelope["retrieval"]["selection"]["ranking_applied"]


def test_catalog_list_explains_an_unranked_inventory():
    code, stdout, _ = run_cli("knowledge", "list", "--repo-type", "mlx",
                              "--limit", "1", "--explain")
    assert code == 0
    result = json.loads(stdout)
    observation = result["retrieval"]
    assert observation["calls"] == ["knowledge list"]
    assert observation["selection"]["state"] == "not_requested"
    assert observation["counts"]["matched"] == 3 and observation["counts"]["returned"] == 1
    assert result["items"][0]["id"] in observation["items"][0]["ref"]


@pytest.mark.parametrize("argv", [
    ("knowledge", "search", "graph mode"), ("knowledge", "research", "Model"),
    ("collect", "graph mode"), ("collect", "--relevance", "graph mode"),
    ("context", "graph mode", "--repo-type", "inferrsi", "--backend", "ascend"),
    ("campaign", "capture-context", "--directory", ".", "--id", "r1", "--relevance", "graph"),
    ("campaign", "capture-context", "--directory", "absent-directory", "--id", "r1",
     "--relevance", "graph", "--relevance-method", "find-lexical-v1"),
    ("campaign", "knowledge", "--session", ".", "--query", "graph mode"),
    ("benchmarks", "session", "knowledge", "--session", ".", "--query", "graph mode"),
    ("cannbot", "search", "graph mode"), ("mindie", "query", "--input", "query.json"),
])
def test_retired_text_queries_point_to_find(argv):
    assert "find" in run_cli_error(*argv).splitlines()[-1]


def test_collect_attachment_cue_keeps_the_explicit_owner():
    identity = "package:inferrsi.common.skills.calibrate_serving_simulation"
    code, stdout, _ = run_cli("collect", "--id", identity, "--relevance", "serving",
                              "--context-bytes", "65536", "--json")
    assert code == 0
    result = json.loads(stdout)
    assert [item["ref"] for item in result["items"]] == [identity]
    assert result["selection"]["scope"] == "context-resources"
    assert not result["selection"]["ranking_applied"]


def test_exact_capture_keeps_the_pinned_owner_and_its_selected_attachments(tmp_path):
    from inferrsi.apps.workflows.campaign import verify_capture

    ref = "package:inferrsi.common.skills.video_diffusion_optimization"
    revision = KnowledgeReader().read(ref).revision
    options = ["--revision", f"{ref}={revision}", "--context-bytes", "65536",
               "--relevance-method", "find-lexical-v1"]
    cue = ["--relevance", "numerical parity"]

    def resources(argv):
        _, output, _ = run_cli("collect", "--id", ref, *options, *argv, "--json")
        context, = json.loads(output)["contexts"]
        assert (context["ref"], context["revision"]) == (ref, revision)
        return context["resources"]

    complete = resources([])
    selected = resources(cue)
    assert [Path(item["path"]).name for item in complete] == ["SKILL.md", "campaign.template.json"]
    assert selected == complete[:1]

    run_cli("campaign", "init", "--directory", str(tmp_path), "--id", "manual")
    _, output, _ = run_cli("campaign", "capture-context", "--directory", str(tmp_path),
                           "--id", "one", "--id-ref", ref, *options, *cue)
    receipt = json.loads(output)
    raw = (tmp_path / receipt["context"]).read_bytes()
    assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
    capture, state = verify_capture(raw)
    assert state == "verified"
    assert capture["request"]["revisions"] == {ref: revision}
    assert capture["request"]["relevance"] == "numerical parity"
    assert capture["request"]["relevance_method"] == "find-lexical-v1"
    assert capture["retrieval"]["selection"]["state"] == "explicit_ids"
    assert capture["selection"]["ranking_applied"] is False
    context, = capture["contexts"]
    assert (context["ref"], context["revision"]) == (ref, revision)
    body, = context["resources"]
    assert body["content"] == selected[0]["content"]
    assert {"path": complete[1]["path"], "reason": "not_relevant"} in context["omissions"]


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


@pytest.mark.parametrize("authority", ["checkout", "store"])
def test_material_delivers_procedure_and_exact_resource_preserves_raw_source(authority, tmp_path):
    identity = f"checkout:{SOURCE}"
    source_args = ["--skill-root", str(SKILLS)]
    if authority == "store":
        source = KnowledgeReader(skill_root=SKILLS).read(identity)
        KnowledgeStore(tmp_path, skill_root=SKILLS).create(local_candidate(source))
        identity = f"store:{LOCAL}"
        source_args += ["--store", str(tmp_path)]
    procedure_pages = read_pages("read", identity, "--material", "--omit-resources", *source_args)
    view = procedure_pages[0]
    raw_pages = read_pages(
        "read", identity, "--revision", view["revision"], "--resource", view["entrypoint"],
        "--omit-resources", *source_args,
    )
    assert raw_pages[0]["revision"] == view["revision"]
    raw = b"".join(page["content"].encode("utf-8") for page in raw_pages)
    delivered = b"".join(page["content"].encode("utf-8") for page in procedure_pages)
    assert b"  inferrsi: |" in raw and b"  inferrsi: |" not in delivered
    assert raw.split(b"---", 2)[2] == delivered.split(b"---", 2)[2]
    source_digest = hashlib.sha256(raw).hexdigest()
    for page in procedure_pages:
        proof = page["content_view"]
        content = page["content"].encode("utf-8")
        assert proof["locator"] == ("byte-range" if "content_range" in page else "skill-procedure")
        assert proof["source_sha256"] == source_digest
        assert proof["sha256"] == hashlib.sha256(content).hexdigest()
        assert content == b"".join(raw[start:end] for start, end in proof["source_byte_ranges"])


@pytest.mark.parametrize("identity", [
    "package:vllm_omni.common.diffusion.step_state_and_output_validation",
    "package:inferrsi.common.skills.calibrate_serving_simulation",
])
def test_read_lists_inventory_separately_from_material(identity):
    pages = read_pages("read", identity, "--material")
    assert all("resources" not in page and "required_resources" not in page for page in pages)
    pinned = ("read", identity, "--revision", pages[0]["revision"])
    code, stdout, stderr = run_cli(*pinned)
    assert code == 0, stderr
    inventory = json.loads(stdout)
    assert inventory["revision"] == pages[0]["revision"]
    assert "content" not in inventory
    assert inventory["entrypoint"] == "record.json"
    content = b"".join(page["content"].encode("utf-8") for page in pages)
    assert inventory["resources"]["record.json"] == hashlib.sha256(content).hexdigest()
    assert inventory["required_resources"]

    code, stdout, stderr = run_cli(*pinned, "--omit-resources")
    assert code == 0, stderr
    assert json.loads(stdout) == {
        key: value for key, value in inventory.items()
        if key not in ("resources", "required_resources")
    }


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
    args = ("collect", "--id", "package:inferrsi.common.skills.calibrate_serving_simulation",
            "--material")
    code, stdout, _ = run_cli(*args)
    assert code == 0
    assert "--- begin content package:" in stdout
    assert "--- end content package:" in stdout
    _, json_stdout, _ = run_cli(*args, "--json")
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
    code, stdout, _ = run_cli("collect", "--limit", "2")
    assert code == 0
    _, json_stdout, _ = run_cli("collect", "--limit", "2", "--json")
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
    code, stdout, _ = run_cli("collect", "--kind", "case", "--repo-type", "mlx")
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


def _case_root(root: Path, identity: str, applicability) -> Path:
    cases = root / "owner" / "cases"
    cases.mkdir(parents=True)
    (root / "owner" / "SKILL.md").write_text(
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
        "applicability": applicability,
    }
    (cases / "note.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def test_collect_projects_recorded_applicability_including_empty_values(tmp_path):
    # An empty list/object/string is a RECORDED value and must render literally,
    # distinct from the "-" marker reserved for an absent field. A bundle without
    # applicability is rejected by the manifest as an invalid omission, so the
    # absent case is never reachable as a projected item.
    for index, (value, expected) in enumerate((([], "[]"), ({}, "{}"), ("", ""))):
        root = _case_root(tmp_path / f"case{index}", "shape-check", value)
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
