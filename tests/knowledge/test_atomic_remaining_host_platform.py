"""Exercise the remaining Host Platform checkouts against their recorded v0.3.4 contracts."""

import json
import shutil

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import (
    InstalledGeneration,
    directory_skill_path,
    filesystem_root,
)
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    FIXTURES,
    assert_empty,
    canonical,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

RELEASE = json.loads((FIXTURES / "remaining-host-platform-v0.3.4.json").read_bytes())
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"


@pytest.fixture(scope="module")
def installed_skills(tmp_path_factory):
    root = tmp_path_factory.mktemp("remaining-host-platform")
    author = make_author_root(root)
    pinned = root / "release"
    shutil.copytree(RELEASE_ROOT, pinned)
    for ref, old in RELEASE["refs"].items():
        name = ref.removeprefix("checkout:") + ".json"
        spec = ATOMS.parent / "compositions" / name
        shutil.copyfile(spec, author / "compositions" / name)
        desc = json.loads(spec.read_bytes())
        nodes = desc["metadata"]["composition"]["nodes"]
        assert desc["directory_resources"].keys() == old["resources"].keys()
        for path, node in desc["directory_resources"].items():
            atom_name = nodes[node]["ref"].removeprefix("checkout:") + ".json"
            descriptor = ATOMS / atom_name
            shutil.copyfile(descriptor, author / "atoms" / atom_name)
            (resource,) = json.loads(descriptor.read_bytes())["content"].values()
            raw = (ATOMS / resource["path"]).read_bytes()
            assert digest(raw) == old["resources"][path]
            for dest in (pinned / (LIBRARY + path), author / "atoms" / resource["path"]):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
    target = root / "installed"
    seal = build_generation(
        author, target, permits=allow, source_roots={RELEASE["source_commit"]: pinned},
    )
    return filesystem_root(target), InstalledGeneration(target, expected=seal)


@pytest.mark.parametrize("ref", sorted(RELEASE["refs"]))
def test_released_checkout_layers_and_receipts(installed_skills, ref):
    _, installed = installed_skills
    old = RELEASE["refs"][ref]
    revision = installed.catalog[ref]["revision"]
    _, bundle = installed.read_resolved(ref, revision=revision)
    assert bundle.view()["resources"] == old["resources"]
    assert bundle.dependencies == old["dependencies"]
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert digest(canonical(metadata)) == old["metadata_sha256"]

    files = bundle.content
    guide = old["entrypoint"]
    layers = {}
    for layer in ("L0", "L1", "L2", "L3"):
        result = select(installed, ref, layer, sum(map(len, files.values())))
        assert result.receipt["status"] == "delivered"
        size = sum(map(len, result.bodies))
        assert result.receipt["body_bytes"] == size
        assert select(installed, ref, layer, size) == result
        short = select(installed, ref, layer, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        assert_empty(
            select(installed, ref, layer, size, revision=old["revision"]), "unavailable_revision",
        )
        delivered = result.receipt["delivered"]
        for item, body in zip(delivered, result.bodies, strict=True):
            start, end = item["source_byte_range"]
            path = item["source_path"].removeprefix(LIBRARY)
            assert item["source_path"] == LIBRARY + path
            assert item["source"]["commit"] == RELEASE["source_commit"]
            assert item["source_range_verification"] == "verified_at_build"
            assert body == files[path][start:end]
            assert digest(body) == item["source_sha256"]
        for denied in (ref, *(item["ref"] for item in delivered)):
            refusal = select(installed, ref, layer, size, permits=lambda pin, op: pin.ref != denied)
            assert_empty(refusal, "permission_denied")
        layers[layer] = result.bodies

    (navigation,) = layers["L0"]
    assert files[guide].startswith(navigation) and b"description:" in navigation
    assert b"metadata:" not in navigation
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(ref, old["revision"], "skill", guide, guide, fields).project()["card"]
    assert card["status"] == "partial"
    assert card["missing_fields"] == old["missing_fields"]
    assert digest(canonical(card)) == old["card_sha256"]
    assert len(canonical(card)) == old["card_bytes"]
    assert layers["L2"][0] == decision
    assert b"".join(layers["L2"][:2]) == files[guide]
    assert layers["L2"][2:] == tuple(files[path] for path in old["l2_resources"])
    assert layers["L3"] == tuple(files[path] for path in bundle.metadata["required_resources"])


@pytest.mark.parametrize("ref", sorted(RELEASE["refs"]))
def test_host_export_keeps_relative_navigation_and_licenses(installed_skills, ref):
    target, installed = installed_skills
    old = RELEASE["refs"][ref]
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    for path, sha in old["resources"].items():
        exported = target / directory_skill_path(bundle.metadata, path)
        assert digest(exported.read_bytes()) == sha
    for path, links in old["links"].items():
        source = target / directory_skill_path(bundle.metadata, path)
        for href, link in links.items():
            assert href.encode() in source.read_bytes()
            if not link["in_scope"]:
                assert link["resolved_path"] not in bundle.content
                assert link["resolved_path"] not in bundle.dependencies
                continue
            resolved = source.parent / href.partition("#")[0]
            target_path = target / directory_skill_path(bundle.metadata, link["resolved_path"])
            assert resolved == target_path
            assert digest(resolved.read_bytes()) == old["resources"][link["resolved_path"]]

    name = ref.removeprefix("checkout:") + ".json"
    spec = json.loads((ATOMS.parent / "compositions" / name).read_bytes())
    nodes = bundle.metadata["composition"]["nodes"]
    for path, expected in old["scoped_files"].items():
        node = nodes[spec["directory_resources"][path]]
        _, atom = installed.read_resolved(node["ref"], revision=node["revision"])
        (credit,) = atom.metadata["attribution"]
        for source in (credit, atom.metadata["sources"][1]):
            assert all(source[field] == expected[field] for field in expected)
