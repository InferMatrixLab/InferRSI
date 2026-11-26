"""Casebooks comparison inputs from the released v0.3.4 wheel and its native Reader."""

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest

from inferrsi.apps.workflows.knowledge import read_selection
from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.decision_cards import DecisionSource, UnknownFinding
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root, write_json
from tests.knowledge.test_atomic_reader import allow

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "atomic-reader"
ATOMS = FIXTURES.parents[2] / "src" / "inferrsi" / "knowledge" / "atoms"
RELEASE_COMMIT = "e2f3be102c66c358803ed2186ed67bf627ebcbdf"
BASELINE = json.loads((FIXTURES / "casebook-domain-v0.3.4.json").read_bytes())
CASES = {ref: row for ref, row in BASELINE["refs"].items() if row["kind"] == "case"}
FINDINGS = [(ref, index) for ref, row in CASES.items() for index in range(len(row["findings"]))]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


@pytest.fixture(scope="module")
def originals():
    with ZipFile(FIXTURES / "casebook-sources-v0.3.4.zip") as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    assert {name: {"bytes": len(raw), "sha256": digest(raw)} for name, raw in files.items()} == (
        BASELINE["files"]
    )
    return files


def decision_source(ref, originals):
    row = CASES[ref]
    raw = originals[row["case_aliases"]["case.json"]]
    record = json.loads(raw)
    assert row["case_file_sha256"] == digest(raw)
    return DecisionSource(ref, row["revision"], "case", "case.json", record["content"], record)


@pytest.mark.parametrize(("ref", "index"), FINDINGS)
def test_one_released_finding_reproduces_its_native_decision_card(originals, ref, index):
    row = CASES[ref]
    expected = row["findings"][index]
    source = decision_source(ref, originals)
    raw = originals[row["case_aliases"]["case.json"]]
    excerpt = raw[expected["start_byte"]:expected["end_byte"]]
    assert digest(excerpt) == expected["span_sha256"]
    finding = json.loads(excerpt)
    assert source.record["findings"][index] == finding
    assert digest(canonical(finding)) == expected["finding_sha256"]

    selector = expected["selector"]
    budget = expected["card_bytes"]
    exact = source.project(finding=selector, max_bytes=budget)
    card = exact["card"]
    assert card["atom"]["pointer"] == expected["pointer"]
    assert card["declared"]["finding"] == finding
    assert exact["status"] == card["status"] == expected["status"]
    assert card["missing_fields"] == expected["missing_fields"]
    assert len(canonical(card)) == exact["card_bytes"] == budget
    assert digest(canonical(card)) == expected["card_sha256"]

    short = source.project(finding=selector, max_bytes=budget - 1)
    assert short["status"] == "over_budget" and "card" not in short


@pytest.mark.parametrize("ref", sorted(CASES))
def test_casebooks_require_a_finding_from_the_selected_case(originals, ref):
    source = decision_source(ref, originals)
    with pytest.raises(ValueError, match="Select one --finding"):
        source.project()
    with pytest.raises(UnknownFinding):
        source.project(finding=f"case.json#/findings/{len(CASES[ref]['findings'])}")


@pytest.mark.parametrize("ref", sorted(CASES))
def test_case_atoms_keep_both_complete_sources_and_the_original_credit(originals, ref):
    row = CASES[ref]
    record = decision_source(ref, originals).record
    for suffix, resource in (("original", "case.json"), ("guide", record["content"])):
        identity = record["id"] + "." + suffix
        descriptor = json.loads((ATOMS / (identity + ".json")).read_bytes())
        meta = descriptor["metadata"]
        assert (descriptor["authority"], meta["id"]) == ("checkout", identity)
        for field in ("origin", "state", "applicability", "limitations", "attribution"):
            assert meta[field] == record[field]
        assert meta["sources"][1:] == record["sources"]
        old_path = row["case_aliases"][resource]
        raw = originals[old_path]
        assert (ATOMS / descriptor["content"][resource]["path"]).read_bytes() == raw
        assert meta["entrypoint"] == resource
        pin = meta["sources"][0]
        assert (pin["commit"], pin["sha256"]) == (RELEASE_COMMIT, digest(raw))
        assert pin["path"] == "src/inferrsi/knowledge/data/skill_library/" + old_path
        assert meta["atom"]["layer"] == "L3"
        assert meta["atom"]["source_span"] == {
            "source_index": 0, "path": pin["path"],
            "byte_range": [0, len(raw)], "sha256": digest(raw),
        }


@pytest.mark.parametrize(("ref", "index"), FINDINGS)
def test_one_finding_and_its_shared_fields_reproduce_the_released_card(ref, index):
    row = CASES[ref]
    expected = row["findings"][index]
    identity = ref.partition(":")[2]
    descriptor = json.loads((ATOMS / (identity + ".original.json")).read_bytes())
    raw = (ATOMS / descriptor["content"]["case.json"]["path"]).read_bytes()
    shared = {}
    for name in ("origin-state", "sources", "applicability", "limits-attribution"):
        part = descriptor["parts"][name]
        start, end = part["byte_range"]
        data = raw[start:end]
        fields = json.loads(b"{" + data + b"}")
        assert part["layer"] == "L1" and digest(data) == part["sha256"]
        assert part["pointers"] == ["/" + field for field in fields]
        shared.update(fields)
    part = descriptor["parts"][f"finding-{index}"]
    assert (part["layer"], part["pointers"]) == ("L1", [f"/findings/{index}"])
    start, end = part["byte_range"]
    assert (start, end) == (expected["start_byte"], expected["end_byte"])
    data = raw[start:end]
    assert digest(data) == part["sha256"] == expected["span_sha256"]
    shared["findings"] = [{} for _ in range(index)] + [json.loads(data)]
    markdown = Path(row["entry_source"]).name
    source = DecisionSource(ref, row["revision"], "case", "case.json", markdown, shared)
    result = source.project(finding=expected["selector"])
    assert result["status"] == expected["status"]
    assert digest(canonical(result["card"])) == expected["card_sha256"]


def case_sources(root, originals):
    author = make_author_root(root)
    release = root / "pinned"
    shutil.copytree(RELEASE_ROOT, release)
    for name, raw in originals.items():
        path = release / "src/inferrsi/knowledge/data/skill_library" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    for ref in CASES:
        name = ref.partition(":")[2]
        for suffix in ("original", "guide"):
            filename = f"{name}.{suffix}.json"
            shutil.copyfile(ATOMS / filename, author / "atoms" / filename)
        shutil.copyfile(ATOMS.parent / "compositions" / (name + ".json"),
                        author / "compositions" / (name + ".json"))
    shutil.copytree(ATOMS / "casebooks", author / "atoms/casebooks")
    return author, release


@pytest.fixture(scope="module")
def installed_cases(tmp_path_factory, originals):
    root = tmp_path_factory.mktemp("cases")
    author, release = case_sources(root, originals)
    target = root / "installed"
    generation = build_generation(author, target, permits=allow,
                                  source_roots={RELEASE_COMMIT: release})
    return InstalledGeneration(target, expected=generation)


def select(installed, ref, layer, budget, **request):
    revision = request.pop("revision", installed.catalog[ref]["revision"])
    return read_selection(installed, ref, revision=revision, layer=layer, max_bytes=budget,
                          context={}, permits=request.pop("permits", allow), **request)


def assert_empty(delivery, reason):
    assert delivery.receipt["status"] == reason
    assert delivery.bodies == () and delivery.receipt["delivered"] == []
    assert delivery.receipt["body_bytes"] == 0


@pytest.mark.parametrize("ref", sorted(CASES))
def test_public_case_resources_and_layers(installed_cases, originals, ref):
    row = CASES[ref]
    released = {name: originals[path] for name, path in row["case_aliases"].items()}
    record = json.loads(released["case.json"])
    guide = record["content"]
    revision = installed_cases.catalog[ref]["revision"]
    _, bundle = installed_cases.read_resolved(ref, revision=revision)
    assert bundle.content == released and not bundle.dependencies
    required = [guide, "case.json", *record["required_resources"]]
    assert bundle.metadata["required_resources"] == required
    assert bundle.metadata["entrypoint"] == guide
    for key in ("origin", "state", "applicability", "limitations", "attribution"):
        assert bundle.metadata[key] == record[key]
    assert bundle.metadata["sources"][1:] == record["sources"]
    for layer in ("L0", "L2", "L3"):
        result = select(installed_cases, ref, layer, sum(map(len, released.values())))
        assert result.receipt["status"] == "delivered"
        for item, body in zip(result.receipt["delivered"], result.bodies, strict=True):
            start, end = item["source_byte_range"]
            name = item["source_path"].split("/skill_library/", 1)[1]
            assert body == originals[name][start:end]
            assert item["source_range_verification"] == "verified_at_build"
        if layer == "L0":
            assert json.loads(b"{" + result.bodies[0] + b"}")["id"] == record["id"]
        elif layer == "L2":
            assert result.bodies[-1] == released[guide]
        else:
            assert result.bodies == (released["case.json"], released[guide])
    for selector in (None, "id:missing", f"case.json#/findings/{len(row['findings'])}"):
        result = select(installed_cases, ref, "L1", 100_000, finding=selector)
        assert_empty(result, "not_applicable")
    assert_empty(select(installed_cases, ref, "L1", 100_000, revision=row["revision"],
                        finding=row["findings"][0]["selector"]), "unavailable_revision")


@pytest.mark.parametrize(("ref", "index"), FINDINGS)
def test_public_selection_delivers_one_released_card(installed_cases, originals, ref, index):
    row = CASES[ref]
    expected = row["findings"][index]
    raw = originals[row["case_aliases"]["case.json"]]
    selector = expected["selector"]
    result = select(installed_cases, ref, "L1", len(raw), finding=selector)
    assert result.receipt["status"] == "delivered"
    assert result.receipt["selection"]["canonical_finding"] == selector
    assert len(result.bodies) == 5
    fields = {}
    for item, body in zip(result.receipt["delivered"], result.bodies, strict=True):
        lo, hi = item["source_byte_range"]
        assert item["source_range_verification"] == "verified_at_build"
        assert item["source"]["commit"] == RELEASE_COMMIT and item["layer"] == "L1"
        assert raw[lo:hi] == body and digest(body) == item["source_sha256"]
        if [lo, hi] == [expected["start_byte"], expected["end_byte"]]:
            assert digest(body) == expected["span_sha256"] and "findings" not in fields
            fields["findings"] = [{} for _ in range(index)] + [json.loads(body)]
        else:
            shared = json.loads(b"{" + body + b"}")
            assert not fields.keys() & shared.keys() and "findings" not in shared
            fields.update(shared)
    card = DecisionSource(ref, row["revision"], "case", "case.json",
                          Path(row["entry_source"]).name, fields).project(finding=selector)["card"]
    assert card["status"] == expected["status"]
    assert (len(canonical(card)), digest(canonical(card))) == (expected["card_bytes"],
                                                               expected["card_sha256"])
    size = result.receipt["body_bytes"]
    assert size == sum(map(len, result.bodies))
    assert select(installed_cases, ref, "L1", size, finding=selector) == result
    short = select(installed_cases, ref, "L1", size - 1, finding=selector)
    assert_empty(short, "over_budget")
    assert short.receipt["required_bytes"] == size
    for denied in (ref, ref + ".original.limits-attribution", ref + f".original.finding-{index}"):
        refusal = select(installed_cases, ref, "L1", size, finding=selector,
                         permits=lambda pin, op: pin.ref != denied)
        assert_empty(refusal, "permission_denied")


@pytest.mark.parametrize(("change", "error"), [
    ("missing alias", "cover the original"), ("another guide", "original relative source"),
    ("excerpt", "complete L3 original"), ("stale", "Missing pinned"), ("identity", "identity"),
    ("swapped selector", "selected original finding"),
    ("optional sibling", "selected original finding"),
    ("missing limits", "required original decision field"),
    ("optional limits", "required original decision field"),
    ("missing sources", "required original decision field"),
    ("missing finding route", "every original finding"),
])
def test_build_refuses_broken_case_bindings(tmp_path, originals, change, error):
    author, release = case_sources(tmp_path, originals)
    first, second = sorted(CASES)[:2]
    directory = author / "compositions"
    path = directory / (first.partition(":")[2] + ".json")
    spec = json.loads(path.read_bytes())
    declaration = spec["metadata"]["composition"]
    nodes, routes = declaration["nodes"], declaration["routes"]
    other = json.loads((directory / (second.partition(":")[2] + ".json")).read_bytes())
    if change == "missing alias":
        del spec["case_resources"][Path(CASES[first]["case_aliases"]["case.json"]).name]
    elif change == "another guide":
        nodes["guide"] = other["metadata"]["composition"]["nodes"]["guide"]
    elif change == "excerpt":
        spec["case_resources"]["case.json"] = "identity"
    elif change == "stale":
        nodes["original"]["revision"] = "sha256:" + "0" * 64
    elif change == "identity":
        spec["metadata"]["id"] = second.partition(":")[2]
    elif change == "swapped selector":
        routes["finding-0"]["finding"] = routes["finding-1"]["finding"]
    elif change == "optional sibling":
        routes["finding-0"]["optional"] = ["finding-1"]
    elif change == "missing finding route":
        del routes["finding-0"]
    else:
        shared = "sources" if change == "missing sources" else "limits-attribution"
        nodes["finding-0"]["requires"].remove(shared)
        if change == "optional limits":
            routes["finding-0"]["optional"] = [shared]
    write_json(path, spec)
    target = tmp_path / "published"
    with pytest.raises(ValueError, match=error):
        build_generation(author, target, permits=allow, source_roots={RELEASE_COMMIT: release})
    assert not target.exists()
