"""Reopen the released performance-ceiling guide and its attachments through the Reader."""

import json
import runpy
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
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow
from tools.plugin_bundle import _io_path

NAME = "performance-ceiling-analysis"
REF = "checkout:" + NAME
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("ceiling")
    author = make_author_root(root)
    release = _io_path(root / "release")
    shutil.copytree(RELEASE_ROOT, release)
    spec_file = ATOMS.parent / "compositions" / (NAME + ".json")
    shutil.copyfile(spec_file, author / "compositions" / spec_file.name)
    spec = json.loads(spec_file.read_bytes())
    nodes = spec["metadata"]["composition"]["nodes"]
    assert spec["directory_resources"].keys() == RELEASE["required_resources"].keys()
    for logical, label in spec["directory_resources"].items():
        atom = ATOMS / (nodes[label]["ref"].removeprefix("checkout:") + ".json")
        shutil.copyfile(atom, author / "atoms" / atom.name)
        (resource,) = json.loads(atom.read_bytes())["content"].values()
        raw = (ATOMS / resource["path"]).read_bytes()
        assert digest(raw) == RELEASE["required_resources"][logical]
        for dest in (author / "atoms" / resource["path"], release / LIBRARY / logical):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
    target = root / "installed"
    generation = build_generation(
        author, target, permits=allow, source_roots={RELEASE_COMMIT: release}
    )
    return InstalledGeneration(target, expected=generation)


def test_original_paths_permissions_and_released_decision(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    assert bundle.view()["resources"] == RELEASE["required_resources"]
    assert len(bundle.content) == 26 and sum(map(len, bundle.content.values())) == 255282
    assert bundle.dependencies == RELEASE["dependencies"] == {}
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert (
        digest(canonical(metadata))
        == "b2624f69eff89125265cb70470d115ffe2c5e1e10c74a97da98e851ab38e4c23"
    )
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        result = select(installed, REF, level, 1_000_000)
        size = sum(map(len, result.bodies))
        assert result.receipt["status"] == "delivered" and result.receipt["body_bytes"] == size
        assert select(installed, REF, level, size) == result
        short = select(installed, REF, level, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        assert_empty(
            select(installed, REF, level, size, revision=RELEASE["revision"]),
            "unavailable_revision",
        )
        for denied in {REF, *(row["ref"] for row in result.receipt["delivered"])}:
            incomplete = select(
                installed, REF, level, size, permits=lambda pin, op: pin.ref != denied
            )
            assert_empty(incomplete, "permission_denied")
        for body, row in zip(result.bodies, result.receipt["delivered"], strict=True):
            lo, hi = row["source_byte_range"]
            path = row["source_path"].removeprefix(LIBRARY)
            assert body == bundle.content[path][lo:hi]
            assert row["source"]["commit"] == RELEASE_COMMIT
            assert row["source_range_verification"] == "verified_at_build"
            assert row["source_sha256"] == digest(body)
        layers[level] = result.bodies
    guide = RELEASE["entrypoint"]
    (decision,) = layers["L1"]
    assert bundle.content[guide].startswith(layers["L0"][0])
    assert layers["L2"][0] == decision and b"".join(layers["L2"]) == bundle.content[guide]
    assert layers["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(REF, RELEASE["revision"], "skill", guide, guide, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert len(canonical(card)) == RELEASE["card_bytes"] == 9794
    assert digest(canonical(card)) == RELEASE["card_sha256"]


def test_source_scope_and_navigation(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    parents = bundle.metadata["sources"][1:]
    assert len(parents) == len(bundle.metadata["attribution"]) == 8
    assert [p["revision_precision"] for p in parents[:3]] == ["prefix"] * 3
    assert [p["license"] for p in parents[3:]] == [
        "UNKNOWN",
        "CC-BY-4.0",
        "MIT",
        "UNKNOWN",
        "Apache-2.0 with component-specific notices",
    ]
    nodes = bundle.metadata["composition"]["nodes"]
    for label, readset in [
        ("mooncake-prefix-reuse-feasibility", "mooncake-prefix-reuse-feasibility.md"),
        ("flexgen-offload-feasibility", "flexgen-offload-feasibility.md"),
        ("huggingarch-checkpoint-anchor", "huggingarch-checkpoint-anchor.md"),
        ("huggingarch-source-identity", "huggingarch-checkpoint-anchor.md"),
        ("xllm-pd-handoff", "xllm-pd-handoff.md"),
    ]:
        node = nodes[label]
        _, material = installed.read_resolved(node["ref"], revision=node["revision"])
        target = "references/" + readset
        assert material.metadata["sources"][1:] == [
            p for p in parents if p.get("readset") == target
        ]
        assert material.metadata["attribution"] == [
            p for p in bundle.metadata["attribution"] if p.get("readset") == target
        ]
    links = RELEASE["relative_guide_links"].values()
    outside = {link["path"] for link in links if not link["in_directory"]}
    assert len(outside) == 3 and outside.isdisjoint(bundle.content)
    assert NAME not in installed.skills
    assert nodes["acceptance-criteria"]["ref"] == REF + ".acceptance-criteria"


def test_released_roofline_calculator_and_example(installed, tmp_path):
    delivered = select(installed, REF, "L3", 1_000_000)
    contents = {
        PurePosixPath(item["source_path"]).name: body
        for item, body in zip(delivered.receipt["delivered"], delivered.bodies, strict=True)
        if item["source_path"].endswith(
            ("/scripts/roofline.py", "/references/roofline-example.json")
        )
    }
    script = tmp_path / "roofline.py"
    script.write_bytes(contents["roofline.py"])
    analyze = runpy.run_path(str(script))["analyze"]
    example = json.loads(contents["roofline-example.json"])
    result = analyze(**example)
    assert result["analysis_status"] == "COMPUTED" and result["evidence_basis"] == "synthetic"
    assert (
        result["analytical_limiting_factor"] == "memory"
        and result["conditional_runtime_floor_s"] == 10
    )
    del example["hardware"]["bandwidth"]["value"]
    incomplete = analyze(**example)
    assert incomplete["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert incomplete["conditional_runtime_floor_s"] is None
    example["hardware"]["bandwidth"]["value"] = -1
    with pytest.raises(ValueError):
        analyze(**example)
