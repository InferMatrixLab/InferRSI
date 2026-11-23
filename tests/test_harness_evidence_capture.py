"""Real H capture lifecycle with a synthetic observer; no task-quality acceptance."""

import json
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256

import pytest

from inferrsi.contracts.json_v1 import decode, encode
from inferrsi.harness import evidence_capture, execution_service, run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError
from tests.test_benchmark_preparation import preparation as preparation
from tests.test_harness_entry_verification import evaluation as evaluation

WORKER = b"""import json, pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
target = pathlib.Path(sys.argv[2])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({'observed_size': len(data)}), encoding='utf-8')
"""


def check(key, source, phase, status, proof):
    return {
        "check_id": key, "checker_revision": "1", "subject": "candidate", "phase": phase,
        "artifact_schema": {"name": key + "-proof", "revision": "1"},
        "status": status, "reasons": [] if status == "passed" else ["observer_result"],
        "proof_key": key if proof is not None else None, "source": source,
    }


class Observer:
    """Test observer for transport/provenance, not a production B grader/projector."""

    def __init__(self, *, format_status="passed", mutate=None):
        self.format_status = format_status
        self.mutate = mutate
        self.calls = []
        self.readers = []

    def capture(self, phase, facts, *, artifacts):
        self.calls.append((phase, deepcopy(facts)))
        self.readers.append(artifacts)
        candidate = next(item for item in facts["bound_inputs"]
                         if item["role"] == facts["candidate"]["input_role"])
        with artifacts.open(candidate["retained_ref"]) as stream:
            data = stream.read()
        common = {"schema_version": 1, **{key: facts[key] for key in
                  ("attempt_id", "operation", "validation_scope")}}
        identity = {**common, "candidate_id": facts["candidate"]["candidate_id"],
                    "actual_sha256": sha256(data).hexdigest()}
        draft, blobs = {"schema_version": 1, "checks": [], "errors": []}, {}
        if phase == "preparing":
            proof = None if self.format_status == "not_performed" else {
                **identity, "claim_id": "F", "checker_revision": "1",
                "status": self.format_status, "reasons": [],
            }
            draft["checks"].append(check("format", "candidate_capture", "preparing",
                                          self.format_status, proof))
            if proof is not None:
                blobs["format"] = encode(proof)
        else:
            outputs = [item for step in facts["steps"] for item in step["artifacts"]
                       if item["role"] == "grader" and item["status"] == "available"]
            proof = None
            if outputs:
                with artifacts.open(outputs[0]["artifact"]) as stream:
                    observed = json.loads(stream.read())
                assert observed["observed_size"] == len(data)
                proof = {**identity, "claim_id": "C", "checker_revision": "1",
                         "status": "passed", "reasons": []}
                blobs["grader"] = encode(proof)
            draft["checks"].append(check("grader", "worker_report", "finalizing",
                                          "passed" if proof is not None else "not_performed",
                                          proof))
            confirmed = facts["cleanup"]["status"] == "confirmed"
            blobs["cleanup"] = encode({**common, "confirmed": confirmed})
            draft["checks"].append(check("cleanup", "cleanup_capture", "finalizing",
                                          "passed" if confirmed else "failed", blobs["cleanup"]))
        if self.mutate:
            self.mutate(phase, facts, artifacts, draft, blobs)
        return draft, blobs


def host(case, observer):
    case["spec"].update(attempt_id="runtime-capture-42", request_id="runtime-capture-42",
                        run_id="runtime-run-42", output_root="attempts/runtime-capture-42")
    case["spec"]["candidate"]["candidate_id"] = "runtime-candidate-42"
    return Harness(case["store"], case["target"], artifact_reader=case["reader"],
                   evidence_capture=observer)


def counts(case):
    with sqlite3.connect(case["store"].root / run_store.INDEX_NAME) as connection:
        return (connection.execute("SELECT count(*) FROM attempts").fetchone()[0],
                connection.execute("SELECT count(*) FROM records").fetchone()[0])


@pytest.mark.parametrize("evaluation", [{"worker_code": WORKER}], indirect=True)
class TestLifecycle:
    def test_two_phases_retain_proofs_and_seal_actual_producers(self, evaluation, monkeypatch):
        case, observer = evaluation, Observer()
        service = host(case, observer)
        supervise = execution_service.local_process._supervise
        pids = []

        def counted(*args, **kwargs):
            result = supervise(*args, **kwargs)
            pids.append(result["pid"])
            return result

        monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
        record = service.execute(case["spec"])
        assert record["started"] is True and record["exit_code"] == 0
        assert len(pids) == 1 and pids[0] is not None
        assert [phase for phase, _ in observer.calls] == ["preparing", "finalizing"]
        assert observer.calls[0][1]["started"] is False
        assert observer.calls[0][1]["cleanup"] is None
        checks = {item["check_id"]: item for item in record["checks"]}
        for key in ("format", "grader", "cleanup"):
            item = checks[key]
            assert item["status"] == "passed" and item["attempt_id"] == "runtime-capture-42"
            assert item["producer"]["control_domain"] == record["target_binding"]["control_domain"]
            with case["reader"].open(item["evidence_refs"][0]) as stream:
                proof = decode(stream.read())
            assert proof["attempt_id"] == "runtime-capture-42"
            if key != "cleanup":
                assert proof["candidate_id"] == "runtime-candidate-42"
        assert checks["grader"]["producer"]["kind"] == "task_worker"
        assert checks["grader"]["producer"]["identity"] == "fixture_worker"
        assert checks["format"]["producer"]["kind"] == "harness_capture"
        assert checks["cleanup"]["producer"]["kind"] == "harness_capture"
        assert counts(case) == (1, 1)
        assert case["store"].read("runtime-capture-42")["record_ref"] == record["record_ref"]
        with pytest.raises(PublicError) as expired:
            observer.readers[0].open(observer.calls[0][1]["bound_inputs"][0]["retained_ref"])
        assert expired.value.code == "UnsafeArtifactPath"

    @pytest.mark.parametrize("format_status", ["failed", "not_performed"])
    def test_valid_format_failure_keeps_the_one_original_run(self, evaluation, format_status):
        observer = Observer(format_status=format_status)
        record = host(evaluation, observer).execute(evaluation["spec"])
        assert record["started"] is True and record["exit_code"] == 0
        item = next(x for x in record["checks"] if x["check_id"] == "format")
        assert item["status"] == format_status
        assert bool(item["evidence_refs"]) is (format_status == "failed")
        assert counts(evaluation) == (1, 1)

    @pytest.mark.parametrize("kind", ["producer", "proof-producer", "attempt", "schema",
                                      "proof-version", "source", "orphan",
                                      "status", "wrong-hash", "phase"])
    def test_illegal_preparing_callback_commits_zero_start_refusal(
        self, evaluation, monkeypatch, kind,
    ):
        def mutate(phase, facts, reader, draft, blobs):
            if phase != "preparing":
                pytest.fail("fixed refusal reached finalizing capture")
            if kind == "producer":
                draft["checks"][0]["producer"] = {"kind": "harness_capture"}
            elif kind == "schema":
                draft["schema_version"] = 2
            elif kind == "source":
                draft["checks"][0]["source"] = {}
            elif kind == "orphan":
                blobs["orphan"] = b"{}"
            elif kind == "phase":
                draft["checks"][0]["phase"] = "finalizing"
            else:
                proof = decode(blobs["format"])
                if kind == "attempt":
                    proof["attempt_id"] = "foreign"
                elif kind == "wrong-hash":
                    proof["actual_sha256"] = "b" * 64
                elif kind == "proof-producer":
                    proof["producer"] = {"kind": "harness_capture"}
                elif kind == "proof-version":
                    proof["schema_version"] = True
                else:
                    proof["status"] = "failed"
                blobs["format"] = encode(proof)

        def forbidden(*args, **kwargs):
            pytest.fail("illegal capture launched a worker")

        monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
        observer = Observer(mutate=mutate)
        record = host(evaluation, observer).execute(evaluation["spec"])
        assert record["started"] is False and record["process_outcome"] == "not_started"
        assert all(step["status"] == "not_started" for step in record["steps"])
        assert record["resource_leases"]["leases"] == [] and counts(evaluation) == (1, 1)
        assert record["checks"][-1]["check_id"] == "evaluation_capture"
        assert record["checks"][-1]["status"] == "not_performed"
        assert record["errors"] and len(observer.calls) == 1

    @pytest.mark.parametrize("kind", ["identity", "cleanup"])
    def test_illegal_post_run_proof_keeps_execution_and_never_restarts(self, evaluation, kind):
        def mutate(phase, facts, reader, draft, blobs):
            if phase != "finalizing":
                return
            key = "grader" if kind == "identity" else "cleanup"
            proof = decode(blobs[key])
            if kind == "identity":
                proof["candidate_id"] = "foreign"
            else:
                proof["confirmed"] = not proof["confirmed"]
            blobs[key] = encode(proof)

        observer = Observer(mutate=mutate)
        service = host(evaluation, observer)
        record = service.execute(evaluation["spec"])
        assert record["started"] is True and record["exit_code"] == 0
        assert record["cleanup"]["status"] == "confirmed"
        assert record["checks"][-1]["check_id"] == "evaluation_capture"
        assert record["errors"][-1]["code"] == "IdentityMismatch"
        replay = service.execute(evaluation["spec"])
        assert replay["record_ref"] == record["record_ref"] and len(observer.calls) == 2
        assert counts(evaluation) == (1, 1)

    def test_callback_mutations_cannot_change_internal_identity_or_terminal_facts(self, evaluation):
        def mutate(phase, facts, reader, draft, blobs):
            facts["attempt_id"] = "foreign"
            facts["candidate"]["candidate_id"] = "foreign"
            facts["target_binding"]["control_domain"] = "foreign"
            if facts["cleanup"] is not None:
                facts["cleanup"]["status"] = "unknown"

        observer = Observer(mutate=mutate)
        record = host(evaluation, observer).execute(evaluation["spec"])
        assert record["attempt_id"] == "runtime-capture-42"
        assert record["candidate"]["candidate_id"] == "runtime-candidate-42"
        assert record["cleanup"]["status"] == "confirmed"
        assert record["target_binding"]["control_domain"] != "foreign"
        assert record["errors"] == []

    @pytest.mark.parametrize("failure", ["proof-retain", "append"])
    def test_post_run_persistence_failure_preserves_actual_started_and_no_implicit_resume(
        self, evaluation, monkeypatch, failure,
    ):
        case, observer = evaluation, Observer()
        service = host(case, observer)
        if failure == "proof-retain":
            retain = case["store"]._retain

            def fail_bytes(ref, source):
                if isinstance(source, bytes):
                    raise OSError("synthetic proof retention failure")
                return retain(ref, source)

            monkeypatch.setattr(case["store"], "_retain", fail_bytes)
        else:
            monkeypatch.setattr(case["store"], "_append",
                                lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic")))
        with pytest.raises(PublicError) as failed:
            service.execute(case["spec"])
        assert failed.value.code == "ExecutionPersistenceError" and failed.value.started is True
        partial = failed.value.to_json()["partial_record"]
        assert partial["started"] is True and partial["steps"][0]["exit_code"] == 0
        assert any(x["check_id"] == "grader" for x in partial["checks"])
        assert failed.value.latest_record_ref is None and counts(case) == (1, 0)
        with pytest.raises(PublicError) as replayed:
            service.execute(case["spec"])
        assert replayed.value.code == "RecoveryRequired" and len(observer.calls) == 2

    def test_replay_and_digest_conflict_do_not_call_capture_or_start(self, evaluation, monkeypatch):
        case, observer = evaluation, Observer()
        service = host(case, observer)
        record = service.execute(case["spec"])

        def forbidden(*args, **kwargs):
            pytest.fail("reentry called capture or launched a worker")

        monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
        retired = LocalCpuTarget("retired", "2", work_root=case["target"].work_root / "retired")
        replay = Harness(case["store"], retired, artifact_reader=object(),
                         evidence_capture=object())
        assert replay.execute(case["spec"])["record_ref"] == record["record_ref"]
        changed = deepcopy(case["spec"])
        changed["deadline_utc"] = "2098-01-01T00:00:00Z"
        with pytest.raises(PublicError) as conflict:
            replay.execute(changed)
        assert conflict.value.code == "RequestConflict" and len(observer.calls) == 2

    def test_unknown_host_programming_error_propagates_and_attempt_is_not_retried(self, evaluation):
        def mutate(*args):
            raise TypeError("synthetic host bug")

        observer = Observer(mutate=mutate)
        service = host(evaluation, observer)
        with pytest.raises(TypeError, match="synthetic host bug"):
            service.execute(evaluation["spec"])
        assert counts(evaluation) == (1, 0)
        with pytest.raises(PublicError) as replay:
            service.execute(evaluation["spec"])
        assert replay.value.code == "RecoveryRequired"

    def test_report_version_gap_is_retained_without_erasing_independent_facts(self, evaluation):
        def mutate(phase, facts, reader, draft, blobs):
            if phase == "finalizing":
                item = draft["checks"][0]
                item.update(status="not_performed", proof_key=None,
                            reasons=["unsupported_report_revision"])
                blobs.pop("grader")
                draft["errors"] = [{"code": "UnsupportedSchema", "check_ids": ["grader"],
                                    "reason": "unsupported_report_revision"}]

        record = host(evaluation, Observer(mutate=mutate)).execute(evaluation["spec"])
        checks = {item["check_id"]: item for item in record["checks"]}
        assert record["started"] is True and record["exit_code"] == 0
        assert checks["format"]["status"] == checks["cleanup"]["status"] == "passed"
        assert checks["grader"]["status"] == "not_performed"
        assert checks["grader"]["evidence_refs"] == []
        assert record["errors"][-1]["code"] == "UnsupportedSchema"

    def test_bad_capture_configuration_is_a_fixed_zero_start_refusal(self, evaluation, monkeypatch):
        def forbidden(*args, **kwargs):
            pytest.fail("bad capture configuration started a worker")

        monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
        record = host(evaluation, object()).execute(evaluation["spec"])
        assert record["started"] is False and record["errors"][-1]["code"] == "InvalidExecutionSpec"
        assert counts(evaluation) == (1, 1)

    def test_unread_source_cannot_be_sealed_as_a_capture_proof(self, evaluation, monkeypatch):
        class Unread:
            def capture(self, phase, facts, *, artifacts):
                proof = {"schema_version": 1, **{key: facts[key] for key in
                         ("attempt_id", "operation", "validation_scope")},
                         "candidate_id": facts["candidate"]["candidate_id"],
                         "actual_sha256": facts["bound_inputs"][0]["actual_sha256"]}
                return ({"schema_version": 1, "errors": [], "checks": [
                    check("format", "candidate_capture", "preparing", "passed", proof),
                ]}, {"format": encode(proof)})

        def forbidden(*args, **kwargs):
            pytest.fail("unobserved source assertion started a worker")

        monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
        record = host(evaluation, Unread()).execute(evaluation["spec"])
        assert record["started"] is False and record["errors"][-1]["code"] == "IdentityMismatch"

    def test_ordinary_mode_does_not_consult_capture_configuration(self, evaluation):
        service = host(evaluation, object())
        spec = evaluation["spec"]
        spec.update(prepared_ref=None, protocol_digest=None, operation=None,
                    validation_scope=None, candidate=None, inputs=[])
        spec["steps"][0].update(entrypoint_kind="executable", entrypoint=sys.executable,
                                expected_code_sha256=None, outputs=[],
                                args=["-c", "print('ordinary')"])
        record = service.execute(spec)
        assert record["started"] is True and record["exit_code"] == 0
        assert record["checks"] == [] and record["prepared_ref"] is None

    def test_cancellation_seen_during_capture_never_starts_a_worker(self, evaluation, monkeypatch):
        cancellation = threading.Event()

        def mutate(phase, *args):
            if phase == "preparing":
                cancellation.set()

        def forbidden(*args, **kwargs):
            pytest.fail("capture reset the original cancellation state")

        monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
        observer = Observer(mutate=mutate)
        record = host(evaluation, observer).execute(evaluation["spec"], cancellation=cancellation)
        assert record["started"] is False and record["process_outcome"] == "cancelled"
        assert record["resource_leases"]["leases"] == []
        assert len(observer.calls) == 2 and counts(evaluation) == (1, 1)


@pytest.mark.parametrize("evaluation", [{"worker_code": WORKER + b"import time\ntime.sleep(10)\n"}],
                         indirect=True)
def test_a_running_attempt_never_calls_capture_or_starts_a_second_worker(evaluation, monkeypatch):
    case, observer, cancellation = evaluation, Observer(), threading.Event()
    service = host(case, observer)
    supervise = execution_service.local_process._supervise
    calls, pids = [], []

    def counted(*args, **kwargs):
        calls.append(True)
        result = supervise(*args, **kwargs)
        pids.append(result["pid"])
        return result

    monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
    output = (case["target"].work_root / "workspaces" / case["spec"]["output_root"]
              / "outputs/grader.json")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.execute, case["spec"], cancellation=cancellation)
        try:
            end = time.monotonic() + 5
            while not output.is_file() and not future.done() and time.monotonic() < end:
                time.sleep(0.01)
            assert output.is_file() and not future.done()
            with pytest.raises(PublicError) as replay:
                service.execute(case["spec"])
            assert replay.value.code == "AttemptInProgress"
            assert len(observer.calls) == 1 and len(calls) == 1
        finally:
            cancellation.set()
        record = future.result(timeout=10)
    assert record["started"] is True and record["process_outcome"] == "cancelled"
    assert record["cleanup"]["status"] == "confirmed"
    assert len(pids) == 1 and pids[0] is not None
    assert len(observer.calls) == 2 and counts(case) == (1, 1)


@pytest.mark.parametrize("failure", ["foreign", "tampered", "missing"])
def test_reader_authorizes_exact_attempt_refs_and_checks_retained_bytes(tmp_path, failure):
    data = b"actual capture"
    path = tmp_path / "captured"
    path.write_bytes(data)
    ref = {"location": "stores/test/objects/" + sha256(data).hexdigest(),
           "sha256": sha256(data).hexdigest(), "size_bytes": len(data),
           "media_type": "application/octet-stream"}
    reader = evidence_capture._Reader(tmp_path, [(ref, path)])
    requested = deepcopy(ref)
    if failure == "foreign":
        requested["location"] = "foreign/" + ref["sha256"]
    elif failure == "tampered":
        path.write_bytes(b"changed bytes")
    else:
        path.unlink()
    with pytest.raises(PublicError) as caught:
        reader.open(requested)
    expected = {"foreign": "UnsafeArtifactPath", "tampered": "ArtifactIntegrityError",
                "missing": "ArtifactUnavailable"}
    assert caught.value.code == expected[failure]
    assert reader.opened == set()
