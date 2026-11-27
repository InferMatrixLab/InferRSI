"""Reopen the released kernel guide, including the Case files readable under its own identity."""

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

NAME = "kernel-writing-guide"
REF = "checkout:" + NAME
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("kernel-guide")
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
    assert len(bundle.content) == 17 and sum(map(len, bundle.content.values())) == 207707
    assert bundle.dependencies == RELEASE["dependencies"] == {}
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert (
        digest(canonical(metadata))
        == "5c4b64f60da59273392e9f3c8a1392f2e37ac64fb2c5bc5fc0d4180c8cde44f2"
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
    assert len(canonical(card)) == RELEASE["card_bytes"] == 23742
    assert digest(canonical(card)) == RELEASE["card_sha256"]


def test_kernel_guide_reuses_five_case_originals_and_preserves_source_rights(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    directory = PurePosixPath(RELEASE["entrypoint"]).parent
    manifest = json.loads((ATOMS.parent / "compositions" / (NAME + ".json")).read_bytes())
    nodes = bundle.metadata["composition"]["nodes"]
    shared = {}
    for path, label in manifest["directory_resources"].items():
        pin = nodes[label]
        if pin["ref"].startswith("checkout:case."):
            shared[PurePosixPath(path).name] = pin["ref"].removeprefix("checkout:case.")
            _, atom = installed.read_resolved(pin["ref"], revision=pin["revision"])
            assert list(atom.content.values()) == [bundle.content[path]]
            assert atom.metadata["sources"][0]["path"] == LIBRARY + path
    assert shared == {
        "sglang-gdn-source-contract.json": "sglang-gdn-source-contract.original",
        "sglang-gdn-source-contract.md": "sglang-gdn-source-contract.guide",
        "vllm-gdn-causal-conv-contract.md": "vllm-gdn-source-contract.causal-conv",
        "vllm-gdn-source-contract.json": "vllm-gdn-source-contract.original",
        "vllm-gdn-source-contract.md": "vllm-gdn-source-contract.guide",
    }
    credits = bundle.metadata["attribution"]
    assert [credit.get("license") for credit in credits] == [
        "BSD-3-Clause", None, "Apache-2.0", "Apache-2.0", "Apache-2.0", "UNKNOWN",
    ]
    assert bundle.metadata["sources"][1:] == [
        {**credit, "revision_precision": "full"} for credit in credits
    ]
    references = directory / "references"
    sources = json.loads(bundle.content[(references / "sglang-gdn-source-files.json").as_posix()])
    notice = bundle.content[(references / "licenses/sglang-LICENSE.md").as_posix()]
    (listed,) = [row for row in sources["files"] if row["path"] == "LICENSE"]
    assert len(notice) == listed["bytes"] == 11346 and digest(notice) == listed["sha256"]
    assert sources["commit"] == credits[4]["commit"] and sources["execution"] == "not_run"
    pplx = json.loads(bundle.content[(references / "pplx-gdn-caller-context.json").as_posix()])
    assert pplx["commit"] == credits[5]["commit"] and pplx["license"] == "UNKNOWN"
    assert pplx["relationship"] == "bounded_caller_context"
    assert pplx["empirical_validation"] == "not_run"
    akg = bundle.content[(references / "akg-affine-tail-guards.md").as_posix()]
    assert b"5aa15f3fe4d856eb60cd3b27447e04f5f1fb4dff" in akg
    assert b"Copyright 2019" in akg and b"Huawei Technologies" in akg

    links = RELEASE["relative_guide_links"].values()
    inside = [link["path"] for link in links if link["in_directory"]]
    outside = [link["path"] for link in links if not link["in_directory"]]
    assert len(inside) == 10 and set(inside).issubset(bundle.content)
    assert len(set(outside)) == 3 and set(outside).isdisjoint(bundle.content)
    assert NAME not in installed.skills
