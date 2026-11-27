"""Pinned CPU software-task mechanics; not merged production or performance acceptance."""

import sqlite3
import subprocess
import sys
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from itertools import count
from pathlib import Path

import pytest

from inferrsi.apps import api
from inferrsi.apps.storage import archive as archive_port
from inferrsi.apps.storage.artifact_reader import ArtifactReader
from inferrsi.benchmark import assessment, cpu_smoke, proofs
from inferrsi.benchmark import preparation as prepare_port
from inferrsi.benchmark.workers import fixture_worker as worker
from inferrsi.contracts.json_v1 import decode
from inferrsi.harness.api import Harness
from inferrsi.harness.executor import LocalCpuTarget
from inferrsi.harness.executor import _execution as execution_service
from inferrsi.harness.records import RunStore
from inferrsi.harness.records import _run_store as run_store
from tests.benchmark.test_benchmark_preparation import preparation as preparation

ROOT = Path(__file__).resolve().parents[2]


def candidates():
    # Task-defined expected answer, independent of the worker's baseline() implementation.
    return {"correct": str(sum(worker.INPUT_BYTES)).encode("ascii") + b"\n",
            "wrong": b"wrong\n", "invalid-utf8": b"\xff\n"}


def check_samples(value):
    assert value is not None
    assert [(x["sample_id"], x["role"], x["round"]) for x in value] == [
        ("A1", "baseline", 1), ("B1", "candidate", 1),
        ("B2", "candidate", 2), ("A2", "baseline", 2),
    ]
    assert all(x["unit"] == "ms" and Decimal(x["value"]) > 0 for x in value)
    proofs.validate_report({"schema_version": 1, "grader": None, "samples": value})


@pytest.mark.parametrize("kind", ["correct", "wrong", "invalid-utf8"])
def test_packaged_worker_runs_without_package_imports_and_measures_real_operations(tmp_path, kind):
    path, output = tmp_path / "candidate.txt", tmp_path / "report.json"
    path.write_bytes(candidates()[kind])
    result = subprocess.run([sys.executable, "-I", "-B", worker.__file__, str(path), str(output)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    value = proofs.decode_report(output.read_bytes())
    assert value["grader"]["status"] == ("passed" if kind == "correct" else "failed")
    check_samples(value["samples"])


def test_wrong_answer_still_executes_all_four_samples_in_order(tmp_path, monkeypatch):
    path = tmp_path / "candidate.txt"
    path.write_bytes(candidates()["wrong"])
    original_read, original_baseline = Path.read_bytes, worker.baseline
    actions = []

    def read(value):
        actions.append("B")
        return original_read(value)

    def reference():
        actions.append("A")
        return original_baseline()

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(worker, "baseline", reference)
    clock = count(step=1000)
    result = worker.evaluate(path, clock=lambda: next(clock))
    assert result["grader"]["status"] == "failed"
    assert actions == ["B", "A", "A", "B", "B", "A"]
    check_samples(result["samples"])


@pytest.mark.parametrize("values", [[0] * 8, list(range(8, 0, -1)), [True] * 8])
def test_invalid_timing_keeps_grade_but_never_fills_or_retries_samples(tmp_path, values):
    path = tmp_path / "candidate.txt"
    path.write_bytes(candidates()["correct"])
    clock = iter(values)
    reads = []

    def next_time():
        reads.append(True)
        return next(clock)

    result = worker.evaluate(path, clock=next_time)
    assert result["grader"]["status"] == "passed" and result["samples"] is None
    assert len(reads) == 8


def test_missing_candidate_produces_incomplete_families(tmp_path):
    result = worker.evaluate(tmp_path / "missing")
    assert result == {"schema_version": 1, "grader": None, "samples": None}


@pytest.mark.parametrize("nanoseconds,text", [(1, "0.000001"), (1000, "0.001"),
                                            (1_000_000, "1"), (10_000_000, "10")])
def test_integer_unit_conversion_preserves_canonical_values(nanoseconds, text):
    assert worker._milliseconds(nanoseconds) == text


def test_profile_freezes_complete_code_and_baseline_resource_closure():
    source = cpu_smoke.worker_source()
    service = cpu_smoke.prepare_service(control_domain="fixture-domain")
    prepared, protocol_bytes, reader = service.prepare(cpu_smoke.default_request())
    prepare_port.validate_prepared(prepared, protocol_bytes)
    protocol = decode(protocol_bytes)
    assert protocol["baseline"]["artifact"]["sha256"] == sha256(source).hexdigest()
    assert prepared["recipe"]["code_sha256"] == sha256(source).hexdigest()
    assert {item["role"] for item in prepared["resources"]} == {"worker-code", "baseline-code"}
    for role in ("worker-code", "baseline-code"):
        with reader(role) as stream:
            assert stream.read() == source


@pytest.mark.parametrize("kind", ["task-version", "grader-version", "mixed-pair"])
def test_unknown_or_mixed_task_versions_are_not_guessed(kind):
    protocol = cpu_smoke.protocol(cpu_smoke.worker_source(), control_domain="fixture-domain")
    if kind == "task-version":
        protocol["task"]["revision"] = "2"
    elif kind == "grader-version":
        protocol["grader"]["revision"] = "2"
    else:
        protocol["grader"] = {"name": "p1-rules", "revision": "1"}
    with pytest.raises(prepare_port.PreparationError) as rejected:
        prepare_port.PreparationService(protocol, resources=lambda role: b"",
                                         worker_role="worker-code")
    assert rejected.value.code == "UnsupportedRuleVersion"


@pytest.mark.parametrize("kind", ["task-version", "grader-version", "mixed-pair", "assessor"])
def test_result_validator_rejects_unregistered_task_grader_or_assessor(kind):
    result = decode((ROOT / "docs/contracts/fixtures/t108-v4/assessment.json").read_bytes())
    result.update(task={"name": "p1-cpu-smoke", "revision": "1"},
                  grader={"name": "p1-cpu-smoke-rules", "revision": "1"})
    if kind == "task-version":
        result["task"]["revision"] = "2"
    elif kind == "grader-version":
        result["grader"]["revision"] = "2"
    elif kind == "mixed-pair":
        result["grader"] = {"name": "p1-rules", "revision": "1"}
    else:
        result["assessor"]["revision"] = "2"
    result["assessment_id"] = assessment.assessment_id(result)
    with pytest.raises(assessment.AssessmentError) as rejected:
        assessment.validate_assessment(result)
    assert rejected.value.code == "UnsupportedRuleVersion"


@pytest.mark.parametrize("kind,publish_failure,missing", [
    ("correct", False, False), ("wrong", False, False), ("invalid-utf8", False, False),
    ("correct", True, False), ("correct", False, True),
])
def test_real_cpu_task_has_independent_claims_fixed_refs_and_original_attempt_replay(
    preparation, tmp_path, monkeypatch, kind, publish_failure, missing,
):
    _, _, _, _, _, config, directory = preparation
    service = cpu_smoke.prepare_service(control_domain=execution_service._CONTROL_DOMAIN)
    prepared_output = api.prepare(
        {"schema_version": 1, "request": cpu_smoke.default_request()}, workspace=tmp_path,
        storage_config=config, prepare_benchmark=service.prepare,
        encode_prepared=prepare_port.encode,
        validate_prepared=prepare_port.validate_prepared, output_id="cpu-prepare",
    )
    assert prepared_output.result["exit_code"] == 0, prepared_output.result
    prepared_ref = prepared_output.result["prepared_ref"]
    prepared = archive_port.read_prepared(config, prepared_ref)
    candidate = candidates()[kind]
    if not missing:
        (directory / "candidate.txt").write_bytes(candidate)
    ref = {"location": "archives/local/candidate.txt", "media_type": "text/plain",
           "sha256": sha256(candidate).hexdigest(), "size_bytes": len(candidate)}
    vector = decode((ROOT / "tests/fixtures/harness-prepared-binding/d023-null-timeout.json")
                    .read_bytes())
    vector.update(attempt_id="runtime-cpu-attempt", request_id="runtime-cpu-attempt",
                  run_id="runtime-cpu-run")
    proposal = {key: deepcopy(vector[key])
                for key in ("candidate", "inputs", "generation_record_ref")}
    proposal["candidate"]["candidate_id"] = "runtime-cpu-candidate"
    proposal["inputs"][0].update(source=ref["location"], source_ref=ref,
                                 expected_sha256=ref["sha256"])
    request = {"schema_version": 1, "prepared_ref": prepared_ref,
               "attempt": {key: vector[key] for key in execution_service.ATTEMPT_FIELDS},
               "proposal": proposal, "output_root": vector["output_root"]}
    reader = ArtifactReader(config)
    with reader.open(prepared["protocol"]) as stream:
        projector = proofs.ProofProjector(prepared, stream.read())
    projections = []

    def project(*args, **kwargs):
        projections.append(args[0])
        return projector.project(*args, **kwargs)

    capture = api.EvidenceCapture(project, candidate_role="candidate", report_role="grader")
    store = RunStore(tmp_path / "store", "test")
    target = LocalCpuTarget("fixture-cpu", "1", work_root=tmp_path / "work",
                            module_root=Path(worker.__file__).parent)
    harness = Harness(store, target, artifact_reader=reader, evidence_capture=capture)

    def publication_error(*args, **kwargs):
        raise OSError("synthetic output publication failure")

    with monkeypatch.context() as fault:
        if publish_failure:
            fault.setattr(archive_port, "_publish_directory", publication_error)
        executed = api.execute(request, workspace=tmp_path, storage_config=config,
                               execute_harness=harness.execute, output_id="cpu-execute")
    assert executed.result["exit_code"] == (6 if publish_failure else 3 if missing else 0)
    record, record_ref = executed.result["execution"], executed.result["record_ref"]
    assert record["started"] is (not missing)
    if publish_failure:
        assert executed.result["error"]["latest_record_ref"] == record_ref
    if not missing:
        assert projections == ["preparing", "finalizing"]
        assert record["cleanup"]["status"] == "confirmed" and record["exit_code"] == 0
        raw = next(x for x in record["artifacts"] if x["role"] == "grader")
        with reader.open(raw["artifact"]) as stream:
            report = proofs.decode_report(stream.read())
        check_samples(report["samples"])
        assert {x["check_id"] for x in record["checks"]} >= {
            "format", "grader", "samples", "cleanup",
        }
    else:
        assert projections == []
    assessed = api.assess(
        {"schema_version": 1, "record_ref": record_ref, "primary_scope": "p1",
         "primary_claim_id": "C"}, workspace=tmp_path, storage_config=config,
        assess_benchmark=assessment.assess, encode_assessment=assessment.encode,
        validate_assessment=assessment.validate_assessment, output_id="cpu-assess",
    )
    assert assessed.result["assessment"] is not None, assessed.result
    result = assessed.result["assessment"]
    expected = (["INCONCLUSIVE"] * 3 if missing else
                ["FAIL" if kind == "invalid-utf8" else "PASS",
                 "PASS" if kind == "correct" else "FAIL", "PASS"])
    assert [x["verdict"] for x in result["claims"]] == expected
    assert result["task"] == {"name": "p1-cpu-smoke", "revision": "1"}
    assert result["metrics"] == result["comparison"] == []
    view = api.read_attempt_view(
        record_ref, storage_config=config, assessment_ref=assessed.result["assessment_ref"],
        include_trace=True,
    )
    assert view["record_ref"] == result["record_ref"] == record_ref
    assert archive_port.read_result(tmp_path, "cpu-assess").result == assessed.result

    def forbidden(*args, **kwargs):
        pytest.fail("fixed CPU task replay implicitly launched or captured again")

    if missing:
        (directory / "candidate.txt").write_bytes(candidate)
    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    retired = Harness(store, LocalCpuTarget("retired", "2", work_root=tmp_path / "retired"),
                      artifact_reader=object(), evidence_capture=object())
    replay = api.execute(request, workspace=tmp_path, storage_config=config,
                         execute_harness=retired.execute, output_id="cpu-replay")
    assert replay.result["record_ref"] == record_ref
    assert len(projections) == (0 if missing else 2)
    with sqlite3.connect(store.root / run_store.INDEX_NAME) as connection:
        assert connection.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 1
