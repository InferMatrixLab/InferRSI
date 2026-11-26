"""Replay the v0.3.4 public Workflow contracts on an independently sealed installation."""

import json
import shutil
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import assert_empty, canonical, digest, select
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/atomic-reader/workflow-domain-v0.3.4.json"
RELEASE = json.loads(FIXTURE.read_bytes())
KNOWLEDGE = FIXTURE.parents[3] / "src/inferrsi/knowledge"
GUIDES = ("cite-check-downstream-pr", "claim-contract", "competitor-scan")


@pytest.fixture(scope="module")
def workflow_installation(tmp_path_factory):
    root = tmp_path_factory.mktemp("workflows")
    author = make_author_root(root)
    pinned = root / "release"
    shutil.copytree(RELEASE_ROOT, pinned)
    (author / "atoms/workflows").mkdir()
    for name in GUIDES:
        row = RELEASE["refs"]["checkout:" + name]
        atom = f"atoms/{name}.original.json"
        descriptor = json.loads((KNOWLEDGE / atom).read_bytes())
        body = "atoms/" + descriptor["content"]["guide.md"]["path"]
        for relative in (atom, body, f"compositions/{name}.json"):
            shutil.copyfile(KNOWLEDGE / relative, author / relative)
        data = (author / body).read_bytes()
        assert RELEASE["files"][row["entry_source"]] == {"sha256": digest(data), "bytes": len(data)}
        assert row["required_resources"] == {row["entry_source"]: digest(data)}
        assert row["dependencies"] == {} and row["relative_guide_links"] == {}
        original = pinned / descriptor["metadata"]["sources"][0]["path"]
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(data)
    target = root / "installed"
    generation = build_generation(author, target, permits=allow,
                                  source_roots={RELEASE["source_commit"]: pinned})
    return InstalledGeneration(target, expected=generation), target


@pytest.mark.parametrize("name", GUIDES)
def test_checkout_host_and_layered_selection_preserve_workflow_guide(workflow_installation, name):
    installed, target = workflow_installation
    ref = "checkout:" + name
    row = RELEASE["refs"][ref]
    guide = row["entry_source"]
    assert installed.skills[name] == ref
    revision = installed.catalog[ref]["revision"]
    _, bundle = installed.read_resolved(ref, revision=revision)
    host = target / "skills" / name
    raw = (host / "SKILL.md").read_bytes()
    assert sorted(p.name for p in host.iterdir()) == ["SKILL.md"]
    assert bundle.content == {guide: raw} and bundle.dependencies == {}
    assert bundle.metadata["required_resources"] == [guide]
    assert digest(raw) == row["entry_sha256"] == row["guide_sha256"]
    assert digest(canonical(bundle.view()["resources"])) == row["resource_set"]
    assert bundle.metadata["state"] == "candidate" and bundle.metadata["origin"] == ["first-party"]
    results = {}
    for layer in ("L0", "L1", "L2", "L3"):
        selected = select(installed, ref, layer, len(raw))
        assert selected.receipt["status"] == "delivered"
        size = sum(map(len, selected.bodies))
        assert size == selected.receipt["body_bytes"]
        assert select(installed, ref, layer, size) == selected
        short = select(installed, ref, layer, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        stale = select(installed, ref, layer, size, revision=row["revision"])
        assert_empty(stale, "unavailable_revision")
        for item, body in zip(selected.receipt["delivered"], selected.bodies, strict=True):
            lo, hi = item["source_byte_range"]
            assert item["source"]["commit"] == RELEASE["source_commit"]
            assert item["source_path"] == "src/inferrsi/knowledge/data/skill_library/" + guide
            assert item["source_range_verification"] == "verified_at_build"
            assert body == raw[lo:hi] and digest(body) == item["source_sha256"]
        for denied in [ref, *(item["ref"] for item in selected.receipt["delivered"])]:
            result = select(installed, ref, layer, size, permits=lambda pin, op: pin.ref != denied)
            assert_empty(result, "permission_denied")
        results[layer] = selected.bodies
    (navigation,) = results["L0"]
    assert raw.startswith(navigation) and name.encode() in navigation
    assert b"description:" in navigation
    assert b"metadata:" not in navigation
    (decision,) = results["L1"]
    _, fields = _skill_search_source(decision.decode())
    assert fields["empirical_validation"] == bundle.metadata["empirical_validation"] == "not_run"
    projected = DecisionSource(ref, revision, "skill", guide, guide, fields).project()["card"]
    assert projected["revision"] == revision
    compared = {**projected, "revision": row["revision"]}
    assert digest(canonical(compared)) == row["card_sha256"]
    assert len(canonical(compared)) == row["card_bytes"]
    assert compared["status"] == row["status"] == "partial"
    assert compared["missing_fields"] == row["missing_fields"] == ["validation"]
    assert results["L2"][0] == decision and b"".join(results["L2"]) == raw
    assert results["L3"] == (raw,)


@pytest.mark.parametrize("name", GUIDES)
def test_package_baseline_has_its_own_card_and_shared_dependency(workflow_installation, name):
    _, target = workflow_installation
    checkout = RELEASE["refs"]["checkout:" + name]
    (ref, row), = [
        (key, value) for key, value in RELEASE["refs"].items()
        if key.startswith("package:") and value["entry_source"] == checkout["entry_source"]
    ]
    assert row["entrypoint"] == "record.json" and row["entry_sha256"] != checkout["entry_sha256"]
    assert row["guide_sha256"] == checkout["guide_sha256"]
    assert row["revision"] != checkout["revision"]
    assert row["required_count"] == 1 + RELEASE["shared_members"] == 716
    assert row["dependencies"] == {"data/skill_library": RELEASE["shared_dependency"]}
    guide = row["guide"]
    assert guide == "data/skill_library/" + checkout["guide"]
    body = (target / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    _, fields = _skill_search_source(body)
    old = DecisionSource(ref, row["revision"], "skill", guide, guide, fields)
    exact = old.project(max_bytes=row["card_bytes"])
    assert digest(canonical(exact["card"])) == row["card_sha256"]
    assert row["card_sha256"] != checkout["card_sha256"]
    short = old.project(max_bytes=row["card_bytes"] - 1)
    assert short["status"] == "over_budget" and "card" not in short
