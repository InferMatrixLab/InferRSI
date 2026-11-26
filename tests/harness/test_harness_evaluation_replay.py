"""Evaluation reentry is decided before preparation, target binding or a new launch."""

import json
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from inferrsi.contracts.json_v1 import encode
from inferrsi.harness import execution_service, run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError
from inferrsi.harness.executor import request_digest
from tests.benchmark.test_benchmark_preparation import preparation as preparation
from tests.harness.test_harness_entry_verification import evaluation as evaluation


def counts(case):
    with sqlite3.connect(case["store"].root / run_store.INDEX_NAME) as connection:
        return (connection.execute("SELECT count(*) FROM attempts").fetchone()[0],
                connection.execute("SELECT count(*) FROM records").fetchone()[0])


def replay_only(case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("replay attempted artifact IO, source binding, clock reset or execution")

    class Never:
        open = forbidden

    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    monkeypatch.setattr(execution_service.entry_code, "capture_module", forbidden)
    monkeypatch.setattr(execution_service, "_deadline_seconds", forbidden)
    monkeypatch.setattr(execution_service, "_budget", forbidden)
    monkeypatch.setattr(execution_service, "_capabilities", forbidden)
    retired = LocalCpuTarget("retired", "2", work_root=case["target"].work_root / "retired")
    return Harness(case["store"], retired, artifact_reader=Never())


@pytest.mark.parametrize("initial", ["exited", "mismatch", "missing"])
def test_completed_evaluation_replays_the_original_ref_without_rebinding(
    evaluation, monkeypatch, initial,
):
    case = evaluation
    saved = deepcopy(case["spec"])
    source = case["modules"] / "fixture_worker.py"
    if initial == "mismatch":
        source.write_bytes(b"changed source\n")
    elif initial == "missing":
        source.unlink()
    record = case["harness"].execute(saved)
    assert record["started"] is (initial == "exited")
    if initial == "exited":
        assert record["exit_code"] == 0
        source.unlink()
    else:
        # Repairing the source does not authorize a new execution of this attempt.
        source.write_bytes(case["source"])
    replayed = replay_only(case, monkeypatch).execute(saved)
    assert replayed["record_ref"] == record["record_ref"]
    assert replayed["target_binding"] == record["target_binding"]
    assert replayed["request_digest"] == request_digest(saved)
    assert replayed["budget_admission"] == record["budget_admission"]
    assert saved == case["spec"]
    assert counts(case) == (1, 1)


@pytest.mark.parametrize("field", ["deadline", "budget", "prepared-ref"])
def test_changed_evaluation_digest_conflicts_without_any_binding(evaluation, monkeypatch, field):
    case = evaluation
    original = case["harness"].execute(case["spec"])
    changed = deepcopy(case["spec"])
    if field == "deadline":
        changed["deadline_utc"] = "2098-01-01T00:00:00Z"
    elif field == "budget":
        changed["budget"]["scope_id"] = "another-scope"
    else:
        changed["prepared_ref"]["artifact"]["sha256"] = "0" * 64
    with pytest.raises(PublicError) as caught:
        replay_only(case, monkeypatch).execute(changed)
    assert caught.value.code == "RequestConflict"
    assert counts(case) == (1, 1)
    assert case["store"].read(original["attempt_id"])["record_ref"] == original["record_ref"]


def test_failed_commit_after_a_real_start_never_replays_the_worker(evaluation, monkeypatch):
    case = evaluation
    supervise = execution_service.local_process._supervise
    observed = []

    def counted(*args, **kwargs):
        result = supervise(*args, **kwargs)
        observed.append(result["pid"])
        return result

    monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
    monkeypatch.setattr(case["store"], "_append",
                        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("fixture")))
    with pytest.raises(PublicError) as failed:
        case["harness"].execute(case["spec"])
    assert failed.value.code == "ExecutionPersistenceError" and failed.value.started is True
    assert len(observed) == 1 and observed[0] is not None
    assert counts(case) == (1, 0)
    with pytest.raises(PublicError) as incomplete:
        replay_only(case, monkeypatch).execute(case["spec"])
    assert incomplete.value.code == "RecoveryRequired"
    assert incomplete.value.started is not False
    assert counts(case) == (1, 0) and len(observed) == 1


@pytest.mark.parametrize("live", [True, False], ids=["live-owner", "owner-gone"])
def test_existing_attempt_without_a_record_never_implicitly_starts(evaluation, monkeypatch, live):
    case = evaluation
    attempt = {key: case["spec"][key] for key in execution_service.ATTEMPT_FIELDS}
    claim = case["store"].claim(attempt, request_digest(case["spec"]))
    try:
        if not live:
            claim.release()
        with pytest.raises(PublicError) as caught:
            replay_only(case, monkeypatch).execute(case["spec"])
        assert caught.value.code == ("AttemptInProgress" if live else "RecoveryRequired")
        assert caught.value.latest_record_ref is None
        assert counts(case) == (1, 0)
    finally:
        claim.release()


def test_caller_mutation_during_preparation_read_cannot_change_the_saved_request(
    evaluation,
):
    case = evaluation
    original = deepcopy(case["spec"])

    class Mutating:
        def open(self, ref):
            case["spec"]["budget"]["scope_id"] = "mutated-caller"
            case["spec"]["output_root"] = "mutated-caller"
            return case["reader"].open(ref)

    harness = Harness(case["store"], case["target"], artifact_reader=Mutating())
    result = harness.execute(case["spec"])
    assert result["request_digest"] == request_digest(original)
    assert result["budget_admission"]["scope_id"] == original["budget"]["scope_id"]
    assert result["started"] is True and result["exit_code"] == 0


SLEEPING_WORKER = (
    b"import json,pathlib,subprocess,sys,time\n"
    b"child=subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(60)'])\n"
    b"out=pathlib.Path(sys.argv[2]); out.parent.mkdir(parents=True,exist_ok=True)\n"
    b"out.write_text(json.dumps({'child_pid':child.pid}),encoding='utf-8')\n"
    b"time.sleep(60)\n"
)


def assert_confirmed_cleanup(record):
    assert record["cleanup"]["status"] == "confirmed"
    assert record["cleanup"]["process_exit_confirmed"] is True
    assert record["resource_leases"]["leases"]
    assert all(lease["release_confirmed"] is True
               for lease in record["resource_leases"]["leases"])
    assert all(lease["release_confirmed_at"] is not None
               for lease in record["resource_leases"]["leases"])


@pytest.mark.parametrize("evaluation", [
    {"worker_code": SLEEPING_WORKER, "deadline_seconds": 3},
], indirect=True)
def test_null_step_timeout_uses_original_attempt_deadline_and_cleans_the_domain(evaluation):
    case = evaluation
    saved = deepcopy(case["spec"])
    assert saved["steps"][0]["timeout_seconds"] is None
    record = case["harness"].execute(saved)
    assert record["started"] is True and record["process_outcome"] == "timed_out"
    assert record["steps"][0]["status"] == "timed_out"
    assert record["request_digest"] == request_digest(saved)
    assert saved["deadline_utc"] == case["spec"]["deadline_utc"]
    assert record["budget_admission"]["scope_id"] == saved["budget"]["scope_id"]
    assert_confirmed_cleanup(record)


@pytest.mark.parametrize("evaluation", [
    {"worker_code": SLEEPING_WORKER, "deadline_seconds": 20},
], indirect=True)
def test_live_cpu_replay_and_cancellation_preserve_identity_without_new_starts(
    evaluation, monkeypatch,
):
    case = evaluation
    saved = deepcopy(case["spec"])
    cancellation = threading.Event()
    command = execution_service.local_process._supervise
    starts = []

    def counted(*args, **kwargs):
        starts.append(1)
        return command(*args, **kwargs)

    monkeypatch.setattr(execution_service.local_process, "_supervise", counted)
    marker = case["target"].work_root / "workspaces" / saved["output_root"] / "outputs/grader.json"
    with ThreadPoolExecutor(max_workers=1) as pool:
        original = pool.submit(case["harness"].execute, saved, cancellation=cancellation)
        try:
            stop = time.monotonic() + 10
            while not marker.exists() and not original.done() and time.monotonic() < stop:
                time.sleep(0.01)
            assert marker.exists(), "the real worker did not publish its running marker"
            assert starts == [1]
            assert counts(case) == (1, 0)
            replay = replay_only(case, monkeypatch)
            with pytest.raises(PublicError) as caught:
                replay.execute(saved)
            assert caught.value.code == "AttemptInProgress"
            assert counts(case) == (1, 0) and starts == [1]
            changed = deepcopy(saved)
            changed["budget"]["scope_id"] = "conflict-during-run"
            with pytest.raises(PublicError) as conflict:
                replay.execute(changed)
            assert conflict.value.code == "RequestConflict"
            assert starts == [1]
        finally:
            cancellation.set()
        record = original.result(timeout=15)
    assert record["started"] is True and record["process_outcome"] == "cancelled"
    assert record["cancellation"]["requested"] is True
    assert record["cancellation"]["source"] == "caller"
    assert_confirmed_cleanup(record)
    again = replay.execute(saved)
    assert again["record_ref"] == record["record_ref"]
    assert counts(case) == (1, 1) and starts == [1]


@pytest.mark.parametrize("limit", ["expired", "cancelled", "budget"])
def test_known_limits_refuse_before_source_capture_and_preserve_original_budget(
    evaluation, monkeypatch, limit,
):
    case = evaluation
    saved = deepcopy(case["spec"])
    cancellation = threading.Event()
    if limit == "expired":
        saved["deadline_utc"] = "2000-01-01T00:00:00Z"
    elif limit == "cancelled":
        cancellation.set()
    else:
        saved["budget"]["dimensions"] = [
            {"dimension": "wall-time", "unit": "second", "limit": "1", "reserve_estimate": None},
        ]

    def forbidden(*args, **kwargs):
        pytest.fail("a refused original limit reached source capture or process execution")

    monkeypatch.setattr(execution_service.entry_code, "capture_module", forbidden)
    monkeypatch.setattr(execution_service.local_process, "_supervise", forbidden)
    record = case["harness"].execute(saved, cancellation=cancellation)
    assert record["started"] is False and record["process_outcome"] == "not_started"
    assert record["request_digest"] == request_digest(saved)
    assert record["budget_admission"]["scope_id"] == saved["budget"]["scope_id"]
    if limit == "cancelled":
        assert record["cancellation"]["requested"] is True
    elif limit == "budget":
        assert record["budget_admission"]["decision"] == "rejected"
        assert all(item["reserved_capacity"] is None and item["charged_capacity"] is None
                   for item in record["budget_admission"]["dimensions"])
    assert counts(case) == (1, 1)


def test_completed_request_replays_in_a_new_controller_without_archive_or_target(evaluation):
    case = evaluation
    saved = deepcopy(case["spec"])
    record = case["harness"].execute(saved)
    case["modules"].joinpath("fixture_worker.py").unlink()
    script = (
        "import json,sys; from pathlib import Path; "
        "from inferrsi.contracts.json_v1 import decode; "
        "from inferrsi.harness import execution_service; "
        "from inferrsi.harness.api import Harness,LocalCpuTarget; "
        "from inferrsi.harness.run_store import RunStore; "
        "s=RunStore(sys.argv[1],'test'); spec=decode(sys.stdin.buffer.read()); "
        "target=LocalCpuTarget('retired','2',work_root=Path(sys.argv[1]).parent/'retired'); "
        "execution_service.prepared_binding.verify=lambda *a,**k: "
        "(_ for _ in ()).throw(RuntimeError('replay read preparation')); "
        "execution_service.local_process._supervise=lambda *a,**k: "
        "(_ for _ in ()).throw(RuntimeError('replay started a worker')); "
        "r=Harness(s,target).execute(spec); "
        "print(json.dumps([r['record_ref'],r['request_digest'],r['budget_admission']]))"
    )
    child = subprocess.run(
        [sys.executable, "-c", script, str(case["store"].root)], input=encode(saved),
        check=True, capture_output=True, timeout=30,
    )
    assert json.loads(child.stdout) == [
        record["record_ref"], record["request_digest"], record["budget_admission"],
    ]
    assert counts(case) == (1, 1)


def test_registration_race_after_lookup_still_uses_the_atomic_claim(evaluation, monkeypatch):
    case = evaluation
    saved = deepcopy(case["spec"])
    attempt = {key: saved[key] for key in execution_service.ATTEMPT_FIELDS}
    held = []

    class Racing:
        def open(self, ref):
            if not held:
                held.append(case["store"].claim(attempt, request_digest(saved)))
            return case["reader"].open(ref)

    monkeypatch.setattr(execution_service.local_process, "_supervise",
                        lambda *a, **k: pytest.fail("registration race started another worker"))
    monkeypatch.setattr(execution_service.entry_code, "capture_module",
                        lambda *a, **k: pytest.fail("registration race bound a new entry"))
    try:
        with pytest.raises(PublicError) as caught:
            Harness(case["store"], case["target"], artifact_reader=Racing()).execute(saved)
        assert caught.value.code == "AttemptInProgress"
        assert len(held) == 1 and counts(case) == (1, 0)
    finally:
        for claim in held:
            claim.release()


@pytest.mark.parametrize("malformed", ["version", "missing-code"])
def test_static_shape_errors_still_precede_existing_state_lookup(
    evaluation, monkeypatch, malformed,
):
    case = evaluation
    original = case["harness"].execute(case["spec"])
    changed = deepcopy(case["spec"])
    if malformed == "version":
        changed["schema_version"] = 2
    else:
        del changed["steps"][0]["expected_code_sha256"]
    monkeypatch.setattr(case["store"], "_reenter_if_registered",
                        lambda *a, **k: pytest.fail("malformed request queried existing state"))
    with pytest.raises(PublicError) as caught:
        case["harness"].execute(changed)
    assert caught.value.code == ("UnsupportedSchema" if malformed == "version"
                                 else "InvalidExecutionSpec")
    assert case["store"].read(original["attempt_id"])["record_ref"] == original["record_ref"]
