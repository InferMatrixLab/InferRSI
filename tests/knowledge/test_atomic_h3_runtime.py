"""Replay the released H3 checkout, its exported host files and its partial decision card."""

import json
import re
import shutil
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration, filesystem_root
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    RELEASE_COMMIT,
    assert_empty,
    canonical,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, file_bytes, make_author_root
from tests.knowledge.test_atomic_reader import allow

NAME = "audit-h3-runtime-residency"
REF = "checkout:" + NAME
LIBRARY = PurePosixPath("src/inferrsi/knowledge/data/skill_library")
# Frozen from the released v0.3.4 CLI, including the original caller and source paths.
LEGACY_REVISION = "sha256:3e0c1665c7957e8a4fd980146176c746a521ef972b267c420ba4be001d90520d"
RESOURCE_DIGEST = "c6f3ce98e16f8ddf71b991fa7e512edd92a86104fa86924364fda50962180be8"
MANIFEST_DIGEST = "74d4ebcd4dd5d9026fa182cfa0cc4081a55880d1ce29af87e77934ac284db9a4"
CARD_DIGEST = "67039f56e5b6b6a359f7ea2a41ecca03a7cea91497db682d610fec114be5e6d0"
GUIDE_PIN = "sha256:76304b695b24527ddd6de42258bd7decdb95c545d757c704bf1ae96f94e0ad29"


@pytest.fixture(scope="module")
def h3(tmp_path_factory):
    root = filesystem_root(tmp_path_factory.mktemp("h3-runtime"))
    authored = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    composition = ATOMS.parent / "compositions" / (NAME + ".json")
    shutil.copyfile(composition, authored / "compositions" / composition.name)
    paths = json.loads(composition.read_bytes())["directory_resources"]
    checksums = {}
    for logical, node in paths.items():
        descriptor = ATOMS / f"{NAME}.{node}.json"
        shutil.copyfile(descriptor, authored / "atoms" / descriptor.name)
        (content,) = json.loads(descriptor.read_bytes())["content"].values()
        raw = (ATOMS / content["path"]).read_bytes()
        checksums[logical] = digest(raw)
        for dest in (authored / "atoms" / content["path"], release / LIBRARY / logical):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
    assert len(checksums) == 10 and digest(canonical(checksums)) == RESOURCE_DIGEST
    target = root / "installed"
    generation = build_generation(
        authored, target, permits=allow, source_roots={RELEASE_COMMIT: release}
    )
    installed = InstalledGeneration(target, expected=generation)
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    return installed, bundle, target / "skills" / NAME


def test_checkout_preserves_the_target_pin_attribution_and_host_navigation(h3):
    installed, bundle, host = h3
    metadata = dict(bundle.metadata)
    nodes = metadata.pop("composition")["nodes"]
    original, *upstream = metadata["sources"]
    metadata["sources"] = upstream
    assert digest(canonical(metadata)) == MANIFEST_DIGEST
    assert installed.skills[NAME] == REF and not bundle.dependencies
    guide = metadata["entrypoint"]
    assert (original["commit"], original["path"]) == (RELEASE_COMMIT, (LIBRARY / guide).as_posix())
    assert original["sha256"] == digest(bundle.content[guide])
    assert nodes["original"] == {"ref": REF + ".original", "revision": GUIDE_PIN}
    assert installed.catalog[REF + ".original"]["revision"] == GUIDE_PIN
    assert metadata["state"] == "candidate" and metadata["empirical_validation"] == "not_run"
    assert metadata["sources"][0]["license"] == "MIT"
    assert [src["license"] for src in metadata["sources"] if src["type"] == "document"] == [
        "UNKNOWN"
    ] * 2
    assert metadata["required_resources"] == sorted(bundle.content)
    assert digest(canonical(bundle.view()["resources"])) == RESOURCE_DIGEST
    assert sum(map(len, bundle.content.values())) == 82_056
    assert file_bytes(host) == {
        PurePosixPath(path).relative_to(PurePosixPath(guide).parent).as_posix(): raw
        for path, raw in bundle.content.items()
    }
    for key, license_id, holder in (
        ("license", "MIT", b"2026 Salvatore Sanfilippo"),
        ("third-party-notices", "BSD-3-Clause", b"2010, Liu Liu"),
    ):
        pin = nodes[key]
        _, atom = installed.read_resolved(pin["ref"], revision=pin["revision"])
        assert atom.metadata["atom"]["license"] == license_id
        assert holder in atom.content[atom.metadata["entrypoint"]]
    assert (
        json.loads((host / "references/source-identity.json").read_bytes())["native_execution"]
        == "not_run"
    )

    links = []
    for document in host.rglob("*.md"):
        for href in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            uri = urlsplit(href)
            if uri.scheme or uri.netloc:
                continue
            target = (document.parent / uri.path).resolve() if uri.path else document.resolve()
            assert target.is_relative_to(host.resolve()) and target.is_file(), (document, href)
            if uri.fragment:
                assert (
                    uri.fragment == "adaln-and-prepared-state"
                    and b"## AdaLN and prepared state" in target.read_bytes()
                )
            links.append(document)
    assert len(links) == 30 and links.count(host / "SKILL.md") == 7


def test_four_layers_preserve_old_judgment_order_budget_and_permissions(h3):
    installed, bundle, _ = h3
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        result = select(installed, REF, level, 1_000_000)
        size = sum(map(len, result.bodies))
        assert result.receipt["status"] == "delivered" and size == result.receipt["body_bytes"] > 0
        assert select(installed, REF, level, size) == result
        short = select(installed, REF, level, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        assert_empty(
            select(installed, REF, level, size, revision=LEGACY_REVISION), "unavailable_revision"
        )
        for item, body in zip(result.receipt["delivered"], result.bodies, strict=True):
            path = PurePosixPath(item["source_path"]).relative_to(LIBRARY).as_posix()
            start, end = item["source_byte_range"]
            assert item["source_range_verification"] == "verified_at_build"
            assert (
                item["source"]["commit"] == RELEASE_COMMIT
                and bundle.content[path][start:end] == body
            )
            forbidden = item["ref"]
            assert_empty(
                select(installed, REF, level, size, permits=lambda pin, op: pin.ref != forbidden),
                "permission_denied",
            )
        layers[level] = result.bodies

    guide = bundle.metadata["entrypoint"]
    (navigation,) = layers["L0"]
    assert (
        NAME.encode() in navigation
        and bundle.content[guide].startswith(navigation)
        and b"metadata:" not in navigation
    )
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(REF, LEGACY_REVISION, "skill", guide, guide, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert (len(canonical(card)), digest(canonical(card))) == (8_791, CARD_DIGEST)
    assert layers["L2"][0] == decision and b"".join(layers["L2"]) == bundle.content[guide]
    assert layers["L3"] == tuple(
        bundle.content[path] for path in bundle.metadata["required_resources"]
    )
