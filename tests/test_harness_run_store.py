from __future__ import annotations

import ast
import errno
import gc
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import time
import weakref
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

import pytest

from inferrsi import _json_v1
from inferrsi.harness import run_store
from inferrsi.harness.errors import PublicError
from inferrsi.harness.run_store import Claim, CommittedRecord, RunStore, RunStoreReader
from tests.h01_run_store_child import (
    ARTIFACT,
    ARTIFACT_MEDIA_TYPE,
    CRASH,
    FIXTURES,
    REPO,
    child_env,
    make_attempt,
    make_digest,
    make_payload,
    run_child,
    start_child,
)

NAMESPACE = "h01-test"
SRC = REPO / "src"
NEW_H_CLOSURE = {"inferrsi.harness.run_store", "inferrsi.harness.errors", "inferrsi._json_v1"}
# Package initializers run on import: the existing mixed harness __init__ loads inferrsi.claim
# (the Verdict enum). This is a known residue, not an edge added by the new H modules.
PACKAGE_INIT_RESIDUE = {"inferrsi", "inferrsi.harness", "inferrsi.claim"}
FORBIDDEN_PREFIXES = (
    "inferrsi.knowledge", "inferrsi.benchmark", "inferrsi.apps", "inferrsi.evaluation",
    "inferrsi.catalog", "inferrsi.research", "inferrsi.knowledge_store", "inferrsi.inspection",
    "inferrsi.skill_catalog", "inferrsi.runspec", "inferrsi.cli", "inferrsi.arguments",
)


def _store(tmp_path: Path, **kwargs: float) -> RunStore:
    return RunStore(tmp_path / "store", NAMESPACE, **kwargs)


def _params(tmp_path: Path, **values: object) -> Path:
    path = tmp_path / "params.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def _store_params(tmp_path: Path, store: RunStore, attempt: dict, digest: str) -> Path:
    return _params(
        tmp_path, root=str(store.root), namespace=NAMESPACE, work=str(tmp_path),
        attempt=attempt, digest=digest,
    )


def _error(call, *args: object) -> PublicError:
    with pytest.raises(PublicError) as caught:
        call(*args)
    return caught.value


def _rows(store: RunStore, sql: str, args: tuple = ()) -> list[tuple]:
    with closing(sqlite3.connect(store.root / run_store.INDEX_NAME)) as conn:
        return conn.execute(sql, args).fetchall()


def _corrupt(store: RunStore, *statements: tuple[str, tuple]) -> None:
    # Simulate damage below the store API: drop the append-only guard and rewrite rows.
    with closing(sqlite3.connect(store.root / run_store.INDEX_NAME)) as conn:
        conn.execute("DROP TRIGGER records_no_update")
        for sql, args in statements:
            conn.execute(sql, args)
        conn.commit()


def test_h01_1_concurrent_processes_register_exactly_one_claim(tmp_path: Path) -> None:
    attempt = make_attempt()
    params = _params(
        tmp_path, root=str(tmp_path / "store"), namespace=NAMESPACE, work=str(tmp_path),
        attempt=attempt, digest=make_digest(attempt),
    )
    children = [start_child("contend", params) for _ in range(6)]
    try:
        (tmp_path / "go").touch()
        # The winner holds its claim until every other contender has answered.
        deadline = time.monotonic() + 120
        while sum(child.poll() is None for child in children) > 1:
            assert time.monotonic() < deadline, "contenders did not finish"
            time.sleep(0.05)
        (tmp_path / "release").touch()
        outputs = [child.communicate(timeout=120) for child in children]
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
    assert [child.returncode for child in children] == [0] * 6, [err for _, err in outputs]
    outcomes = sorted(json.loads(out)["outcome"] for out, _ in outputs)
    assert outcomes == ["AttemptInProgress"] * 5 + ["claimed"]
    store = RunStore(tmp_path / "store", NAMESPACE)
    assert _rows(store, "SELECT request_id, state FROM attempts") == [
        (attempt["attempt_id"], "registered")
    ]


def test_h01_2_same_key_with_another_digest_conflicts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest, other = make_digest(attempt), make_digest(attempt, output_root="elsewhere")
    with store.claim(attempt, digest) as claim:
        # The digest is compared before state, so a live owner does not hide the conflict.
        error = _error(store.claim, attempt, other)
        assert (error.code, error.attempt_id) == ("RequestConflict", attempt["attempt_id"])
        committed = claim.commit(make_payload(attempt, digest, 1, "finished"))
    error = _error(store.claim, attempt, other)
    assert (error.code, error.latest_record_ref) == ("RequestConflict", None)
    assert _rows(store, "SELECT request_digest, state, latest_record_version FROM attempts") == [
        (digest, "finished", 1)
    ]
    assert store.committed(attempt["attempt_id"]).payload_bytes == committed.payload_bytes


def test_h01_3_new_process_reads_the_fixed_record_hash_and_version(tmp_path: Path) -> None:
    # Commit the frozen fixture payload; its golden RecordRef hash is the byte reference.
    payload_bytes = (FIXTURES / "record-payload.json").read_bytes()
    golden = _json_v1.decode((FIXTURES / "fixed-refs.json").read_bytes())["record_ref"]
    payload = _json_v1.decode(payload_bytes)
    attempt = {
        "request_id": "att-1", "run_id": "run-1", "attempt_id": "att-1", "owner": "fixture",
        "target_request": payload["target_request"], "deadline_utc": "2099-01-01T00:00:00Z",
        "resources": {"cpu_count": 1, "memory_bytes": None, "required_capabilities": []},
        "budget": {
            "policy_ref": None, "scope_id": "campaign-1", "declared_by": "fixture",
            "dimensions": [], "required_enforcement": [],
        },
        "retry_of": None, "retry_reason": None,
    }
    store = _store(tmp_path)
    with store.claim(attempt, payload["request_digest"]) as claim:
        committed = claim.commit(payload)
    second = make_attempt()
    second_digest = make_digest(second)
    ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    with store.claim(second, second_digest) as claim:
        with_object = claim.commit(
            make_payload(second, second_digest, 1, "finished", artifact_ref=ref), [(ref, ARTIFACT)]
        )

    artifact = committed.record_ref["artifact"]
    assert committed.payload_bytes == payload_bytes
    assert {key: artifact[key] for key in ("sha256", "size_bytes", "media_type")} == {
        key: golden["artifact"][key] for key in ("sha256", "size_bytes", "media_type")
    }
    hashed = hashlib.sha256(b"att-1").hexdigest()
    assert artifact["location"] == f"stores/{NAMESPACE}/attempts/{hashed}/records/1.json"

    mount = {
        "prefix": f"stores/{NAMESPACE}", "kind": "harness_sqlite", "root": str(store.root),
        "namespace": NAMESPACE,
    }
    for record, objects in ((committed, []), (with_object, [ARTIFACT.decode("utf-8")])):
        attempt_id = record.record_ref["attempt_id"]
        result = run_child(
            "read", _params(tmp_path, mount=mount, attempt_id=attempt_id, record_version=1)
        )
        assert result.returncode == 0, result.stderr
        seen = json.loads(result.stdout)
        assert seen["latest_ref"] == record.record_ref == seen["fixed_ref"]
        assert seen["record_bytes"].encode("utf-8") == record.payload_bytes
        assert seen["objects"] == objects
        assert seen["flat_outer"] == ["controller_observation", "observed_at", "record_ref"]
        assert seen["flat_payload_equal"] is True


@pytest.mark.parametrize(
    "scenario",
    [
        "crash-claim",
        "side-effect",
        "crash-temp",
        "crash-object",
        "crash-record",
        "running-then-crash",
        "lost-response",
    ],
)
def test_h01_4_crash_points_issue_no_fake_ref(tmp_path: Path, scenario: str) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    attempt_id = attempt["attempt_id"]
    result = run_child(scenario, _store_params(tmp_path, store, attempt, digest))
    assert result.returncode == CRASH, result.stderr

    if scenario == "crash-claim":
        # The registration never committed: nothing started and the first claim is still free.
        assert _rows(store, "SELECT COUNT(*) FROM attempts") == [(0,)]
        assert _error(store.read, attempt_id).code == "NoCommittedRecord"
        with store.claim(attempt, digest) as claim:
            assert isinstance(claim, Claim)
        return
    assert _rows(store, "SELECT COUNT(*) FROM attempts") == [(1,)]
    if scenario == "lost-response":
        # Committed but the response was lost: the same key replays the original record.
        replay = store.claim(attempt, digest)
        assert isinstance(replay, CommittedRecord)
        assert replay.payload_bytes == _json_v1.encode(
            make_payload(attempt, digest, 1, "finished")
        )
        assert _error(store.read, attempt_id, 2).code == "RecordNotFound"
        return

    # The owner died before a terminal commit; its lock is free, yet nothing reruns.
    error = _error(store.claim, attempt, digest)
    assert (error.code, error.attempt_id) == ("RecoveryRequired", attempt_id)
    if scenario == "running-then-crash":
        latest = store.committed(attempt_id)
        assert latest.payload["phase"] == "running"
        assert (error.latest_record_ref, error.started) == (latest.record_ref, True)
        return
    assert (error.latest_record_ref, error.started) == (None, None)
    assert _error(store.read, attempt_id).code == "NoCommittedRecord"
    assert _rows(store, "SELECT state FROM attempts") == [("registered",)]
    assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]
    sha = hashlib.sha256(ARTIFACT).hexdigest()
    orphan = store.root / "objects" / sha[:2] / sha
    if scenario == "side-effect":
        assert (tmp_path / "side-effect.txt").read_text(encoding="utf-8") == "external side effect"
    elif scenario == "crash-temp":
        assert not orphan.exists()
        assert len(list((store.root / "tmp").iterdir())) == 1
    else:
        # Published object bytes without a committed record stay unreferenced orphans.
        assert orphan.read_bytes() == ARTIFACT


def test_h01_5_versions_are_append_only_and_no_commit_is_honest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    attempt_id = attempt["attempt_id"]
    assert _error(store.read, attempt_id).code == "NoCommittedRecord"
    assert _error(store.read, attempt_id, 1).code == "RecordNotFound"
    with store.claim(attempt, digest) as claim:
        assert _error(store.read, attempt_id).code == "NoCommittedRecord"
        first = claim.commit(make_payload(attempt, digest, 1, "running"))
        with pytest.raises(ValueError, match="record_version"):
            claim.commit(make_payload(attempt, digest, 1, "running"))
        second = claim.commit(make_payload(attempt, digest, 2, "finished"))
        with pytest.raises(ValueError, match="terminal"):
            claim.commit(make_payload(attempt, digest, 3, "finished"))

    assert first.record_ref["artifact"]["location"] != second.record_ref["artifact"]["location"]
    assert store.committed(attempt_id).record_ref == second.record_ref
    assert store.open(first.record_ref["artifact"]).read() == first.payload_bytes
    assert _error(store.read, attempt_id, 3).code == "RecordNotFound"
    with closing(sqlite3.connect(store.root / run_store.INDEX_NAME)) as conn:
        for statement, message in (
            ("UPDATE records SET payload = x'00'", "append-only"),
            ("DELETE FROM records", "append-only"),
            ("UPDATE attempts SET latest_record_version = 1", "forward"),
            ("UPDATE attempts SET owner_session = 'other'", "immutable"),
            ("DELETE FROM attempts", "retained"),
        ):
            with pytest.raises(sqlite3.DatabaseError, match=message):
                conn.execute(statement)
    assert store.committed(attempt_id, 1).payload_bytes == first.payload_bytes
    assert store.committed(attempt_id, 2).payload_bytes == second.payload_bytes


def _module_file(name: str) -> Path | None:
    base = SRC.joinpath(*name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _inferrsi_imports(module: str) -> set[str]:
    path = _module_file(module)
    if path is None:
        return set()
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join(parts + ([node.module] if node.module else []))
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    # Keep only names that resolve to a real module file; ``from inferrsi import x`` names the
    # package container and an imported attribute such as ``_json_v1`` resolves to its file.
    return {
        name for name in names
        if name.startswith("inferrsi.") and _module_file(name) is not None
    }


def test_h01_6_new_h_closure_reaches_no_legacy_k_b_or_apps_module() -> None:
    # Static closure: explicit imports of the new H modules, followed transitively.
    closure: set[str] = set()
    pending = ["inferrsi.harness.run_store"]
    while pending:
        module = pending.pop()
        if module not in closure:
            closure.add(module)
            pending.extend(_inferrsi_imports(module))
    assert closure == NEW_H_CLOSURE

    # Runtime: importing a submodule also runs each parent package's __init__. The mixed
    # ``inferrsi.harness`` __init__ loads ``inferrsi.claim`` (the Verdict enum). That is a
    # known residue of the existing package, not a legacy, K, B, or Apps module.
    code = (
        "import json, sys, inferrsi.harness.run_store; "
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] == 'inferrsi')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, env=child_env(), encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    loaded = set(json.loads(result.stdout))
    assert not [m for m in loaded if m.startswith(FORBIDDEN_PREFIXES)]
    # Keep the static graph exact. The runtime set may also include inferrsi._version
    # when setuptools_scm has written the gitignored file after `pip install -e`.
    allowed = NEW_H_CLOSURE | PACKAGE_INIT_RESIDUE | {"inferrsi._version"}
    assert loaded <= allowed
    assert NEW_H_CLOSURE | PACKAGE_INIT_RESIDUE <= loaded


def test_commit_rejects_unbacked_or_foreign_artifact_refs(tmp_path: Path) -> None:
    # A committed record must not claim status=available for bytes this store did not retain.
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    missing = run_store.artifact_ref(NAMESPACE, b"missing-bytes\n", ARTIFACT_MEDIA_TYPE)
    retained = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    foreign = run_store.artifact_ref("other-store", ARTIFACT, ARTIFACT_MEDIA_TYPE)

    with store.claim(attempt, digest) as claim:
        payload_a = make_payload(attempt, digest, 1, "finished", artifact_ref=missing)
        with pytest.raises(ValueError, match="illegal record commit"):
            claim.commit(payload_a)
        payload_b = make_payload(attempt, digest, 1, "finished", artifact_ref=foreign)
        with pytest.raises(ValueError, match="illegal record commit"):
            claim.commit(payload_b)
        payload_c = make_payload(attempt, digest, 1, "finished", artifact_ref=missing)
        with pytest.raises(ValueError, match="illegal record commit"):
            claim.commit(payload_c, [(retained, ARTIFACT)])
        assert claim.latest_record_ref is None
        assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]
        committed = claim.commit(
            make_payload(attempt, digest, 1, "finished", artifact_ref=retained),
            [(retained, ARTIFACT)],
        )
    assert committed.record_ref is not None
    assert store.open(retained).read() == ARTIFACT


def test_finished_replay_returns_the_original_record_and_starts_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    with store.claim(attempt, digest) as claim:
        committed = claim.commit(make_payload(attempt, digest, 1, "finished"))
        # The owner still holds its lock; a finished commit is replayed, not rerun.
        assert store.claim(attempt, digest) == committed
    replay = store.claim(attempt, digest)
    assert isinstance(replay, CommittedRecord)
    assert (replay.record_ref, replay.payload_bytes) == (
        committed.record_ref, committed.payload_bytes
    )
    assert _rows(store, "SELECT COUNT(*) FROM records") == [(1,)]


def test_attempt_in_progress_until_the_owner_leaves(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    claim = store.claim(attempt, digest)
    try:
        error = _error(store.claim, attempt, digest)
        assert (error.code, error.latest_record_ref, error.started) == (
            "AttemptInProgress", None, None,
        )
        first = claim.commit(make_payload(attempt, digest, 1, "running"))
        error = _error(store.claim, attempt, digest)
        assert (error.code, error.latest_record_ref, error.started) == (
            "AttemptInProgress", first.record_ref, True,
        )
    finally:
        claim.release()
    error = _error(store.claim, attempt, digest)
    assert (error.code, error.latest_record_ref) == ("RecoveryRequired", first.record_ref)
    with pytest.raises(ValueError, match="released"):
        claim.commit(make_payload(attempt, digest, 2, "finished"))

    # A committed recovery_required phase is never in progress, even with a live owner.
    other = make_attempt()
    other_digest = make_digest(other)
    with store.claim(other, other_digest) as owner:
        recovery = owner.commit(make_payload(other, other_digest, 1, "recovery_required"))
        error = _error(store.claim, other, other_digest)
        assert (error.code, error.latest_record_ref) == ("RecoveryRequired", recovery.record_ref)


def test_record_integrity_errors_never_start_or_return_bad_bytes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    with store.claim(attempt, digest) as claim:
        committed = claim.commit(make_payload(attempt, digest, 1, "finished"))
    damaged = committed.payload_bytes.replace(b'"finished"', b'"finishez"')
    assert len(damaged) == len(committed.payload_bytes) and damaged != committed.payload_bytes

    # A finished state whose registered row has no payload is also an integrity error.
    missing = make_attempt()
    missing_digest = make_digest(missing)
    store.claim(missing, missing_digest).release()
    _corrupt(
        store,
        ("UPDATE records SET payload = ? WHERE attempt_id = ?", (damaged, attempt["attempt_id"])),
        ("UPDATE attempts SET state = 'finished' WHERE attempt_id = ?", (missing["attempt_id"],)),
    )
    assert _error(store.claim, attempt, digest).code == "RecordIntegrityError"
    assert _error(store.read, attempt["attempt_id"]).code == "RecordIntegrityError"
    assert _error(store.open, committed.record_ref["artifact"]).code == "ArtifactIntegrityError"
    assert _error(store.claim, missing, missing_digest).code == "RecordIntegrityError"
    assert _rows(store, "SELECT COUNT(*) FROM records") == [(1,)]


def test_storage_failures_are_execution_persistence_errors(tmp_path: Path) -> None:
    store = _store(tmp_path, busy_timeout=0.2)
    index = store.root / run_store.INDEX_NAME
    attempt = make_attempt()
    digest = make_digest(attempt)
    with closing(sqlite3.connect(index, isolation_level=None)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        error = _error(store.claim, attempt, digest)
        blocker.execute("ROLLBACK")
    assert (error.code, error.started, error.latest_record_ref) == (
        "ExecutionPersistenceError", False, None,
    )
    assert _rows(store, "SELECT COUNT(*) FROM attempts") == [(0,)]

    with store.claim(attempt, digest) as claim:
        first = claim.commit(make_payload(attempt, digest, 1, "running"))
        payload = make_payload(attempt, digest, 2, "running")
        with closing(sqlite3.connect(index, isolation_level=None)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            error = _error(claim.commit, payload)
            blocker.execute("ROLLBACK")
        assert (error.code, error.started, error.latest_record_ref) == (
            "ExecutionPersistenceError", True, first.record_ref,
        )
        assert error.retained_refs == [first.record_ref["artifact"]]
        assert error.partial_record.proposed_record_version == 2
        assert error.to_json()["partial_record"]["phase"] == "running"
        assert store.committed(attempt["attempt_id"]).record_ref == first.record_ref

        # Artifact bytes that differ from their declared Ref never reach a record.
        ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
        staged = make_payload(attempt, digest, 2, "running", artifact_ref=ref)
        error = _error(claim.commit, staged, [(ref, b"other bytes")])
        assert (error.code, error.latest_record_ref) == (
            "ExecutionPersistenceError", first.record_ref
        )

        # A failed commit consumes no version; the owner commits it once storage works.
        second = claim.commit(payload)
        assert second.record_ref["record_version"] == 2


def test_reader_routes_only_its_own_mount_and_locations(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    with store.claim(attempt, digest) as claim:
        claim.commit(
            make_payload(attempt, digest, 1, "finished", artifact_ref=ref), [(ref, ARTIFACT)]
        )
    mount = {
        "prefix": f"stores/{NAMESPACE}", "kind": "harness_sqlite", "root": str(store.root),
        "namespace": NAMESPACE,
    }
    for bad in ({**mount, "prefix": "stores"}, {**mount, "kind": "directory"}):
        assert _error(RunStoreReader.from_mount, bad).code == "InvalidRequest"
    assert _error(RunStoreReader, store.root, "another").code == "InvalidRequest"
    assert _error(RunStore, "relative/store", NAMESPACE).code == "InvalidRequest"

    reader = RunStoreReader.from_mount(mount)
    assert reader.open(ref).read() == ARTIFACT
    for location in (
        f"stores/another/objects/{ref['sha256'][:2]}/{ref['sha256']}",
        f"stores/{NAMESPACE}/objects/../{run_store.INDEX_NAME}",
        f"stores/{NAMESPACE}/objects/00/{ref['sha256']}",
    ):
        assert _error(reader.open, {**ref, "location": location}).code == "UnsafeArtifactPath"
    absent = run_store.artifact_ref(NAMESPACE, b"never stored", ARTIFACT_MEDIA_TYPE)
    assert _error(reader.open, absent).code == "ArtifactUnavailable"
    resized = {**ref, "size_bytes": ref["size_bytes"] + 1}
    assert _error(reader.open, resized).code == "ArtifactIntegrityError"


def test_request_digest_matches_the_d023_anchor() -> None:
    spec = (FIXTURES.parent / "execution-spec-d023.json").read_bytes()
    manifest = json.loads((FIXTURES.parent / "MANIFEST-d023.json").read_text(encoding="utf-8"))
    assert run_store.request_digest(_json_v1.decode(spec)) == manifest["files"][0]["request_digest"]


def test_reentry_of_unknown_side_effect_is_recovery_required_even_with_owner_lock(
    tmp_path: Path,
) -> None:
    # D021 section 3: a committed side_effect_unknown flag is RecoveryRequired
    # before the live-lock row.
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    claim = store.claim(attempt, digest)
    try:
        payload = make_payload(attempt, digest, 1, "running")
        payload["side_effect_unknown"] = True
        committed = claim.commit(payload)
        error = _error(store.claim, attempt, digest)
        assert error.code == "RecoveryRequired"
        assert error.started is True
        assert error.latest_record_ref == committed.record_ref
        assert _rows(store, "SELECT COUNT(*) FROM attempts") == [(1,)]
        assert _rows(store, "SELECT COUNT(*) FROM records") == [(1,)]
        # The owner lock is still held; a second re-entry must not become AttemptInProgress.
        again = _error(store.claim, attempt, digest)
        assert again.code == "RecoveryRequired"
        assert again.latest_record_ref == committed.record_ref
    finally:
        claim.release()


def test_commit_rejects_a_non_mapping_payload_as_illegal_record_commit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    with store.claim(attempt, digest) as claim:
        for payload in ([], "x", None, 3):
            with pytest.raises(ValueError, match="illegal record commit"):
                claim.commit(payload)
        assert claim.latest_record_ref is None
        assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]


def test_fixed_version_read_checks_registration_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    with store.claim(attempt, digest) as claim:
        claim.commit(make_payload(attempt, digest, 1, "finished"))
    with closing(sqlite3.connect(store.root / run_store.INDEX_NAME)) as conn:
        conn.execute("DROP TRIGGER attempts_identity_fixed")
        conn.execute(
            "UPDATE attempts SET request_digest = ?",
            ("sha256:" + "ab" * 32,),
        )
        conn.commit()
    assert _error(store.committed, attempt["attempt_id"], 1).code == "RecordIntegrityError"
    assert _error(store.committed, attempt["attempt_id"]).code == "RecordIntegrityError"


def _strict_json_cases() -> list[dict]:
    path = FIXTURES / "strict-json-byte-vectors.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _strict_json_cases(), ids=lambda case: case["id"])
def test_json_v1_rejects_p0a_strict_byte_vectors(case: dict) -> None:
    with pytest.raises(_json_v1.CanonicalError) as caught:
        _json_v1.decode(bytes.fromhex(case["raw_hex"]))
    assert caught.value.stage == case["expected_rejection_stage"]


def test_json_v1_matches_p0a_codec_string_vectors() -> None:
    vectors = json.loads((FIXTURES / "codec-string-vectors.json").read_text(encoding="utf-8"))
    golden = (FIXTURES / "codec-strings.json").read_bytes()
    assert len(golden) == vectors["bytes"]
    assert hashlib.sha256(golden).hexdigest() == vectors["sha256"]
    assert _json_v1.encode(vectors["value"]) == golden
    assert _json_v1.decode(golden) == vectors["value"]
    assert _json_v1.encode(_json_v1.decode(golden)) == golden
    for case in vectors["negative_fixed_payload_bytes"]:
        with pytest.raises(_json_v1.CanonicalError):
            _json_v1.decode(case["raw_utf8"].encode("utf-8"))


def _object_path(store: RunStore, ref: Mapping) -> Path:
    digest = ref["sha256"]
    return store.root / "objects" / digest[:2] / digest


def _try_symlink(target: Path, link: Path) -> bool:
    try:
        link.symlink_to(target)
    except OSError:
        return False
    return link.is_symlink()


def test_publish_rejects_a_symlink_mode_destination(tmp_path: Path, monkeypatch) -> None:
    # Exercises the no-follow reject path even when the host cannot create symlinks.
    temp = tmp_path / "incoming.tmp"
    temp.write_bytes(ARTIFACT)
    final = tmp_path / "aa" / ("ab" * 32)
    final.parent.mkdir()
    real_lstat = os.lstat

    def fake_lstat(path, *args, **kwargs):
        if Path(path) == final:
            return os.stat_result((stat.S_IFLNK | 0o777,) + (0,) * 9)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", fake_lstat)
    with pytest.raises(run_store._StorageFault, match="not a regular file"):
        run_store._publish(temp, final)
    assert not temp.exists()


def test_commit_rejects_a_symlink_object_path_before_append(tmp_path: Path) -> None:
    # Publish and open must agree: a pre-placed symlink with the right bytes cannot
    # become a committed available artifact that open later rejects.
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    outside = tmp_path / "outside-bytes"
    outside.write_bytes(ARTIFACT)
    destination = _object_path(store, ref)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _try_symlink(outside, destination):
        pytest.skip("this host cannot create symlinks")
    with store.claim(attempt, digest) as claim:
        with pytest.raises(PublicError, match="record commit failed"):
            claim.commit(
                make_payload(attempt, digest, 1, "finished", artifact_ref=ref),
                [(ref, ARTIFACT)],
            )
        assert claim.latest_record_ref is None
        assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]
    assert destination.is_symlink()
    error = _error(store.open, ref)
    assert error.code == "UnsafeArtifactPath"


def test_commit_rejects_a_non_regular_object_path_before_append(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    destination = _object_path(store, ref)
    destination.mkdir(parents=True)
    with store.claim(attempt, digest) as claim:
        with pytest.raises(PublicError, match="record commit failed") as caught:
            claim.commit(
                make_payload(attempt, digest, 1, "finished", artifact_ref=ref),
                [(ref, ARTIFACT)],
            )
        assert caught.value.code == "ExecutionPersistenceError"
        assert claim.latest_record_ref is None
        assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]
    assert destination.is_dir()


def test_publish_fsyncs_prefix_and_objects_including_reuse(tmp_path: Path, monkeypatch) -> None:
    calls: list[Path] = []

    def record(path: Path) -> None:
        calls.append(Path(path))

    monkeypatch.setattr(run_store, "_fsync_directory", record)
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    prefix = store.root / "objects" / ref["sha256"][:2]
    objects = store.root / "objects"
    with store.claim(attempt, digest) as claim:
        claim.commit(
            make_payload(attempt, digest, 1, "running", artifact_ref=ref),
            [(ref, ARTIFACT)],
        )
        first = list(calls)
        assert first == [prefix, objects]
        calls.clear()
        # The same content address is reused; the prefix entry must still be fsync'd.
        other = make_attempt()
        other_digest = make_digest(other)
    with store.claim(other, other_digest) as claim:
        claim.commit(
            make_payload(other, other_digest, 1, "finished", artifact_ref=ref),
            [(ref, ARTIFACT)],
        )
    assert calls == [prefix]


def test_commit_does_not_append_when_directory_fsync_fails(
    tmp_path: Path, monkeypatch
) -> None:
    store = _store(tmp_path)
    objects = store.root / "objects"
    real = run_store._fsync_directory

    def boom(path: Path) -> None:
        if Path(path) == objects:
            raise OSError(errno.EIO, "injected directory fsync failure")
        real(path)

    monkeypatch.setattr(run_store, "_fsync_directory", boom)
    attempt = make_attempt()
    digest = make_digest(attempt)
    ref = run_store.artifact_ref(NAMESPACE, ARTIFACT, ARTIFACT_MEDIA_TYPE)
    with store.claim(attempt, digest) as claim:
        with pytest.raises(PublicError, match="record commit failed"):
            claim.commit(
                make_payload(attempt, digest, 1, "finished", artifact_ref=ref),
                [(ref, ARTIFACT)],
            )
        assert claim.latest_record_ref is None
        assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]


def test_abandoned_claim_releases_the_lock_on_collection(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    claim = store.claim(attempt, digest)
    held = weakref.ref(claim)
    assert _error(store.claim, attempt, digest).code == "AttemptInProgress"
    del claim
    gc.collect()
    assert held() is None
    error = _error(store.claim, attempt, digest)
    assert error.code == "RecoveryRequired"
    assert error.latest_record_ref is None
    assert _rows(store, "SELECT COUNT(*) FROM attempts") == [(1,)]
    assert _rows(store, "SELECT COUNT(*) FROM records") == [(0,)]


def test_explicit_claim_release_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attempt = make_attempt()
    digest = make_digest(attempt)
    claim = store.claim(attempt, digest)
    claim.release()
    claim.release()
    assert _error(store.claim, attempt, digest).code == "RecoveryRequired"
    with pytest.raises(ValueError, match="released"):
        claim.commit(make_payload(attempt, digest, 1, "finished"))
    # A later collection must not close the already-released fd.
    held = weakref.ref(claim)
    del claim
    gc.collect()
    assert held() is None
