import hashlib
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import PUBLIC_TASKS, InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import RELEASE, allow

ATOMS = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/atoms"
SOURCE = "src/inferrsi/knowledge/data/skill_library/tasks"
ORIGINALS = (
    (
        "inference-task-router",
        6199,
        "3dae791f61b26810332e05fbabe6fd7113abf9ed8609aef663535a267525849c",
    ),
    ("task-accuracy", 4767, "a441eb5565cd39674307f2cc870cb0d8d4c90314bb7df80245162df1dc3d1ae3"),
    ("task-day-0", 4496, "ca187de2205b3aa86b4ca5123fb0107a8235aa84f9d942d3771a8a665df1a0a3"),
    ("task-debug", 4686, "2e1e91cf429384c7cb3de68cb9a896a645853f819b23bbe2c10792b2813ae5f0"),
    (
        "task-derived-engine",
        4606,
        "976a01cf23e626fb2112fa637bb76da3f59532d27ee93f22365ea2c752dd0942",
    ),
    (
        "task-independent-engine",
        5045,
        "37e122098f2df35edc466d5b70598039ae640c8f4bb683b694d9195b0a83089e",
    ),
    ("task-performance", 4809, "bf5a137504566b6ee4eeaee18400d52aae99a1db3c8247dea7247d653103df0b"),
    (
        "task-version-alignment",
        4568,
        "114a2f41ce5b45f61b7cbb55d1cf9fa99a7c9aaff5e5597e563d9a00a7727c8c",
    ),
)


@pytest.fixture(scope="module")
def task_originals(tmp_path_factory):
    root = tmp_path_factory.mktemp("released-task-originals")
    authors = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    for slug, size, digest in ORIGINALS:
        descriptor = ATOMS / f"skill-library.v0-3-4.{slug}.json"
        relative = json.loads(descriptor.read_bytes())["content"]["SKILL.md"]["path"]
        raw = (ATOMS / relative).read_bytes()
        assert len(raw) == size
        assert hashlib.sha256(raw).hexdigest() == digest
        shutil.copyfile(descriptor, authors / "atoms" / descriptor.name)
        for destination in (authors / "atoms" / relative, release / SOURCE / slug / "SKILL.md"):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)

    target = root / "installed"
    generation = build_generation(authors, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=generation)
    uses = []
    for slug, _, _ in ORIGINALS:
        ref = f"package:skill-library.v0-3-4.{slug}"
        use = AtomUse(AtomPin(ref, installed.catalog[ref]["revision"]), (ref,))
        uses.append(use)
    return installed, tuple(uses)


def test_released_task_originals_keep_their_v034_bytes_without_new_public_routes(task_originals):
    installed, uses = task_originals
    assert set(installed.tasks) == PUBLIC_TASKS
    assert set(installed.skills) == PUBLIC_TASKS | {"analysis-example"}
    for slug, _, _ in ORIGINALS:
        assert f"checkout:skill-library.v0-3-4.{slug}" not in installed.catalog

    reader = AtomicReader(installed, permits=allow)
    result = reader.read_group(
        uses, max_bytes=39176, context={}, operations=("retain", "redistribute")
    )
    assert result.receipt["status"] == "delivered"
    assert result.receipt["body_bytes"] == 39176
    for use, (slug, size, digest), body, delivered in zip(
        uses, ORIGINALS, result.bodies, result.receipt["delivered"], strict=True
    ):
        assert len(body) == size
        assert hashlib.sha256(body).hexdigest() == digest
        assert delivered["ref"] == use.pin.ref
        assert delivered["revision"] == use.pin.revision
        expected_path = f"{SOURCE}/{slug}/SKILL.md"
        assert delivered["source_path"] == delivered["source"]["path"] == expected_path
        assert delivered["source"]["commit"] == RELEASE
        assert delivered["source_byte_range"] == [0, size]
        assert delivered["source_range_verification"] == "verified_at_build"
        assert delivered["sha256"] == delivered["source"]["sha256"] == digest
        assert delivered["layer"] == "L3"
        _, bundle = installed.read_resolved(use.pin.ref, revision=use.pin.revision)
        assert bundle.metadata["atom"]["license"] == "Apache-2.0"
        assert bundle.metadata["attribution"] == "InferMatrixLab/InferRSI contributors"


def test_released_task_originals_refuse_a_partial_group(task_originals):
    installed, uses = task_originals
    reader = AtomicReader(installed, permits=allow)
    over_budget = reader.read_group(uses, max_bytes=39175, context={})

    def deny_one(pin, _operation):
        return pin != uses[-1].pin

    denied = AtomicReader(installed, permits=deny_one).read_group(
        uses, max_bytes=39176, context={}
    )
    wrong_revision = AtomUse(AtomPin(uses[-1].pin.ref, "sha256:" + "0" * 64), uses[-1].path)
    stale = reader.read_group((*uses[:-1], wrong_revision), max_bytes=39176, context={})
    for result, status in (
        (over_budget, "over_budget"),
        (denied, "permission_denied"),
        (stale, "unavailable_revision"),
    ):
        assert result.receipt["status"] == status
        assert result.receipt["body_bytes"] == 0
        assert result.receipt["delivered"] == []
        assert result.bodies == ()
