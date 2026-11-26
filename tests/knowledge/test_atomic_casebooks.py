"""Casebooks comparison inputs from the released v0.3.4 wheel and its native Reader."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from inferrsi.knowledge.decision_cards import DecisionSource, UnknownFinding

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "atomic-reader"
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
