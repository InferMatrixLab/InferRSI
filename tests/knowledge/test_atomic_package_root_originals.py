"""Install the library guide and index distributed as package material in v0.3.4."""

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
SOURCE = "src/inferrsi/knowledge/data/skill_library/"
# SHA-256 and byte lengths from the released package material receipts.
ORIGINALS = (
    ("skill-library.v0-3-4.readme", "README.md", "library-guide.md", 27_545,
     "f1bc0b65faba73511e32fd5750c468e0a0218e8863a3e674a396d498c83436c2"),
    ("skill-library.v0-3-4.index", "skill-index.json", "library-index.json", 11_203,
     "d243e2ae44c7badc8e68788153de35fe6ac31de618b7499fef6339eadf396871"),
)


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    root = tmp_path_factory.mktemp("library-snapshot")
    authors = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    for identity, original, entrypoint, length, digest in ORIGINALS:
        descriptor = identity + ".json"
        author = json.loads((ATOMS / descriptor).read_bytes())
        relative = author["content"][entrypoint]["path"]
        raw = (ATOMS / relative).read_bytes()
        assert len(raw) == length and hashlib.sha256(raw).hexdigest() == digest
        shutil.copyfile(ATOMS / descriptor, authors / "atoms" / descriptor)
        for path in (authors / "atoms" / relative, release / SOURCE / original):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    target = root / "installed"
    generation = build_generation(authors, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=generation)
    uses = []
    for identity, *_ in ORIGINALS:
        ref = "package:" + identity
        uses.append(AtomUse(AtomPin(ref, installed.catalog[ref]["revision"]), (ref,)))
    return installed, uses, target


def test_snapshot_delivers_frozen_package_bytes_and_compositions_supply_host_entries(snapshot):
    installed, uses, target = snapshot
    result = AtomicReader(installed, permits=allow).read_group(
        uses, max_bytes=38_748, context={}, operations=("retain", "redistribute"),
    )
    assert result.receipt["status"] == "delivered" and result.receipt["body_bytes"] == 38_748
    for spec, use, body, receipt in zip(
        ORIGINALS, uses, result.bodies, result.receipt["delivered"], strict=True,
    ):
        identity, original, _, length, digest = spec
        assert len(body) == length and hashlib.sha256(body).hexdigest() == digest
        assert receipt["ref"] == use.pin.ref and receipt["revision"] == use.pin.revision
        assert receipt["source_path"] == receipt["source"]["path"] == SOURCE + original
        assert receipt["source"]["commit"] == RELEASE
        assert receipt["source_byte_range"] == [0, length]
        assert receipt["sha256"] == receipt["source"]["sha256"] == digest
        assert receipt["layer"] == "L3"
        assert receipt["source_range_verification"] == "verified_at_build"
        _, bundle = installed.read_resolved(use.pin.ref, revision=use.pin.revision)
        assert bundle.metadata["atom"]["license"] == "Apache-2.0"
        assert bundle.metadata["attribution"] == "InferMatrixLab/InferRSI contributors"
        assert "checkout:" + identity not in installed.catalog
    released_index = json.loads(result.bodies[1])
    assert released_index["schema_version"] == 1 and len(released_index["skills"]) == 89
    assert set(installed.tasks) == PUBLIC_TASKS
    assert set(installed.skills) == PUBLIC_TASKS | {"analysis-example"}
    assert not list(target.rglob("skill-index.json"))


def test_short_budget_denied_permission_or_stale_revision_refuses_both_originals(snapshot):
    installed, uses, _ = snapshot
    reader = AtomicReader(installed, permits=allow)
    short = reader.read_group(uses, max_bytes=38_747, context={})
    assert short.bodies == ()
    assert short.receipt == {
        "status": "over_budget", "body_bytes": 0, "delivered": [], "required_bytes": 38_748,
    }
    for index, use in enumerate(uses):
        for operation in ("read", "retain", "redistribute"):
            restricted = AtomicReader(
                installed, permits=lambda pin, op: (pin, op) != (use.pin, operation),
            )
            denied = restricted.read_group(
                uses, max_bytes=38_748, context={}, operations=(operation,),
            )
            assert denied.bodies == ()
            assert denied.receipt == {
                "status": "permission_denied", "body_bytes": 0, "delivered": [],
            }
        stale = AtomUse(AtomPin(use.pin.ref, "sha256:" + "0" * 64), use.path)
        missing = reader.read_group(
            [*uses[:index], stale, *uses[index + 1:]], max_bytes=38_748, context={},
        )
        assert missing.bodies == ()
        assert missing.receipt == {
            "status": "unavailable_revision", "body_bytes": 0, "delivered": [],
        }
