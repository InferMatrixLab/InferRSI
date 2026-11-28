"""Replay the released Project Maya checkout and its original license scope."""

import json
import shutil

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration, filesystem_root
from inferrsi.knowledge.atomic_reader import AtomicReader
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import (
    ATOMS,
    FIXTURES,
    assert_empty,
    canonical,
    digest,
    select,
)
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import allow

REF = "checkout:project-maya"
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
RELEASE = json.loads((FIXTURES / "project-maya-v0.3.4.json").read_bytes())


def test_project_maya_replays_original_directory_without_implicit_references(tmp_path):
    root = filesystem_root(tmp_path)
    author = make_author_root(root)
    pinned = root / "release"
    shutil.copytree(RELEASE_ROOT, pinned)
    composition = ATOMS.parent / "compositions/project-maya.json"
    shutil.copyfile(composition, author / "compositions" / composition.name)
    descriptor = json.loads(composition.read_bytes())
    bindings = descriptor["directory_resources"]
    declared = descriptor["metadata"]["composition"]
    nodes = declared["nodes"]
    assert declared["license"] == RELEASE["authored_license"] == "Apache-2.0"
    assert len(bindings) == 21
    assert bindings.keys() == RELEASE["resources"].keys()
    assert len(RELEASE["license_scope"]) == 1
    for logical, node in bindings.items():
        atom_path = ATOMS / (nodes[node]["ref"].removeprefix("checkout:") + ".json")
        shutil.copyfile(atom_path, author / "atoms" / atom_path.name)
        atom = json.loads(atom_path.read_bytes())
        (resource,) = atom["content"].values()
        raw = (ATOMS / resource["path"]).read_bytes()
        assert digest(raw) == RELEASE["resources"][logical]
        if logical.endswith(".py"):
            assert resource["path"].endswith(".py.txt")
        for target in (pinned / (LIBRARY + logical), author / "atoms" / resource["path"]):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        if logical in RELEASE["license_scope"]:
            scope = RELEASE["license_scope"][logical]
            assert atom["metadata"]["atom"]["license"] == scope["license"]
            assert scope["source"] in atom["metadata"]["sources"]
        else:
            license_name = RELEASE["helper_licenses"].get(logical, RELEASE["authored_license"])
            assert atom["metadata"]["atom"]["license"] == license_name

    destination = root / "installed"
    seal = build_generation(
        author, destination, permits=allow, source_roots={RELEASE["source_commit"]: pinned}
    )
    installed = InstalledGeneration(destination, expected=seal)
    revision = installed.catalog[REF]["revision"]
    _, bundle = installed.read_resolved(REF, revision=revision)
    assert REF.removeprefix("checkout:") not in installed.skills
    assert bundle.view()["resources"] == RELEASE["resources"]
    assert bundle.dependencies == RELEASE["dependencies"] == {}
    assert bundle.metadata["empirical_validation"] == RELEASE["empirical_validation"]
    assert bundle.metadata["empirical_validation"] == "partial_cpu_only"
    assert bundle.metadata["state"] == RELEASE["state"] == "candidate"
    metadata = dict(bundle.metadata)
    metadata.pop("composition")
    metadata["sources"] = metadata["sources"][1:]
    assert digest(canonical(metadata)) == RELEASE["metadata_sha256"]

    files = bundle.content
    guide = RELEASE["entrypoint"]
    assert sum(map(len, files.values())) == RELEASE["original_bytes"]
    assert b"license: NO_LICENSE" in files[guide]
    assert b"disable-model-invocation: true" in files[guide]
    notice = files["systems/engines/project-maya/sub-skills/model-runtime/references/notices.md"]
    assert b"Peasant Smith" in notice
    assert b"Niko1221" in notice
    assert b"NO_LICENSE" in notice
    layers = {}
    for level in ("L0", "L1", "L2", "L3"):
        delivery = select(installed, REF, level, RELEASE["original_bytes"])
        assert delivery.receipt["status"] == "delivered"
        size = sum(map(len, delivery.bodies))
        assert delivery.receipt["body_bytes"] == size
        assert select(installed, REF, level, size) == delivery
        short = select(installed, REF, level, size - 1)
        assert_empty(short, "over_budget")
        assert short.receipt["required_bytes"] == size
        stale = select(installed, REF, level, size, revision=RELEASE["revision"])
        assert_empty(stale, "unavailable_revision")
        for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
            path = item["source_path"].removeprefix(LIBRARY)
            start, end = item["source_byte_range"]
            assert item["source_path"] == LIBRARY + path
            assert item["source"]["commit"] == RELEASE["source_commit"]
            assert item["source_range_verification"] == "verified_at_build"
            assert body == files[path][start:end]
            assert digest(body) == item["source_sha256"]
            denied_ref = item["ref"]
            refusal = select(
                installed, REF, level, size, permits=lambda pin, op: pin.ref != denied_ref
            )
            assert_empty(refusal, "permission_denied")
        layers[level] = delivery.bodies

    (navigation,) = layers["L0"]
    assert files[guide].startswith(navigation) and b"description:" in navigation
    (decision,) = layers["L1"]
    _, fields = _skill_search_source(decision.decode())
    card = DecisionSource(REF, RELEASE["revision"], "skill", guide, guide, fields).project()["card"]
    assert card["status"] == "partial"
    assert card["missing_fields"] == RELEASE["missing_fields"] == ["validation"]
    assert len(canonical(card)) == RELEASE["card_bytes"]
    assert digest(canonical(card)) == RELEASE["card_sha256"]
    assert layers["L2"][0] == decision
    assert b"".join(layers["L2"][:2]) == files[guide]
    assert layers["L2"][2:] == tuple(files[path] for path in RELEASE["l2_resources"])
    assert layers["L3"] == tuple(files[path] for path in sorted(files))

    all_delivered = select(installed, REF, "L3", RELEASE["original_bytes"])
    assert all_delivered.receipt["body_bytes"] == RELEASE["original_bytes"]
    reader = AtomicReader(installed, permits=allow)
    for name in ("model-runtime", "serving-state", "qualification"):
        private_guide = f"systems/engines/project-maya/sub-skills/{name}/SKILL.md"
        assert b"disable-model-invocation: true" in files[private_guide]
        assert b"license: NO_LICENSE" in files[private_guide]
        for private_ref in (f"checkout:{name}", f"checkout:project-maya.{name}"):
            refusal = reader.read_selection(
                private_ref, revision=revision, layer="L3",
                max_bytes=RELEASE["original_bytes"], context={},
            )
            assert_empty(refusal, "unavailable_revision")
