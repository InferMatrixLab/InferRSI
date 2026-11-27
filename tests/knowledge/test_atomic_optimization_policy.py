"""Verify the published optimization policy, including the order and grants of all 16 references."""

import json
import posixpath
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
from tests.knowledge.test_atomic_dense_evidence import LIBRARY, stage_atom
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow
from tools.plugin_bundle import _io_path

NAME = "optimization-search-policy"
REF = "checkout:" + NAME
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = _io_path(tmp_path_factory.mktemp("policy"))
    author = make_author_root(root)
    release = root / "pinned"
    shutil.copytree(RELEASE_ROOT, release)
    source = ATOMS.parent / "compositions" / (NAME + ".json")
    shutil.copyfile(source, author / "compositions" / source.name)
    spec = json.loads(source.read_bytes())
    nodes = spec["metadata"]["composition"]["nodes"]
    hashes = {
        path: stage_atom(author, release, path, nodes[label])
        for path, label in spec["directory_resources"].items()
    }
    assert hashes == RELEASE["required_resources"]
    target = root / "installed"
    generation = build_generation(
        author, target, permits=allow, source_roots={RELEASE_COMMIT: release}
    )
    return InstalledGeneration(target, expected=generation)


def test_reads_full_policy_in_declared_order_or_refuses_the_group(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    assert bundle.view()["resources"] == RELEASE["required_resources"]
    assert len(bundle.content) == 25 and sum(map(len, bundle.content.values())) == 204266
    assert bundle.dependencies == RELEASE["dependencies"]
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        delivery = select(installed, REF, level, 1_000_000)
        size = sum(map(len, delivery.bodies))
        assert delivery.receipt["status"] == "delivered" and delivery.receipt["body_bytes"] == size
        assert select(installed, REF, level, size) == delivery
        short = select(installed, REF, level, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        assert_empty(
            select(installed, REF, level, size, revision=RELEASE["revision"]),
            "unavailable_revision",
        )
        for denied in {REF, *(row["ref"] for row in delivery.receipt["delivered"])}:
            assert_empty(
                select(installed, REF, level, size, permits=lambda pin, op: pin.ref != denied),
                "permission_denied",
            )
        for body, item in zip(delivery.bodies, delivery.receipt["delivered"], strict=True):
            start, end = item["source_byte_range"]
            path = item["source_path"].removeprefix(LIBRARY)
            assert body == bundle.content[path][start:end]
            assert item["source"]["commit"] == RELEASE_COMMIT
            assert item["source_range_verification"] == "verified_at_build"
            assert item["source_sha256"] == digest(body)
        layers[level] = delivery

    guide = RELEASE["entrypoint"]
    (decision,) = layers["L1"].bodies
    _, fields = _skill_search_source(decision.decode())
    declared = [
        posixpath.normpath(posixpath.join(posixpath.dirname(guide), path))
        for path in fields["references"]
    ]
    assert len(declared) == 16 and set(declared) == bundle.dependencies.keys()
    assert bundle.content[guide].startswith(layers["L0"].bodies[0])
    assert (
        layers["L2"].bodies[0] == decision
        and b"".join(layers["L2"].bodies[:2]) == bundle.content[guide]
    )
    assert layers["L2"].bodies[2:] == tuple(bundle.content[path] for path in declared)
    assert [item["source_path"] for item in layers["L2"].receipt["delivered"][2:]] == [
        LIBRARY + path for path in declared
    ]
    assert layers["L3"].bodies == tuple(bundle.content[path] for path in sorted(bundle.content))
    card = DecisionSource(REF, RELEASE["revision"], "skill", guide, guide, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert len(canonical(card)) == RELEASE["card_bytes"] == 9371
    assert digest(canonical(card)) == RELEASE["card_sha256"]


def test_paper_credits_and_legacy_source_limits(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert (
        digest(canonical(metadata))
        == "9527b88ae221cedafd2a87ceed7354492b16b9f2f3c2dff23d967a07e1af6be6"
    )
    paper, historical = metadata["attribution"]
    assert metadata["sources"] == [paper, historical] and historical["type"] == "unknown"
    base = posixpath.dirname(RELEASE["entrypoint"])
    record = json.loads(bundle.content[posixpath.join(base, paper["readset"])])
    source = record["source"]
    assert source["id"] == paper["id"] == "usenix:osdi24:zhong-yinmin"
    assert source["url"] == paper["url"] and source["publisher"] == "USENIX Association"
    assert (
        len(source["authors"]) == 8
        and source["authors"][0] == "Yinmin Zhong"
        and source["authors"][-1] == "Hao Zhang"
    )
    for right in (
        "paper_specific_redistribution_license",
        "paper_specific_derivative_permission",
        "author_permission",
    ):
        assert record["rights"][right] == "UNKNOWN"
    assert "Raw PDF" in record["rights"]["excluded_assets"]
    assert not any(path.endswith(".pdf") for path in bundle.content)
    assert (
        metadata["empirical_validation"]
        == record["verification"]["local_distserve_runtime"]
        == "not_run"
    )
    assert NAME not in installed.skills
