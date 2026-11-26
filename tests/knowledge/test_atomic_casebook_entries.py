"""Compare both Casebook guides against the decisions observed from the released wheel."""

import json
import shutil
from pathlib import PurePosixPath
from zipfile import ZipFile

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    BASELINE,
    FIXTURES,
    RELEASE_COMMIT,
    assert_empty,
    canonical,
    case_sources,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import write_json
from tests.knowledge.test_atomic_reader import allow

GUIDES = {ref: row for ref, row in BASELINE["refs"].items() if "decision" in row}
DIRECTORIES = sorted(ref for ref in GUIDES if ref.startswith("checkout:"))


@pytest.mark.parametrize("ref", sorted(GUIDES))
def test_released_guide_reproduces_each_namespaced_decision(ref):
    row = GUIDES[ref]
    expected = row["decision"]
    with ZipFile(FIXTURES / "casebook-sources-v0.3.4.zip") as archive:
        data = archive.read(row["entry_source"])
    assert digest(data) == row["entry_sha256"]
    _, metadata = _skill_search_source(data.decode())
    assert metadata["empirical_validation"] == "not_run"
    guide = ("" if ref.startswith("checkout:") else "data/skill_library/") + row["entry_source"]
    assert expected["atom"] == {"kind": "skill", "resource": guide}
    if ref.startswith("package:"):
        assert row["legacy_entrypoint"] == "record.json"
        assert row["legacy_entrypoint_sha256"] != digest(data)
    else:
        assert row["legacy_entrypoint"] == guide and row["legacy_entrypoint_sha256"] == digest(data)
    source = DecisionSource(ref, row["revision"], "skill", guide, guide, metadata)
    budget = expected["card_bytes"]
    reply = source.project(max_bytes=budget)
    card = reply["card"]
    assert reply["card_bytes"] == len(canonical(card)) == budget
    assert digest(canonical(card)) == expected["card_sha256"]
    assert card["status"] == expected["status"] == "partial"
    assert card["missing_fields"] == expected["missing_fields"] == ["validation"]
    short = source.project(max_bytes=budget - 1)
    assert short["status"] == "over_budget" and "card" not in short


@pytest.fixture(scope="module")
def casebook_files():
    with ZipFile(FIXTURES / "casebook-sources-v0.3.4.zip") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def directory_sources(root, files):
    author, release = case_sources(root, files)
    for ref in DIRECTORIES:
        name = ref.partition(":")[2]
        for directory, filename in (("atoms", f"{name}.original.json"),
                                    ("compositions", f"{name}.json")):
            shutil.copyfile(ATOMS.parent / directory / filename, author / directory / filename)
    return author, release


@pytest.fixture(scope="module")
def installed_directories(tmp_path_factory, casebook_files):
    root = tmp_path_factory.mktemp("casebook-entries")
    author, release = directory_sources(root, casebook_files)
    target = root / "installed"
    generation = build_generation(author, target, permits=allow,
                                  source_roots={RELEASE_COMMIT: release})
    return InstalledGeneration(target, expected=generation), target


@pytest.mark.parametrize("ref", DIRECTORIES)
def test_directory_replays_all_resources_and_exports_the_original_host_tree(
    installed_directories, casebook_files, ref,
):
    row = GUIDES[ref]
    entry = PurePosixPath(row["legacy_entrypoint"])
    released = {path: raw for path, raw in casebook_files.items()
                if PurePosixPath(path).is_relative_to(entry.parent)}
    installed, target = installed_directories
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    assert not bundle.dependencies and bundle.content == released
    assert len(released) == row["resource_count"] == row["required_count"]
    assert bundle.metadata["required_resources"] == sorted(released)
    assert digest(canonical(bundle.view()["resources"])) == row["resource_set_sha256"]
    assert bundle.metadata["origin"] == ["external"]
    assert bundle.metadata["state"] == "candidate"
    assert bundle.metadata["empirical_validation"] == "not_run"
    assert installed.skills[entry.parent.name] == ref
    host = target / "skills" / entry.parent.name
    assert {path.relative_to(host).as_posix(): path.read_bytes()
            for path in host.rglob("*") if path.is_file()} == {
        PurePosixPath(path).relative_to(entry.parent).as_posix(): raw
        for path, raw in released.items()
    }


@pytest.mark.parametrize("ref", DIRECTORIES)
def test_directory_read_selection_replays_each_layer_and_refuses_incomplete_groups(
    installed_directories, casebook_files, ref,
):
    row = GUIDES[ref]
    installed, _ = installed_directories
    guide = row["entry_source"]
    raw = casebook_files[guide]
    result = {}
    for layer in ("L0", "L1", "L2", "L3"):
        delivery = select(installed, ref, layer, 1_000_000)
        assert delivery.receipt["status"] == "delivered"
        result[layer] = delivery
        size = sum(map(len, delivery.bodies))
        assert delivery.receipt["body_bytes"] == size and size > 0
        assert select(installed, ref, layer, size) == delivery
        short = select(installed, ref, layer, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            lo, hi = item["source_byte_range"]
            path = item["source_path"].split("/skill_library/", 1)[1]
            assert item["source"]["commit"] == RELEASE_COMMIT
            assert item["source_range_verification"] == "verified_at_build"
            assert casebook_files[path][lo:hi] == body and item["source_sha256"] == digest(body)
            forbidden = item["ref"]
            denied = select(installed, ref, layer, size,
                            permits=lambda pin, op: pin.ref != forbidden)
            assert_empty(denied, "permission_denied")
        stale = select(installed, ref, layer, size, revision=row["revision"])
        assert_empty(stale, "unavailable_revision")
        assert_empty(select(installed, ref, layer, size, permits=lambda pin, op: pin.ref != ref),
                     "permission_denied")
    (navigation,) = result["L0"].bodies
    assert ref.partition(":")[2].encode() in navigation and b"description:" in navigation
    assert b"metadata:" not in navigation and raw.startswith(navigation)
    (decision,) = result["L1"].bodies
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(ref, row["revision"], "skill", guide, guide, fields).project()["card"]
    expected = row["decision"]
    assert len(canonical(card)) == expected["card_bytes"]
    assert digest(canonical(card)) == expected["card_sha256"]
    assert card["missing_fields"] == ["validation"] and card["status"] == "partial"
    assert result["L2"].bodies[0] == decision and b"".join(result["L2"].bodies) == raw
    assert result["L3"].bodies == tuple(
        casebook_files[name] for name in sorted(casebook_files)
        if PurePosixPath(name).parent.is_relative_to(PurePosixPath(guide).parent)
    )


@pytest.mark.parametrize(("change", "error"), [
    ("dropped file and declaration", "complete original directory"),
    ("wrong alias", "original relative source"), ("excerpt", "complete L3 original"),
    ("missing L3 attachment", "L3 must deliver"), ("omitted prerequisite", "L2 must deliver"),
    ("reversed guide sections", "L2 must deliver"),
    ("another guide decision", "L1 must deliver"), ("wrong section", "source range or layer"),
    ("conditional override", "unconditional delivery"),
    ("unbound host export", "requires checked"), ("identity", "original SKILL.md and identity"),
])
def test_cannot_publish_a_partial_or_misbound_directory(tmp_path, casebook_files, change, error):
    author, release = directory_sources(tmp_path, casebook_files)
    ref = "checkout:inference-optimization-casebook"
    name = ref.partition(":")[2]
    path = author / "compositions" / (name + ".json")
    spec = json.loads(path.read_bytes())
    declaration = spec["metadata"]["composition"]
    bindings = spec["directory_resources"]
    attachment = next(key for key in bindings if key.endswith(".json"))
    if change == "dropped file and declaration":
        del bindings[attachment]
        spec["metadata"]["required_resources"].remove(attachment)
    elif change == "wrong alias":
        bindings[attachment] = bindings[attachment.removesuffix(".json") + ".md"]
    elif change == "excerpt":
        bindings[attachment] = "navigation"
    elif change == "missing L3 attachment":
        declaration["routes"]["originals"]["required"].remove(bindings[attachment])
    elif change == "omitted prerequisite":
        del declaration["nodes"]["procedure"]["requires"]
    elif change == "reversed guide sections":
        del declaration["nodes"]["procedure"]["requires"]
        declaration["routes"]["procedure"]["required"] = ["procedure", "decision"]
    elif change == "another guide decision":
        other = json.loads((path.parent / "ascend-optimization-casebook.json").read_bytes())
        declaration["nodes"]["decision"] = other["metadata"]["composition"]["nodes"]["decision"]
    elif change == "conditional override":
        declaration["routes"]["alternate"] = {
            "layer": "L1", "when": {"backend": ["cpu"]}, "supersedes": ["decision"],
            "required": ["navigation"],
        }
    elif change == "wrong section":
        path = author / "atoms" / (name + ".original.json")
        spec = json.loads(path.read_bytes())
        spec["parts"]["procedure"]["skill_section"] = "decision"
    elif change == "unbound host export":
        del spec["directory_resources"]
    else:
        spec["metadata"]["id"] = "another-directory"
    write_json(path, spec)
    with pytest.raises(ValueError, match=error):
        build_generation(author, tmp_path / "installed", permits=allow,
                         source_roots={RELEASE_COMMIT: release})
    assert not (tmp_path / "installed").exists()
