"""Replay a released Playbook whose two required files belong to a separate Casebook."""

import json
import shutil

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    FIXTURES,
    RELEASE_COMMIT,
    assert_empty,
    canonical,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root, write_json
from tests.knowledge.test_atomic_reader import allow

NAME = "dense-performance-evidence"
REF = "checkout:" + NAME
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]
COMPOSITIONS = ATOMS.parent / "compositions"


def stage_atom(author, release, logical, pin):
    descriptor = ATOMS / (pin["ref"].removeprefix("checkout:") + ".json")
    shutil.copyfile(descriptor, author / "atoms" / descriptor.name)
    (resource,) = json.loads(descriptor.read_bytes())["content"].values()
    raw = (ATOMS / resource["path"]).read_bytes()
    for dest in (author / "atoms" / resource["path"], release / LIBRARY / logical):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    return digest(raw)


def dense_sources(root):
    author = make_author_root(root)
    release = root / "pinned"
    shutil.copytree(RELEASE_ROOT, release)
    path = author / "compositions" / (NAME + ".json")
    shutil.copyfile(COMPOSITIONS / path.name, path)
    spec = json.loads(path.read_bytes())
    nodes = spec["metadata"]["composition"]["nodes"]
    hashes = {logical: stage_atom(author, release, logical, nodes[node])
              for logical, node in spec["directory_resources"].items()}
    assert hashes == RELEASE["required_resources"]
    return author, release, path, spec


def test_dense_playbook_delivers_both_declared_case_files_with_the_original_card(tmp_path):
    author, release, _, _ = dense_sources(tmp_path)
    target = tmp_path / "installed"
    generation = build_generation(author, target, permits=allow,
                                  source_roots={RELEASE_COMMIT: release})
    reader = InstalledGeneration(target, expected=generation)
    _, bundle = reader.read_resolved(REF, revision=reader.catalog[REF]["revision"])
    assert bundle.view()["resources"] == RELEASE["required_resources"]
    assert bundle.dependencies == RELEASE["dependencies"]
    assert bundle.metadata["empirical_validation"] == "not_run"
    assert bundle.metadata["origin"] == ["external"] and bundle.metadata["attribution"] == []
    assert NAME not in reader.skills
    linked = {row["path"] for row in RELEASE["relative_guide_links"].values()}
    navigation = linked - bundle.dependencies.keys()
    assert len(navigation) == 3 and navigation.isdisjoint(bundle.content)
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        delivery = select(reader, REF, level, 100_000)
        assert delivery.receipt["status"] == "delivered"
        size = sum(map(len, delivery.bodies))
        assert delivery.receipt["body_bytes"] == size
        assert select(reader, REF, level, size) == delivery
        short = select(reader, REF, level, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        stale = select(reader, REF, level, size, revision=RELEASE["revision"])
        assert_empty(stale, "unavailable_revision")
        assert_empty(select(reader, REF, level, size, permits=lambda pin, op: pin.ref != REF),
                     "permission_denied")
        for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            start, end = item["source_byte_range"]
            assert item["source_path"].startswith(LIBRARY)
            assert item["source"]["commit"] == RELEASE_COMMIT
            assert item["source_range_verification"] == "verified_at_build"
            assert body == bundle.content[item["source_path"].removeprefix(LIBRARY)][start:end]
            denied_ref = item["ref"]
            denied = select(reader, REF, level, size, permits=lambda pin, op: pin.ref != denied_ref)
            assert_empty(denied, "permission_denied")
        layers[level] = delivery.bodies
    entry = RELEASE["entrypoint"]
    assert bundle.content[entry].startswith(layers["L0"][0])
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(REF, RELEASE["revision"], "skill", entry, entry, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert len(canonical(card)) == RELEASE["card_bytes"]
    assert digest(canonical(card)) == RELEASE["card_sha256"]
    record, guide = sorted(RELEASE["dependencies"])
    assert record.endswith(".json") and guide.endswith(".md")
    assert layers["L2"][0] == decision and b"".join(layers["L2"][:2]) == bundle.content[entry]
    assert layers["L2"][2:] == (bundle.content[guide], bundle.content[record])
    assert layers["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))


@pytest.mark.parametrize(("change", "error"), [
    ("omit declared file", "complete original directory"),
    ("reverse declared order", "L2 must deliver its declared original references"),
    ("add navigation-only file", "complete original directory"),
    ("rename original path", "differs from its original relative source"),
])
def test_compiler_rejects_changed_cross_directory_contract(tmp_path, change, error):
    author, release, path, spec = dense_sources(tmp_path)
    bindings = spec["directory_resources"]
    metadata = spec["metadata"]
    composition = metadata["composition"]
    procedure = composition["routes"]["procedure"]["required"]
    originals = composition["routes"]["originals"]["required"]
    case_record = next(name for name, node in bindings.items() if node == "case-record")
    if change == "omit declared file":
        del bindings[case_record]
        originals.remove("case-record")
        procedure.remove("case-record")
        del composition["nodes"]["case-record"]
    elif change == "reverse declared order":
        procedure[-2:] = reversed(procedure[-2:])
    elif change == "add navigation-only file":
        link = next(row for row in RELEASE["relative_guide_links"].values()
                    if row["path"].endswith("COMPARISON.md"))
        target = json.loads((COMPOSITIONS / "npu-skill-factory.json").read_bytes())
        node = target["directory_resources"][link["path"]]
        pin = target["metadata"]["composition"]["nodes"][node]
        assert stage_atom(author, release, link["path"], pin) == link["sha256"]
        bindings[link["path"]] = "navigation-target"
        composition["nodes"]["navigation-target"] = pin
        originals.append("navigation-target")
    else:
        bindings["casebooks/copied-case.json"] = bindings.pop(case_record)
    metadata["required_resources"] = sorted(bindings)
    write_json(path, spec)
    target = tmp_path / "installed"
    with pytest.raises(ValueError, match=error):
        build_generation(author, target, permits=allow, source_roots={RELEASE_COMMIT: release})
    assert not target.exists()
