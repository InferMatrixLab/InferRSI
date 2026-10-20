import json
from pathlib import Path

import pytest

from inferrsi.knowledge_operations import (
    IdentityError,
    KnowledgeReader,
    RevisionConflict,
    safe_path,
)

ROOT = Path(__file__).resolve().parents[1] / "src/inferrsi/data/skill_library"


def test_normalized_sources_and_original_catalog_identity():
    reader = KnowledgeReader(skill_root=ROOT)
    repository = reader.read("audit-vllm-kv-lifetimes")
    paper = reader.read("calibrate-serving-simulation")
    case = reader.read("case.admission-drain-occupancy")
    assert repository.metadata["sources"][0]["type"] == "git"
    assert paper.metadata["sources"][0]["type"] == "paper"
    assert "commit" not in paper.metadata["sources"][0]
    assert case.metadata["sources"][0]["type"] == "internal"
    assert case.metadata["state"] == "historical_observation"
    record = reader.read("vllm.common.llm.runtime_and_kv_ownership")
    assert record.metadata["state"] == "imported"
    assert record.metadata["tier"] == "contribution"
    assert any("zh-CN" in path for path in record.content)
    assert any(path.endswith("LICENSE") for path in record.content)
    assert record.dependencies["data/skill_library"].startswith("sha256:")


def test_resource_only_change_invalidates_old_snapshot_revision(tmp_path):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text("---\nname: selected\ndescription: test\n---\nBody")
    resource = directory / "notes.md"
    resource.write_text("first")
    reader = KnowledgeReader(skill_root=tmp_path)
    original = reader.read("selected")
    assert reader.resource("selected", "selected/notes.md", revision=original.revision) == b"first"
    resource.write_text("second")
    assert reader.read("selected").revision != original.revision
    with pytest.raises(RevisionConflict):
        reader.resource("selected", "selected/notes.md", revision=original.revision)


def test_collect_limits_omissions_and_shared_resource_revision():
    reader = KnowledgeReader(skill_root=ROOT)
    selected = reader.read("inference-benchmark-design")
    shared = "methods/inference-optimization-casebook/cases/admission-drain-occupancy.md"
    assert shared in selected.content and shared in selected.dependencies
    result = reader.collect(
        ids=["inference-benchmark-design", "dense-performance-evidence"], limit=1
    )
    assert len(result["items"]) == 1
    assert result["omissions"] == [{"id": "dense-performance-evidence", "reason": "output_limit"}]
    limited = reader.collect(ids=["calibrate-serving-simulation"], max_bytes=1, material=True)
    assert limited["no_match"] and limited["omissions"]
    missing = reader.collect(ids=["not-a-real-id"])
    assert missing["no_match"] and missing["omissions"]
    assert reader.collect(query="doesnotmatchanyrecord", ids=["calibrate-serving-simulation"])[
        "no_match"
    ]


def test_collect_filters_and_revision_conflicts():
    reader = KnowledgeReader()
    result = reader.collect(repo="flashinfer", tier="dependency", material=True)
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert json.loads(item["content"])["id"] == item["id"]
    assert item["sources"][0]["type"] == "git"
    assert item["authority"] == "package" and item["ref"] == f"package:{item['id']}"
    conflict = reader.collect(ids=[item["id"]], revisions={item["id"]: "sha256:" + "0" * 64})
    assert conflict["no_match"]
    assert conflict["omissions"][0]["reason"] == "unavailable_revision"


def _case(root: Path, identity: str) -> None:
    cases = root / "owner" / "cases"
    cases.mkdir(parents=True)
    (root / "owner" / "SKILL.md").write_text(
        "---\nname: owner\ndescription: test\n---\nBody", encoding="utf-8"
    )
    (cases / "note.md").write_text("observation", encoding="utf-8")
    record = {
        "id": identity,
        "kind": "case",
        "state": "historical_observation",
        "content": "note.md",
        "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
        "applicability": [],
        "limitations": [],
        "attribution": "fixture",
    }
    (cases / "note.json").write_text(json.dumps(record), encoding="utf-8")


def test_cross_adapter_collision_is_ambiguous_not_shadowed(tmp_path):
    package_id = KnowledgeReader().identities()[0].partition(":")[2]
    _case(tmp_path, package_id)
    reader = KnowledgeReader(skill_root=tmp_path)
    with pytest.raises(IdentityError, match="Ambiguous") as error:
        reader.read(package_id)
    assert error.value.code == "ambiguous_identity"
    assert reader.read(f"checkout:{package_id}").metadata["kind"] == "case"
    assert reader.read(f"package:{package_id}").metadata["kind"] == "knowledge"
    explicit = reader.collect(ids=[package_id])
    assert explicit["no_match"] and explicit["omissions"][0]["reason"] == "ambiguous_identity"
    everything = reader.collect(kind="case", limit=100)
    assert package_id in everything["collisions"]
    assert [item["ref"] for item in everything["items"]] == [f"checkout:{package_id}"]


def test_every_package_record_normalizes_with_legacy_types_kept():
    reader = KnowledgeReader()
    references = reader.identities()
    legacy = []
    for reference in references:
        bundle = reader.read(reference)
        legacy += [s for s in bundle.metadata["sources"] if "original_type" in s]
    assert references and legacy
    assert all(s["type"] in ("git", "unknown") for s in legacy)
    unknown = [s for s in legacy if s["type"] == "unknown"]
    assert unknown and all("commit" not in s or s["original_type"] for s in unknown)
    result = reader.collect(limit=len(references))
    assert not [o for o in result["omissions"] if o["reason"] == "invalid"]


def test_malformed_items_are_reported_not_raised(tmp_path):
    _case(tmp_path, "case.no-sources")
    record = tmp_path / "owner" / "cases" / "note.json"
    record.write_text(record.read_text(encoding="utf-8").replace('"sources"', '"x"'), "utf-8")
    reader = KnowledgeReader(skill_root=tmp_path)
    result = reader.collect(ids=["case.no-sources", "owner"])
    assert [o["reason"] for o in result["omissions"]] == ["invalid"]
    assert [item["ref"] for item in result["items"]] == ["checkout:owner"]


def test_incidental_files_and_hashes_do_not_affect_reads(tmp_path):
    directory = tmp_path / "selected"
    directory.mkdir()
    (directory / "SKILL.md").write_text("---\nname: selected\ndescription: t\n---\nBody")
    before = KnowledgeReader(skill_root=tmp_path).read("selected").revision
    (directory / "__pycache__").mkdir()
    (directory / "__pycache__" / "x.pyc").write_bytes(b"\0")
    reader = KnowledgeReader(skill_root=tmp_path)
    assert reader.read("selected").revision == before
    assert reader.collect("sha256", ids=["selected"])["omissions"][0]["reason"] == "query"


def test_qualified_identity_rules(tmp_path):
    _case(tmp_path, "case.local-only")
    reader = KnowledgeReader(skill_root=tmp_path)
    assert reader.resolve("case.local-only") == "checkout:case.local-only"
    for reference, code in [
        ("package:case.local-only", "unknown_identity"),
        ("elsewhere:case.local-only", "invalid_identity"),
        ("Bad ID", "invalid_identity"),
    ]:
        with pytest.raises(IdentityError) as error:
            reader.resolve(reference)
        assert error.value.code == code
    duplicate = reader.collect(ids=["case.local-only", "checkout:case.local-only"])
    assert len(duplicate["items"]) == 1
    assert duplicate["omissions"][0]["reason"] == "duplicate_identity"
    package_filter = reader.collect(ids=["case.local-only"], repo="flashinfer")
    assert package_filter["omissions"] == [{"id": "case.local-only", "reason": "filters"}]


def test_legacy_frontmatter_reference_is_a_dependency(tmp_path):
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "SKILL.md").write_text("---\nname: other\ndescription: t\n---\nB")
    target = tmp_path / "other" / "notes.md"
    target.write_text("first")
    (tmp_path / "selected").mkdir()
    (tmp_path / "selected" / "SKILL.md").write_text(
        "---\nname: selected\ndescription: t\nreferences: [../other/notes.md]\n"
        "applicability: {backend: any}\n---\nBody"
    )
    reader = KnowledgeReader(skill_root=tmp_path)
    original = reader.read("selected")
    assert original.metadata["applicability"] == {"backend": "any"}
    assert original.content["other/notes.md"] == b"first"
    assert "other/notes.md" in original.dependencies
    target.write_text("second")
    assert reader.read("selected").revision != original.revision
    target.unlink()
    with pytest.raises(ValueError, match="Missing skill reference"):
        reader.read("selected")


def _declare(root: Path, **fields) -> None:
    path = root / "owner" / "cases" / "note.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**record, **fields}), encoding="utf-8")


def test_case_required_resources_are_retained_and_checked(tmp_path):
    _case(tmp_path, "case.measured")
    data = tmp_path / "owner" / "cases" / "measurements.csv"
    data.write_text("a,1", encoding="utf-8")
    plain = KnowledgeReader(skill_root=tmp_path).read("case.measured")
    assert plain.metadata["required_resources"] == ["note.md", "case.json"]
    _declare(tmp_path, required_resources=["measurements.csv"])
    reader = KnowledgeReader(skill_root=tmp_path)
    original = reader.read("case.measured")
    assert original.content["measurements.csv"] == b"a,1"
    data.write_text("a,2", encoding="utf-8")
    assert reader.read("case.measured").revision != original.revision
    data.unlink()
    with pytest.raises(ValueError, match="Missing case resource"):
        reader.read("case.measured")
    data.write_text("a,1", encoding="utf-8")
    for fields, message in [
        ({"required_resources": ["../SKILL.md"]}, "Unsafe"),
        ({"required_resources": "measurements.csv"}, "string list"),
        ({"required_resources": ["measurements.csv"] * 2}, "repeat"),
        ({"required_resources": ["case.json"]}, "collides"),
        ({"required_resources": [], "references": ["x.md"]}, "not supported"),
        ({"required_resources": [], "dependencies": {}}, "not supported"),
    ]:
        path = tmp_path / "owner" / "cases" / "note.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.pop("references", None)
        record.pop("dependencies", None)
        path.write_text(json.dumps({**record, **fields}), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            KnowledgeReader(skill_root=tmp_path).read("case.measured")


def test_missing_declared_skill_document_is_explicit():
    reader = KnowledgeReader()
    identity, record = next((i, r) for i, r in reader.records().items() if r.get("skill_documents"))
    library, digest = reader._skill_library()
    target = next(iter(record["skill_documents"].values()))
    reader._library = ({k: v for k, v in library.items() if k != target}, digest)
    with pytest.raises(ValueError, match="Missing declared skill document"):
        reader.read(identity)
    result = reader.collect(ids=[identity])
    assert result["omissions"][0]["reason"] == "invalid"


def test_malformed_checkout_discovery_fails_explicitly(tmp_path):
    _case(tmp_path, "case.broken")
    (tmp_path / "owner" / "cases" / "note.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        KnowledgeReader(skill_root=tmp_path).collect(ids=["owner"])


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a\\b", "C:/outside", "a/../b"])
def test_unsafe_resource_paths_fail(path):
    with pytest.raises(ValueError, match="Unsafe"):
        safe_path(path)
