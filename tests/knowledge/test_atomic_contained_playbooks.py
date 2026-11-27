"""Compare installed measurement and training Playbooks with their released decisions and files."""

import json
import shutil
from pathlib import PurePosixPath

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
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, file_bytes, make_author_root
from tests.knowledge.test_atomic_reader import allow

RELEASED = json.loads((FIXTURES / "contained-playbooks-v0.3.4.json").read_bytes())
LIBRARY = "src/inferrsi/knowledge/data/skill_library"


@pytest.fixture(scope="module")
def installed_playbooks(tmp_path_factory):
    root = tmp_path_factory.mktemp("contained-playbooks")
    authored = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    for name in RELEASED:
        comp = ATOMS.parent / "compositions" / (name + ".json")
        shutil.copyfile(comp, authored / "compositions" / comp.name)
        spec = json.loads(comp.read_bytes())
        for logical, node in spec["directory_resources"].items():
            pin = spec["metadata"]["composition"]["nodes"][node]
            descriptor = ATOMS / (pin["ref"].removeprefix("checkout:") + ".json")
            shutil.copyfile(descriptor, authored / "atoms" / descriptor.name)
            (resource,) = json.loads(descriptor.read_bytes())["content"].values()
            for target in (authored / "atoms" / resource["path"], release / LIBRARY / logical):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ATOMS / resource["path"], target)
    target = root / "installed"
    generation = build_generation(authored, target, permits=allow,
                                  source_roots={RELEASE_COMMIT: release})
    return InstalledGeneration(target, expected=generation), target


@pytest.mark.parametrize("name", sorted(RELEASED))
def test_host_files_and_reader_match_released_playbook(installed_playbooks, name):
    installed, target = installed_playbooks
    expected = RELEASED[name]
    ref = "checkout:" + name
    assert installed.skills[name] == ref
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    pinned_guide, *upstream_sources = metadata["sources"]
    metadata["sources"] = upstream_sources
    assert digest(canonical(metadata)) == expected["manifest_sha256"]
    assert digest(canonical(bundle.view()["resources"])) == expected["resource_set_sha256"]
    guide = metadata["entrypoint"]
    root = PurePosixPath(guide).parent
    assert pinned_guide["path"] == f"{LIBRARY}/{guide}"
    assert pinned_guide["sha256"] == digest(bundle.content[guide])
    assert pinned_guide["commit"] == RELEASE_COMMIT and bundle.dependencies == {}
    originals = {PurePosixPath(path).relative_to(root).as_posix(): raw
                 for path, raw in bundle.content.items()}
    assert set(originals) == {"SKILL.md", *expected["attachments"]}
    assert file_bytes(target / "skills" / name) == originals

    layers = {}
    for layer in ("L0", "L1", "L2", "L3"):
        delivery = select(installed, ref, layer, 1_000_000)
        assert delivery.receipt["status"] == "delivered"
        size = sum(map(len, delivery.bodies))
        assert select(installed, ref, layer, size) == delivery
        assert_empty(select(installed, ref, layer, size - 1), "over_budget")
        assert_empty(select(installed, ref, layer, size, revision=expected["revision"]),
                     "unavailable_revision")
        for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            path = PurePosixPath(item["source_path"]).relative_to(LIBRARY).as_posix()
            start, end = item["source_byte_range"]
            assert body == bundle.content[path][start:end]
            assert item["source"]["commit"] == RELEASE_COMMIT
            assert item["source_range_verification"] == "verified_at_build"
            forbidden = item["ref"]
            assert_empty(select(installed, ref, layer, size,
                                permits=lambda pin, op: pin.ref != forbidden), "permission_denied")
        layers[layer] = delivery.bodies

    (navigation,) = layers["L0"]
    assert name.encode() in navigation and originals["SKILL.md"].startswith(navigation)
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    decision_source = DecisionSource(ref, expected["revision"], "skill", guide, guide, fields)
    card = decision_source.project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == expected["missing_fields"]
    assert digest(canonical(card)) == expected["card_sha256"]
    assert len(canonical(card)) == expected["card_bytes"]
    assert layers["L2"][0] == decision and b"".join(layers["L2"]) == originals["SKILL.md"]
    assert layers["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))


def test_serving_calibration_installs_the_scoped_upstream_rights_record(installed_playbooks):
    installed, target = installed_playbooks
    name = "calibrate-serving-simulation"
    ref = installed.skills[name]
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    directory = target / "skills" / name / "references" / "infera-serving-search"
    source = json.loads((directory / "source-record.json").read_bytes())
    assert (directory / "README.md").is_file() and source["owner"] == name
    assert bundle.metadata["origin"] == ["external"]
    assert bundle.metadata["empirical_validation"] == "not_run"
    assert source["source"]["commit"] == "ff1136e4a51998eba2933ed63cfb9c10120f86ea"
    rights = source["rights"]
    selected_license = rights["selected_original_software_and_documentation"]
    assert selected_license == "MIT under the pinned root LICENSE"
    assert "Advanced Micro Devices, Inc." in rights["copyright"]
    assert "Models and weights" in rights["excluded_rights"]
