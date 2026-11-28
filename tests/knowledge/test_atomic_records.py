import hashlib
import json
import shutil
from argparse import Namespace
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pytest

from inferrsi.apps.cli.atomic_knowledge import AtomicKnowledgeCLI
from inferrsi.apps.workflows.knowledge import read_selection
from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.atomic_json import matches_span, member_spans
from inferrsi.knowledge.decision_cards import DecisionSource
from inferrsi.knowledge.knowledge_operations import Bundle
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root, write_json
from tests.knowledge.test_atomic_reader import RELEASE, allow

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/atomic-reader"
BASELINE = json.loads((FIXTURES / "record-domain-v0.3.4.json").read_bytes())
LIBRARY = FIXTURES.parents[2] / "src/inferrsi/knowledge"
SELF_CONTAINED = sorted(
    ref for ref, row in BASELINE["records"].items() if row["old_required_count"] == 1
)
RECORD_PATH = "src/inferrsi/knowledge/data/skill_library/records"


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


def record_sources(root, originals, refs):
    author = make_author_root(root)
    release = root / "pinned-source"
    shutil.copytree(RELEASE_ROOT, release)
    (release / RECORD_PATH).mkdir(parents=True)
    (author / "atoms/records").mkdir()
    for ref in refs:
        name = ref.removeprefix("package:")
        for file in (f"atoms/{name}.original.json", f"atoms/records/{name}.json",
                     f"compositions/{name}.json"):
            shutil.copyfile(LIBRARY / file, author / file)
        (release / RECORD_PATH / (name + ".json")).write_bytes(originals[ref])
    return author, release


@pytest.fixture(scope="module")
def installed_records(tmp_path_factory, originals):
    root = tmp_path_factory.mktemp("record-domain")
    author, release = record_sources(root, originals, SELF_CONTAINED)
    target = root / "install"
    generation = build_generation(author, target, permits=allow, source_roots={RELEASE: release})
    return InstalledGeneration(target, expected=generation)


def delivered_record_fields(installed, delivery, raw):
    """Reconstruct only fields present in the returned, independently pinned source spans."""
    assert delivery.receipt["status"] == "delivered"
    assert delivery.receipt["body_bytes"] == sum(map(len, delivery.bodies))
    fields, claims = {}, {}
    for item, body in zip(delivery.receipt["delivered"], delivery.bodies, strict=True):
        assert item["source_range_verification"] == "verified_at_build"
        assert item["source"]["commit"] == RELEASE
        lo, hi = item["source_byte_range"]
        assert body == raw[lo:hi]
        assert hashlib.sha256(body).hexdigest() == item["source_sha256"]
        _, atom = installed.read_resolved(item["ref"], revision=item["revision"])
        pointers = atom.metadata["atom"]["source_pointers"]
        if pointers == [""]:
            assert len(delivery.bodies) == 1 and body == raw
            return json.loads(body)
        if pointers[0].startswith("/claims/"):
            assert len(pointers) == 1
            index = int(pointers[0].removeprefix("/claims/"))
            assert index not in claims
            claims[index] = json.loads(body)
        else:
            fragment = json.loads(b"{" + body + b"}")
            assert ["/" + key for key in fragment] == pointers
            assert not fields.keys() & fragment.keys()
            fields.update(fragment)
    if claims:
        fields["claims"] = [claims[i] for i in range(len(claims))]
    return fields


@pytest.mark.parametrize("ref", SELF_CONTAINED)
def test_public_installed_record_replays_the_wheel_decision(installed_records, originals, ref):
    cli = AtomicKnowledgeCLI(installed_records)
    row = BASELINE["records"][ref]
    revision = installed_records.compositions[ref]["revision"]

    def read(**overrides):
        arguments = {
            "id": ref,
            "revision": revision,
            "layer": "L1",
            "skill_root": None,
            "store": None,
            "resource": None,
            "compact": False,
            "material": False,
            "omit_resources": False,
            "finding": None,
            "max_bytes": None,
            "installed_library": False,
        }
        return cli.read(Namespace(**{**arguments, **overrides}))

    result = read()
    replay = canonical({**result["card"], "revision": row["revision"]})
    assert len(replay) == row["l1_card_bytes"]
    assert hashlib.sha256(replay).hexdigest() == row["l1_card_sha256"]
    assert read(max_bytes=result["card_bytes"])["card"] == result["card"]
    assert "card" not in read(max_bytes=result["card_bytes"] - 1)
    assert read(revision=row["revision"])["status"] == "unavailable_revision"
    resource = read(layer=None, resource="record.json", omit_resources=True)
    assert resource["content"].encode() == canonical(json.loads(originals[ref]))
    with pytest.raises(ValueError, match="Resource not found"):
        read(layer=None, resource="README.md")
    with pytest.raises(ValueError, match="public composition"):
        read(id=ref.removeprefix("package:"))


@pytest.mark.parametrize("ref", SELF_CONTAINED)
def test_installed_record_layers_replay_the_wheel_decision(installed_records, originals, ref):
    raw = originals[ref]
    record = json.loads(raw)
    row = BASELINE["records"][ref]
    revision = installed_records.catalog[ref]["revision"]
    _, bundle = installed_records.read_resolved(ref, revision=revision)
    assert bundle.content == {"record.json": canonical(record)}
    assert bundle.metadata["required_resources"] == ["record.json"] and not bundle.dependencies
    assert bundle.metadata["sources"][1:] == record["sources"]
    assert bundle.metadata["verification"] == record["verification"]
    assert bundle.metadata["state"] == record["status"]
    assert bundle.metadata["attribution"] == record.get("attribution", record["sources"])

    def select(layer, budget, *, context=None, **kwargs):
        return read_selection(installed_records, ref, revision=revision, layer=layer,
                              max_bytes=budget, context=context or {}, permits=allow, **kwargs)

    for layer in ("L0", "L1", "L2", "L3"):
        result = select(layer, len(raw))
        fields = delivered_record_fields(installed_records, result, raw)
        assert fields == {key: record[key] for key in fields}
        if layer == "L0":
            assert {"id", "title", "summary", "status", "verification"} <= fields.keys()
            if record.get("translations"):
                assert "translations" not in fields
                translated = select(layer, len(raw), context={"locale": "zh-CN"})
                assert delivered_record_fields(installed_records, translated, raw) == {
                    **fields, "translations": record["translations"]}
        elif layer == "L1":
            assert {"/" + key for key in fields} == set(row["l1_required_pointers"])
            # The release pin is the only substituted field in the card comparison.
            source = DecisionSource(ref, revision, "record", "record.json", "record.json", fields)
            card = source.project()["card"]
            assert card == DecisionSource.from_bundle(ref, bundle, bundle.view()).project()["card"]
            assert card["status"] == "complete"
            replay = canonical({**card, "revision": row["revision"]})
            assert (len(replay), hashlib.sha256(replay).hexdigest()) == (
                row["l1_card_bytes"], row["l1_card_sha256"])
            size = result.receipt["body_bytes"]
            assert select(layer, size) == result
            short = select(layer, size - 1)
            assert short.receipt["status"] == "over_budget" and not short.bodies
            assert short.receipt["required_bytes"] == size and not short.receipt["delivered"]
        elif layer == "L2":
            assert {"applicability", "limitations", "verification", "sources", "status",
                    "recommendations", "validation_plan"} <= fields.keys()
        else:
            assert result.bodies == (raw,)
    assert select("L1", len(raw), finding="id:unknown").receipt["status"] == "not_applicable"


def test_record_identity_and_required_permissions_are_atomic(installed_records):
    ref = SELF_CONTAINED[0]
    revision = installed_records.catalog[ref]["revision"]
    request = dict(revision=revision, layer="L1", context={}, max_bytes=1_000_000, permits=allow)
    denied_ref = ref + ".original.verification"
    for reference, change, reason in (
        (ref.replace("package:", "checkout:"), {}, "unavailable_revision"),
        (ref, {"revision": BASELINE["records"][ref]["revision"]}, "unavailable_revision"),
        (ref, {"permits": lambda pin, op: pin.ref != denied_ref}, "permission_denied"),
    ):
        result = read_selection(installed_records, reference, **{**request, **change})
        assert result.receipt["status"] == reason and result.receipt["body_bytes"] == 0
        assert not result.bodies and not result.receipt["delivered"]


def test_source_pointers_select_exact_members_in_the_original_utf8():
    source = r'  {"文\/字~" : [ "同", "同" ], "other":{}, "last": {"":true} }'.encode()
    members = member_spans(source)
    array = "/文~1字~0"
    first = source.index('"同"'.encode())
    size = len('"同"'.encode())
    second = source.index('"同"'.encode(), first + size)
    assert matches_span(members, [array + "/0"], first, first + size)
    assert matches_span(members, [array + "/1"], second, second + size)
    assert matches_span(members, [array + "/0", array + "/1"], first, second + size)
    assert not matches_span(members, [array + "/1"], first, first + size)
    assert not matches_span(members, [array + "/01"], second, second + size)
    assert not matches_span(members, [array + "/0"], first, first + size + 1)

    start, end = source.index(b'"'), source.index(b"true}") + len(b"true}")
    assert matches_span(members, [array, "/other", "/last"], start, end)
    assert not matches_span(members, [array, "/last"], start, end)
    assert not matches_span(members, [array, "/last", "/other"], start, end)
    assert not matches_span(members, [array, "/other", "/other", "/last"], start, end)
    assert not matches_span(members, [array + "/0", "/other"], first, source.index(b"{}") + 2)
    assert matches_span(members, ["/last/"], source.index(b'""'), end - 1)


def test_duplicate_decoded_member_names_have_no_unique_source_pointer():
    with pytest.raises(ValueError, match="Duplicate JSON member at /nested/a"):
        member_spans(br'{"nested":{"a": 1, "\u0061": 2}}')


@pytest.mark.parametrize(("change", "reason"), [
    ("unknown node", "declared source node"),
    ("partial source", "complete L3 original"),
    ("wrong Record", "match its identity"),
    ("wrong part digest", "declared source digest"),
    ("outside original", "Invalid source range"),
    ("wrong existing pointer", "JSON pointers do not match the source range"),
])
def test_invalid_record_candidate_never_publishes(tmp_path, originals, change, reason):
    ref = SELF_CONTAINED[0]
    name = ref.removeprefix("package:")
    author, release = record_sources(tmp_path, originals, [ref])
    path = author / "compositions" / (name + ".json")
    if change in {"wrong part digest", "outside original", "wrong existing pointer"}:
        path = author / "atoms" / (name + ".original.json")
    spec = json.loads(path.read_bytes())
    if change == "unknown node":
        spec["content"]["record.json"]["record_node"] = "missing"
    elif change == "partial source":
        spec["content"]["record.json"]["record_node"] = "scope"
    elif change == "wrong Record":
        spec["metadata"]["id"] = "another-record"
    elif change == "wrong part digest":
        spec["parts"]["scope"]["sha256"] = "0" * 64
    elif change == "wrong existing pointer":
        # A stale composition pin must not mask acceptance of the mislabelled part.
        (author / "compositions" / (name + ".json")).unlink()
        assert spec["parts"]["status"]["pointers"] == ["/status"]
        spec["parts"]["status"]["pointers"] = ["/summary"]
    else:
        spec["parts"]["scope"]["byte_range"][1] = len(originals[ref]) + 1
    write_json(path, spec)
    target = tmp_path / "install"
    with pytest.raises(ValueError, match=reason):
        build_generation(author, target, permits=allow, source_roots={RELEASE: release})
    assert not target.exists()


def test_attached_record_cannot_be_published_as_self_contained(tmp_path, originals):
    ref = next(ref for ref in originals if BASELINE["records"][ref]["old_required_count"] == 716)
    raw = originals[ref]
    record = json.loads(raw)
    assert record["skill_documents"]
    name = record["id"]
    sha = hashlib.sha256(raw).hexdigest()
    author = make_author_root(tmp_path)
    source = RECORD_PATH + "/" + name + ".json"
    release = tmp_path / "release"
    shutil.copytree(RELEASE_ROOT, release)
    (release / source).parent.mkdir(parents=True)
    (release / source).write_bytes(raw)

    example = SELF_CONTAINED[0].removeprefix("package:")
    original = json.loads((LIBRARY / "atoms" / (example + ".original.json")).read_bytes())
    meta = original["metadata"]
    meta["id"] = name + ".original"
    meta["sources"][0].update(path=source, sha256=sha)
    meta["atom"]["source_span"].update(path=source, sha256=sha, byte_range=[0, len(raw)])
    (author / "atoms/inputs/record.json").write_bytes(raw)
    write_json(author / "atoms" / (name + ".json"), {
        "metadata": meta, "content": {"record.json": {"path": "inputs/record.json"}}})
    composition = json.loads((LIBRARY / "compositions" / (example + ".json")).read_bytes())
    composition["metadata"]["id"] = name
    composition["metadata"]["composition"]["nodes"]["original"] = {
        "ref": "package:" + meta["id"], "revision": Bundle(meta, {"record.json": raw}, {}).revision,
    }
    write_json(author / "compositions" / (name + ".json"), composition)
    target = tmp_path / "install"
    with pytest.raises(ValueError, match="self-contained"):
        build_generation(author, target, permits=allow, source_roots={RELEASE: release})
    assert not target.exists()
