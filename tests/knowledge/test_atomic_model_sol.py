"""Reopen the released model-level speed-of-light guide and its attachments through the Reader."""

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
from tools.plugin_bundle import _io_path

NAME = "model-sol-analysis"
REF = "checkout:" + NAME
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RELEASE = json.loads((FIXTURES / "playbook-domain-v0.3.4.json").read_bytes())["refs"][REF]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("model-sol")
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
    assert len(bundle.content) == 10 and sum(map(len, bundle.content.values())) == 130869
    assert bundle.dependencies == RELEASE["dependencies"] == {}
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert (
        digest(canonical(metadata))
        == "ae20a01935831d1ceb202eb125b6fb80f52e222537aa1603fc7cf34c32769e06"
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
    assert len(canonical(card)) == RELEASE["card_bytes"] == 11661
    assert digest(canonical(card)) == RELEASE["card_sha256"]


def test_huggingarch_credit_scope_and_navigation(installed):
    _, bundle = installed.read_resolved(REF, revision=installed.catalog[REF]["revision"])
    (credit,) = bundle.metadata["attribution"]
    assert bundle.metadata["sources"][1:] == [credit]
    assert credit["url"] == "https://github.com/shenh10/HuggingArch"
    assert credit["commit"] == "e69d20a028e5b17524aa48b53bddf8b9aad5d15b"
    assert credit["license"] == "MIT" and len(set(credit["paths"])) == 36
    assert credit["readset"] == "references/huggingarch-model-sol.md"
    assert credit["identity"] == "references/huggingarch-source-identity.json"
    base = PurePosixPath(RELEASE["entrypoint"]).parent
    identity = json.loads(bundle.content[(base / credit["identity"]).as_posix()])
    verified = identity["verification"]
    assert verified["locally_verified"] is False
    assert verified["native_execution"] == verified["empirical_validation"] == "not_run"
    nodes = bundle.metadata["composition"]["nodes"]
    manifest = json.loads((ATOMS.parent / "compositions" / (NAME + ".json")).read_bytes())
    for path, label in manifest["directory_resources"].items():
        node = nodes[label]
        _, atom = installed.read_resolved(node["ref"], revision=node["revision"])
        rel = PurePosixPath(path).relative_to(base).as_posix()
        credits = [credit] if rel in {"SKILL.md", credit["identity"], credit["readset"]} else []
        assert atom.metadata["attribution"] == credits
        assert atom.metadata["sources"][1:] == credits

    links = RELEASE["relative_guide_links"].values()
    outside = [link["path"] for link in links if not link["in_directory"]]
    assert len(outside) == 5 and len(set(outside)) == 4
    assert set(outside).isdisjoint(bundle.content)
    inside = [link["path"] for link in links if link["in_directory"]]
    assert len(inside) == 6 and set(inside).issubset(bundle.content)
    assert NAME not in installed.skills


def test_released_qwen_calculator_from_installed_l3(installed, tmp_path):
    result = select(installed, REF, "L3", 1_000_000)
    prefix = PurePosixPath(LIBRARY, RELEASE["entrypoint"]).parent
    for row, body in zip(result.receipt["delivered"], result.bodies, strict=True):
        dest = tmp_path / PurePosixPath(row["source_path"]).relative_to(prefix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
    command = [sys.executable, "-B", str(tmp_path / "scripts" / "qwen38_h200_tp4.py")]
    for arguments, tokens, steps, times in (
        ([], (8192, 256), 255, [0.2785117744889662, 0.2785117744889662]),
        (["--prompt-tokens", "1", "--output-tokens", "1"], (1, 1), 0, [0.0009398058666666666]),
    ):
        completed = subprocess.run(
            command + arguments, cwd=tmp_path, capture_output=True, check=True
        )
        report = json.loads(completed.stdout)
        assert completed.stderr == b""
        assert (report["prompt_tokens"], report["output_tokens"]) == tokens
        assert report["decode_steps"] == steps and report["request_resource_s"] == pytest.approx(
            times
        )
        assert report["revision"] == "812d96e10a0dd82b69d749e68693698cf6c36daa"
        assert report["hardware"] == "H200-SXM" and report["tp"] == 4
        assert report["allocated_fit"] == "unverified"
        whole = report["whole_model"]
        assert whole["analysis_status"] == "INSUFFICIENT_EVIDENCE"
        assert whole["qualified_bound_s"] is None and whole["measured_latency_s"] is None
    invalid = subprocess.run(command + ["--prompt-tokens", "0"], cwd=tmp_path, capture_output=True)
    assert invalid.returncode != 0 and not invalid.stdout
    assert (
        invalid.stderr.splitlines()[-1]
        == b"ValueError: Use positive lengths within the model context"
    )
