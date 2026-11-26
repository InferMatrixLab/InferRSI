"""Compare both Casebook guides against the decisions observed from the released wheel."""

from zipfile import ZipFile

import pytest

from inferrsi.knowledge.catalog import _skill_search_source
from inferrsi.knowledge.decision_cards import DecisionSource
from tests.knowledge.test_atomic_casebooks import BASELINE, FIXTURES, canonical, digest

GUIDES = {ref: row for ref, row in BASELINE["refs"].items() if "decision" in row}


@pytest.mark.parametrize("ref", sorted(GUIDES))
def test_released_guide_reproduces_each_namespaced_decision(ref):
    row = GUIDES[ref]
    expected = row["decision"]
    with ZipFile(FIXTURES / "casebook-sources-v0.3.4.zip") as archive:
        data = archive.read(row["entry_source"])
    assert digest(data) == row["entry_sha256"]
    _, metadata = _skill_search_source(data.decode())
    assert metadata["empirical_validation"] == "not_run"
    guide = ("" if ref.startswith("checkout:") else "data/skill_library/") + row["entry_source"]
    assert expected["atom"] == {"kind": "skill", "resource": guide}
    if ref.startswith("package:"):
        assert row["legacy_entrypoint"] == "record.json"
        assert row["legacy_entrypoint_sha256"] != digest(data)
    else:
        assert row["legacy_entrypoint"] == guide and row["legacy_entrypoint_sha256"] == digest(data)
    source = DecisionSource(ref, row["revision"], "skill", guide, guide, metadata)
    budget = expected["card_bytes"]
    reply = source.project(max_bytes=budget)
    card = reply["card"]
    assert reply["card_bytes"] == len(canonical(card)) == budget
    assert digest(canonical(card)) == expected["card_sha256"]
    assert card["status"] == expected["status"] == "partial"
    assert card["missing_fields"] == expected["missing_fields"] == ["validation"]
    short = source.project(max_bytes=budget - 1)
    assert short["status"] == "over_budget" and "card" not in short
