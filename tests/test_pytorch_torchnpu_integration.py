"""Framework graphs preserve local profiles and complete read-only bundles."""

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from inferrsi.knowledge._source_snapshot import source_entry
from inferrsi.knowledge.catalog import get_knowledge
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.knowledge.skill_catalog import skill_metadata, skill_resource

PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = PROJECT / "src/inferrsi/knowledge/data/skill_library"
GRAPHS = (("pytorch", "common"), ("torch-npu", "ascend"))


def _pinned(path: Path) -> str:
    """Name a corpus file the way the pinned source_revision recorded it."""
    return source_entry(path.relative_to(LIBRARY.parent.parent).as_posix())


@pytest.mark.parametrize("name,backend", GRAPHS)
def test_framework_roots_register_graphs_without_registering_children(name, backend):
    registry = json.loads((LIBRARY / "skill-index.json").read_text(encoding="utf-8"))["skills"]
    owner = LIBRARY / "systems/frameworks" / name / name
    assert registry[name] == {"path": f"systems/frameworks/{name}/{name}", "backend": backend}
    children = sorted((owner / "sub-skills").glob("*/SKILL.md"))
    assert len(children) == 8
    assert not {path.parent.name for path in children} & set(registry)
    repository_license = skill_metadata(LIBRARY, name)["license"]
    for document in [owner / "SKILL.md", *children]:
        frontmatter = document.read_text(encoding="utf-8").split("---", 2)[1]
        header = yaml.safe_load(frontmatter)
        assert set(header) == {"name", "description", "metadata"}
        assert header["name"] == document.parent.name
        assert re.search(r'^description: ".+"$', frontmatter, re.MULTILINE)
        fields = json.loads(header["metadata"]["inferrsi"])
        assert fields["profile"] == "local-skill-v1"
        assert fields["status"] == "candidate"
        assert fields["disable-model-invocation"] is True
        assert fields["metadata"]["disco-role"] == "operating"
        assert isinstance(fields["license"], str) and fields["license"].strip()
        assert fields["license"] == repository_license
        # A child is still a valid local skill when selected from its flat parent.
        root = LIBRARY if document.parent == owner else owner / "sub-skills"
        native = {key: header[key] for key in ("name", "description")}
        assert skill_metadata(root, header["name"]) == native | fields


@pytest.mark.parametrize("name,backend", GRAPHS)
def test_framework_graph_resources_survive_checkout_bundle_reads(name, backend):
    owner = LIBRARY / "systems/frameworks" / name / name
    reader = KnowledgeReader(skill_root=LIBRARY)
    identity = f"checkout:{name}"
    bundle = reader.read(identity)
    assert bundle.metadata["state"] == "candidate"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(bundle.metadata["limitations"])
    files = [path for path in owner.rglob("*") if path.is_file()]
    assert any(path.parent.name == "scripts" and path.suffix == ".py" for path in files)
    for path in files:
        relative = path.relative_to(owner).as_posix()
        key = path.relative_to(LIBRARY).as_posix()
        assert bundle.content[key] == path.read_bytes()
        if path != owner / "SKILL.md":
            assert skill_resource(LIBRARY, name, relative).read_bytes() == path.read_bytes()
    child = next((owner / "sub-skills").glob("*/SKILL.md"))
    child_key = child.relative_to(LIBRARY).as_posix()
    assert reader.resource(identity, child_key, revision=bundle.revision) == child.read_bytes()


@pytest.mark.parametrize("name,backend", GRAPHS)
def test_framework_catalog_preserves_owner_metadata_and_scope_without_promotion(name, backend):
    owner = LIBRARY / "systems/frameworks" / name / name
    record = get_knowledge(f"inferrsi.{backend}.skills.{name.replace('-', '_')}")
    assert record["backend"] == backend
    assert record["status"] == "imported"
    assert record["skill_metadata"] == skill_metadata(LIBRARY, name)
    assert not record["verification"]["locally_verified"]
    assert record["skill_documents"] == {
        "original": f"data/skill_library/systems/frameworks/{name}/{name}/SKILL.md",
    }
    source_paths = set(record["source_files"])
    for document in owner.rglob("SKILL.md"):
        # source_files names each input at the pinned source_revision, where the
        # corpus still sat directly under src/inferrsi/data.
        assert _pinned(document) in source_paths


def test_pytorch_retained_license_and_notice_match_declared_immutable_blob_bytes():
    owner = LIBRARY / "systems/frameworks/pytorch/pytorch"
    ledger = json.loads((owner / "references/source-readset.json").read_text(encoding="utf-8"))
    metadata = skill_metadata(LIBRARY, "pytorch")
    assert ledger["commit"] in {source["commit"] for source in metadata["sources"]}
    identities = {item["path"]: item for item in ledger["files"]}
    for upstream, retained in (("LICENSE", "LICENSE"), ("NOTICE", "references/upstream-NOTICE")):
        assert hashlib.sha256((owner / retained).read_bytes()).hexdigest() == (
            identities[upstream]["git_blob_sha256"]
        )


def test_torchnpu_retained_source_documentation_and_third_party_notices_keep_blob_bytes():
    owner = LIBRARY / "systems/frameworks/torch-npu/torch-npu"
    ledger = json.loads(
        (owner / "references/licenses/source-identities.json").read_text(encoding="utf-8")
    )
    metadata = skill_metadata(LIBRARY, "torch-npu")
    commits = {source["commit"] for source in metadata["sources"]}
    assert len(ledger["retained_files"]) == 5
    for item in ledger["retained_files"]:
        retained = (owner / item["bundled_path"]).resolve()
        assert retained.is_relative_to(owner.resolve())
        assert item["commit"] in commits
        assert hashlib.sha256(retained.read_bytes()).hexdigest() == item["git_blob_sha256"]
