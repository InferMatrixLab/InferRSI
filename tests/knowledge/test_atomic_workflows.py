"""Replay the v0.3.4 public Workflow contracts on an independently sealed installation."""

import json
import shutil
from pathlib import Path, PurePosixPath

import pytest

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import assert_empty, canonical, digest, select
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root, write_json
from tests.knowledge.test_atomic_reader import allow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/atomic-reader/workflow-domain-v0.3.4.json"
RELEASE = json.loads(FIXTURE.read_bytes())
KNOWLEDGE = FIXTURE.parents[3] / "src/inferrsi/knowledge"
GUIDES = ("cite-check-downstream-pr", "claim-contract", "competitor-scan", "npu-skill-factory")
LINKED_GUIDES = ("draft-acceptance-issue", "repository-evolution-analysis", "rsi-evidence",
                 "skill-evolution-playbook")
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"


def workflow_sources(root, names):
    author = make_author_root(root)
    pinned = root / "release"
    shutil.copytree(RELEASE_ROOT, pinned)
    for name in names:
        row = RELEASE["refs"]["checkout:" + name]
        composition = Path("compositions", name + ".json")
        shutil.copyfile(KNOWLEDGE / composition, author / composition)
        declaration = json.loads((author / composition).read_bytes())
        bindings = declaration["directory_resources"]
        assert bindings.keys() == row["required_resources"].keys()
        nodes = declaration["metadata"]["composition"]["nodes"]
        for path, key in bindings.items():
            identity = nodes[key]["ref"].removeprefix("checkout:")
            atom = Path("atoms", identity + ".json")
            shutil.copyfile(KNOWLEDGE / atom, author / atom)
            descriptor = json.loads((author / atom).read_bytes())
            (resource,) = descriptor["content"].values()
            body = Path("atoms", resource["path"])
            (author / body).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(KNOWLEDGE / body, author / body)
            data = (author / body).read_bytes()
            assert RELEASE["files"][path] == {"sha256": digest(data), "bytes": len(data)}
            assert row["required_resources"][path] == digest(data)
            original = pinned / (LIBRARY + path)
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(data)
    return author, pinned


@pytest.fixture(scope="module")
def workflow_installation(tmp_path_factory):
    root = tmp_path_factory.mktemp("workflows")
    author, pinned = workflow_sources(root, (*GUIDES, *LINKED_GUIDES))
    target = root / "installed"
    generation = build_generation(author, target, permits=allow,
                                  source_roots={RELEASE["source_commit"]: pinned})
    return InstalledGeneration(target, expected=generation), target


@pytest.mark.parametrize("name", (*GUIDES, *LINKED_GUIDES))
def test_checkout_layered_selection_preserves_workflow_guide(workflow_installation, name):
    installed, target = workflow_installation
    ref = "checkout:" + name
    row = RELEASE["refs"][ref]
    guide = row["entry_source"]
    revision = installed.catalog[ref]["revision"]
    _, bundle = installed.read_resolved(ref, revision=revision)
    files = bundle.content
    raw = files[guide]
    assert {path: digest(data) for path, data in files.items()} == row["required_resources"]
    assert bundle.dependencies == row["dependencies"]
    if name in GUIDES or name in installed.skills:
        assert installed.skills[name] == ref
        host = target / "skills" / name
        directory = PurePosixPath(guide).parent
        exported = {(directory / p.relative_to(host).as_posix()).as_posix(): p.read_bytes()
                    for p in host.rglob("*") if p.is_file()}
        assert exported == files
    assert bundle.metadata["required_resources"] == sorted(files)
    assert digest(raw) == row["entry_sha256"] == row["guide_sha256"]
    assert digest(canonical(bundle.view()["resources"])) == row["resource_set"]
    assert bundle.metadata["state"] == "candidate"
    results = {}
    for layer in ("L0", "L1", "L2", "L3"):
        selected = select(installed, ref, layer, sum(map(len, files.values())))
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
            path = item["source_path"].removeprefix(LIBRARY)
            assert item["source_path"] == LIBRARY + path
            if layer == "L2":
                assert path == guide or path in row["dependencies"]
            elif layer != "L3":
                assert path == guide
            assert item["source_range_verification"] == "verified_at_build"
            assert body == files[path][lo:hi] and digest(body) == item["source_sha256"]
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
    assert fields["origin"] == bundle.metadata["origin"]
    assert fields["empirical_validation"] == bundle.metadata["empirical_validation"] == "not_run"
    projected = DecisionSource(ref, revision, "skill", guide, guide, fields).project()["card"]
    assert projected["revision"] == revision
    compared = {**projected, "revision": row["revision"]}
    assert digest(canonical(compared)) == row["card_sha256"]
    assert len(canonical(compared)) == row["card_bytes"]
    assert compared["status"] == row["status"] == "partial"
    assert compared["missing_fields"] == row["missing_fields"]
    assert "validation" in compared["missing_fields"]
    assert results["L2"][0] == decision and b"".join(results["L2"][:2]) == raw
    assert results["L2"][2:] == tuple(files[path] for path in row["dependencies"])
    for path, revision in row["dependencies"].items():
        assert revision == "sha256:" + digest(files[path])
    assert results["L3"] == tuple(files[path] for path in sorted(files))


def test_factory_exports_linked_notes_and_preserves_source_attribution(workflow_installation):
    installed, target = workflow_installation
    name = "npu-skill-factory"
    ref = "checkout:" + name
    row = RELEASE["refs"][ref]
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    host = target / "skills" / name
    _, fields = _skill_search_source((host / "SKILL.md").read_text(encoding="utf-8"))
    assert bundle.metadata["origin"] == ["external"]
    assert bundle.metadata["attribution"] == bundle.metadata["sources"][1:] == fields["sources"]
    assert len(fields["sources"]) == 3
    assert len(row["relative_guide_links"]) == 5 and len(row["required_resources"]) == 17
    for link, old in row["relative_guide_links"].items():
        assert old["in_directory"] and digest((host / link).read_bytes()) == old["sha256"]
    assert len(fields["provenance_readsets"]) == 14
    for readset in fields["provenance_readsets"]:
        original = (PurePosixPath(row["guide"]).parent / readset).as_posix()
        assert digest((host / readset).read_bytes()) == row["required_resources"][original]
    manifest = host / "references/papers-20261015/references/source-manifest.json"
    declared = json.loads(manifest.read_bytes())
    assert len(declared) == 8
    assert all(item["source_copy_in_deliverable"] is False for item in declared)
    assert {item["sha256"] for item in declared}.isdisjoint(row["required_resources"].values())


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


def test_loopx_originals_keep_upstream_terms_and_attribution(workflow_installation):
    installed, _ = workflow_installation
    ref = "checkout:rsi-evidence"
    _, bundle = installed.read_resolved(ref, revision=installed.catalog[ref]["revision"])
    ledger_path = next(path for path in bundle.content if path.endswith("/source-ledger.json"))
    ledger = json.loads(bundle.content[ledger_path])
    assert ledger["source"]["license"] == "Apache-2.0"
    assert ledger["source"]["commit"] == "f094b2cfb2acde7a4a0d4d875bba52f64ac31ba9"
    originals = {row["resource"]: row for row in ledger["preserved_originals"]}
    assert originals.keys() == {"LICENSE", "LICENSE-MIT.md", "NOTICE.md"}
    directory = PurePosixPath(ledger_path).parent
    attached = {p: body for p, body in bundle.content.items()
                if PurePosixPath(p).parent == directory}
    assert len(attached) == 7
    for path, body in attached.items():
        filename = PurePosixPath(path)
        atom_ref = ref + "." + filename.stem.lower()
        revision = installed.catalog[atom_ref]["revision"]
        _, atom = installed.read_resolved(atom_ref, revision=revision)
        credit, = atom.metadata["attribution"]
        assert credit["url"] == ledger["source"]["url"]
        assert credit["commit"] == ledger["source"]["commit"]
        assert credit in atom.metadata["sources"]
        assert atom.metadata["empirical_validation"] == "not_run"
        assert dict(atom.content) == {filename.name: body}
        expected_license = "MIT" if filename.name == "LICENSE-MIT.md" else "Apache-2.0"
        assert atom.metadata["atom"]["license"] == expected_license
        if filename.name in originals:
            old = originals[filename.name]
            assert credit["path"] == old["source_path"]
            assert credit["sha256"] == old["sha256"] == digest(body)
            assert len(body) == old["bytes"]


@pytest.mark.parametrize(("change", "error"), [
    ("missing required guide", "L2 must deliver"), ("optional guide", "unconditional delivery"),
    ("different attachment", "L2 must deliver"), ("undeclared extra", "L2 must deliver"),
    ("unbound checkout", "requires checked"), ("unbound navigation", "requires checked"),
    ("invented dependency revision", "source-declared dependencies"),
    ("remove resource", "complete original directory"),
])
def test_checkout_requires_the_released_dependency(tmp_path, change, error):
    name = "repository-evolution-analysis"
    author, pinned = workflow_sources(tmp_path, [name])
    path = author / "compositions" / (name + ".json")
    spec = json.loads(path.read_bytes())
    meta = spec["metadata"]
    route = meta["composition"]["routes"]["procedure"]
    attachment = "rtk-consumer-path-transition"
    original = next(p for p, node in spec["directory_resources"].items() if node == attachment)
    if change == "missing required guide":
        route["required"].remove(attachment)
    elif change == "optional guide":
        route["required"].remove(attachment)
        route["optional"] = [attachment]
    elif change == "different attachment":
        route["required"] = ["procedure", "capability-presence-audit"]
    elif change == "undeclared extra":
        route["required"].append("capability-presence-audit")
    elif change.startswith("unbound"):
        del spec["directory_resources"]
        if change == "unbound navigation":
            del meta["entrypoint"]
            del meta["required_resources"]
    elif change == "invented dependency revision":
        spec["dependencies"] = {original: "sha256:" + "0" * 64}
    else:
        del spec["directory_resources"][original]
        meta["required_resources"].remove(original)
    write_json(path, spec)
    target = tmp_path / "installed"
    with pytest.raises(ValueError, match=error):
        build_generation(author, target, permits=allow,
                         source_roots={RELEASE["source_commit"]: pinned})
    assert not target.exists()
