"""Standalone Apps knowledge reads use fixed Bundle revisions and source authority."""

from hashlib import sha256

import pytest

from inferrsi.apps.workflows.knowledge import knowledge_reader, open_knowledge_store, read
from inferrsi.knowledge.knowledge_operations import Bundle, RevisionConflict
from inferrsi.knowledge.knowledge_store import KnowledgeStore

_IDENTITY = "inferrsi.common.skills.audit_h3_runtime_residency"


def test_knowledge_read_exposes_fixed_qualified_bundle_and_resource():
    reader = knowledge_reader()
    reference, revision, view = read(reader, _IDENTITY)
    assert reference == f"package:{_IDENTITY}"
    assert view["id"] == _IDENTITY
    assert view["revision"] == revision
    assert read(reader, reference, revision=revision) == (reference, revision, view)
    path = view["entrypoint"]
    contents = reader.resource(reference, path, revision=revision)
    assert sha256(contents).hexdigest() == view["resources"][path]
    with pytest.raises(RevisionConflict):
        read(reader, reference, revision="sha256:" + "0" * 64)


def test_checkout_read_resolves_once_without_enumerating_all_owners(tmp_path, monkeypatch):
    skills = tmp_path / "checkout" / "skills"
    skill = skills / "checkout-example"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(
        b"---\nname: checkout-example\ndescription: Test entry\n---\nExample\n",
    )
    store_root = tmp_path / "store"
    store_root.mkdir()
    store = KnowledgeStore(store_root, skill_root=skills)
    reader = knowledge_reader(skill_root=skills, store_root=store_root)
    assert reader.store.read_only
    assert reader.store.database == store.database
    resolve = reader.resolve
    resolutions = []

    def track_resolution(reference):
        resolutions.append(reference)
        return resolve(reference)

    def reject_global_scan():
        pytest.fail("An exact read loaded the global owner catalog")

    monkeypatch.setattr(reader, "resolve", track_resolution)
    monkeypatch.setattr(reader, "owners", reject_global_scan)
    reference, revision, view = read(reader, "checkout-example", material=True)
    assert reference == "checkout:checkout-example"
    assert revision == view["revision"]
    assert view["content"].endswith("Example\n")
    assert resolutions == ["checkout-example"]


def test_apps_store_requires_explicit_write_and_retains_fixed_history(tmp_path):
    root = tmp_path / "candidate-store"
    root.mkdir()
    with pytest.raises(ValueError, match="requires an existing database"):
        open_knowledge_store(store_root=root)
    with pytest.raises(ValueError, match="boolean"):
        open_knowledge_store(store_root=root, writable="yes")
    assert not list(root.iterdir())

    source = knowledge_reader().read(_IDENTITY)
    source_ref = f"package:{_IDENTITY}"
    identity = "apps-example-candidate"
    metadata = {
        **source.metadata,
        "id": identity,
        "state": "candidate",
        "derived_from": [{"ref": source_ref, "revision": source.revision}],
    }
    bundle = Bundle(metadata, source.content, source.dependencies)
    store = open_knowledge_store(store_root=root, writable=True)
    first = store.create(bundle)
    updated = Bundle(
        {**metadata, "title": "Revised candidate"}, bundle.content, bundle.dependencies,
    )
    second = store.update(updated, expected=first, reason="clarify title", evidence=[])
    with pytest.raises(RevisionConflict, match="Stale"):
        store.update(bundle, expected=first, reason="stale write", evidence=[])

    viewer = open_knowledge_store(store_root=root)
    assert viewer.history(identity) == [
        {"revision": first, "parent": None, "reason": "create", "evidence": []},
        {"revision": second, "parent": first, "reason": "clarify title", "evidence": []},
    ]
    with pytest.raises(ValueError, match="read-only"):
        viewer.update(bundle, expected=second, reason="read-only write", evidence=[])
    reader = knowledge_reader(store_root=root)
    assert read(reader, f"store:{identity}")[1] == second
    assert read(reader, f"store:{identity}", revision=first)[1] == first
