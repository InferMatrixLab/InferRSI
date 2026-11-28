"""Real Apps capture composition; diagnostic worker semantics, not task acceptance."""

import json
import sqlite3
from copy import deepcopy
from functools import partial
from hashlib import sha256
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from inferrsi.apps import api
from inferrsi.apps.cli import main
from inferrsi.apps.storage import archive as archive_port
from inferrsi.apps.storage.archive import read_prepared
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.apps.views.dashboard_live import DashboardServer
from inferrsi.benchmark import assessment, proofs
from inferrsi.benchmark import preparation as benchmark
from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness.executor import LocalCpuTarget, execute_attempt
from inferrsi.harness.executor import _execution as execution_service
from inferrsi.harness.records import RunStore
from inferrsi.harness.records import _run_store as run_store
from tests.benchmark.test_benchmark_preparation import preparation as preparation

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("candidate_bytes,worker_status,publish_failure", [
    (b"accept\n", "passed", False), (b"reject\n", "failed", False),
    (b"reject\n", "failed", True),
])
def test_actual_report_capture_and_assessment_share_runtime_refs(
    preparation, tmp_path, monkeypatch, capsys, candidate_bytes, worker_status, publish_failure,
):
    _, prepare_request, sources, protocol, _, config, archive = preparation
    vector = decode((ROOT / "tests/fixtures/harness-prepared-binding/"
                     "d023-null-timeout.json").read_bytes())
    worker = b"""import json, pathlib, sys
candidate = pathlib.Path(sys.argv[1]).read_bytes()
status = 'passed' if candidate == b'accept\\n' else 'failed'
proof = {'schema_version': 1, 'grader': {'status': status,
         'reasons': [] if status == 'passed' else ['probe_rejection']}, 'samples': None}
output = pathlib.Path(sys.argv[2])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(proof), encoding='utf-8')
"""
    sources["worker-code"].write_bytes(worker)
    protocol = deepcopy(protocol)
    protocol["worker_recipe"]["code_sha256"] = sha256(worker).hexdigest()
    pin = next(x for x in protocol["resources"] if x["role"] == "worker-code")
    pin["artifact"].update(sha256=sha256(worker).hexdigest(), size_bytes=len(worker))
    for required in protocol["required_evidence"]:
        required["allowed_control_domains"] = [execution_service._CONTROL_DOMAIN]
    service = benchmark.PreparationService(
        protocol, resources=lambda role: sources[role].open("rb"), worker_role="worker-code",
    )
    prepared_output = api.prepare(
        {"schema_version": 1, "request": prepare_request}, workspace=tmp_path,
        storage_config=config, prepare_benchmark=service.prepare,
        encode_prepared=benchmark.encode, validate_prepared=benchmark.validate_prepared,
        output_id="probe-prepare",
    )
    assert prepared_output.result["exit_code"] == 0
    prepared_ref = prepared_output.result["prepared_ref"]
    prepared = read_prepared(config, prepared_ref)
    vector.update(request_id="runtime-probe-47", attempt_id="runtime-probe-47",
                  run_id="runtime-run-47", output_root="attempts/runtime-probe-47")
    vector["candidate"]["candidate_id"] = "runtime-candidate-47"
    (archive / "candidate.txt").write_bytes(candidate_bytes)
    candidate_ref = {"location": "archives/local/candidate.txt", "media_type": "text/plain",
                     "sha256": sha256(candidate_bytes).hexdigest(),
                     "size_bytes": len(candidate_bytes)}
    proposal = {k: deepcopy(vector[k]) for k in ("candidate", "inputs", "generation_record_ref")}
    proposal["inputs"][0].update(source=candidate_ref["location"], source_ref=candidate_ref,
                                 expected_sha256=candidate_ref["sha256"])
    request = {
        "schema_version": 1, "prepared_ref": prepared_ref,
        "attempt": {key: vector[key] for key in execution_service.ATTEMPT_FIELDS},
        "proposal": proposal, "output_root": vector["output_root"],
    }
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "fixture_worker.py").write_bytes(worker)
    store = RunStore(tmp_path / "store", "test")
    target = LocalCpuTarget("fixture-cpu", "1", work_root=tmp_path / "work", module_root=modules)
    reader = ArtifactReader(config)
    with reader.open(prepared["protocol"]) as stream:
        projector = proofs.ProofProjector(prepared, stream.read())
    capture = api.EvidenceCapture(
        projector.project, candidate_role=prepared["candidate_contract"]["input_role"],
        report_role=prepared["recipe"]["outputs"][0]["role"],
    )
    harness = partial(
        execute_attempt, store, target, artifact_reader=reader, evidence_capture=capture
    )
    supervise = execution_service.local_process._supervise
    pids = []

    def counted(*args, **kwargs):
        result = supervise(*args, **kwargs)
        pids.append(result["pid"])
        return result

    monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
    def failed_publication(*args, **kwargs):
        raise OSError("synthetic output publication failure")

    with monkeypatch.context() as publication:
        if publish_failure:
            publication.setattr(archive_port, "_publish_directory", failed_publication)
        executed = api.execute(request, workspace=tmp_path, storage_config=config,
                               execute_harness=harness, output_id="probe-execute")
    assert executed.result["exit_code"] == (6 if publish_failure else 0), executed.result
    record = executed.result["execution"]
    record_ref = executed.result["record_ref"]
    if publish_failure:
        assert executed.result["error"]["latest_record_ref"] == record_ref
        assert executed.result["reason_code"] == "ArchivePersistenceError"
    assert record["started"] is True and record["process_outcome"] == "exited"
    assert len(pids) == 1 and pids[0] is not None
    assert record["cleanup"]["status"] == "confirmed"
    assert record["target_binding"]["control_domain"] == execution_service._CONTROL_DOMAIN
    runtime = record["target_binding"]["runtime_bindings_by_step"][0]
    assert runtime["code_sha256"] == sha256(worker).hexdigest()
    expected_checks = {"entry_code_identity", "input_identity", "format", "grader", "samples",
                       "cleanup"}
    assert {x["check_id"] for x in record["checks"]} == expected_checks
    output = next(x for x in record["artifacts"] if x["role"] == "grader")
    assert output["status"] == "available"
    with reader.open(output["artifact"]) as stream:
        raw = stream.read()
    proof = json.loads(raw)
    assert proof["grader"]["status"] == worker_status
    required = next(x for x in prepared["required_evidence"] if x["check_id"] == "grader")
    check = next(x for x in record["checks"] if x["check_id"] == "grader")
    assert check["producer"]["kind"] == "task_worker"
    with reader.open(check["evidence_refs"][0]) as stream:
        normalized = assessment._proof(stream.read(), required, record, candidate_ref["sha256"])
    assert normalized["attempt_id"] == "runtime-probe-47"
    assert normalized["candidate_id"] == "runtime-candidate-47"
    assert normalized["status"] == worker_status

    assessed = api.assess(
        {"schema_version": 1, "record_ref": record_ref,
         "primary_scope": "p1", "primary_claim_id": "C"}, workspace=tmp_path,
        storage_config=config, assess_benchmark=assessment.assess,
        validate_assessment=assessment.validate_assessment, encode_assessment=assessment.encode,
        output_id="probe-assess",
    )
    assert assessed.result["exit_code"] == (0 if worker_status == "passed" else 8), assessed.result
    result = assessed.result["assessment"]
    assert [(x["claim_id"], x["verdict"]) for x in result["claims"]] == [
        ("F", "PASS"), ("C", "PASS" if worker_status == "passed" else "FAIL"),
        ("M", "INCONCLUSIVE"),
    ]
    assert result["claims"][2]["missing_evidence"] == ["samples"]
    assert result["record_ref"] == record_ref
    view = api.read_attempt_view(
        record_ref, storage_config=config, assessment_ref=assessed.result["assessment_ref"],
        include_trace=True,
    )
    assert view["record_ref"] == record_ref
    assert view["assessment"]["claims"] == [
        {k: x[k] for k in ("claim_id", "validation_scope", "verdict", "reasons",
                           "missing_evidence")}
        for x in result["claims"]
    ]
    assert {x["check_id"] for x in view["trace"]["checks"]} == expected_checks
    assert len(list(tmp_path.rglob("manifest.json"))) == (2 if publish_failure else 3)
    assert len(list(tmp_path.rglob("result.json"))) == (2 if publish_failure else 3)
    for output_id, expected in (("probe-prepare", prepared_output), ("probe-assess", assessed)):
        assert archive_port.read_result(tmp_path, output_id).result == expected.result
    if not publish_failure:
        saved = archive_port.read_result(tmp_path, "probe-execute")
        assert saved.result == executed.result and saved.result["record_ref"] == record_ref

    flags = []
    for name, value in (("record-ref", record_ref), ("storage-config", config),
                        ("assessment-ref", assessed.result["assessment_ref"])):
        path = tmp_path / f"{name}.json"
        path.write_bytes(encode(value))
        flags.extend((f"--{name}", str(path)))
    assert main(["trace", *flags]) == 0
    assert json.loads(capsys.readouterr().out) == view
    documents = {}
    for command in ("report", "dashboard"):
        html = tmp_path / f"{command}.html"
        assert main([command, *flags, "--output", str(html)]) == 0
        capsys.readouterr()
        document = html.read_text(encoding="utf-8")
        assert record_ref["artifact"]["sha256"] in document
        assert assessed.result["assessment_ref"]["artifact"]["sha256"] in document
        assert "runtime-probe-47" in document and "INCONCLUSIVE" in document
        documents[command] = document
    with DashboardServer(None, None, 0, fixed_attempt=view) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base}/api/state", timeout=5) as response:
                assert json.load(response)["data"]["fixed_attempt"] == view
            with urlopen(base, timeout=5) as response:
                assert response.read().decode("utf-8") == documents["dashboard"]
        finally:
            server.shutdown()
            thread.join(timeout=5)

    def forbidden(*args, **kwargs):
        pytest.fail("completed attempt was implicitly executed again")

    class Never:
        open = forbidden

    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    replay = partial(
        execute_attempt,
        store,
        LocalCpuTarget("retired", "2", work_root=tmp_path / "retired"),
        artifact_reader=Never(),
        evidence_capture=object(),
    )
    replayed = api.execute(
        request,
        workspace=tmp_path,
        storage_config=config,
        execute_harness=replay,
        output_id="probe-replay",
    )
    assert replayed.result["record_ref"] == record_ref
    assert replayed.result["execution"]["request_digest"] == record["request_digest"]
    assert archive_port.read_result(tmp_path, "probe-replay").result == replayed.result
    with sqlite3.connect(store.root / run_store.INDEX_NAME) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM records").fetchone()[0] == 1
