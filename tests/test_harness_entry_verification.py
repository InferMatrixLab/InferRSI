"""T37 happens after registration; declaration-only refusals remain in their own test file."""

import json
import sqlite3
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from inferrsi.apps import api
from inferrsi.apps.handoff.bridge import bind_execution
from inferrsi.apps.storage.archive import read_prepared
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.benchmark import preparation as benchmark
from inferrsi.contracts.json_v1 import decode
from inferrsi.harness import execution_service, run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError
from tests.test_benchmark_preparation import preparation as preparation

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def evaluation(preparation, tmp_path):
    service, request, sources, _, _, config, _ = preparation
    output = api.prepare(
        {"schema_version": 1, "request": request}, workspace=tmp_path,
        storage_config=config, prepare_benchmark=service.prepare,
        encode_prepared=benchmark.encode, validate_prepared=benchmark.validate_prepared,
    )
    assert output.result["exit_code"] == 0
    ref = output.result["prepared_ref"]
    prepared = read_prepared(config, ref)
    vector = decode((ROOT / "tests/fixtures/harness-prepared-binding/d023-null-timeout.json")
                    .read_bytes())
    controller, modules = tmp_path / "controller", tmp_path / "modules"
    controller.mkdir()
    modules.mkdir()
    source = sources["worker-code"].read_bytes()
    (modules / "fixture_worker.py").write_bytes(source)
    candidate = b"raise RuntimeError('candidate input must never replace the trusted worker')\n"
    (controller / "candidate.txt").write_bytes(candidate)
    proposal = {key: deepcopy(vector[key])
                for key in ("candidate", "inputs", "generation_record_ref")}
    proposal["inputs"][0].update(
        source="candidate.txt", source_namespace="controller", source_ref=None,
        expected_sha256=sha256(candidate).hexdigest(),
    )
    request = {
        "schema_version": 1, "prepared_ref": ref,
        "attempt": {key: vector[key] for key in execution_service.ATTEMPT_FIELDS},
        "proposal": proposal, "output_root": vector["output_root"],
    }
    spec = bind_execution(request, prepared)
    store = run_store.RunStore(tmp_path / "store", "test")
    target = LocalCpuTarget(
        "fixture-cpu", "1", work_root=tmp_path / "work", controller_root=controller,
        module_root=modules,
    )
    reader = ArtifactReader(config)
    return {"spec": spec, "store": store, "target": target, "modules": modules,
            "source": source, "reader": reader, "harness": Harness(store, target,
                                                                    artifact_reader=reader)}


def assert_fixed_refusal(case, record, status, actual):
    schema = json.loads((ROOT / "docs/contracts/schemas/contract-v1.schema.json")
                        .read_text(encoding="utf-8"))
    Draft202012Validator({**schema, "$ref": "#/$defs/ExecutionRecord"}).validate(record)
    assert record["started"] is False and record["phase"] == "finished"
    assert record["process_outcome"] == "not_started" and record["exit_code"] is None
    assert record["prepared_ref"] == case["spec"]["prepared_ref"]
    assert record["candidate"] == case["spec"]["candidate"]
    check = record["checks"][0]
    assert check["check_id"] == "entry_code_identity" and check["status"] == status
    assert check["operation"] == "evaluate" and check["validation_scope"] == "p1"
    runtime = record["target_binding"]["runtime_bindings_by_step"][0]
    assert runtime["code_sha256"] == actual
    assert all(step["status"] == "not_started" for step in record["steps"])
    if actual is not None:
        assert runtime["argv"][1:3] == ["-I", "-B"]
    assert record["resource_leases"]["leases"] == []
    saved = case["store"].read(record["attempt_id"], record["record_version"])
    assert saved["record_ref"] == record["record_ref"]
    assert saved["checks"] == record["checks"]
    with sqlite3.connect(case["store"].root / run_store.INDEX_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 1


@pytest.mark.parametrize("failure", ["mismatch", "missing"])
def test_t37_entry_failure_commits_a_not_started_record(evaluation, monkeypatch, failure):
    case = evaluation
    source = case["modules"] / "fixture_worker.py"
    if failure == "mismatch":
        observed = b"raise RuntimeError('changed worker must not start')\n"
        source.write_bytes(observed)
        actual = sha256(observed).hexdigest()
    else:
        source.unlink()
        actual = None

    def forbidden(*args, **kwargs):
        pytest.fail("T37-N1/N2 launched a process")

    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    record = case["harness"].execute(case["spec"])
    assert_fixed_refusal(
        case, record, "failed" if failure == "mismatch" else "not_performed", actual,
    )
    refs = record["checks"][0]["evidence_refs"]
    if failure == "mismatch":
        assert len(refs) == 1 and refs[0]["sha256"] == actual
        with case["reader"].open(refs[0]) as stream:
            assert stream.read() == observed
    else:
        assert refs == []
        assert record["target_binding"]["runtime_bindings_by_step"][0]["argv"] == []


@pytest.mark.parametrize("interference", ["workspace-shadow", "changed-origin"])
def test_matching_entry_executes_its_snapshot_and_retains_the_observed_digest(
    evaluation, monkeypatch, interference,
):
    case = evaluation
    supervise = execution_service.local_process._supervise
    observed_pids = []

    def counted(*args, **kwargs):
        result = supervise(*args, **kwargs)
        observed_pids.append(result["pid"])
        return result

    monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
    if interference == "workspace-shadow":
        case["spec"]["inputs"][0]["materialized_path"] = "fixture_worker.py"
        case["spec"]["steps"][0]["args"][0] = "fixture_worker.py"
    else:
        original = execution_service.entry_code.capture_module

        def capture_then_change(*args, **kwargs):
            result = original(*args, **kwargs)
            (case["modules"] / "fixture_worker.py").write_bytes(
                b"raise RuntimeError('mutable origin is not the bound entry')\n",
            )
            return result

        monkeypatch.setattr(execution_service.entry_code, "capture_module", capture_then_change)
    record = case["harness"].execute(case["spec"])
    assert record["started"] is True and record["process_outcome"] == "exited"
    assert record["exit_code"] == 0
    assert len(observed_pids) == 1 and observed_pids[0] is not None
    check = record["checks"][0]
    assert check["status"] == "passed"
    actual = sha256(case["source"]).hexdigest()
    assert record["target_binding"]["runtime_bindings_by_step"][0]["code_sha256"] == actual
    assert record["target_binding"]["runtime_bindings_by_step"][0]["argv"][1:3] == ["-I", "-B"]
    with case["reader"].open(check["evidence_refs"][0]) as stream:
        assert stream.read() == case["source"]
    assert "verdict" not in record


@pytest.mark.parametrize("failure", ["mismatch", "missing"])
def test_t37_commit_failure_preserves_not_started_and_no_committed_record(
    evaluation, monkeypatch, failure,
):
    case = evaluation
    source = case["modules"] / "fixture_worker.py"
    if failure == "missing":
        source.unlink()
    else:
        source.write_bytes(b"changed worker\n")

    def fail_commit(*args, **kwargs):
        raise sqlite3.OperationalError("fixture commit failure")

    monkeypatch.setattr(case["store"], "_append", fail_commit)
    monkeypatch.setattr(execution_service.local_process, "_supervise",
                        lambda *a, **k: pytest.fail("failed T37 commit started a process"))
    with pytest.raises(PublicError) as caught:
        case["harness"].execute(case["spec"])
    assert caught.value.code == "ExecutionPersistenceError"
    assert caught.value.started is False
    assert caught.value.latest_record_ref is None
    assert caught.value.partial_record is not None
    assert caught.value.partial_record.started is False
    with pytest.raises(PublicError) as missing:
        case["store"].read(case["spec"]["attempt_id"])
    assert missing.value.code == "NoCommittedRecord"


def test_t37_fixed_mismatch_and_source_bytes_can_be_read_in_a_fresh_process(
    evaluation, monkeypatch,
):
    case = evaluation
    changed = b"raise RuntimeError('mismatching worker never executes')\n"
    source = case["modules"] / "fixture_worker.py"
    source.write_bytes(changed)
    monkeypatch.setattr(execution_service.local_process, "_supervise",
                        lambda *a, **k: pytest.fail("mismatching worker started"))
    record = case["harness"].execute(case["spec"])
    source.unlink()
    script = (
        "import sys,json,hashlib; from inferrsi.harness.run_store import RunStore,RunStoreReader; "
        "s=RunStore(sys.argv[1],'test'); r=s.read(sys.argv[2],1); "
        "ref=r['checks'][0]['evidence_refs'][0]; "
        "stream=RunStoreReader(s.root,'test').open(ref); raw=stream.read(); stream.close(); "
        "print(json.dumps([r['record_ref'],r['started'],r['checks'][0]['status'],"
        "r['target_binding']['runtime_bindings_by_step'][0]['code_sha256'],"
        "hashlib.sha256(raw).hexdigest()]))"
    )
    child = subprocess.run(
        [sys.executable, "-c", script, str(case["store"].root), record["attempt_id"]],
        check=True, capture_output=True, text=True, timeout=30,
    )
    actual = sha256(changed).hexdigest()
    assert json.loads(child.stdout) == [record["record_ref"], False, "failed", actual, actual]


def test_entry_capture_write_failure_is_not_an_unresolvable_entry(evaluation, monkeypatch):
    case = evaluation

    def fail_capture(*args, **kwargs):
        raise execution_service.entry_code.EntryCaptureError("fixture capture failure")

    monkeypatch.setattr(execution_service.entry_code, "capture_module", fail_capture)
    monkeypatch.setattr(execution_service.local_process, "_supervise",
                        lambda *a, **k: pytest.fail("failed capture started a worker"))
    with pytest.raises(PublicError) as caught:
        case["harness"].execute(case["spec"])
    assert caught.value.code == "ExecutionPersistenceError"
    assert caught.value.started is False and caught.value.latest_record_ref is None
    with pytest.raises(PublicError) as missing:
        case["store"].read(case["spec"]["attempt_id"])
    assert missing.value.code == "NoCommittedRecord"
