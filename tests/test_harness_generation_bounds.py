"""Retain original generation bounds without changing sealed execution identity."""

import shutil
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import run_store
from inferrsi.harness.errors import PublicError
from inferrsi.harness.generation import prepare_generation
from tests.test_apps_generation_plan import generation as generation
from tests.test_harness_generation_seal import cpu_generation as cpu_generation


def expected_bounds(spec, plan_ref):
    return {
        "schema_version": 1,
        **{key: deepcopy(spec[key]) for key in (
            "attempt_id", "run_id", "owner", "deadline_utc", "budget",
        )},
        "generation_plan": plan_ref, "request_digest": run_store.request_digest(spec),
    }


def test_bounds_are_committed_with_the_unchanged_plan_and_read_in_a_new_process(
    cpu_generation, tmp_path,
):
    store, target, harness, _, inputs = cpu_generation
    reader = run_store.RunStoreReader(store.root, store.namespace)
    attempt_id = inputs["attempt"]["attempt_id"]
    assert reader._read_generation_bounds(attempt_id) is None
    spec = prepare_generation(store, target, **inputs)
    plan_ref = spec["inputs"][-1]["source_ref"]
    expected = expected_bounds(spec, plan_ref)
    assert reader._read_generation_bounds(attempt_id) == expected
    original = encode(spec)
    with reader.open(plan_ref) as stream:
        plan_bytes = stream.read()
    assert "original_bounds" not in decode(plan_bytes)
    assert prepare_generation(store, target, **inputs) == spec
    result = harness.execute(spec)
    assert result["exit_code"] == 0
    assert result["request_digest"] == expected["request_digest"]
    assert harness.execute(spec)["record_ref"] == result["record_ref"]
    assert encode(spec) == original
    borrowed = reader._read_generation_bounds(attempt_id)
    borrowed["budget"]["scope_id"] = "caller mutation"
    assert reader._read_generation_bounds(attempt_id) == expected
    child = """
import sys
sys.path.insert(0, sys.argv[1])
from inferrsi.contracts.json_v1 import encode
from inferrsi.harness.run_store import RunStoreReader
sys.stdout.buffer.write(encode(
    RunStoreReader(sys.argv[2], 'generation')._read_generation_bounds(sys.argv[3])
))
"""
    received = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", child, str(Path(__file__).resolve().parents[1] / "src"),
         str(store.root), attempt_id], cwd=tmp_path, timeout=30,
    )
    assert decode(received) == expected


def test_failed_plan_commit_publishes_no_bounds(cpu_generation, monkeypatch):
    store, target, _, _, inputs = cpu_generation
    reader = run_store.RunStoreReader(store.root, store.namespace)
    attempt_id = inputs["attempt"]["attempt_id"]
    original_transaction = run_store._transaction
    writes = 0

    @contextmanager
    def fail_plan(connection, *args):
        nonlocal writes
        writes += 1
        with original_transaction(connection, *args):
            yield
            if writes == 2:
                assert reader._read_generation_bounds(attempt_id) is None
                raise sqlite3.OperationalError("synthetic failure before plan commit")

    with monkeypatch.context() as patch:
        patch.setattr(run_store, "_transaction", fail_plan)
        with pytest.raises(PublicError, match="ExecutionPersistenceError"):
            prepare_generation(store, target, **inputs)
    assert reader._read_generation_bounds(attempt_id) is None
    assert reader.read_delivered_context(attempt_id)
    with store._connection() as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    prepare_generation(store, target, **inputs)
    assert reader._read_generation_bounds(attempt_id) is not None


def test_legacy_repreparation_and_replay_do_not_backfill_bounds(cpu_generation, monkeypatch):
    store, target, harness, _, inputs = cpu_generation
    original_seal = store._seal_generation_input

    def legacy_seal(id_, role, data, *, descriptor=None):
        if role == "generation-plan":
            descriptor = {"request_digest": descriptor["request_digest"]}
        return original_seal(id_, role, data, descriptor=descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_seal_generation_input", legacy_seal)
        spec = prepare_generation(store, target, **inputs)
    attempt_id = spec["attempt_id"]
    key = run_store.attempt_hash(attempt_id)
    with store._connection() as connection:
        old = tuple(connection.execute(
            "SELECT sha256, data, descriptor FROM generation_inputs "
            "WHERE attempt_hash = ? AND role = 'generation-plan'", (key,),
        ).fetchone())
    assert store._read_generation_bounds(attempt_id) is None
    assert prepare_generation(store, target, **inputs) == spec
    result = harness.execute(spec)
    assert result["exit_code"] == 0
    assert prepare_generation(store, target, **inputs) == spec
    assert harness.execute(spec)["record_ref"] == result["record_ref"]
    assert store._read_generation_bounds(attempt_id) is None
    with store._connection() as connection:
        assert tuple(connection.execute(
            "SELECT sha256, data, descriptor FROM generation_inputs "
            "WHERE attempt_hash = ? AND role = 'generation-plan'", (key,),
        ).fetchone()) == old


@pytest.mark.parametrize("fault", ["checksum", "attempt", "plan", "digest", "partial", "data"])
def test_corrupt_bounds_fail_closed_without_mutating_the_original(
    cpu_generation, tmp_path, fault,
):
    store, target, _, _, inputs = cpu_generation
    spec = prepare_generation(store, target, **inputs)
    attempt_id = spec["attempt_id"]
    expected = store._read_generation_bounds(attempt_id)
    damaged = tmp_path / "damaged"
    damaged.mkdir()
    shutil.copyfile(store.root / run_store.INDEX_NAME, damaged / run_store.INDEX_NAME)
    with sqlite3.connect(damaged / run_store.INDEX_NAME) as connection:
        connection.execute("DROP TRIGGER generation_inputs_no_update")
        data, metadata = connection.execute(
            "SELECT data, descriptor FROM generation_inputs WHERE role = 'generation-plan'",
        ).fetchone()
        descriptor = decode(metadata)
        bounds = descriptor["original_bounds"]
        if fault == "checksum":
            bounds["budget"]["scope_id"] = "damaged"
        elif fault == "attempt":
            bounds["attempt_id"] = "another-attempt"
        elif fault == "plan":
            bounds["generation_plan"]["sha256"] = "0" * 64
        elif fault == "digest":
            bounds["request_digest"] = "sha256:" + "0" * 64
        elif fault == "partial":
            descriptor.pop("original_bounds_sha256")
        elif fault == "data":
            data += b" "
        if fault in {"attempt", "plan", "digest"}:
            descriptor["original_bounds_sha256"] = sha256(encode(bounds)).hexdigest()
        connection.execute(
            "UPDATE generation_inputs SET data = ?, descriptor = ? WHERE role = 'generation-plan'",
            (data, encode(descriptor)),
        )
    reader = run_store.RunStoreReader(damaged, store.namespace)
    with pytest.raises(PublicError, match="ArtifactIntegrityError") as caught:
        reader._read_generation_bounds(attempt_id)
    assert caught.value.stage == "read_generation_bounds"
    assert store._read_generation_bounds(attempt_id) == expected


def test_invalid_lookup_is_not_a_missing_historical_snapshot(cpu_generation):
    store, _, _, _, _ = cpu_generation
    with pytest.raises(PublicError, match="InvalidRequest"):
        store._read_generation_bounds("../invalid")


def test_full_declared_budget_is_retained_without_reserving_or_admitting_it(cpu_generation):
    store, target, harness, _, inputs = cpu_generation
    inputs["attempt"]["budget"].update(
        policy_ref={"name": "original-policy", "revision": "1"},
        scope_id="original-scope", declared_by="original-owner",
        dimensions=[{"dimension": "api-cost", "unit": "USD", "limit": "1",
                     "reserve_estimate": None}], required_enforcement=["api-cost"],
    )
    budget = deepcopy(inputs["attempt"]["budget"])
    spec = prepare_generation(store, target, **inputs)
    assert store._read_generation_bounds(spec["attempt_id"])["budget"] == budget
    with pytest.raises(PublicError, match="NoCommittedRecord"):
        harness.read(spec["attempt_id"])
    with store._connection() as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_bounds_storage_error_is_not_reported_as_a_missing_snapshot(cpu_generation, monkeypatch):
    store, _, _, _, inputs = cpu_generation
    reader = run_store.RunStoreReader(store.root, store.namespace)

    def unavailable():
        raise sqlite3.OperationalError("synthetic read failure")

    monkeypatch.setattr(reader, "_connection", unavailable)
    with pytest.raises(PublicError, match="ArtifactUnavailable") as caught:
        reader._read_generation_bounds(inputs["attempt"]["attempt_id"])
    assert caught.value.stage == "read_generation_bounds"
