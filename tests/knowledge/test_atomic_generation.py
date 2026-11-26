import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from inferrsi.apps.workflows.knowledge import read_selection
from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import PUBLIC_TASKS, SEAL, InstalledGeneration, digest
from inferrsi.knowledge.atomic_reader import AtomPin
from inferrsi.knowledge.knowledge_operations import Bundle, UnavailableRevision, _json
from tests.fixtures.atomic_composition import composition, metadata, node
from tests.knowledge.test_atomic_reader import allow, excerpt


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def local_atom(name, layer, body):
    sha = hashlib.sha256(body).hexdigest()
    fields = metadata(name, "knowledge", "body", {"type": "fixture", "sha256": sha})
    fields["atom"] = {
        "layer": layer, "when": {}, "license": "Apache-2.0",
        "permissions": {"read": True, "retain": True, "redistribute": True},
        "source_span": {"source_index": 0, "byte_range": [0, len(body)],
                        "path": "sample", "sha256": sha},
    }
    return Bundle(fields, {"body": body}, {})


@pytest.fixture
def author_root(tmp_path):
    root = tmp_path / "source"
    atoms, compositions = root / "atoms", root / "compositions"
    (atoms / "inputs").mkdir(parents=True)
    compositions.mkdir()
    nav = local_atom("navigation", "L0", b"See [criteria](references/criteria.md).\n")
    binary = local_atom("attachment", "L3", bytes([0xff, 0x00, 0x22]))
    nodes = {}
    for bundle in [nav, binary, *(excerpt(level) for level in ("L1", "L2", "L3"))]:
        identity = bundle.metadata["id"]
        name, data = next(iter(bundle.content.items()))
        if identity == "navigation":
            source = {"text": data.decode()}
        else:
            relative = "inputs/" + identity
            (atoms / relative).write_bytes(data)
            source = {"path": relative}
        write_json(atoms / (identity + ".json"),
                   {"metadata": bundle.metadata, "content": {name: source}})
        nodes[identity] = node(AtomPin("package:" + identity, bundle.revision))
    nodes["ceiling-l2"]["requires"] = ["ceiling-l1"]
    routes = {
        "navigate": {"layer": "L0", "required": ["navigation"]},
        "rules": {"layer": "L1", "required": ["ceiling-l1"]},
        "steps": {"layer": "L2", "required": ["ceiling-l1", "ceiling-l2"],
                  "optional": ["ceiling-l3"], "when": {"query": ["acceptance criteria"]}},
        "attachment": {"layer": "L3", "required": ["attachment"]},
    }
    for skill_name in sorted(PUBLIC_TASKS | {"analysis-example"}):
        fields = composition(nodes, routes).metadata
        fields["id"] = "entry-" + skill_name
        del fields["entrypoint"]  # Single authored file for a navigation composition.
        fields["composition"]["skill"] = {
            "name": skill_name, "description": "Inspect the fixture.",
            "body": "navigation", "resources": {"references/criteria.md": "ceiling-l2",
                                               "assets/example.bin": "attachment"},
        }
        write_json(compositions / (skill_name + ".json"), {"metadata": fields})
    return root


def file_bytes(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_same_source_builds_byte_identical_catalog_skills_and_pinned_reader(author_root, tmp_path):
    first, second = tmp_path / "install-a", tmp_path / "install-b"
    generation = build_generation(author_root, first, permits=allow)
    assert build_generation(author_root, second, permits=allow) == generation
    assert file_bytes(first) == file_bytes(second)
    assert build_generation(author_root, first, permits=allow) == generation
    assert not list(author_root.rglob("SKILL.md"))
    assert not list(first.rglob("skill-index.json"))
    installed = InstalledGeneration(first, expected=generation)
    assert set(installed.tasks) == PUBLIC_TASKS
    assert set(installed.skills) == PUBLIC_TASKS | {"analysis-example"}
    for name, ref in installed.skills.items():
        host = first / "skills" / name
        header = (host / "SKILL.md").read_text(encoding="utf-8")
        assert header == (f'---\nname: "{name}"\ndescription: "Inspect the fixture."\n---\n\n'
                          "See [criteria](references/criteria.md).\n")
        assert (host / "references/criteria.md").read_bytes() == next(
            iter(excerpt("L2").content.values()))
        assert (host / "assets/example.bin").read_bytes() == bytes([0xff, 0, 0x22])
        entry = installed.catalog[ref]
        request = dict(revision=entry["revision"], layer="L2", max_bytes=2383,
                       context={"query": "acceptance criteria"}, permits=allow)
        chosen = read_selection(installed, ref, **request)
        assert [len(body) for body in chosen.bodies] == [845, 1538]
        assert chosen.receipt["body_bytes"] == 2383
        short = read_selection(installed, ref, **{**request, "max_bytes": 2382})
        assert short.receipt["status"] == "over_budget" and not short.bodies
        with pytest.raises(UnavailableRevision):
            installed.read_resolved(ref.replace("package:", "checkout:"),
                                    revision=entry["revision"])


@pytest.mark.parametrize("change", [
    "missing task", "missing revision", "retain", "license", "policy", "outside",
    "alias", "wrong layer", "incomplete skill", "missing relative link",
])
def test_invalid_candidate_publishes_no_partial_tree(author_root, tmp_path, change):
    descriptor = author_root / "compositions/task-debug.json"
    spec = json.loads(descriptor.read_bytes())
    dec = spec["metadata"]["composition"]
    if change == "missing task":
        descriptor.unlink()
    elif change == "outside":
        spec["content"] = {"source": {"path": "../sibling"}}
    elif change == "missing revision":
        dec["nodes"]["navigation"]["revision"] = "sha256:" + "0" * 64
    elif change == "retain":
        dec["permissions"]["retain"] = False
    elif change == "license":
        dec["license"] = "NOASSERTION"
    elif change == "wrong layer":
        dec["routes"]["rules"]["required"] = ["attachment"]
    elif change == "incomplete skill":
        dec["skill"]["resources"]["assets/missing"] = "not-declared"
    elif change == "missing relative link":
        del dec["skill"]["resources"]["references/criteria.md"]
    elif change == "alias":
        dec["skill"]["resources"]["assets/Example.bin"] = "attachment"
    if descriptor.exists():
        write_json(descriptor, spec)

    def policy(pin, op):
        return not (change == "policy" and pin.ref == "package:ceiling-l1" and op == "redistribute")

    with pytest.raises((ValueError, PermissionError)):
        build_generation(author_root, tmp_path / "generation", permits=policy)
    assert not (tmp_path / "generation").exists()


def test_pinned_history_survives_new_build_and_mixed_install_is_rejected(author_root, tmp_path):
    first, second = tmp_path / "release-a", tmp_path / "release-b"
    old_id = build_generation(author_root, first, permits=allow)
    original = InstalledGeneration(first)
    spec = author_root / "compositions/task-debug.json"
    obj = json.loads(spec.read_bytes())
    obj["metadata"]["limitations"] = ["revision B"]
    write_json(spec, obj)
    new_id = build_generation(author_root, second, permits=allow)
    assert new_id != old_id
    with pytest.raises(UnavailableRevision):
        build_generation(author_root, first, permits=allow)
    new = InstalledGeneration(second)
    ref = original.tasks["task-debug"]
    revision = original.catalog[ref]["revision"]
    assert original.read_resolved(ref, revision=revision)[1].revision == revision
    with pytest.raises(UnavailableRevision):
        new.read_resolved(ref, revision=revision)
    (first / SEAL).write_bytes((second / SEAL).read_bytes())
    with pytest.raises(ValueError, match="differ"):
        InstalledGeneration(first)
    assert original.read_resolved(ref, revision=revision)[1].revision == revision


def test_concurrent_identical_builders_share_one_complete_destination(author_root, tmp_path):
    destination = tmp_path / "generation"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [pool.submit(build_generation, author_root, destination, permits=allow)
                         for _ in range(2)]
    assert first.result() == second.result() == InstalledGeneration(destination).generation


def test_installed_catalog_must_match_the_exporter_even_if_resealed(author_root, tmp_path):
    destination = tmp_path / "generation"
    build_generation(author_root, destination, permits=allow)
    path = destination / SEAL
    seal = json.loads(path.read_bytes())
    del seal["generation"]
    seal["skills"]["task-debug"] = seal["skills"]["task-accuracy"]
    seal["generation"] = "sha256:" + digest(_json(seal))
    path.write_bytes(_json(seal))
    with pytest.raises(ValueError, match="composition exports"):
        InstalledGeneration(destination)
