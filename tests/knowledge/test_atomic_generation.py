import hashlib
import io
import json
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import PUBLIC_TASKS, SEAL, InstalledGeneration, digest
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from inferrsi.knowledge.knowledge_operations import Bundle, UnavailableRevision, _json
from tests.fixtures.atomic_composition import composition, metadata, node
from tests.knowledge.test_atomic_reader import RELEASE, UPSTREAM, allow, excerpt
from tools.check_release import check_generation
from tools.plugin_bundle import bundle_runtime

RELEASE_ROOT = Path(__file__).resolve().parents[1] / "fixtures/atomic-reader/release-v0.3.4"
build_release = partial(build_generation, source_roots={RELEASE: RELEASE_ROOT})


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


def make_author_root(tmp_path):
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
        del fields["entrypoint"]
        fields["composition"]["skill"] = {
            "name": skill_name, "description": "Inspect the fixture.",
            "body": "navigation", "resources": {"references/criteria.md": "ceiling-l2",
                                               "assets/example.bin": "attachment"},
        }
        write_json(compositions / (skill_name + ".json"), {"metadata": fields})
    return root


@pytest.fixture
def author_root(tmp_path):
    return make_author_root(tmp_path)


def file_bytes(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_same_source_builds_byte_identical_catalog_skills_and_pinned_reader(author_root, tmp_path):
    first, second = tmp_path / "install-a", tmp_path / "install-b"
    generation = build_release(author_root, first, permits=allow)
    assert build_release(author_root, second, permits=allow) == generation
    assert file_bytes(first) == file_bytes(second)
    assert build_release(author_root, first, permits=allow) == generation
    assert not list(author_root.rglob("SKILL.md"))
    assert not list(first.rglob("skill-index.json"))
    installed = InstalledGeneration(first, expected=generation)
    reader = AtomicReader(installed, permits=allow)
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
                       context={"query": "acceptance criteria"})
        chosen = reader.read_selection(ref, **request)
        assert [len(body) for body in chosen.bodies] == [845, 1538]
        assert chosen.receipt["body_bytes"] == 2383
        assert all(item["source_range_verification"] == "verified_at_build"
                   for item in chosen.receipt["delivered"])
        short = reader.read_selection(ref, **{**request, "max_bytes": 2382})
        assert short.receipt["status"] == "over_budget" and not short.bodies
        with pytest.raises(UnavailableRevision):
            installed.read_resolved(ref.replace("package:", "checkout:"),
                                    revision=entry["revision"])


def test_release_artifacts_include_every_file_from_the_sealed_generation(author_root, tmp_path):
    source = tmp_path / "src" / "inferrsi"
    source.mkdir(parents=True)
    staged = source / "_atomic"
    expected = build_release(author_root, staged, permits=allow)
    runtime = tmp_path / "runtime"
    bundle_runtime(
        source, runtime, plugin_version="test", runtime_version="test", include_generation=True,
    )
    files = file_bytes(staged)
    assert file_bytes(runtime / "inferrsi/_atomic") == files

    sdist, wheel, codex, workswarm = [
        tmp_path / name for name in ("sdist.tar.gz", "wheel.zip", "codex.zip", "ws.zip")
    ]
    with tarfile.open(sdist, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(f"inferrsi-test/src/inferrsi/_atomic/{name}")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))

    def write_zip(archive, prefix, payload):
        with zipfile.ZipFile(archive, "w") as output:
            for name, data in payload.items():
                output.writestr(prefix + name, data)

    write_zip(wheel, "inferrsi/_atomic/", files)
    write_zip(codex, "inferrsi/runtime/inferrsi/_atomic/", files)
    inner = io.BytesIO()
    write_zip(inner, "inferrsi/_atomic/", files)
    write_zip(workswarm, "inferrsi/runtime/", {"payload.zip": inner.getvalue()})
    assert check_generation(staged, sdist, wheel, codex, workswarm) == expected

    with pytest.raises(ValueError, match="Source distribution differs"):
        check_generation(source / "absent", sdist, wheel, codex, workswarm)

    asset = "skills/analysis-example/assets/example.bin"
    write_zip(codex, "inferrsi/runtime/inferrsi/_atomic/", files | {asset: b"xyz"})
    with pytest.raises(ValueError, match="Codex ZIP differs"):
        check_generation(staged, sdist, wheel, codex, workswarm)
    write_zip(codex, "inferrsi/runtime/inferrsi/_atomic/", files)

    inner = io.BytesIO()
    incomplete = {name: data for name, data in files.items() if name != asset}
    write_zip(inner, "inferrsi/_atomic/", incomplete)
    write_zip(workswarm, "inferrsi/runtime/", {"payload.zip": inner.getvalue()})
    with pytest.raises(ValueError, match="WorkSwarm ZIP differs"):
        check_generation(staged, sdist, wheel, codex, workswarm)

    (staged / asset).unlink()
    with pytest.raises(ValueError, match="Plugin payload differs"):
        bundle_runtime(
            source, tmp_path / "incomplete", plugin_version="test", runtime_version="test",
            include_generation=True,
        )


def test_source_attestation_needs_the_callers_release_pin(author_root, tmp_path):
    destination = tmp_path / "install"
    release_id = build_release(author_root, destination, permits=allow)
    pinned = InstalledGeneration(destination, expected=release_id)
    unpinned = InstalledGeneration(destination)
    ref = pinned.tasks["task-debug"]
    request = dict(revision=pinned.catalog[ref]["revision"], layer="L2", max_bytes=2383,
                   context={"query": "acceptance criteria"})
    attested = AtomicReader(pinned, permits=allow).read_selection(ref, **request)
    declared = AtomicReader(unpinned, permits=allow).read_selection(ref, **request)
    assert attested.bodies == declared.bodies
    assert [len(body) for body in attested.bodies] == [845, 1538]
    verified = attested.receipt["delivered"]
    assert [item["source_range_verification"] for item in verified] == ["verified_at_build"] * 2
    assert declared.receipt == {
        **attested.receipt,
        "delivered": [{**item, "source_range_verification": "declared"} for item in verified],
    }
    with pytest.raises(UnavailableRevision):
        InstalledGeneration(destination, expected="sha256:" + "0" * 64)


def test_one_read_reports_the_external_source_check_for_each_atom(author_root, tmp_path):
    external = tmp_path / "original"
    external.mkdir()
    body = (author_root / "atoms/inputs/attachment").read_bytes()
    (external / "sample").write_bytes(body)
    roots = {RELEASE: RELEASE_ROOT, digest(body): external}
    target = tmp_path / "installation"
    generation = build_generation(author_root, target, permits=allow, source_roots=roots)
    installed = InstalledGeneration(target, expected=generation)
    uses = []
    for name in ("ceiling-l1", "navigation", "attachment"):
        ref = "package:" + name
        uses.append(AtomUse(AtomPin(ref, installed.catalog[ref]["revision"]), (name,)))
    delivery = AtomicReader(installed, permits=allow).read_group(
        uses, context={}, max_bytes=10000,
    )
    assert [item["source_range_verification"] for item in delivery.receipt["delivered"]] == [
        "verified_at_build", "declared", "verified_at_build",
    ]
    assert delivery.bodies[-1] == body
    (external / "sample").write_bytes(b"wrong external source")
    with pytest.raises(ValueError, match="Complete pinned source file differs"):
        build_generation(author_root, tmp_path / "corrupt", permits=allow, source_roots=roots)
    assert not (tmp_path / "corrupt").exists()


def test_host_procedure_assembles_pinned_sections_without_changing_l0(author_root, tmp_path):
    descriptor = author_root / "compositions/task-debug.json"
    spec = json.loads(descriptor.read_bytes())
    skill = spec["metadata"]["composition"]["skill"]
    skill["sections"] = ["ceiling-l1", "ceiling-l2"]
    skill["resources"]["references/acceptance-criteria.md"] = "ceiling-l2"
    write_json(descriptor, spec)
    destination = tmp_path / "install"
    build_release(author_root, destination, permits=allow)
    installed = InstalledGeneration(destination)
    ref = installed.tasks["task-debug"]
    navigation = AtomicReader(installed, permits=allow).read_selection(
        ref, revision=installed.catalog[ref]["revision"], layer="L0", context={}, max_bytes=100,
    )
    assert navigation.bodies == (b"See [criteria](references/criteria.md).\n",)
    host = (destination / "skills/task-debug/SKILL.md").read_bytes()
    assert host.split(b"\n---\n\n", 1)[1] == navigation.bodies[0] + b"".join(
        next(iter(excerpt(layer).content.values())) for layer in ("L1", "L2")
    )


@pytest.mark.parametrize("header", [
    None,
    "---\nname: task-performance\ndescription: Inspect the fixture.\n---\n",
    "---\nname: task-debug\ndescription: Inspect the fixture.\n---\nextra instructions\n",
    "---\nname: task-debug\ndescription: Inspect the fixture.\n",
])
def test_invalid_host_header_rejects_generation(author_root, tmp_path, header):
    descriptor = author_root / "compositions/task-debug.json"
    spec = json.loads(descriptor.read_bytes())
    spec["metadata"]["composition"]["skill"]["frontmatter"] = "host.yaml"
    if header is not None:
        spec.setdefault("content", {})["host.yaml"] = {"text": header}
    write_json(descriptor, spec)
    target = tmp_path / "install"
    with pytest.raises(ValueError, match="frontmatter"):
        build_release(author_root, target, permits=allow)
    assert not target.exists()


@pytest.mark.parametrize("change", [
    "missing task", "missing revision", "retain", "license", "policy", "outside",
    "alias", "wrong layer", "incomplete skill", "missing relative link",
    "undeclared section", "repeated section", "missing section link", "no license",
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
    elif change == "no license":
        dec["license"] = "NO_LICENSE"
    elif change == "wrong layer":
        dec["routes"]["rules"]["required"] = ["attachment"]
    elif change == "incomplete skill":
        dec["skill"]["resources"]["assets/missing"] = "not-declared"
    elif change == "missing relative link":
        del dec["skill"]["resources"]["references/criteria.md"]
    elif change == "undeclared section":
        dec["skill"]["sections"] = ["absent"]
    elif change == "repeated section":
        dec["skill"]["sections"] = ["navigation"]
    elif change == "missing section link":
        dec["skill"]["sections"] = ["ceiling-l1"]
    elif change == "alias":
        dec["skill"]["resources"]["assets/Example.bin"] = "attachment"
    if descriptor.exists():
        write_json(descriptor, spec)

    def policy(pin, op):
        return not (change == "policy" and pin.ref == "package:ceiling-l1" and op == "redistribute")

    with pytest.raises((ValueError, PermissionError)):
        build_release(author_root, tmp_path / "generation", permits=policy)
    assert not (tmp_path / "generation").exists()


def test_pinned_history_survives_new_build_and_mixed_install_is_rejected(author_root, tmp_path):
    first, second = tmp_path / "release-a", tmp_path / "release-b"
    old_id = build_release(author_root, first, permits=allow)
    original = InstalledGeneration(first)
    spec = author_root / "compositions/task-debug.json"
    obj = json.loads(spec.read_bytes())
    obj["metadata"]["limitations"] = ["revision B"]
    write_json(spec, obj)
    new_id = build_release(author_root, second, permits=allow)
    assert new_id != old_id
    with pytest.raises(UnavailableRevision):
        build_release(author_root, first, permits=allow)
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
        first, second = [pool.submit(build_release, author_root, destination, permits=allow)
                         for _ in range(2)]
    assert first.result() == second.result() == InstalledGeneration(destination).generation


def test_installed_catalog_must_match_the_exporter_even_if_resealed(author_root, tmp_path):
    destination = tmp_path / "generation"
    build_release(author_root, destination, permits=allow)
    path = destination / SEAL
    seal = json.loads(path.read_bytes())
    del seal["generation"]
    seal["skills"]["task-debug"] = seal["skills"]["task-accuracy"]
    seal["generation"] = "sha256:" + digest(_json(seal))
    path.write_bytes(_json(seal))
    with pytest.raises(ValueError, match="composition exports"):
        InstalledGeneration(destination)


def test_same_length_shift_cannot_publish_a_false_source_range(author_root, tmp_path):
    descriptor = author_root / "atoms/ceiling-l1.json"
    spec = json.loads(descriptor.read_bytes())
    span = spec["metadata"]["atom"]["source_span"]
    start, end = span["byte_range"]
    original = (RELEASE_ROOT / span["path"]).read_bytes()
    body = (author_root / "atoms/inputs/ceiling-l1").read_bytes()
    assert original[start:end] == body and original[start + 1:end + 1] != body
    span["byte_range"] = [start + 1, end + 1]
    write_json(descriptor, spec)
    changed = Bundle(spec["metadata"], {"rule.md": body}, {})
    for path in (author_root / "compositions").glob("*.json"):
        composition_spec = json.loads(path.read_bytes())
        nodes = composition_spec["metadata"]["composition"]["nodes"]
        nodes["ceiling-l1"]["revision"] = changed.revision
        write_json(path, composition_spec)
    with pytest.raises(ValueError, match="pinned source range"):
        build_release(author_root, tmp_path / "install", permits=allow)
    assert not (tmp_path / "install").exists()


def test_pinned_source_checks_the_complete_file_and_its_immutable_root(author_root, tmp_path):
    alternate = tmp_path / "wrong-release"
    path = UPSTREAM + "SKILL.md"
    old = (RELEASE_ROOT / path).read_bytes()
    (alternate / path).parent.mkdir(parents=True)
    (alternate / path).write_bytes(b"X" + old[1:])
    destination = tmp_path / "install"
    for roots, reason in (({RELEASE: alternate}, "Complete pinned source file differs"),
                          ({"0" * 40: RELEASE_ROOT}, "Missing pinned source root")):
        with pytest.raises(ValueError, match=reason):
            build_generation(author_root, destination, source_roots=roots, permits=allow)
        assert not destination.exists()
