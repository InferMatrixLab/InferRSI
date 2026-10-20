"""The installed discovery index preserves checkout metadata without bundling bodies."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from inferrsi.arguments import parser
from inferrsi.catalog import REPO_TYPES, repository_pack, search_knowledge
from inferrsi.cli import main
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import skill_metadata, skill_records
from tools import build_skill_index as index_builder
from tools.build_skill_index import DESTINATION, build_index, render_index

PROJECT = Path(__file__).resolve().parents[1]


def test_complete_index_retains_metadata_states_and_unknown_license():
    records = search_knowledge(repo="inferrsi", limit=100)
    names = {record["name"] for record in skill_records(PROJECT / "skills")}
    assert len(records) == len(names) == 48
    assert {record["skill_metadata"]["name"] for record in records} == names
    states = []
    for record in records:
        metadata = record["skill_metadata"]
        name = metadata["name"]
        assert metadata == skill_metadata(PROJECT / "skills", name)
        assert record["checkout_ref"] == f"checkout:{name}"
        assert record["id"] == f"inferrsi.common.skills.{name.replace('-', '_')}"
        assert record["status"] == "imported"
        assert not record["verification"]["locally_verified"]
        assert record["index_type"] == "skill-metadata-only"
        assert "skill_documents" not in record
        assert set(record["source_files"]) == set(record["sources"][0]["paths"])
        states.append(metadata.get("status"))
    assert states.count("candidate") == 43
    assert states.count(None) == 5
    profiling = next(r for r in records if r["title"] == "ascend-operator-profiling")
    assert profiling["skill_metadata"]["license"] == "UNKNOWN"
    assert profiling["skill_metadata"]["synced-commit"] == (
        "ac5bbd2b4cf427d011874e11f8d1e8b1bef66eda"
    )


def test_generated_index_matches_current_sources_without_historical_git_objects():
    records = search_knowledge(repo="inferrsi", limit=100)
    revisions = {record["sources"][0]["commit"] for record in records}
    assert len(revisions) == 1
    # CI uses shallow checkouts. Compare the whole generated projection and its
    # text hashes without requiring the old source commit in the local object DB.
    inputs = [
        path for path in (PROJECT / "skills").glob("*/*")
        if path.name in ("SKILL.md", "metadata.json")
    ]
    source_files = {
        path.relative_to(PROJECT).as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in inputs
    }
    generated = render_index(PROJECT / "skills", revisions.pop(), source_files)
    destination = PROJECT / DESTINATION
    actual = {
        path.relative_to(destination).as_posix(): path.read_text(encoding="utf-8")
        for path in destination.rglob("*") if path.is_file()
    }
    assert actual == generated


def test_index_checks_drift_and_rejects_changed_or_added_source_inputs(tmp_path, monkeypatch):
    # A tiny committed source fixture proves a stale revision cannot attribute
    # uncommitted instructions or newly introduced metadata to old Git bytes.
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init")
    root = tmp_path / "skills" / "example"
    root.mkdir(parents=True)
    source = "---\nname: example\ndescription: A source fixture\n---\nOriginal body\n"
    (root / "SKILL.md").write_text(source, encoding="utf-8")
    git("add", "skills")
    git(
        "-c", "user.name=Index test fixture", "-c", "user.email=index@example.invalid",
        "commit", "-s", "-m", "Create test source",
    )
    monkeypatch.setattr(index_builder, "PROJECT", tmp_path)
    assert index_builder.main(["--source-revision", "HEAD"]) == 0
    assert index_builder.main(["--source-revision", "HEAD", "--check"]) == 0
    generated = tmp_path / DESTINATION / "common/skills/example.json"
    generated.write_text("changed projection", encoding="utf-8")
    assert index_builder.main(["--source-revision", "HEAD", "--check"]) == 1
    assert generated.read_text(encoding="utf-8") == "changed projection"
    assert index_builder.main(["--source-revision", "HEAD"]) == 0
    extra = tmp_path / DESTINATION / "obsolete.json"
    extra.write_text("{}", encoding="utf-8")
    assert index_builder.main(["--source-revision", "HEAD", "--check"]) == 1
    assert extra.is_file()
    (root / "SKILL.md").write_text(source + "Changed body\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inputs differ"):
        build_index(tmp_path, "HEAD")
    (root / "SKILL.md").write_text(source, encoding="utf-8")
    (root / "metadata.json").write_text('{"status": "candidate"}', encoding="utf-8")
    with pytest.raises(ValueError, match="input paths differ"):
        build_index(tmp_path, "HEAD")


def test_package_index_and_checkout_skill_have_distinct_read_boundaries():
    reader = KnowledgeReader(skill_root=PROJECT / "skills")
    identity = "inferrsi.common.skills.claim_contract"
    bundle = reader.read(identity)
    assert set(bundle.content) == {"record.json"}
    assert bundle.dependencies == {}
    assert bundle.metadata["kind"] == "knowledge"
    assert bundle.metadata["origin"] == ["unknown"]
    assert reader.resolve(identity) == f"package:{identity}"
    assert reader.resolve("claim-contract") == "checkout:claim-contract"
    assert reader.read("claim-contract").metadata["kind"] == "skill"
    collected = reader.collect(repo="inferrsi", kind="knowledge", limit=100, material=True)
    assert len(collected["items"]) == 48
    assert not collected["collisions"] and not collected["omissions"]
    assert all(item["authority"] == "package" for item in collected["items"])
    assert all(set(item["resources"]) == {"record.json"} for item in collected["items"])
    assert reader.collect(repo="inferrsi", kind="skill")["no_match"]


def test_index_cli_search_show_context_and_execution_boundary(capsys):
    assert main([
        "knowledge", "search", "profiling", "--repo-type", "inferrsi", "--json",
    ]) == 0
    records = json.loads(capsys.readouterr().out)
    assert records and all(record["repo"] == "inferrsi" for record in records)
    identity = "inferrsi.common.skills.ascend_operator_profiling"
    assert main(["knowledge", "show", identity]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["skill_metadata"]["license"] == "UNKNOWN"
    assert main(["context", identity, "--repo-type", "inferrsi", "--backend", "cpu"]) == 0
    context = capsys.readouterr().out
    assert identity in context and "not the original skill" in context
    assert "locally_verified\": false" in context
    assert "inferrsi" not in REPO_TYPES
    with pytest.raises(ValueError, match="Unknown repository type"):
        repository_pack("inferrsi")
    with pytest.raises(SystemExit):
        parser().parse_args(["doctor", "--repo-type", "inferrsi"])
