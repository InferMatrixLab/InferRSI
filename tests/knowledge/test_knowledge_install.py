"""Clean-install contracts: package-only commands without PyYAML and the real-CLI checkout chain."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.knowledge.knowledge_operations import KnowledgeReader

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "src" / "inferrsi" / "knowledge" / "data" / "skill_library"
SOURCE = "calibrate-serving-simulation"


def _cli_env(blocked_yaml: Path | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if blocked_yaml is not None:
        env["PYTHONPATH"] = str(blocked_yaml) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(args: list[str], env: dict, *, cwd: Path = REPO) -> subprocess.CompletedProcess:
    # Real CLI entry point, not an in-process main() call.
    return subprocess.run(
        [sys.executable, "-m", "inferrsi", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
    )


@pytest.fixture
def without_yaml(tmp_path):
    # Shadow PyYAML with a failing module: exactly the base install without
    # the skills extra, without touching the test environment itself.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "yaml.py").write_text(
        "raise ImportError('PyYAML intentionally unavailable for this test')\n",
        encoding="utf-8",
    )
    return blocked


def test_package_only_commands_work_without_pyyaml(without_yaml):
    env = _cli_env(without_yaml)
    listed = _run(["collect", "--limit", "1", "--json"], env)
    assert listed.returncode == 0, listed.stderr
    items = json.loads(listed.stdout)["items"]
    assert items and items[0]["authority"] == "package"
    result = _run(["read", items[0]["id"]], env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["id"] == items[0]["id"]

    query = "ascend graph mode"
    catalog = _run(["knowledge", "list", "--repo-type", "inferrsi", "--limit", "1", "--json"], env)
    assert catalog.returncode == 0, catalog.stderr
    assert json.loads(catalog.stdout)[0]["repo"] == "inferrsi"
    target = "inferrsi.ascend.skills.ascend_graph_mode"
    research = _run(["find", query, "--repo-type", "inferrsi", "--limit", "1", "--json"], env)
    assert research.returncode == 0, research.stderr
    assert json.loads(research.stdout)["items"][0]["id"] == target


def test_packaged_skill_search_and_resource_work_without_pyyaml(without_yaml, tmp_path):
    env = _cli_env(without_yaml)
    query = "ascend graph mode"
    found = _run(["find", query, "--kinds", "skill", "--limit", "1", "--json"], env)
    assert found.returncode == 0, found.stderr
    hit, = json.loads(found.stdout)["items"]
    assert hit["id"] == "ascend-graph-mode"
    opened = _run(hit["read_args"], env)
    assert opened.returncode == 0, opened.stderr
    read = json.loads(opened.stdout)

    collected = _run(["collect", "--id", read["ref"], "--limit", "1", "--material", "--json"], env)
    assert collected.returncode == 0, collected.stderr
    packaged, = json.loads(collected.stdout)["items"]
    assert packaged["authority"] == "package"
    original = packaged["skill_documents"]["original"]
    expected = (SKILLS / Path(original).relative_to("data/skill_library")).read_bytes()
    assert read["id"] == packaged["id"]
    assert read["revision"] == packaged["revision"]
    assert read["content_resource"] == original
    assert hit["next_read_content_bytes"] == len(read["content"].encode())
    received = read["content"].encode()
    page = read
    while "next_read_args" in page:
        opened = _run(page["next_read_args"], env)
        assert opened.returncode == 0, opened.stderr
        page = json.loads(opened.stdout)
        received += page["content"].encode()
    assert received == expected

    output = tmp_path / "packaged-skill.md"
    fetched = _run([
        "resource", packaged["ref"], original, "--revision", packaged["revision"],
        "--output", str(output),
    ], env)
    assert fetched.returncode == 0, fetched.stderr
    assert output.read_bytes() == expected


def test_capture_scope_skill_delivers_packaged_text_without_pyyaml(without_yaml, tmp_path):
    campaign = tmp_path / "campaign"
    env = _cli_env(without_yaml)
    created = _run(["evidence", "init", "--directory", str(campaign), "--id", "lean"], env)
    assert created.returncode == 0, created.stderr
    result = _run([
        "find", "ascend graph mode", "--session", str(campaign),
        "--kinds", "skill", "--limit", "1",
    ], env)
    assert result.returncode == 0, result.stderr
    hit, = json.loads(result.stdout)["items"]
    opened = _run(hit["read_args"], env)
    assert opened.returncode == 0, opened.stderr
    read = json.loads(opened.stdout)
    capture = json.loads((campaign / read["reference"]["path"]).read_bytes())
    item, = capture["items"]
    context, = capture["contexts"]
    assert item["ref"] == "package:inferrsi.ascend.skills.ascend_graph_mode"
    assert context["revision"] == item["revision"]
    original = context["resources"][0]
    assert original["path"] == hit["body_resource"] == read["content_resource"]
    source = (
        SKILLS / Path(original["path"]).relative_to("data/skill_library")
    ).read_bytes()
    assert original["locator"] == "byte-range"
    assert hashlib.sha256(source).hexdigest() == original["source_sha256"]
    procedure = b"".join(source[start:end] for start, end in original["source_byte_ranges"])
    assert original["content"].encode() == read["content"].encode() == procedure
    assert hashlib.sha256(procedure).hexdigest() == original["sha256"]
    assert capture["omissions"] == []
    received = procedure
    page = read
    while "next_read_args" in page:
        opened = _run(page["next_read_args"], env)
        assert opened.returncode == 0, opened.stderr
        page = json.loads(opened.stdout)
        capture = json.loads((campaign / page["reference"]["path"]).read_bytes())
        resource, = capture["contexts"][0]["resources"]
        assert resource["content_range"]["start"] == len(received)
        data = b"".join(source[start:end] for start, end in resource["source_byte_ranges"])
        assert data == resource["content"].encode() == page["content"].encode()
        assert hashlib.sha256(source).hexdigest() == resource["source_sha256"]
        assert hashlib.sha256(data).hexdigest() == resource["sha256"]
        received += data
    from inferrsi.knowledge._skill_selection import skill_procedure

    assert received == skill_procedure(original["path"], source)[0]


def test_custom_skill_does_not_open_the_installed_projection_without_pyyaml(without_yaml, tmp_path):
    relative = "hardware/ascend/ascend-graph-mode"
    directory = tmp_path / relative
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: ascend-graph-mode\ndescription: Ascend graph mode experiment\n---\n"
        "This is a private local observation.\n",
        encoding="utf-8",
    )
    (tmp_path / "skill-index.json").write_text(json.dumps({
        "schema_version": 1,
        "skills": {"ascend-graph-mode": {"path": relative, "backend": "ascend"}},
    }), encoding="utf-8")
    result = _run([
        "find", "ascend graph mode", "--skill-root", str(tmp_path), "--kinds", "skill", "--json",
    ], _cli_env(without_yaml))
    assert result.returncode == 0, result.stderr
    hit, = json.loads(result.stdout)["items"]
    assert hit["source_location"] == "checkout"
    assert "PyYAML" in hit["unreadable"]
    assert "read_args" not in hit


def test_skill_root_without_pyyaml_fails_with_install_hint(without_yaml):
    result = _run(
        ["collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS)],
        _cli_env(without_yaml),
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "[skills]" in result.stderr and "PyYAML" in result.stderr
    assert "<inferrsi-checkout>[skills]" in result.stderr


def test_install_hint_is_actionable_outside_the_repository(without_yaml, tmp_path):
    # The hint must not depend on the caller's working directory.
    result = _run(
        ["collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS)],
        _cli_env(without_yaml),
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "<inferrsi-checkout>[skills]" in result.stderr and "placeholder" in result.stderr


def test_checkout_chain_collect_read_resource_through_real_cli(tmp_path):
    env = _cli_env()
    collected = _run(
        ["collect", "--id", f"checkout:{SOURCE}", "--skill-root", str(SKILLS), "--json"], env
    )
    assert collected.returncode == 0, collected.stderr
    item = json.loads(collected.stdout)["items"][0]
    revision, entrypoint = item["revision"], item["entrypoint"]

    read = _run(
        ["read", SOURCE, "--revision", revision, "--skill-root", str(SKILLS), "--material"], env
    )
    assert read.returncode == 0, read.stderr
    assert json.loads(read.stdout)["revision"] == revision

    output = tmp_path / "entry.md"
    resource = _run(
        [
            "resource",
            SOURCE,
            entrypoint,
            "--revision",
            revision,
            "--skill-root",
            str(SKILLS),
            "--output",
            str(output),
        ],
        env,
    )
    assert resource.returncode == 0, resource.stderr
    expected = KnowledgeReader(skill_root=SKILLS).read(SOURCE).content[entrypoint]
    assert output.read_bytes() == expected


def test_corrupted_store_database_fails_without_traceback(tmp_path):
    workspace = tmp_path / "broken-store"
    workspace.mkdir()
    (workspace / "knowledge.sqlite3").write_bytes(b"this is not a database")
    result = _run(["read", "some-id", "--store", str(workspace)], _cli_env())
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
