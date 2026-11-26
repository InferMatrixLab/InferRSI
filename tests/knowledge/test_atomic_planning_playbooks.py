"""Compare six installed planning Skills with their frozen v0.3.4 public reads."""

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

RELEASED = json.loads((FIXTURES / "planning-playbooks-v0.3.4.json").read_bytes())
LIBRARY = "src/inferrsi/knowledge/data/skill_library"


@pytest.fixture(scope="module")
def installed_plans(tmp_path_factory):
    root = tmp_path_factory.mktemp("planning-playbooks")
    authored = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    for name, expected in RELEASED.items():
        composition = ATOMS.parent / "compositions" / (name + ".json")
        shutil.copyfile(composition, authored / "compositions" / composition.name)
        released = {}
        for relative in ["SKILL.md", *expected["attachments"]]:
            guide = relative == "SKILL.md"
            part = "original" if guide else PurePosixPath(relative).stem
            descriptor = ATOMS / f"{name}.{part}.json"
            shutil.copyfile(descriptor, authored / "atoms" / descriptor.name)
            body = (PurePosixPath("playbooks", name + ".md") if guide
                    else PurePosixPath("playbooks", name, relative))
            raw = (ATOMS / body).read_bytes()
            logical = PurePosixPath("playbooks/planning", name, relative)
            released[logical.as_posix()] = digest(raw)
            for path in (authored / "atoms" / body, release / LIBRARY / logical):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        assert digest(canonical(released)) == expected["resource_set_sha256"]
    target = root / "installed"
    generation = build_generation(authored, target, permits=allow,
                                  source_roots={RELEASE_COMMIT: release})
    return InstalledGeneration(target, expected=generation), target


@pytest.mark.parametrize("name", sorted(RELEASED))
def test_installed_planning_host_preserves_resources_and_provenance(installed_plans, name):
    installed, target = installed_plans
    ref = "checkout:" + name
    expected = RELEASED[name]
    assert installed.skills[name] == ref
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    metadata = dict(bundle.metadata)
    declaration = metadata.pop("composition")
    first, *old_sources = metadata["sources"]
    metadata["sources"] = old_sources
    assert digest(canonical(metadata)) == expected["manifest_sha256"]
    assert first["commit"] == RELEASE_COMMIT and not bundle.dependencies
    guide = metadata["entrypoint"]
    root = PurePosixPath(guide).parent
    assert first["path"] == (PurePosixPath(LIBRARY) / guide).as_posix()
    assert first["sha256"] == digest(bundle.content[guide])
    assert metadata["empirical_validation"] == "not_run"
    assert sorted(bundle.content) == metadata["required_resources"]
    assert digest(canonical(bundle.view()["resources"])) == expected["resource_set_sha256"]
    assert file_bytes(target / "skills" / name) == {
        PurePosixPath(path).relative_to(root).as_posix(): raw
        for path, raw in bundle.content.items()
    }
    for path, raw in bundle.content.items():
        part = "original" if path == guide else PurePosixPath(path).stem
        pin = declaration["nodes"][part]
        _, atom = installed.read_resolved(pin["ref"], revision=pin["revision"])
        source, *upstream = atom.metadata["sources"]
        assert upstream == old_sources
        assert source["path"] == (PurePosixPath(LIBRARY) / path).as_posix()
        assert (source["commit"], source["sha256"]) == (RELEASE_COMMIT, digest(raw))
        for key in ("origin", "applicability", "state", "limitations", "attribution",
                    "empirical_validation"):
            assert atom.metadata[key] == metadata[key]


@pytest.mark.parametrize("name", sorted(RELEASED))
def test_planning_layers_preserve_decisions_and_require_complete_delivery(installed_plans, name):
    installed, _ = installed_plans
    ref = "checkout:" + name
    expected = RELEASED[name]
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    guide = bundle.metadata["entrypoint"]
    result = {}
    for layer in ("L0", "L1", "L2", "L3"):
        delivery = select(installed, ref, layer, 1_000_000)
        assert delivery.receipt["status"] == "delivered"
        size = sum(map(len, delivery.bodies))
        assert size == delivery.receipt["body_bytes"] > 0
        assert select(installed, ref, layer, size) == delivery
        short = select(installed, ref, layer, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            source_path = PurePosixPath(item["source_path"]).relative_to(LIBRARY).as_posix()
            start, end = item["source_byte_range"]
            assert item["source_range_verification"] == "verified_at_build"
            assert item["source"]["commit"] == RELEASE_COMMIT
            assert bundle.content[source_path][start:end] == body
            forbidden = item["ref"]
            assert_empty(select(installed, ref, layer, size,
                                permits=lambda pin, op: pin.ref != forbidden), "permission_denied")
        assert_empty(select(installed, ref, layer, size, revision=expected["revision"]),
                     "unavailable_revision")
        result[layer] = delivery.bodies

    (navigation,) = result["L0"]
    assert name.encode() in navigation and b"description:" in navigation
    assert b"metadata:" not in navigation and bundle.content[guide].startswith(navigation)
    (decision,) = result["L1"]
    _, fields = _skill_search_source(decision.decode())
    source = DecisionSource(ref, expected["revision"], "skill", guide, guide, fields)
    card = source.project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert len(canonical(card)) == expected["card_bytes"]
    assert digest(canonical(card)) == expected["card_sha256"]
    assert result["L2"][0] == decision and b"".join(result["L2"]) == bundle.content[guide]
    assert result["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))
