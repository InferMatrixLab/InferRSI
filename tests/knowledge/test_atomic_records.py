import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pytest

from inferrsi.knowledge.decision_cards import DecisionSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/atomic-reader"
BASELINE = json.loads((FIXTURES / "record-domain-v0.3.4.json").read_bytes())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture(scope="module")
def originals():
    path = FIXTURES / "record-sources-v0.3.4.zip"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE["release_record_files_sha256"]
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    guide = files.pop("records/README.md")
    assert hashlib.sha256(guide).hexdigest() == BASELINE["author_guide_sha256"]
    return {f"package:{Path(name).stem}": body for name, body in files.items()}


def test_release_inventory_preserves_both_record_dependency_shapes(originals):
    rows = BASELINE["records"]
    assert originals.keys() == rows.keys()
    assert Counter(row["old_required_count"] for row in rows.values()) == {1: 30, 716: 18}


@pytest.mark.parametrize("ref", sorted(BASELINE["records"]))
def test_record_l1_contract_matches_the_published_release_card(originals, ref):
    row = BASELINE["records"][ref]
    raw = originals[ref]
    record = json.loads(raw)
    assert ref == "package:" + record["id"]
    assert hashlib.sha256(raw).hexdigest() == row["original_sha256"]
    assert hashlib.sha256(canonical(record)).hexdigest() == row["record_sha256"]
    assert row["old_required_count"] == 1 + (
        BASELINE["shared_resource_count"] if record.get("skill_documents") else 0
    )

    # The independently installed v0.3.4 CLI supplied both goldens. This replay
    # uses only the archived Record, without consulting the working library.
    source = DecisionSource(ref, row["revision"], "record", "record.json", "record.json", record)
    card = source.project()["card"]
    assert card["status"] == "complete" and not card["missing_fields"]
    assert len(canonical(card)) == row["l1_card_bytes"]
    assert hashlib.sha256(canonical(card)).hexdigest() == row["l1_card_sha256"]
    required = set(row["l1_required_pointers"])
    assert {"/" + key for key in card["declared"]} <= required <= {"/" + key for key in record}
    assert card["declared"] == {key: record[key] for key in card["declared"]}
