"""Casebooks comparison inputs from the released v0.3.4 wheel and its native Reader."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from inferrsi.knowledge.decision_cards import DecisionSource, UnknownFinding

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
    # Retain the public index without providing sibling finding contents.
    shared["findings"] = [{} for _ in range(index)] + [json.loads(data)]
    markdown = Path(row["entry_source"]).name
    source = DecisionSource(ref, row["revision"], "case", "case.json", markdown, shared)
    result = source.project(finding=expected["selector"])
    assert result["status"] == expected["status"]
    assert digest(canonical(result["card"])) == expected["card_sha256"]
