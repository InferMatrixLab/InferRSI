"""Install the six Engine originals linked by the released research Workflow."""

import hashlib
import json
import re
import shutil
from pathlib import Path
from posixpath import normpath

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import RELEASE, allow

ATOMS = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/atoms"
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RESEARCH = "workflows/research/inference-engine-research"
H3 = "h3-c/audit-h3-runtime-residency"
# The order and hashes come from six material receipts from the installed v0.3.4 wheel.
RELEASED = {
    H3: "dd9539c5189582df0ffac7cf24461e377298507566cec44ca3bb9dec1def4b8d",
    "strata": "0e5daeb6409c916be45ecd7ce2531ea5f1c60a4a53e2b0ed25dc1e2cdc5c17ed",
    "vllm": "6f36cee8293b5484fd387a798cd450ad10cc2dc64aaded529e3a71ef4ecbe45f",
    "sglang": "e26877c23af54ba58eb443ca72ec6993c2cb8fd387d1871b2ff7f8be5eb8aab8",
    "sglang-omni": "d75f5b2881b240ec2d9d4f5cc8e3f7d53e4378cb01732a2fb9699da2901ba38c",
    "vllm-omni": "df3e63dc28de2dac2aa92824fd88719159138650d96487332e0effca3f0e2a80",
}
PROVENANCE = {
    "strata": "05f17d0ae996ad6c12314bdd29f3427574f6aa611ea60effd18598a0f386638b",
    "vllm": "6e841c38c35ff2cd6ff8139cb1a6c8f75701647897f1089a94a5c62928609941",
    "sglang": "534d95ae8d0b29bcbc8f6707b3d38fb964e31f5b66ba13517a9a6b8f309bbb38",
    "sglang-omni": "5e8dbe168a8885e209d4b4532944ffa7fead658b23fd6588054d57b22476f63b",
    "vllm-omni": "43bbfe431434ca4ad6157ba35cbb9ce2d89e4065f427abfdd5f372f51ba0c9c9",
}


def reference(engine):
    if engine == H3:
        return "checkout:audit-h3-runtime-residency.original"
    return f"package:engine-directory.{engine}.original"


@pytest.fixture(scope="module")
def guides(tmp_path_factory):
    root = tmp_path_factory.mktemp("engine-guides")
    source = make_author_root(root)
    release = root / "release"
    shutil.copytree(RELEASE_ROOT, release)
    bodies = []
    for engine, checksum in RELEASED.items():
        descriptor = reference(engine).split(":")[1] + ".json"
        author = json.loads((ATOMS / descriptor).read_bytes())
        local = author["content"]["guide.md"]["path"]
        body = (ATOMS / local).read_bytes()
        assert hashlib.sha256(body).hexdigest() == checksum
        shutil.copyfile(ATOMS / descriptor, source / "atoms" / descriptor)
        original = release / LIBRARY / "systems/engines" / engine / "SKILL.md"
        for path in (source / "atoms" / local, original):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        bodies.append(body)

    target = root / "installed"
    generation = build_generation(source, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=generation)
    uses = []
    for engine in RELEASED:
        ref = reference(engine)
        uses.append(AtomUse(AtomPin(ref, installed.catalog[ref]["revision"]), (ref,)))
    return installed, uses, tuple(bodies)


def test_research_links_deliver_the_released_targets_and_attribution(guides):
    installed, uses, bodies = guides
    guide = (ATOMS / "workflows/inference-engine-research/guide.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+/systems/engines/[^)]+/SKILL\.md)\)", guide)
    assert [normpath(f"{RESEARCH}/{link}") for link in links] == [
        f"systems/engines/{engine}/SKILL.md" for engine in RELEASED
    ]
    delivered = AtomicReader(installed, permits=allow).read_group(
        uses, max_bytes=33_588, context={}, operations=("retain", "redistribute"),
    )
    assert delivered.bodies == bodies
    assert delivered.receipt["status"] == "delivered" and delivered.receipt["body_bytes"] == 33_588
    for engine, use, item, raw in zip(
        RELEASED, uses, delivered.receipt["delivered"], bodies, strict=True,
    ):
        original = f"{LIBRARY}systems/engines/{engine}/SKILL.md"
        assert item["layer"] == "L3" and item["source_range_verification"] == "verified_at_build"
        assert (item["ref"], item["revision"]) == (use.pin.ref, use.pin.revision)
        assert item["source_path"] == item["source"]["path"] == original
        assert item["source"]["commit"] == RELEASE and item["source_byte_range"] == [0, len(raw)]
        assert item["sha256"] == item["source"]["sha256"] == RELEASED[engine]
        _, bundle = installed.read_resolved(use.pin.ref, revision=use.pin.revision)
        metadata = bundle.metadata
        assert metadata["state"] == "candidate" and metadata["empirical_validation"] == "not_run"
        assert metadata["atom"]["license"] == ("MIT" if engine == "strata" else "Apache-2.0")
        if engine == H3:
            fields = ("title", "origin", "applicability", "state", "limitations",
                      "attribution", "empirical_validation")
            inherited = {key: metadata[key] for key in fields}
            inherited["sources"] = metadata["sources"][1:]
            old_manifest = json.dumps(
                inherited, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            )
            assert hashlib.sha256(old_manifest.encode()).hexdigest() == (
                "fad9760bb35fc60f9ab04b61c05d88f0d4528ef2120af82aef7b9491b66994d8"
            )
        else:
            evidence, = metadata["attribution"]
            assert evidence == metadata["sources"][1]
            assert evidence["commit"] == RELEASE and evidence["sha256"] == PROVENANCE[engine]
            directory = original.removesuffix("SKILL.md")
            assert evidence["path"] == directory + "references/repo-provenance.md"
            assert f"checkout:{engine}" not in installed.catalog and engine not in installed.skills


def test_each_target_retains_its_own_authorization_revision_and_byte_budget(guides):
    installed, uses, bodies = guides
    reader = AtomicReader(installed, permits=allow)
    short = reader.read_group(uses, max_bytes=33_587, context={})
    assert short.bodies == ()
    assert short.receipt == {
        "status": "over_budget", "body_bytes": 0, "delivered": [], "required_bytes": 33_588,
    }
    for index, (use, body) in enumerate(zip(uses, bodies, strict=True)):
        assert reader.read_group([use], max_bytes=len(body), context={}).bodies == (body,)
        denied = AtomicReader(installed, permits=lambda pin, op: pin != use.pin or op != "read")
        assert denied.read_group(uses, max_bytes=33_588, context={}).receipt == {
            "status": "permission_denied", "body_bytes": 0, "delivered": [],
        }
        stale_pin = AtomPin(use.pin.ref, "sha256:" + "0" * 64)
        stale = [*uses[:index], AtomUse(stale_pin, use.path), *uses[index + 1:]]
        assert reader.read_group(stale, max_bytes=33_588, context={}).receipt == {
            "status": "unavailable_revision", "body_bytes": 0, "delivered": [],
        }
