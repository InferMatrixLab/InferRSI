import hashlib
import json
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


def test_public_cli_follows_pinned_routes_without_a_legacy_source(
    author_root, tmp_path, monkeypatch, capsys,
):
    from inferrsi.apps import cli as commands
    from inferrsi.apps.cli import atomic_knowledge

    optional_text = "Evidence – checked.\n"
    optional = local_atom("optional-card", "L1", optional_text.encode("utf-8"))
    write_json(author_root / "atoms/optional-card.json", {
        "metadata": optional.metadata, "content": {"body": {"text": optional_text}},
    })
    path = author_root / "compositions/analysis-example.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    composition_spec = spec["metadata"]["composition"]
    composition_spec["nodes"]["optional-card"] = node(
        AtomPin("package:optional-card", optional.revision),
    )
    composition_spec["routes"]["rules"]["optional"] = ["optional-card"]
    write_json(path, spec)
    generation = build_release(author_root, tmp_path / "_atomic", permits=allow)
    monkeypatch.setattr(atomic_knowledge, "__file__", str(
        tmp_path / "apps" / "cli" / "atomic_knowledge.py",
    ))
    monkeypatch.setenv("INFERRSI_KNOWLEDGE_GENERATION", generation)

    def unexpected_channels(**_kwargs):
        pytest.fail("Pinned find initialized external channels")

    monkeypatch.setattr(commands, "_channels", unexpected_channels)

    def cli(arguments):
        assert commands.main(arguments) == 0
        return json.loads(capsys.readouterr().out)

    def reject(arguments, message):
        with pytest.raises(SystemExit) as rejected:
            commands.main(arguments)
        assert rejected.value.code == 2
        failure = capsys.readouterr()
        assert failure.out == ""
        assert message in failure.err

    find_args = ["find", "analysis-example", "--kinds", "skill,record", "--limit", "1"]
    assert commands.main([*find_args, "--decision-cards", "--json"]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert output == json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    assert result["knowledge_generation"] == generation
    assert result.get("external", []) == []
    [match] = result["items"]
    assert match["id"] == "entry-analysis-example"
    assert match["authority"] == "package"
    assert match["knowledge_generation"] == generation
    navigation = cli(match["read_args"])
    assert navigation["bodies"] == [{"text": "See [criteria](references/criteria.md).\n"}]
    assert navigation["receipt"]["selection"]["layer"] == "L0"
    nav_bytes = navigation["receipt"]["body_bytes"]
    assert match["next_read_content_bytes"] == nav_bytes

    assert commands.main(find_args) == 0
    plain = capsys.readouterr().out
    assert f"read content: {nav_bytes} UTF-8 bytes" in plain
    assert "L1 (available" not in plain

    follow = match["decision_card"]["read_args"]
    assert follow[:2] == ["read", "package:entry-analysis-example"]
    complete = cli(follow)
    card_bytes = complete["receipt"]["body_bytes"]
    assert card_bytes == 845 + len(optional_text.encode("utf-8"))
    assert complete["bodies"][-1] == {"text": optional_text}
    assert match["decision_card"]["card_bytes"] == card_bytes
    assert commands.main([*find_args, "--decision-cards"]) == 0
    cards = capsys.readouterr().out
    assert f"L1 (available, {card_bytes} UTF-8 bytes)" in cards
    assert optional_text.strip() not in cards

    delivered = cli([*follow, "--max-bytes", "845"])
    assert delivered["receipt"]["status"] == "delivered"
    assert delivered["receipt"]["body_bytes"] == 845
    assert delivered["bodies"] == [{"text": next(iter(excerpt("L1").content.values())).decode()}]
    assert delivered["receipt"]["selection"] == {
        "ref": follow[1], "revision": follow[3], "layer": "L1", "finding": None,
        "canonical_finding": None, "routes": ["rules"],
    }
    [source] = delivered["receipt"]["delivered"]
    assert source["ref"] == "package:ceiling-l1"
    assert source["revision"] == excerpt("L1").revision
    refused = cli([*follow, "--max-bytes", "844"])
    assert refused["receipt"]["status"] == "over_budget"
    assert refused["bodies"] == []
    inapplicable = cli([*follow[:-1], "L2"])
    receipt = inapplicable["receipt"]
    assert receipt["status"] == "not_applicable"
    assert receipt["body_bytes"] == 0
    assert receipt["delivered"] == []
    assert receipt["selection"] == {
        "ref": follow[1], "revision": follow[3], "layer": "L2", "finding": None,
    }
    assert inapplicable["bodies"] == []
    attachment = cli([*follow[:-1], "L3"])
    assert attachment["bodies"] == [{"base64": "/wAi"}]

    stale = cli([*follow[:3], "sha256:" + "0" * 64, "--layer", "L1"])
    assert stale["receipt"]["status"] == "unavailable_revision"
    assert stale["bodies"] == []
    reject(["read", "package:ceiling-l1", "--revision", excerpt("L1").revision, "--layer", "L1"],
           "Read requires a public composition reference from find")
    reject([*follow, "--resource", "references/criteria.md"], "Pinned generation reads accept")
    reject([*find_args, "--external-source", "mindie-agent", "--backend", "ascend"],
           "Pinned generation find only supports the installed catalog")
    monkeypatch.setenv("INFERRSI_KNOWLEDGE_GENERATION", "sha256:" + "0" * 64)
    reject(follow, "Requested generation is unavailable")


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
