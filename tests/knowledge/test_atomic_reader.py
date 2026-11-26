import hashlib
from pathlib import Path

import pytest

from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse, applies
from inferrsi.knowledge.knowledge_operations import Bundle, UnavailableRevision
from inferrsi.knowledge.knowledge_store import KnowledgeStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "atomic-reader"
UPSTREAM = (
    "src/inferrsi/knowledge/data/skill_library/playbooks/measurement/performance-ceiling-analysis/"
)
RELEASE = "e2f3be102c66c358803ed2186ed67bf627ebcbdf"
SOURCE_DIGESTS = {
    "L1": "baeab73fb1fbf09da6ae0930b380720c66d9dc8085f8ccd1fb61381bb894799f",
    "L2": "e96efc42005af591a87b57dd6f1e9bffa8e351bcd023bd093ac37239a0486638",
    "L3": "597cd3205df043cff3ae9d15924c77934e8d8eb300c00c4840f6bb2921f90faf",
}
EXCERPTS = {
    "L1": (
        "rule.md", "SKILL.md", 10266, 11111,
        "b4e6bdffe5cf990a6be96b6ae8d1b442cf61b47f63bcd8949aae6650ab538089",
    ),
    "L2": (
        "steps.md", "references/acceptance-criteria.md", 252, 1790,
        "b1c9caafde8ac6912a5e4678bd11212a68016fb685a633970c69ad4977d9134a",
    ),
    "L3": (
        "roofline-example.json", "references/roofline-example.json", 0, 2015,
        "597cd3205df043cff3ae9d15924c77934e8d8eb300c00c4840f6bb2921f90faf",
    ),
}


def excerpt(layer):
    filename, path, start, end, digest = EXCERPTS[layer]
    return Bundle(
        {
            "id": "ceiling-" + layer.lower(), "kind": "knowledge", "entrypoint": filename,
            "state": "candidate", "applicability": {}, "limitations": [],
            "sources": [{
                "type": "git", "url": "https://github.com/InferMatrixLab/InferRSI",
                "commit": RELEASE, "path": UPSTREAM + path, "sha256": SOURCE_DIGESTS[layer],
            }],
            "attribution": "InferMatrixLab/InferRSI",
            "atom": {
                "layer": layer, "license": "Apache-2.0", "when": {},
                "permissions": {"read": True, "retain": True, "redistribute": True},
                "source_span": {
                    "source_index": 0, "path": UPSTREAM + path,
                    "byte_range": [start, end], "sha256": digest,
                },
            },
        },
        {filename: (FIXTURES / filename).read_bytes()}, {},
    )


class Snapshots:
    def __init__(self):
        self.items = {}
        self.reads = []

    def add(self, bundle, authority="package"):
        pin = AtomPin(f"{authority}:{bundle.metadata['id']}", bundle.revision)
        self.items[pin] = (pin.ref, bundle)
        return pin

    def read_resolved(self, reference, *, revision):
        pin = AtomPin(reference, revision)
        self.reads.append(pin)
        if pin not in self.items:
            raise UnavailableRevision(reference)
        return self.items[pin]


def allow(pin, operation):
    return True


def test_required_paths_share_bytes_and_receipts_reopen_the_exact_version():
    source = Snapshots()
    rule, steps = (source.add(excerpt(level)) for level in ("L1", "L2"))
    uses = [AtomUse(rule, ("rule",)), AtomUse(rule, ("prerequisite", "rule")),
            AtomUse(steps, ("steps",))]
    reader = AtomicReader(source, permits=allow)
    result = reader.read_group(uses, max_bytes=2383, context={})
    assert result.receipt["status"] == "delivered"
    assert result.receipt["body_bytes"] == sum(map(len, result.bodies)) == 2383
    assert source.reads == [rule, steps]
    records = result.receipt["delivered"]
    assert [record["paths"] for record in records] == [
        [["rule"], ["prerequisite", "rule"]], [["steps"]],
    ]
    for (pin, level), record, body in zip([(rule, "L1"), (steps, "L2")], records, result.bodies):
        filename, path, start, end, digest = EXCERPTS[level]
        assert record["ref"] == pin.ref and record["revision"] == pin.revision
        assert record["layer"] == level and record["bytes"] == end - start
        assert record["source"]["commit"] == RELEASE and record["source_path"] == UPSTREAM + path
        assert record["source_byte_range"] == [start, end]
        assert record["source_range_verification"] == "declared"
        assert record["source_sha256"] == record["sha256"] == hashlib.sha256(body).hexdigest()
        assert record["sha256"] == digest
        _, pinned = source.read_resolved(record["ref"], revision=record["revision"])
        assert body == pinned.content[filename] == (FIXTURES / filename).read_bytes()
    short = reader.read_group(uses, max_bytes=2382, context={})
    assert short.bodies == ()
    assert short.receipt == {
        "status": "over_budget", "body_bytes": 0, "delivered": [], "required_bytes": 2383,
    }


@pytest.mark.parametrize("level,size", [("L2", 1538), ("L3", 2015)])
def test_layer_budget_counts_the_last_byte(level, size):
    source = Snapshots()
    uses = [AtomUse(source.add(excerpt(level)), ("direct",))]
    reader = AtomicReader(source, permits=allow)
    complete = reader.read_group(uses, max_bytes=size, context={})
    assert complete.receipt["body_bytes"] == len(complete.bodies[0]) == size
    short = reader.read_group(uses, max_bytes=size - 1, context={})
    assert short.receipt["status"] == "over_budget" and short.bodies == ()


def test_authorities_cannot_lend_each_other_bytes_revisions_or_grants():
    source = Snapshots()
    original = excerpt("L1")
    first = source.add(original, "package")
    second = source.add(original, "checkout")
    uses = [AtomUse(pin, ("rule",)) for pin in (first, second)]
    reader = AtomicReader(source, permits=allow)
    result = reader.read_group(uses, max_bytes=1690, context={})
    assert [r["ref"] for r in result.receipt["delivered"]] == [first.ref, second.ref]
    assert len(result.bodies) == 2 and result.receipt["body_bytes"] == 1690
    source.reads.clear()
    denied = AtomicReader(source, permits=lambda pin, op: pin == first)
    result = denied.read_group(uses, max_bytes=1690, context={})
    assert source.reads == []
    assert result.bodies == () and result.receipt == {
        "status": "permission_denied", "delivered": [], "body_bytes": 0,
    }
    del source.items[second]
    updated = excerpt("L1")
    updated.metadata["limitations"] = ["Fixture revision B"]
    source.add(updated, "checkout")
    result = reader.read_group(uses, max_bytes=1690, context={})
    assert result.bodies == () and result.receipt == {
        "status": "unavailable_revision", "delivered": [], "body_bytes": 0,
    }


def test_operation_rights_and_conditions_apply_before_any_body_is_delivered():
    source = Snapshots()
    steps = excerpt("L2")
    steps.metadata["atom"].update(
        permissions={"read": True, "retain": False, "redistribute": True},
        license="NOASSERTION", when={"engine": ["v0.4", "v0.5"], "backend": ["gpu"]},
    )
    uses = [AtomUse(source.add(excerpt("L1")), ("rule",)), AtomUse(source.add(steps), ("steps",))]
    reader = AtomicReader(source, permits=allow)
    matching = {"engine": "v0.5", "backend": "gpu"}
    result = reader.read_group(uses, max_bytes=2383, context=matching)
    assert result.receipt["status"] == "delivered"
    for operation in ("retain", "redistribute"):
        result = reader.read_group(uses, max_bytes=2383, context=matching, operations=[operation])
        assert result.bodies == () and result.receipt["status"] == "permission_denied"
    for context in ({}, {"engine": "v0.4"}, {**matching, "engine": "v0"}):
        result = reader.read_group(uses, max_bytes=2383, context=context)
        assert result.bodies == () and result.receipt["status"] == "not_applicable"


@pytest.mark.parametrize("change", ["digest", "range", "locator", "unstable", "condition"])
def test_invalid_source_declaration_cannot_mint_a_receipt(change):
    source = Snapshots()
    bundle = excerpt("L2")
    atom = bundle.metadata["atom"]
    if change == "digest":
        atom["source_span"]["sha256"] = "0" * 64
    elif change == "range":
        atom["source_span"]["byte_range"][1] += 1
    elif change == "locator":
        atom["source_span"]["path"] = "../outside.md"
    elif change == "unstable":
        bundle.metadata["sources"][0]["commit"] = RELEASE[:7]
    else:
        atom["when"] = {"engine": "v0.5"}
    pin = source.add(bundle)
    with pytest.raises(ValueError):
        AtomicReader(source, permits=allow).read_group(
            [AtomUse(pin, ("steps",))], max_bytes=1538, context={"engine": "v0"},
        )


def test_existing_knowledge_store_can_reopen_old_atom_after_metadata_update(tmp_path):
    store = KnowledgeStore(tmp_path, skill_root=None)
    old = excerpt("L2")
    pin = AtomPin("store:" + old.metadata["id"], store.create(old))
    latest = excerpt("L2")
    latest.metadata["limitations"] = ["For the matching engine only"]
    assert store.update(latest, expected=pin.revision, reason="Clarify bounds", evidence=[]) != (
        pin.revision
    )
    reader = AtomicReader(store.reader(), permits=allow)
    result = reader.read_group([AtomUse(pin, ("historical",))], max_bytes=1538, context={})
    assert result.bodies == (old.content["steps.md"],)
    assert result.receipt["delivered"][0]["revision"] == pin.revision


def test_release_bounds_route_only_matching_numeric_versions_and_keep_exact_names():
    source = Snapshots()
    steps = excerpt("L2")
    steps.metadata["atom"]["when"] = {
        "engine": {"min": "v0.5", "before": "1.0"}, "backend": ["gpu"],
    }
    uses = [AtomUse(source.add(steps), ("release-steps",))]
    reader = AtomicReader(source, permits=allow)
    for version in ("0.5", "v0.5.0", "v0.10", "0.99.2"):
        context = {"engine": version, "backend": "gpu"}
        result = reader.read_group(uses, max_bytes=1538, context=context)
        assert result.bodies == (steps.content["steps.md"],)
    for version in ("0.4.99", "1", "v1.0.0", "nightly", "v0.5rc1"):
        context = {"engine": version, "backend": "gpu"}
        result = reader.read_group(uses, max_bytes=1538, context=context)
        assert result.bodies == () and result.receipt["status"] == "not_applicable"
    assert applies({"engine": {"min": "0.0"}}, {"engine": "v0"})
    assert applies({"engine": {"before": "0.5"}}, {"engine": "v0.4"})
    assert not applies({"engine": {"before": "0.5"}}, {})
    assert applies({"engine": ["v0.5rc1", "nightly"]}, {"engine": "nightly"})


@pytest.mark.parametrize("condition", [
    {}, {"min": "nightly"}, {"before": None}, {"min": 0.5},
    {"min": "0.5", "before": "0.5.0"}, {"min": "0.10", "before": "0.5"},
    {"unknown": "0.5"}, [],
])
def test_invalid_release_range_is_reported_even_after_an_unmatched_condition(condition):
    with pytest.raises(ValueError):
        applies({"backend": ["gpu"], "engine": condition}, {})


def test_receipt_retains_its_pinned_provenance_when_source_metadata_is_edited():
    source = Snapshots()
    rule = excerpt("L1")
    rule.metadata["sources"][0]["upstream_refs"] = ["release"]
    uses = [AtomUse(source.add(rule), ("rule",))]
    result = AtomicReader(source, permits=allow).read_group(uses, max_bytes=845, context={})
    rule.metadata["sources"][0]["upstream_refs"].append("latest")
    assert result.receipt["delivered"][0]["source"]["upstream_refs"] == ["release"]
