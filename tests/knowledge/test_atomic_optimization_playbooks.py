"""Replay the video diffusion and weight loading Playbooks from the v0.3.4 release."""

import json
import shutil
import subprocess
import sys
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
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

VIDEO = "checkout:video-diffusion-optimization"
WEIGHTS = "checkout:weight-loading-optimization"
METADATA_SHA256 = {
    VIDEO: "a6414ae5a6c3e0d87f88ad3d81198b3cf0f41bea156430daee9026b18f7ad5eb",
    WEIGHTS: "605fc2ccbbf5124b570d323e97dac5f7e0b89f0827cffc139cbb5d78acd6b3bd",
}
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"]
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("optimization")
    author = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    for ref in (VIDEO, WEIGHTS):
        composition = ATOMS.parent / "compositions" / (ref.removeprefix("checkout:") + ".json")
        shutil.copyfile(composition, author / "compositions" / composition.name)
        spec = json.loads(composition.read_bytes())
        bindings = spec["directory_resources"]
        assert bindings.keys() == RELEASE[ref]["required_resources"].keys()
        nodes = spec["metadata"]["composition"]["nodes"]
        for logical, node in bindings.items():
            descriptor = ATOMS / (nodes[node]["ref"].removeprefix("checkout:") + ".json")
            shutil.copyfile(descriptor, author / "atoms" / descriptor.name)
            (resource,) = json.loads(descriptor.read_bytes())["content"].values()
            raw = (ATOMS / resource["path"]).read_bytes()
            assert digest(raw) == RELEASE[ref]["required_resources"][logical]
            for dest in (author / "atoms" / resource["path"], release / (LIBRARY + logical)):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
    target = root / "installed"
    generation = build_generation(
        author, target, permits=allow, source_roots={RELEASE_COMMIT: release}
    )
    return InstalledGeneration(target, expected=generation)


@pytest.mark.parametrize("ref", [VIDEO, WEIGHTS])
def test_released_directory_and_all_four_layers(installed, ref):
    old = RELEASE[ref]
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    assert bundle.dependencies == old["dependencies"] == {}
    assert bundle.view()["resources"] == old["required_resources"]
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert digest(canonical(metadata)) == METADATA_SHA256[ref]
    entry = old["entrypoint"]
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        result = select(installed, ref, level, 1_000_000)
        assert result.receipt["status"] == "delivered"
        size = sum(map(len, result.bodies))
        assert result.receipt["body_bytes"] == size
        assert select(installed, ref, level, size) == result
        short = select(installed, ref, level, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        assert_empty(
            select(installed, ref, level, size, revision=old["revision"]), "unavailable_revision"
        )
        for item, body in zip(result.receipt["delivered"], result.bodies, strict=True):
            lo, hi = item["source_byte_range"]
            path = item["source_path"].removeprefix(LIBRARY)
            assert bundle.content[path][lo:hi] == body
            assert (
                item["source"]["commit"] == RELEASE_COMMIT and digest(body) == item["source_sha256"]
            )
            assert item["source_range_verification"] == "verified_at_build"
        for denied in {ref, *(item["ref"] for item in result.receipt["delivered"])}:
            failure = select(installed, ref, level, size, permits=lambda pin, op: pin.ref != denied)
            assert_empty(failure, "permission_denied")
        layers[level] = result.bodies
    assert bundle.content[entry].startswith(layers["L0"][0])
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(ref, old["revision"], "skill", entry, entry, fields).project()["card"]
    assert card["status"] == old["status"] == "partial"
    assert card["missing_fields"] == old["missing_fields"]
    assert (len(canonical(card)), digest(canonical(card))) == (
        old["card_bytes"],
        old["card_sha256"],
    )
    assert layers["L2"][0] == decision and b"".join(layers["L2"]) == bundle.content[entry]
    assert layers["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))


@pytest.mark.parametrize(("ref", "external_links"), [(VIDEO, 2), (WEIGHTS, 3)])
def test_navigation_does_not_grant_target_content(installed, ref, external_links):
    old = RELEASE[ref]
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    links = tuple(old["relative_guide_links"].values())
    assert sum(not link["in_directory"] for link in links) == external_links
    for link in links:
        assert (link["path"] in bundle.content) == link["in_directory"]
    assert ref not in installed.skills.values()


def test_weight_reference_credits_stay_with_their_source(installed):
    _, guide = installed.read_resolved(WEIGHTS, revision=installed.catalog[WEIGHTS]["revision"])
    credits = {row["readset"]: row for row in guide.metadata["attribution"]}
    upstreams = {row["readset"]: row for row in guide.metadata["sources"][1:]}
    assert len(credits) == len(upstreams) == 4
    nodes = guide.metadata["composition"]["nodes"]
    for path in sorted(guide.content.keys() - {guide.metadata["entrypoint"]}):
        leaf = PurePosixPath(path)
        node = nodes[leaf.stem]
        _, atom = installed.read_resolved(node["ref"], revision=node["revision"])
        readset = "references/" + leaf.name
        if leaf.name == "deepseek-expert-cache-source.json":
            readset = "references/deepseek-expert-cache-oracles.md"
        assert atom.metadata["attribution"] == [credits[readset]]
        assert atom.metadata["sources"][1:] == [upstreams[readset]]
        assert credits[readset]["commit"] == upstreams[readset]["commit"]
        denied = select(
            installed,
            WEIGHTS,
            "L3",
            1_000_000,
            operations={"redistribute"},
            permits=lambda pin, op: (pin.ref, op) != (node["ref"], "redistribute"),
        )
        assert_empty(denied, "permission_denied")


def test_video_evaluator_accepts_the_delivered_template_and_reports_invalid_json(
    installed, tmp_path
):
    delivery = select(installed, VIDEO, "L3", 1_000_000)
    bodies = {
        PurePosixPath(row["source_path"]).name: body
        for row, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True)
    }
    script = tmp_path / "evaluate_target.py"
    script.write_bytes(bodies["evaluate_target.py"])
    for payload, code, verdict in (
        (bodies["campaign.template.json"], 0, "PASS"),
        (b"{", 2, "INVALID"),
    ):
        call = subprocess.run(
            [sys.executable, "-I", str(script), "-"], input=payload, capture_output=True
        )
        assert call.returncode == code and call.stderr == b""
        assert json.loads(call.stdout)["verdict"] == verdict
