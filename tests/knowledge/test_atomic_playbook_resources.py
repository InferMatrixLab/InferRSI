"""Released Playbook resources that other Workflow guides navigate to."""
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

from inferrsi.knowledge.atomic_build import build_generation
from inferrsi.knowledge.atomic_generation import InstalledGeneration
from inferrsi.knowledge.atomic_reader import AtomicReader, AtomPin, AtomUse
from tests.knowledge.test_atomic_generation import RELEASE_ROOT, make_author_root
from tests.knowledge.test_atomic_reader import RELEASE, allow

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/atomic-reader/playbook-domain-v0.3.4.json"
ATOMS = Path(__file__).resolve().parents[2] / "src/inferrsi/knowledge/atoms"
LIBRARY = "src/inferrsi/knowledge/data/skill_library/"
# Canonical digests of the metadata inherited from each released checkout manifest.
OWNER_METADATA = {
    "checkout:optimization-search-policy":
        "f69689fea3effe0f8186347430ad2d0fcc6d92406e9ab43158ae9d74fbfa76e4",
    "checkout:performance-ceiling-analysis":
        "fb72e7a467bbb83077c17670d3f777f52ff01579ae1a32fede5c56e0c18886b2",
}


def test_installed_reader_reopens_original_playbook_navigation_material(tmp_path):
    baseline = json.loads(FIXTURE.read_bytes())
    assert baseline["source_commit"] == RELEASE
    authors = make_author_root(tmp_path)
    release = tmp_path / "release"
    shutil.copytree(RELEASE_ROOT, release)
    targets = list(baseline["workflow_navigation_targets"].items())
    policy = "checkout:optimization-search-policy"
    adaptation = PurePosixPath(baseline["workflow_navigation_targets"][policy])
    notes = adaptation.parent.parent / "references/source-notes.md"
    targets.append((policy, notes.as_posix()))
    resources = {}
    for owner, old_path in targets:
        path = PurePosixPath(old_path)
        old_entry = PurePosixPath(baseline["refs"][owner]["entrypoint"])
        atom_id = old_entry.parent.name + "." + path.stem
        descriptor = atom_id + ".json"
        shutil.copyfile(ATOMS / descriptor, authors / "atoms" / descriptor)
        owner_root = PurePosixPath("playbooks", old_entry.parent.name)
        location = owner_root / path.relative_to(old_entry.parent)
        body = (ATOMS / location).read_bytes()
        checksum = hashlib.sha256(body).hexdigest()
        assert baseline["files"][old_path] == {"bytes": len(body), "sha256": checksum}
        assert baseline["refs"][owner]["required_resources"][old_path] == checksum
        for copy in (authors / "atoms" / location, release / LIBRARY / path):
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(body)
        resources["checkout:" + atom_id] = (owner, old_path, body)

    target = tmp_path / "installed"
    generation = build_generation(authors, target, source_roots={RELEASE: release}, permits=allow)
    installed = InstalledGeneration(target, expected=generation)
    reader = AtomicReader(installed, permits=allow)
    for ref, (owner, path, body) in resources.items():
        pin = AtomPin(ref, installed.catalog[ref]["revision"])
        use = AtomUse(pin, (ref,))
        request = {"max_bytes": len(body), "context": {}, "operations": ("retain", "redistribute")}
        delivery = reader.read_group([use], **request)
        assert delivery.bodies == (body,)
        record, = delivery.receipt["delivered"]
        assert record["ref"] == ref and record["revision"] == pin.revision
        assert record["layer"] == "L3"
        assert record["source_range_verification"] == "verified_at_build"
        assert record["source"]["commit"] == RELEASE and record["source_path"] == LIBRARY + path
        assert record["source_byte_range"] == [0, len(body)]
        assert record["source"]["sha256"] == record["sha256"] == baseline["files"][path]["sha256"]
        _, original = installed.read_resolved(ref, revision=pin.revision)
        metadata = original.metadata
        fields = ("origin", "applicability", "limitations", "state",
                  "empirical_validation", "attribution")
        inherited = {key: metadata[key] for key in fields}
        encoded = json.dumps(inherited, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()
        assert hashlib.sha256(encoded).hexdigest() == OWNER_METADATA[owner]
        assert metadata["state"] == "candidate" and metadata["empirical_validation"] == "not_run"

        short = reader.read_group([use], **{**request, "max_bytes": len(body) - 1})
        assert short.receipt == {"status": "over_budget", "body_bytes": 0,
                                 "delivered": [], "required_bytes": len(body)}
        stale = AtomUse(AtomPin(ref, baseline["refs"][owner]["revision"]), (ref,))
        expired = reader.read_group([stale], **request)
        denied = AtomicReader(installed, permits=lambda _, action: action != "retain").read_group(
            [use], **request)
        assert expired.receipt["status"] == "unavailable_revision"
        assert denied.receipt["status"] == "permission_denied"
        assert short.bodies == expired.bodies == denied.bodies == ()
        assert not expired.receipt["delivered"] and not denied.receipt["delivered"]

    assert b"[source notes](../references/source-notes.md)" in resources[
        "checkout:optimization-search-policy.adaptation-interfaces"][2]
    notes_body = resources["checkout:optimization-search-policy.source-notes"][2]
    assert b"No source PDF is redistributed." in notes_body
