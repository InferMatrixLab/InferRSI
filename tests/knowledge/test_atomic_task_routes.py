import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import PUBLIC_TASKS, InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader
from inferrsi.knowledge.knowledge_operations import UnavailableRevision
from inferrsi.knowledge.skill_catalog import primary_task_instructions, skill_resource

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/atomic-reader"
OLD = json.loads((FIXTURES / "task-domain-v0.3.4.json").read_bytes())
ROUTER = "inference-task-router"


@pytest.fixture(scope="module")
def generation(tmp_path_factory):
    stage = tmp_path_factory.mktemp("task-domain").resolve()
    root, original, source = stage / "installed", stage / "release", stage / "authored"
    published = {}
    for item in OLD["entries"].values():
        published[item["source"]] = item["original_sha256"]
        if card := item.get("route_card"):
            published[card["source"]] = card["sha256"]
    with ZipFile(FIXTURES / "task-sources-v0.3.4.zip") as archive:
        assert set(archive.namelist()) == published.keys()
        for path, expected in published.items():
            data = archive.read(path)
            assert hashlib.sha256(data).hexdigest() == expected
            target = original / "src/inferrsi/knowledge/data/skill_library" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    library = ROOT / "src/inferrsi/knowledge"
    def copy_descriptor(family, name):
        directory = library / family
        dest = source / family
        dest.mkdir(exist_ok=True, parents=True)
        descriptor = directory / f"{name}.json"
        shutil.copyfile(descriptor, dest / descriptor.name)
        spec = json.loads(descriptor.read_bytes())
        for item in spec.get("content", {}).values():
            if path := item.get("path"):
                shutil.copyfile(directory / path, dest / path)
        return spec["metadata"]

    atoms = set()
    for task in OLD["entries"]:
        spec = copy_descriptor("compositions", task)
        atoms.update(node["ref"].split(":", 1)[1] for node in spec["composition"]["nodes"].values())
    for atom in sorted(atoms):
        copy_descriptor("atoms", atom)
    generation_id = build_generation(source, root, permits=lambda pin, op: True,
                                     source_roots={OLD["commit"]: original})
    return root / "skills", InstalledGeneration(root, expected=generation_id)


@pytest.mark.parametrize("name", sorted(OLD["entries"]))
def test_all_published_task_owners_and_host_instructions(generation, name):
    skills, installed = generation
    before = OLD["entries"][name]
    ref = installed.skills[name]
    assert ref == before["target"]
    revision = installed.catalog[ref]["revision"]
    _, bundle = installed.read_resolved(ref, revision=revision)
    assert bundle.metadata["state"] == "candidate"
    assert bundle.metadata["empirical_validation"] == "not_run"
    source = bundle.metadata["sources"][0]
    assert source["commit"] == OLD["commit"] and source["sha256"] == before["original_sha256"]
    original = (skills / name / "SKILL.md").read_bytes()
    assert len(original) == before["original_bytes"]
    assert hashlib.sha256(original).hexdigest() == before["original_sha256"]
    header = bundle.content[bundle.metadata["composition"]["skill"]["frontmatter"]]
    assert hashlib.sha256(header).hexdigest() == before["header_sha256"]
    assert original.startswith(header)
    assert hashlib.sha256(original[len(header):]).hexdigest() == before["body_sha256"]
    for old_ref, old_revision in before["original_refs"].items():
        with pytest.raises(UnavailableRevision):
            installed.read_resolved(old_ref, revision=old_revision)
    assert set(installed.tasks) == PUBLIC_TASKS == OLD["entries"].keys() - {ROUTER}
    if name == ROUTER:
        with pytest.raises(ValueError, match="Not a primary inference task skill"):
            primary_task_instructions(skills, name)
        return
    instructions = primary_task_instructions(skills, name).encode()
    assert len(instructions) == before["enter_instruction_bytes"]
    assert hashlib.sha256(instructions).hexdigest() == before["enter_instruction_sha256"]
    card = before["route_card"]
    data = skill_resource(skills, ROUTER, card["public_relative_path"]).read_bytes()
    assert len(data) == card["bytes"] and hashlib.sha256(data).hexdigest() == card["sha256"]
    assert set(json.loads(data)["candidate_skill_ids"]) == card["seed_owners"].keys()


@pytest.mark.parametrize("name", sorted(PUBLIC_TASKS))
def test_task_layers_preserve_source_ranges_and_refuse_partial_or_foreign_routes(generation, name):
    skills, installed = generation
    reader = AtomicReader(installed, permits=lambda pin, op: True)

    def read(owner, layer, task, budget):
        ref = installed.skills[owner]
        return reader.read_selection(ref, revision=installed.catalog[ref]["revision"],
                                     layer=layer, context={"task": task}, max_bytes=budget)

    before = OLD["entries"][name]
    card = before["route_card"]
    other = next(task for task in sorted(PUBLIC_TASKS) if task != name)
    for layer in ("L0", "L1", "L2", "L3"):
        full = read(name, layer, name, 100_000)
        assert full.receipt["status"] == "delivered"
        size = sum(map(len, full.bodies))
        assert full.receipt["body_bytes"] == size
        assert read(name, layer, name, size).bodies == full.bodies
        short = read(name, layer, name, size - 1)
        assert not short.bodies and short.receipt["status"] == "over_budget"
        assert short.receipt["body_bytes"] == 0 and short.receipt["required_bytes"] == size
        for data, record in zip(full.bodies, full.receipt["delivered"], strict=True):
            path = record["source_path"].split("/data/skill_library/", 1)[1]
            if path.endswith("/SKILL.md"):
                raw = (skills / Path(path).parent.name / "SKILL.md").read_bytes()
            else:
                assert path == card["source"]
                raw = skill_resource(skills, ROUTER, card["public_relative_path"]).read_bytes()
            assert record["source"]["commit"] == OLD["commit"]
            assert record["source_range_verification"] == "verified_at_build"
            assert hashlib.sha256(raw).hexdigest() == record["source"]["sha256"]
            start, end = record["source_byte_range"]
            assert raw[start:end] == data
        if layer == "L0":
            assert read(name, layer, "", size).bodies == full.bodies
            assert len(full.bodies) == 1
            continue
        wrong = read(name, layer, other, size)
        assert not wrong.bodies and wrong.receipt["status"] == "not_applicable"
        if layer == "L1":
            assert card["choose_when"].encode() in full.bodies
        if layer == "L2":
            roles = ("procedure", "condition", "support", "acceptance")
            expected = {f"package:{name}-{role}" for role in roles} | {"package:task-capture-run"}
            assert {r["ref"] for r in full.receipt["delivered"]} == expected
        if layer == "L3":
            via_router = read(ROUTER, layer, name, size)
            assert via_router.bodies == full.bodies
            assert len(full.bodies) == 1
            assert hashlib.sha256(full.bodies[0]).hexdigest() == card["sha256"]
            direct, shared = (reply.receipt["delivered"][0] for reply in (full, via_router))
            assert (direct["ref"], direct["revision"]) == (shared["ref"], shared["revision"])


def test_router_keeps_general_decision_guidance_and_requires_a_target_for_card(generation):
    _, installed = generation
    router = installed.skills[ROUTER]
    reader = AtomicReader(installed, permits=lambda pin, op: True)
    read_args = {"revision": installed.catalog[router]["revision"],
                 "context": {}, "max_bytes": 20_000}
    for layer, expected in (("L0", b"# Choose an inference task"), ("L1", b"## Target conditions"),
                            ("L2", b"## Use and handoff")):
        result = reader.read_selection(router, layer=layer, **read_args)
        assert any(body.startswith(expected) for body in result.bodies)
    result = reader.read_selection(router, layer="L3", **read_args)
    assert result.receipt["status"] == "not_applicable" and not result.bodies
