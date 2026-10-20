import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

import inferrsi
from inferrsi.knowledge_operations import Bundle, IdentityError, KnowledgeReader, RevisionConflict
from inferrsi.knowledge_store import KnowledgeStore

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "skills"
NOTES = "calibrate-serving-simulation/references/source-notes.md"
LOCAL = "calibrate-serving-simulation-local"


def adaptation(source="calibrate-serving-simulation", identity=LOCAL):
    bundle = KnowledgeReader(skill_root=ROOT).read(source)
    metadata = {
        **bundle.metadata,
        "id": identity,
        "state": "candidate",
        "derived_from": [{"ref": f"checkout:{source}", "revision": bundle.revision}],
    }
    return Bundle(metadata, dict(bundle.content), dict(bundle.dependencies))


def changed(bundle, suffix):
    content = dict(bundle.content)
    content[NOTES] += suffix
    return Bundle(dict(bundle.metadata), content, dict(bundle.dependencies))


def store_at(path):
    return KnowledgeStore(path, skill_root=ROOT)


def test_duplicate_stale_update_and_immutable_resources(tmp_path):
    store = store_at(tmp_path)
    original = adaptation()
    revision = store.create(original)
    with pytest.raises(RevisionConflict, match="Duplicate"):
        store.create(original)
    successor = changed(original, b"\nScoped interpretation amendment.\n")
    with pytest.raises(ValueError, match="evidence must be a list"):
        store.update(successor, expected=revision, reason="clarify", evidence="log.txt")
    next_revision = store.update(successor, expected=revision, reason="clarify", evidence=[])
    assert next_revision != revision
    with pytest.raises(RevisionConflict, match="Stale"):
        store.update(original, expected=revision, reason="stale", evidence=[])
    with pytest.raises(RevisionConflict, match="retained revision"):
        store.update(original, expected=next_revision, reason="revert", evidence=[])
    assert store.resource(LOCAL, NOTES, revision=revision) == original.content[NOTES]
    assert store.read(LOCAL).revision == next_revision
    assert store.history(LOCAL)[1]["parent"] == revision
    collected = store.collect(ids=[LOCAL], revisions={LOCAL: revision}, material=True)
    item = collected["items"][0]
    assert (item["revision"], item["authority"]) == (revision, "store")
    assert item["ref"] == f"store:{LOCAL}"


def test_store_cannot_shadow_read_only_identities(tmp_path):
    store = store_at(tmp_path)
    for source in ("calibrate-serving-simulation", "case.admission-drain-occupancy"):
        bundle = KnowledgeReader(skill_root=ROOT).read(source)
        copied = Bundle({**bundle.metadata, "state": "candidate"}, bundle.content, {})
        with pytest.raises(IdentityError, match="read-only checkout"):
            store.create(copied)
    package_id = KnowledgeReader().identities()[0].partition(":")[2]
    record = KnowledgeReader().read(package_id)
    copied = Bundle({**record.metadata, "state": "candidate"}, record.content, record.dependencies)
    with pytest.raises(IdentityError, match="read-only package"):
        store.create(copied)
    looped = adaptation()
    looped.metadata["derived_from"] = [{"ref": f"store:{LOCAL}", "revision": None}]
    with pytest.raises(IdentityError, match="distinct identity"):
        store.create(looped)
    malformed = adaptation()
    malformed.metadata["derived_from"] = [{"ref": "calibrate-serving-simulation"}]
    with pytest.raises(ValueError, match="authority"):
        store.create(malformed)
    assert store.identities() == []


def test_identity_added_later_to_checkout_is_ambiguous(tmp_path):
    skills = tmp_path / "checkout" / "skills"
    (skills / "later").mkdir(parents=True)
    (skills / "later" / "SKILL.md").write_text(
        "---\nname: later\ndescription: test\n---\nBody", encoding="utf-8"
    )
    workspace = tmp_path / "store"
    workspace.mkdir()
    store = KnowledgeStore(workspace, skill_root=skills)
    store.create(adaptation(identity="arrives-later"))
    (skills / "arrives-later").mkdir()
    (skills / "arrives-later" / "SKILL.md").write_text(
        "---\nname: arrives-later\ndescription: test\n---\nBody", encoding="utf-8"
    )
    reader = store.reader()
    with pytest.raises(IdentityError, match="Ambiguous"):
        reader.read("arrives-later")
    assert reader.read("store:arrives-later").metadata["state"] == "candidate"
    assert reader.collect(ids=["arrives-later"])["omissions"][0]["reason"] == "ambiguous_identity"
    with pytest.raises(IdentityError, match="read-only checkout"):
        current = store.read("arrives-later")
        store.update(changed(current, b"x"), expected=current.revision, reason="r", evidence=[])
    with pytest.raises(ValueError, match="same checkout"):
        KnowledgeReader(skill_root=ROOT, store=store)


def test_concurrent_writers_compare_expected_inside_transaction(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    original = adaptation()
    revision = store.create(original)
    lock_attempts = []
    connect = store._connect

    def traced_connect():
        connection = connect()
        connection.set_trace_callback(
            lambda sql: lock_attempts.append(sql) if sql == "BEGIN IMMEDIATE" else None
        )
        return connection

    monkeypatch.setattr(store, "_connect", traced_connect)

    def update(index):
        try:
            return store.update(
                changed(original, str(index).encode()),
                expected=revision,
                reason="concurrent amendment",
                evidence=[],
            )
        except RevisionConflict:
            return "conflict"

    # Hold the write lock so both writers pass any pre-transaction check before
    # either can publish; only an in-transaction comparison yields one conflict.
    blocker = sqlite3.connect(store.database, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending = [workers.submit(update, index) for index in (1, 2)]
        # Both writers must be waiting on the lock, well inside its 5 s timeout.
        deadline = time.monotonic() + 2
        while len(lock_attempts) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(lock_attempts) == 2
        assert not any(future.done() for future in pending)
        blocker.execute("ROLLBACK")
        blocker.close()
        results = [future.result() for future in pending]
    assert results.count("conflict") == 1
    assert len(store.history(LOCAL)) == 2


def test_database_rejection_rolls_back_complete_publication(tmp_path):
    store = store_at(tmp_path)
    original = adaptation()
    revision = store.create(original)
    with sqlite3.connect(store.database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_resource BEFORE INSERT ON resources "
            "WHEN NEW.path LIKE '%source-notes.md' "
            "BEGIN SELECT RAISE(ABORT, 'resource rejected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="resource rejected"):
        store.update(changed(original, b"new"), expected=revision, reason="blocked", evidence=[])
    assert store.read(LOCAL).revision == revision
    assert len(store.history(LOCAL)) == 1


def test_incomplete_unsafe_and_promotion_writes_fail(tmp_path):
    store = store_at(tmp_path)
    original = adaptation()
    incomplete = dict(original.content)
    del incomplete[NOTES]
    with pytest.raises(ValueError, match="Missing required"):
        store.create(Bundle(original.metadata, incomplete, {}))
    bad_metadata = {**original.metadata, "required_resources": ["missing.md"]}
    with pytest.raises(ValueError, match="Missing required"):
        store.create(Bundle(bad_metadata, original.content, {}))
    with pytest.raises(ValueError, match="Unsafe"):
        store.create(Bundle(original.metadata, {**original.content, "../outside": b"no"}, {}))
    with pytest.raises(ValueError, match="Missing dependency"):
        store.create(Bundle(original.metadata, original.content, {"missing": "sha256:" + "0" * 64}))
    with pytest.raises(ValueError, match="candidate"):
        store.create(Bundle({**original.metadata, "state": "active"}, original.content, {}))
    entry = original.metadata["entrypoint"]
    with pytest.raises(ValueError, match="UTF-8"):
        store.create(Bundle(original.metadata, {**original.content, entry: b"\xff\xfe"}, {}))
    bad_lineage = {**original.metadata, "derived_from": [{"ref": "checkout:x", "revision": 7}]}
    with pytest.raises(ValueError, match="content revision"):
        store.create(Bundle(bad_lineage, original.content, {}))
    revision = store.create(original)
    with pytest.raises(ValueError, match="promote"):
        store.update(
            Bundle({**original.metadata, "state": "active"}, original.content, {}),
            expected=revision,
            reason="promote",
            evidence=[],
        )
    assert len(store.history(LOCAL)) == 1


def test_workspace_location_and_symlinks(tmp_path):
    with pytest.raises(ValueError, match="existing authorized"):
        store_at(tmp_path / "not-authorized-or-created")
    for skill_root in (ROOT, None):
        with pytest.raises(ValueError, match="outside read-only"):
            KnowledgeStore(REPO / "evidence", skill_root=skill_root)
    with pytest.raises(ValueError, match="outside read-only"):
        KnowledgeStore(Path(inferrsi.__file__).parent / "data", skill_root=None)
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(ValueError, match="existing authorized"):
        store_at(link)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "knowledge.sqlite3").symlink_to(target / "elsewhere.sqlite3")
    with pytest.raises(ValueError, match="symlink"):
        store_at(workspace)


def test_real_shared_resource_bundle_keeps_old_dependency_bytes(tmp_path):
    original = adaptation("inference-benchmark-design", "inference-benchmark-design-local")
    store = store_at(tmp_path)
    revision = store.create(original)
    shared = "inference-optimization-casebook/cases/admission-drain-occupancy.md"
    identity = original.metadata["id"]
    assert store.resource(identity, shared, revision=revision) == original.content[shared]
    altered = dict(original.content)
    altered[shared] += b"changed"
    with pytest.raises(RevisionConflict, match="Dependency bytes"):
        store.update(
            Bundle(original.metadata, altered, original.dependencies),
            expected=revision,
            reason="stale dependency",
            evidence=[],
        )


def _digest(paths):
    digest = hashlib.sha256()
    for root in paths:
        files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else [root]
        for path in files:
            digest.update(path.relative_to(REPO).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_operations_leave_sources_evidence_and_matrices_unchanged(tmp_path):
    watched = [
        ROOT,
        REPO / "src" / "inferrsi" / "data",
        REPO / "evidence",
        REPO / "docs" / "reference-matrix.md",
        REPO / "docs" / "searchspace-matrix.md",
    ]
    before = _digest(watched)
    store = store_at(tmp_path)
    revision = store.create(adaptation())
    store.update(changed(adaptation(), b"amend"), expected=revision, reason="r", evidence=[])
    store.collect(limit=500, material=True)
    store.reader().collect("calibration", material=True)
    store.read(LOCAL, revision=revision)
    assert _digest(watched) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["knowledge.sqlite3"]


def test_package_only_collect_without_checkout_or_yaml(tmp_path):
    script = (
        "import sys; sys.modules['yaml'] = None\n"
        "from inferrsi.knowledge_operations import KnowledgeReader\n"
        "reader = KnowledgeReader()\n"
        "result = reader.collect(tier='dependency', material=True, limit=2)\n"
        "item = result['items'][0]\n"
        "assert item['authority'] == 'package', item\n"
        "assert reader.read(item['ref'], revision=item['revision']).revision == item['revision']\n"
        "assert 'inferrsi.skill_catalog' not in sys.modules\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_read_only_store_requires_existing_database_and_creates_nothing(tmp_path):
    workspace = tmp_path / "empty"
    workspace.mkdir()
    with pytest.raises(ValueError, match="existing database"):
        KnowledgeStore(workspace, skill_root=ROOT, read_only=True)
    assert list(workspace.iterdir()) == []


def test_read_only_store_serves_reads_without_modification(tmp_path):
    # Spaces and non-ASCII in the workspace exercise the read-only file: URI quoting.
    workspace = tmp_path / "space store 文本"
    workspace.mkdir()
    store = store_at(workspace)
    revision = store.create(adaptation())
    expected = store.resource(LOCAL, NOTES, revision=revision)
    digest = hashlib.sha256(store.database.read_bytes()).hexdigest()
    viewer = KnowledgeStore(workspace, skill_root=ROOT, read_only=True)
    assert viewer.identities() == [LOCAL]
    assert viewer.read(LOCAL).revision == revision
    assert viewer.read(LOCAL, revision=revision).content[NOTES] == expected
    assert viewer.resource(LOCAL, NOTES, revision=revision) == expected
    assert [entry["revision"] for entry in viewer.history(LOCAL)] == [revision]
    item = viewer.collect(ids=[LOCAL], revisions={LOCAL: revision}, material=True)["items"][0]
    assert (item["authority"], item["revision"]) == ("store", revision)
    with closing(viewer._connect()) as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE forbidden (id TEXT)")
    assert hashlib.sha256(viewer.database.read_bytes()).hexdigest() == digest
    assert sorted(p.name for p in workspace.iterdir()) == ["knowledge.sqlite3"]


def test_read_only_store_rejects_writes(tmp_path):
    store = store_at(tmp_path)
    revision = store.create(adaptation())
    viewer = KnowledgeStore(tmp_path, skill_root=ROOT, read_only=True)
    with pytest.raises(ValueError, match="read-only"):
        viewer.create(adaptation())
    with pytest.raises(ValueError, match="read-only"):
        viewer.update(adaptation(), expected=revision, reason="amend", evidence=[])
    assert [entry["revision"] for entry in viewer.history(LOCAL)] == [revision]


def test_default_writer_construction_still_initializes_database(tmp_path):
    workspace = tmp_path / "writer"
    workspace.mkdir()
    store = KnowledgeStore(workspace, skill_root=ROOT)
    assert store.database.is_file()
    assert store.identities() == []
    assert sorted(p.name for p in workspace.iterdir()) == ["knowledge.sqlite3"]


def test_store_records_reserved_skill_root_and_rejects_mismatch(tmp_path):
    workspace = tmp_path / "reserved"
    workspace.mkdir()
    KnowledgeStore(workspace, skill_root=ROOT).create(adaptation())
    assert KnowledgeStore(workspace, skill_root=ROOT, read_only=True).identities() == [LOCAL]
    with pytest.raises(ValueError, match="reserves the skills checkout"):
        KnowledgeStore(workspace, skill_root=None, read_only=True)
    with pytest.raises(ValueError, match="reserves the skills checkout"):
        KnowledgeStore(workspace, skill_root=None)
    other = tmp_path / "nested" / "other-skills"
    other.mkdir(parents=True)
    with pytest.raises(ValueError, match="reserves the skills checkout"):
        KnowledgeStore(workspace, skill_root=other)
    package_only = tmp_path / "package-only"
    package_only.mkdir()
    KnowledgeStore(package_only, skill_root=None)
    with pytest.raises(ValueError, match="package-only"):
        KnowledgeStore(package_only, skill_root=ROOT, read_only=True)
    assert KnowledgeStore(package_only, skill_root=None, read_only=True).identities() == []
