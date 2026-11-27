"""The four external originals the released inference benchmark requires together."""
import hashlib
import json
import shutil
from pathlib import Path

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import RELEASE, allow

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
# Released declaration order, owner revision, and digest of the native owner's metadata.
GUIDES = (
    ("deepinfer", "budget-speculative-verification",
     "sha256:2bc62cda2beff7dd3898e81f9c5eda756e860577d5f63321e548febab965977c",
     "8a63e9ec266fdd498ad9fdcb0f1a72e2d009a091d6a20746446d4aeb1bc767df"),
    ("vllm-rlt", "audit-recurrent-kv-finalization",
     "sha256:a6e56602b29202af5478389dd0514af221e6e28868c439596ced22c82ce85629",
     "97782f08b3d733e43a40a68eac64ca87d5658ce58bae6bc0b60cff28c5fc616f"),
)


def test_installed_benchmark_dependencies_retain_published_order_and_read_together(tmp_path):
    fixtures = ROOT / "tests/fixtures/atomic-reader"
    baseline = json.loads((fixtures / "playbook-domain-v0.3.4.json").read_bytes())
    assert baseline["source_commit"] == RELEASE
    benchmark = baseline["refs"]["checkout:inference-benchmark-design"]
    casebook = json.loads((fixtures / "casebook-domain-v0.3.4.json").read_bytes())
    assert casebook["release"] == "v0.3.4"
    case_revision = casebook["refs"]["checkout:case.admission-drain-occupancy"]["revision"]
    authors = make_author_root(tmp_path)
    originals = ROOT / "src/inferrsi/knowledge/atoms"
    release = tmp_path / "release"
    shutil.copytree(RELEASE_ROOT, release)
    expected = []

    def stage_original(atom_id, path, location, old_revision, metadata_digest=None):
        descriptor = atom_id + ".json"
        shutil.copyfile(originals / descriptor, authors / "atoms" / descriptor)
        body = (originals / location).read_bytes()
        checksum = hashlib.sha256(body).hexdigest()
        assert benchmark["required_resources"][path] == checksum
        assert benchmark["dependencies"][path] == "sha256:" + checksum
        for destination in (authors / "atoms" / location, release / LIBRARY / path):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        ref = "checkout:" + atom_id
        expected.append((ref, path, body, old_revision, metadata_digest))

    for kind, extension in (("guide", "md"), ("original", "json")):
        filename = f"admission-drain-occupancy.{extension}"
        stage_original(
            f"case.admission-drain-occupancy.{kind}",
            f"casebooks/inference/inference-optimization-casebook/cases/{filename}",
            f"casebooks/{filename}",
            case_revision,
        )
    for engine, name, old_revision, metadata_digest in GUIDES:
        stage_original(
            f"{name}.original",
            f"systems/engines/{engine}/{name}/SKILL.md",
            f"engines/{engine}/{name}.md",
            old_revision,
            metadata_digest,
        )

    target = tmp_path / "installation"
    generation = build_generation(authors, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=generation)
    uses = []
    for ref, _, _, _, metadata_digest in expected:
        pin = AtomPin(ref, installed.catalog[ref]["revision"])
        uses.append(AtomUse(pin, (ref,)))
        if metadata_digest is None:
            continue
        _, bundle = installed.read_resolved(ref, revision=pin.revision)
        fields = ("title", "origin", "applicability", "state", "limitations", "attribution",
                  "empirical_validation")
        inherited = {key: bundle.metadata[key] for key in fields}
        inherited["sources"] = bundle.metadata["sources"][1:]
        serialized = json.dumps(inherited, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":"))
        assert hashlib.sha256(serialized.encode()).hexdigest() == metadata_digest

    reader = AtomicReader(installed, permits=allow)
    bodies = tuple(row[2] for row in expected)
    budget = sum(map(len, bodies))
    request = dict(context={}, max_bytes=budget, operations=("retain", "redistribute"))
    delivery = reader.read_group(uses, **request)
    assert tuple(map(len, delivery.bodies)) == (3134, 3602, 15070, 11778)
    assert delivery.bodies == bodies and delivery.receipt["body_bytes"] == budget == 33584
    for row, use, item in zip(expected, uses, delivery.receipt["delivered"], strict=True):
        ref, path, body, _, _ = row
        assert (item["ref"], item["revision"], item["layer"]) == (ref, use.pin.revision, "L3")
        assert item["source_range_verification"] == "verified_at_build"
        assert item["source_path"] == LIBRARY + path and item["source"]["commit"] == RELEASE
        assert item["source_byte_range"] == [0, len(body)]
        assert item["sha256"] == item["source"]["sha256"] == benchmark["required_resources"][path]

    short = reader.read_group(uses, **{**request, "max_bytes": budget - 1})
    assert short.bodies == ()
    assert short.receipt == {"status": "over_budget", "required_bytes": budget,
                             "body_bytes": 0, "delivered": []}
    for index, (ref, _, _, old_revision, _) in enumerate(expected):
        denied = AtomicReader(installed, permits=lambda pin, op: pin.ref != ref or op != "retain")
        stale_uses = uses.copy()
        stale_uses[index] = AtomUse(AtomPin(ref, old_revision), (ref,))
        for result, reason in ((denied.read_group(uses, **request), "permission_denied"),
                               (reader.read_group(stale_uses, **request), "unavailable_revision")):
            assert result.receipt["status"] == reason
            assert result.receipt["body_bytes"] == 0 and result.receipt["delivered"] == []
            assert result.bodies == ()
