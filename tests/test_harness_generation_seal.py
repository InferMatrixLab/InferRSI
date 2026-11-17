"""T38 through the real Apps providers and the CPU Harness generation path."""

import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from inferrsi.apps.context_provider import ContextProvider
from inferrsi.apps.knowledge import knowledge_reader
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError
from inferrsi.harness.generation import prepare_generation
from tests.test_apps_generation_plan import _fixed_input, _provider
from tests.test_apps_generation_plan import generation as generation

_KNOWLEDGE = "package:inferrsi.common.skills.cgroup_resource_controls"


@pytest.fixture
def cpu_generation(generation, tmp_path):
    store = run_store.RunStore(tmp_path / "store", "generation")
    target_request = generation["attempt"]["target_request"]
    target = LocalCpuTarget(target_request["target_id"], target_request["config_revision"],
                            tmp_path / "work")
    harness = Harness(store, target, artifact_reader=store)
    attempt = harness.allocate(
        run_id="t38", owner="testing", target_request=target_request,
        deadline_utc="2099-01-01T00:00:00Z", resources=generation["attempt"]["resources"],
        budget=generation["attempt"]["budget"],
    )
    reader = knowledge_reader()
    revision = reader.read(_KNOWLEDGE).revision
    request = {
        "query": None, "ids": [_KNOWLEDGE], "pins": [{"name": _KNOWLEDGE, "revision": revision}],
        "selection_limits": {}, "max_bytes": 65536, "round_id": "round-t38",
    }
    context_provider = ContextProvider(reader)
    draft = context_provider.collect(request)
    context = deepcopy(generation["context"])
    context.pop("delivered_context")
    context.update(task_materials=[], allowed_feedback=[])
    metadata = {"candidate_id": "generated-t38", "kind": "text", "input_role": "candidate",
                "parent_id": None, "parent_digest": None}
    step = generation["steps"][0]
    worker = (
        "from pathlib import Path\n"
        "from hashlib import sha256\n"
        "import json\n"
        "context = Path('inputs/knowledge').read_bytes()\n"
        "plan = json.loads(Path('inputs/generation-plan.json').read_bytes())\n"
        "assert plan['context_refs'][0]['sha256'] == sha256(context).hexdigest()\n"
        f"assert plan['attempt_id'] == {attempt['attempt_id']!r}\n"
        "Path('output').mkdir()\n"
        f"Path('output/manifest.json').write_bytes({encode(metadata)!r})\n"
        "Path('output/candidate.txt').write_bytes(context)\n"
    )
    step.update(entrypoint_kind="executable", entrypoint=sys.executable, args=["-c", worker])

    def bind_inputs(candidate_context):
        sealed = candidate_context["delivered_context"]
        assert store.read_delivered_context(attempt["attempt_id"]) == sealed
        with store.open(sealed["artifact"]) as stream:
            assert stream.read() == draft.content
        return [_fixed_input("knowledge", sealed["artifact"])]

    def parse_candidate(manifest, candidate_bytes):
        assert candidate_bytes == draft.content
        return decode(manifest), {"candidate": "candidate"}

    provider = _provider(generation, bind_inputs, parse_candidate=parse_candidate)
    return store, target, harness, draft, {
        "context_provider": context_provider, "candidate_provider": provider,
        "context_request": request, "candidate_context": context, "attempt": attempt,
    }


def test_seal_commits_context_and_plan_before_cpu_execution(cpu_generation):
    store, target, harness, draft, inputs = cpu_generation
    assert not hasattr(draft, "artifact")
    attempt_id = inputs["attempt"]["attempt_id"]
    spec = prepare_generation(store, target, **inputs)
    with pytest.raises(PublicError, match="NoCommittedRecord"):
        harness.read(attempt_id)
    manifest_ref = spec["inputs"][-1]["source_ref"]
    context = store.read_delivered_context(attempt_id)
    assert context["items"] == draft.items
    with store.open(manifest_ref) as stream:
        assert decode(stream.read())["context_refs"] == [context["artifact"]]
    assert prepare_generation(store, target, **inputs) == spec

    record = harness.execute(spec)
    assert record["request_digest"] == run_store.request_digest(spec)
    assert record["attempt_id"] == attempt_id
    assert record["exit_code"] == 0
    proposal = inputs["candidate_provider"].collect_candidate(record, artifacts=store)
    assert proposal["candidate"]["context_refs"] == [context["artifact"]]
    assert proposal["generation_record_ref"] == record["record_ref"]
    assert harness.execute(spec)["record_ref"] == record["record_ref"]

    child = """
import sys
from inferrsi.harness.run_store import RunStoreReader
from inferrsi.contracts.json_v1 import encode
reader = RunStoreReader(sys.argv[1], 'generation')
delivery = reader.read_delivered_context(sys.argv[2])
sys.stdout.buffer.write(encode(delivery) + b'\\n' + reader.open(delivery['artifact']).read())
"""
    source = str(Path(__file__).resolve().parents[1] / "src")
    received = subprocess.check_output(
        [sys.executable, "-c", child, str(store.root), attempt_id],
        env={**os.environ, "PYTHONPATH": source}, timeout=30,
    )
    descriptor, data = received.split(b"\n", 1)
    assert decode(descriptor) == context
    assert data == draft.content


@pytest.mark.parametrize("after_stage", [False, True])
def test_retention_failure_exposes_neither_context_nor_plan(
    cpu_generation, monkeypatch, after_stage,
):
    store, target, harness, draft, inputs = cpu_generation
    attempt_id = inputs["attempt"]["attempt_id"]
    prospective_ref = run_store._generation_ref(
        store.namespace, run_store.attempt_hash(attempt_id), "delivered-context", draft.content,
    )
    reader = run_store.RunStoreReader(store.root, store.namespace)
    transact = run_store._transaction

    @contextmanager
    def fault(conn, *args):
        if not after_stage:
            raise sqlite3.OperationalError("stop before staging")
        with transact(conn, *args):
            yield
            with pytest.raises(PublicError, match="ArtifactUnavailable"):
                reader.open(prospective_ref)
            raise sqlite3.OperationalError("stop before commit")

    with monkeypatch.context() as patch:
        patch.setattr(run_store, "_transaction", fault)
        patch.setattr(inputs["candidate_provider"], "plan_generation",
                      lambda *args: pytest.fail("planner called after failed delivery"))
        with pytest.raises(PublicError, match="ExecutionPersistenceError") as caught:
            prepare_generation(store, target, **inputs)
    assert caught.value.stage == "delivered-context-retention"
    with pytest.raises(PublicError, match="ArtifactUnavailable"):
        reader.open(prospective_ref)
    with pytest.raises(PublicError, match="ArtifactUnavailable"):
        reader.read_delivered_context(attempt_id)
    with store._connection() as conn:
        assert conn.execute("SELECT count(*) FROM generation_inputs").fetchone()[0] == 0
    with pytest.raises(PublicError, match="NoCommittedRecord"):
        harness.read(attempt_id)

    spec = prepare_generation(store, target, **inputs)
    assert spec["attempt_id"] == attempt_id
    assert reader.read_delivered_context(attempt_id)["artifact"] == prospective_ref


@pytest.mark.parametrize("field", ["context_request", "candidate_context", "attempt"])
def test_same_attempt_rejects_changed_preparation(cpu_generation, monkeypatch, field):
    store, target, _, _, inputs = cpu_generation
    attempt_id = inputs["attempt"]["attempt_id"]
    first = prepare_generation(store, target, **inputs)
    committed = store.read_delivered_context(attempt_id)
    changes = {"context_request": {"max_bytes": 0},
               "candidate_context": {"generation_id": "different-generation"},
               "attempt": {"deadline_utc": "2099-02-01T00:00:00Z"}}
    changed = {**inputs[field], **changes[field]}
    monkeypatch.setattr(inputs["context_provider"], "collect",
                        lambda request: pytest.fail("committed delivery was recollected"))
    with pytest.raises(PublicError, match="RequestConflict"):
        prepare_generation(store, target, **{**inputs, field: changed})
    assert store.read_delivered_context(attempt_id) == committed
    assert prepare_generation(store, target, **inputs) == first


def test_generation_slots_are_append_only_through_sqlite(cpu_generation):
    store, target, _, _, inputs = cpu_generation
    spec = prepare_generation(store, target, **inputs)
    id_ = spec["attempt_id"]
    delivery = store.read_delivered_context(id_)
    key = run_store.attempt_hash(id_)
    # Direct SQLite clients use the default recursive-trigger setting.
    with sqlite3.connect(store.root / run_store.INDEX_NAME) as conn:
        for operation in (
            "UPDATE generation_inputs SET data = X'ff' WHERE attempt_hash = ?",
            "DELETE FROM generation_inputs WHERE attempt_hash = ?",
            "INSERT OR REPLACE INTO generation_inputs(attempt_hash, role, sha256, data) "
            "VALUES (?, 'delivered-context', 'changed', X'ff')",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="generation inputs"):
                conn.execute(operation, (key,))
    assert store.read_delivered_context(id_) == delivery
    assert prepare_generation(store, target, **inputs) == spec


def test_manifest_commit_failure_keeps_delivery_without_registering_execution(
    cpu_generation, monkeypatch,
):
    store, target, harness, draft, inputs = cpu_generation
    inputs["context_request"] = {**inputs["context_request"], "pins": []}
    attempt_id = inputs["attempt"]["attempt_id"]
    transact = run_store._transaction
    writes = 0

    @contextmanager
    def fail_manifest(conn, *args):
        nonlocal writes
        writes += 1
        with transact(conn, *args):
            yield
            if writes == 2:
                raise sqlite3.OperationalError("stop before manifest commit")

    with monkeypatch.context() as patch:
        patch.setattr(run_store, "_transaction", fail_manifest)
        with pytest.raises(PublicError, match="ExecutionPersistenceError") as caught:
            prepare_generation(store, target, **inputs)
    assert caught.value.stage == "generation-seal"
    delivery = store.read_delivered_context(attempt_id)
    assert delivery["items"] == draft.items
    with store._connection() as conn:
        sealed_roles = [row[0] for row in conn.execute("SELECT role FROM generation_inputs")]
        assert sealed_roles == ["delivered-context"]
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    changed_content = b"updated Knowledge bytes"
    changed = replace(
        draft, content=changed_content, sha256=sha256(changed_content).hexdigest(),
        items=[{**draft.items[0], "delivered_bytes": len(changed_content),
                "pin": {"reference": _KNOWLEDGE, "revision": "sha256:" + "1" * 64}}],
    )
    sightings = []

    def changed_knowledge(request):
        sightings.append(request)
        return changed

    monkeypatch.setattr(inputs["context_provider"], "collect", changed_knowledge)
    spec = prepare_generation(store, target, **inputs)
    assert sightings == []
    assert store.read_delivered_context(attempt_id) == delivery
    assert harness.execute(spec)["attempt_id"] == attempt_id
