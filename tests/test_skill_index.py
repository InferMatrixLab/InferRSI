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
from tools.build_skill_index import DESTINATION, LIBRARY, build_index, render_index, source_inputs

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / LIBRARY


def _physical(relative: str) -> Path:
    """Map a pinned input name to today's checkout location.

    After the K02 re-pin the recorded prefix agrees with ``LIBRARY``. The helper
    still strips the pinned prefix so a future split would keep working.
    """
    pinned = index_builder.PINNED_LIBRARY.as_posix()
    assert relative.startswith(pinned + "/"), relative
    return PROJECT / LIBRARY / relative[len(pinned) + 1:]


def test_complete_index_retains_metadata_states_and_unknown_license():
    records = search_knowledge(repo="inferrsi", limit=100)
    names = {record["name"] for record in skill_records(ROOT)}
    registry = json.loads((ROOT / "skill-index.json").read_text(encoding="utf-8"))["skills"]
    assert len(records) == len(names) == 80
    assert {record["skill_metadata"]["name"] for record in records} == names
    states = []
    for record in records:
        metadata = record["skill_metadata"]
        name = metadata["name"]
        assert metadata == skill_metadata(ROOT, name)
        assert record["checkout_ref"] == f"checkout:{name}"
        assert record["backend"] == registry[name]["backend"]
        assert record["id"] == f"inferrsi.{record['backend']}.skills.{name.replace('-', '_')}"
        assert record["status"] == "imported"
        assert not record["verification"]["locally_verified"]
        assert record["index_type"] == "packaged-skill"
        assert record["skill_documents"] == {
            "original": f"data/skill_library/{registry[name]['path']}/SKILL.md",
        }
        assert set(record["source_files"]) == set(record["sources"][0]["paths"])
        states.append(metadata.get("status"))
    assert states.count("candidate") == 80
    profiling = next(r for r in records if r["title"] == "ascend-operator-profiling")
    assert profiling["skill_metadata"]["license"] == "UNKNOWN"
    assert profiling["skill_metadata"]["synced-commit"] == (
        "ac5bbd2b4cf427d011874e11f8d1e8b1bef66eda"
    )


def test_generated_index_matches_current_sources_without_historical_git_objects():
    records = search_knowledge(repo="inferrsi", limit=100)
    revisions = {record["sources"][0]["commit"] for record in records}
    assert len(revisions) == 1
    snapshot = json.loads((PROJECT / DESTINATION / "_provenance.json").read_text(encoding="utf-8"))
    assert snapshot["source_revision"] in revisions
    # CI uses shallow checkouts. Compare the whole generated projection and its
    # text hashes without requiring the old source commit in the local object DB.
    recorded_hashes = {
        relative: digest
        for record in records for relative, digest in record["source_files"].items()
    }
    source_files = {}
    for relative in source_inputs(ROOT):
        data = _physical(relative).read_bytes()
        raw_hash = hashlib.sha256(data).hexdigest()
        # Byte-preserved upstream notices can contain canonical CRLF. Ordinary
        # text may instead have platform checkout newlines; match the recorded
        # blob hash before trying that existing LF equivalence.
        source_files[relative] = (
            raw_hash if raw_hash == recorded_hashes.get(relative)
            else hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
        )
    generated = render_index(ROOT, revisions.pop(), source_files)
    destination = PROJECT / DESTINATION
    actual = {
        path.relative_to(destination).as_posix(): path.read_text(encoding="utf-8")
        for path in destination.rglob("*") if path.is_file()
    }
    assert actual == generated


def test_committed_source_hashes_preserve_binary_and_newline_bytes(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True
        ).stdout

    git("init")
    git("config", "core.autocrlf", "false")
    resources = {
        "empty.md": b"",
        "crlf.md": b"first\r\nsecond\r\n",
        "space in name.bin": b"\x00\nblob 12\n\xffno-final-newline",
    }
    for name, content in resources.items():
        (tmp_path / name).write_bytes(content)
    git("add", *resources)
    git(
        "-c", "user.name=Index test fixture", "-c", "user.email=index@example.invalid",
        "commit", "-s", "-m", "Create byte-exact sources",
    )
    hashes = index_builder._source_hashes(tmp_path, "HEAD", set(resources))
    assert hashes == {
        name: hashlib.sha256(git("show", f"HEAD:{name}")).hexdigest()
        for name in resources
    }
    assert hashes == {
        name: hashlib.sha256(content).hexdigest() for name, content in resources.items()
    }


def test_replacement_refs_cannot_rewrite_indexed_source_bytes(tmp_path):
    # refs/replace/* leaves rev-parse alone but changes what cat-file returns,
    # so the pinned revision must be read with the hardened Git invocation.
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        ).stdout

    git("init")
    (tmp_path / "source.md").write_bytes(b"original bytes\n")
    git("add", "source.md")
    git(
        "-c", "user.name=Index test fixture", "-c", "user.email=index@example.invalid",
        "commit", "-s", "-m", "Original",
    )
    original = git("rev-parse", "HEAD").strip()
    (tmp_path / "source.md").write_bytes(b"replacement bytes\n")
    git("add", "source.md")
    git(
        "-c", "user.name=Index test fixture", "-c", "user.email=index@example.invalid",
        "commit", "-s", "-m", "Replacement",
    )
    git("replace", original, git("rev-parse", "HEAD").strip())
    hashes = index_builder._source_hashes(tmp_path, original, {"source.md"})
    assert hashes == {"source.md": hashlib.sha256(b"original bytes\n").hexdigest()}


def test_index_checks_drift_and_rejects_changed_or_added_source_inputs(tmp_path, monkeypatch):
    # A tiny committed source fixture proves a stale revision cannot attribute
    # uncommitted instructions or newly introduced metadata to old Git bytes.
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init")
    # The fixture holds its corpus at the recorded location, where the physical
    # root and the pinned prefix are the same. The repository itself separates
    # them only because K02 moved the files after their pinned revision.
    fixture_library = index_builder.PINNED_LIBRARY
    library = tmp_path / fixture_library
    root = library / "methods" / "example"
    root.mkdir(parents=True)
    (library / "skill-index.json").write_text(json.dumps({
        "schema_version": 1,
        "skills": {"example": {"path": "methods/example", "backend": "common"}},
    }), encoding="utf-8")
    source = "---\nname: example\ndescription: A source fixture\n---\nOriginal body\n"
    (root / "SKILL.md").write_text(source, encoding="utf-8")
    git("add", fixture_library.as_posix())
    git(
        "-c", "user.name=Index test fixture", "-c", "user.email=index@example.invalid",
        "commit", "-s", "-m", "Create test source",
    )
    monkeypatch.setattr(index_builder, "PROJECT", tmp_path)
    monkeypatch.setattr(index_builder, "LIBRARY", fixture_library)
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
    (root / "references").mkdir()
    (root / "references/notes.md").write_text("New resource", encoding="utf-8")
    with pytest.raises(ValueError, match="input paths differ"):
        build_index(tmp_path, "HEAD")
    (root / "references/notes.md").unlink()
    (root / "metadata.json").write_text('{"status": "candidate"}', encoding="utf-8")
    with pytest.raises(ValueError, match="input paths differ"):
        build_index(tmp_path, "HEAD")


def test_moved_corpus_regenerates_from_its_pin_but_refuses_a_new_one(tmp_path, monkeypatch):
    # K02 moved the corpus and kept the recorded prefix. Regenerating against the
    # pinned revision still reads that revision's bytes, so no hash changes.
    # Pinning a revision that no longer carries the recorded prefix is refused,
    # which keeps re-pinning an explicit, separately reviewed change.
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def commit(message):
        git("-c", "user.name=Index test fixture", "-c", "user.email=index@example.invalid",
            "commit", "-s", "-m", message)

    git("init")
    pinned = tmp_path / index_builder.PINNED_LIBRARY
    root = pinned / "methods" / "example"
    root.mkdir(parents=True)
    (pinned / "skill-index.json").write_text(json.dumps({
        "schema_version": 1,
        "skills": {"example": {"path": "methods/example", "backend": "common"}},
    }), encoding="utf-8")
    (root / "SKILL.md").write_text(
        "---\nname: example\ndescription: A source fixture\n---\nOriginal body\n",
        encoding="utf-8",
    )
    git("add", index_builder.PINNED_LIBRARY.as_posix())
    commit("Create test source")
    monkeypatch.setattr(index_builder, "PROJECT", tmp_path)

    (tmp_path / LIBRARY).parent.mkdir(parents=True, exist_ok=True)
    git("mv", index_builder.PINNED_LIBRARY.as_posix(), LIBRARY.as_posix())
    commit("Move the corpus")
    assert (tmp_path / LIBRARY / "skill-index.json").is_file()

    outputs = build_index(tmp_path, "HEAD~1")
    record = json.loads(outputs["common/skills/example.json"])
    recorded = set(record["source_files"])
    assert recorded
    prefix = index_builder.PINNED_LIBRARY.as_posix()
    assert all(path.startswith(prefix + "/") for path in recorded), recorded
    assert not any(path.startswith(LIBRARY.as_posix() + "/") for path in recorded), recorded

    with pytest.raises(ValueError, match="input paths differ"):
        build_index(tmp_path, "HEAD")


def test_package_index_and_checkout_skill_have_distinct_read_boundaries():
    reader = KnowledgeReader(skill_root=ROOT)
    identity = "inferrsi.common.skills.claim_contract"
    bundle = reader.read(identity)
    assert "record.json" in bundle.content
    assert "data/skill_library/workflows/claim-contract/SKILL.md" in bundle.content
    assert bundle.dependencies
    assert bundle.metadata["kind"] == "knowledge"
    # The sidecar now declares an origin, so the package record stops falling
    # back to unknown; the checkout read still resolves the skill itself.
    assert bundle.metadata["origin"] == ["first-party"]
    assert reader.resolve(identity) == f"package:{identity}"
    assert reader.resolve("claim-contract") == "checkout:claim-contract"
    assert reader.read("claim-contract").metadata["kind"] == "skill"
    collected = reader.collect(repo="inferrsi", kind="knowledge", limit=100, material=True)
    assert len(collected["items"]) == 80
    assert not collected["collisions"] and not collected["omissions"]
    assert all(item["authority"] == "package" for item in collected["items"])
    assert all("record.json" in item["resources"] for item in collected["items"])
    assert all(len(item["resources"]) > 1 for item in collected["items"])
    assert reader.collect(repo="inferrsi", kind="skill")["no_match"]


def test_index_cli_search_show_context_and_execution_boundary(capsys):
    assert main([
        "knowledge", "search", "profiling", "--repo-type", "inferrsi", "--json",
    ]) == 0
    records = json.loads(capsys.readouterr().out)
    assert records and all(record["repo"] == "inferrsi" for record in records)
    identity = "inferrsi.ascend.skills.ascend_operator_profiling"
    assert main(["knowledge", "show", identity]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["skill_metadata"]["license"] == "UNKNOWN"
    assert main(["context", identity, "--repo-type", "inferrsi", "--backend", "ascend"]) == 0
    context = capsys.readouterr().out
    assert identity in context and "not the original skill" in context
    assert "locally_verified\": false" in context
    assert "inferrsi" not in REPO_TYPES
    with pytest.raises(ValueError, match="Unknown repository type"):
        repository_pack("inferrsi")
    with pytest.raises(SystemExit):
        parser().parse_args(["doctor", "--repo-type", "inferrsi"])


def test_hardware_filters_include_only_matching_and_shared_skills():
    for backend, count in (("ascend", 75), ("cuda", 64), ("cpu", 59)):
        records = search_knowledge(repo="inferrsi", backend=backend, limit=100)
        assert len(records) == count
        assert all(record["backend"] in (backend, "common") for record in records)
    assert not (PROJECT / "skills").exists()
    assert len(list(ROOT.rglob("SKILL.md"))) == 143
