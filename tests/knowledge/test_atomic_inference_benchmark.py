"""Replay the released benchmark-design entry, its four declared prerequisites and its sources."""

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
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow
from tools.plugin_bundle import _io_path

NAME = "inference-benchmark-design"
REF = "checkout:" + NAME
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("inference-benchmark")
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
    assert len(bundle.content) == 21 and sum(map(len, bundle.content.values())) == 354668
    assert bundle.dependencies == RELEASE["dependencies"] and len(bundle.dependencies) == 4
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert (
        digest(canonical(metadata))
        == "859ef7a9a74c6c4c729e461ff632e01f37620f0dc074b1f16a3e9645b514ee0f"
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
    assert layers["L2"][0] == decision and b"".join(layers["L2"][:2]) == bundle.content[guide]
    case = "casebooks/inference/inference-optimization-casebook/cases/admission-drain-occupancy"
    prerequisites = [
        case + ".md",
        case + ".json",
        "systems/engines/deepinfer/budget-speculative-verification/SKILL.md",
        "systems/engines/vllm-rlt/audit-recurrent-kv-finalization/SKILL.md",
    ]
    assert set(prerequisites) == bundle.dependencies.keys()
    assert layers["L2"][2:] == tuple(bundle.content[path] for path in prerequisites)
    assert layers["L3"] == tuple(bundle.content[path] for path in sorted(bundle.content))
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(REF, RELEASE["revision"], "skill", guide, guide, fields).project()["card"]
    assert card["status"] == "partial" and card["missing_fields"] == ["validation"]
    assert len(canonical(card)) == RELEASE["card_bytes"] == 46351
    assert digest(canonical(card)) == RELEASE["card_sha256"]


def test_upstream_credits_precision_and_inspection_limits(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    credits = bundle.metadata["attribution"]
    inventory = bundle.metadata["sources"][1:]
    assert len(credits) == len(inventory) == 30
    annotated = 0
    for declared, source in zip(credits, inventory, strict=True):
        if source == declared:
            continue
        assert "revision_precision" not in declared
        assert source == {**declared, "revision_precision": "full"}
        annotated += 1
    assert annotated == 16
    base = PurePosixPath(RELEASE["entrypoint"]).parent
    records = {
        PurePosixPath(path).name: json.loads(body)
        for path, body in bundle.content.items()
        if path.startswith((base / "references").as_posix() + "/") and path.endswith(".json")
    }
    assert len(records) == 6
    assert records["faster-cosyvoice-source.json"]["rights"]["repository_license"] == "UNKNOWN"
    assert records["ninfer-source.json"]["evidence_boundary"]["native_execution"] == "not_run"
    assert records["autotunebench-source.json"]["empirical_state"]["performance"] == "not_run"
    assert records["justgoal-source.json"]["empirical_state"]["paper_outcomes"] == "author_reported"
    embodied_rights = records["embodied-cpp-source.json"]["rights"]
    assert "Copyright 2026 SEU-PAISys" in embodied_rights["attribution"]
    assert records["xeforge-source.json"]["verification_boundaries"]["source_tests"] == "not_run"

    spec = json.loads((ATOMS.parent / "compositions" / (NAME + ".json")).read_bytes())
    for path, label in spec["directory_resources"].items():
        if path in bundle.dependencies:
            continue
        node = bundle.metadata["composition"]["nodes"][label]
        _, atom = installed.read_resolved(node["ref"], revision=node["revision"])
        relative = PurePosixPath(path).relative_to(base).as_posix()
        old_credits = [item for item in credits if item["readset"] == relative]
        assert all(item in atom.metadata["attribution"] for item in old_credits)
        assert atom.metadata["atom"]["source_span"]["sha256"] == RELEASE["required_resources"][path]
    links = RELEASE["relative_guide_links"].values()
    outside = [link for link in links if not link["in_directory"]]
    assert len(outside) == 3
    assert sum(link["path"] in bundle.content for link in outside) == 1
    assert NAME not in installed.skills
