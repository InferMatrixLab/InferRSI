"""Replay the released training resource-budget guide, its references and adaptation terms."""

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
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

NAME = "training-resource-budget"
REF = "checkout:" + NAME
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"


@pytest.fixture(scope="module")
def installed_budget(tmp_path_factory):
    root = tmp_path_factory.mktemp("training-budget")
    author = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    composition = ATOMS.parent / "compositions" / (NAME + ".json")
    shutil.copyfile(composition, author / "compositions" / composition.name)
    declaration = json.loads(composition.read_bytes())
    nodes = declaration["metadata"]["composition"]["nodes"]
    bindings = declaration["directory_resources"]
    assert bindings.keys() == RELEASE["required_resources"].keys()
    for logical, node in bindings.items():
        descriptor = ATOMS / (nodes[node]["ref"].removeprefix("checkout:") + ".json")
        shutil.copyfile(descriptor, author / "atoms" / descriptor.name)
        (resource,) = json.loads(descriptor.read_bytes())["content"].values()
        raw = (ATOMS / resource["path"]).read_bytes()
        assert digest(raw) == RELEASE["required_resources"][logical]
        for dest in (author / "atoms" / resource["path"], release / (LIBRARY + logical)):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
    # Keep the deepest published resource above the legacy Windows path limit on a short drive.
    target = root / ("installed-" + "nested-" * 12) / ("tenant-" * 8) / "release"
    generation = build_generation(author, target, permits=allow,
                                  source_roots={RELEASE_COMMIT: release})
    return InstalledGeneration(target, expected=generation)


def test_training_budget_preserves_released_layers_and_navigation_scope(installed_budget):
    reader = installed_budget
    _, bundle = reader.read_resolved(REF, revision=reader.catalog[REF]["revision"])
    assert bundle.view()["resources"] == RELEASE["required_resources"]
    assert bundle.dependencies == RELEASE["dependencies"] == {}
    entry = RELEASE["entrypoint"]
    navigation = [link for link in RELEASE["relative_guide_links"].values()
                  if not link["in_directory"]]
    assert len(navigation) == 3
    assert all(link["path"] not in bundle.content for link in navigation)
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        delivery = select(reader, REF, level, 1_000_000)
        assert delivery.receipt["status"] == "delivered"
        size = sum(map(len, delivery.bodies))
        assert select(reader, REF, level, size) == delivery
        assert_empty(select(reader, REF, level, size - 1), "over_budget")
        stale = select(reader, REF, level, size, revision=RELEASE["revision"])
        assert_empty(stale, "unavailable_revision")
        for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            start, end = item["source_byte_range"]
            path = item["source_path"].removeprefix(LIBRARY)
            assert body == bundle.content[path][start:end]
            assert item["source_range_verification"] == "verified_at_build"
            assert item["source"]["commit"] == RELEASE_COMMIT
            denied_ref = item["ref"]
            assert_empty(select(reader, REF, level, size,
                                permits=lambda pin, op: pin.ref != denied_ref), "permission_denied")
        layers[level] = delivery.bodies

    assert bundle.content[entry].startswith(layers["L0"][0])
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(REF, RELEASE["revision"], "skill", entry, entry, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert digest(canonical(card)) == RELEASE["card_sha256"]
    assert len(canonical(card)) == RELEASE["card_bytes"]
    assert layers["L2"][0] == decision and b"".join(layers["L2"]) == bundle.content[entry]
    assert layers["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))


def test_training_budget_keeps_share_alike_on_the_adapted_note(installed_budget):
    reader = installed_budget
    _, bundle = reader.read_resolved(REF, revision=reader.catalog[REF]["revision"])
    nodes = bundle.metadata["composition"]["nodes"]
    note = nodes["stas-decision-notes"]
    _, atom = reader.read_resolved(note["ref"], revision=note["revision"])
    credit, = atom.metadata["attribution"]
    assert atom.metadata["atom"]["license"] == credit["license"] == "CC-BY-SA-4.0"
    assert credit["author"] == "Stas Bekman" and credit in atom.metadata["sources"]
    content = atom.content["stas-decision-notes.md"]
    assert credit["commit"].encode() in content and credit["license_url"].encode() in content
    assert b"paraphrased adaptation" in content
    for node in ("mindspeed-historical", "mindspeed-source-readset", "sources"):
        pin = nodes[node]
        _, independent = reader.read_resolved(pin["ref"], revision=pin["revision"])
        assert independent.metadata["atom"]["license"] == "Apache-2.0"
    assert bundle.metadata["empirical_validation"] == "not_run"
    denied = select(reader, REF, "L3", 1_000_000, operations={"redistribute"},
                    permits=lambda pin, op: (pin.ref, op) != (note["ref"], "redistribute"))
    assert_empty(denied, "permission_denied")
