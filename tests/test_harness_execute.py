from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from inferrsi import _json_v1
from inferrsi.harness import execution_service, input_binding, local_process, run_store
from inferrsi.harness.api import Harness, LocalCpuTarget
from inferrsi.harness.errors import PublicError
from inferrsi.harness.run_store import RunStore, RunStoreReader
from tests._gate_policy_support import ROOT, _scan, _walk, exact_pairs, load_manifest
from tests.h01_run_store_child import REPO, child_env

NAMESPACE = "h02-test"
TARGET = {"target_id": "cpu-h02", "executor_kind": "local_cpu", "config_revision": "1"}
FREE_BUDGET = {
    "policy_ref": None, "scope_id": "campaign-h02", "declared_by": "h02-test",
    "dimensions": [], "required_enforcement": [],
}
SCHEMA = REPO / "docs" / "contracts" / "schemas" / "contract-v1.schema.json"
# The new H closure: the H01/H02 modules, the canonical encoder, and the package init
# residue (the mixed ``inferrsi.harness`` __init__ loads ``inferrsi.claim``).
NEW_H_CLOSURE = {
    "inferrsi.harness.api", "inferrsi.harness.execution_service",
    "inferrsi.harness.input_binding", "inferrsi.harness.local_process",
    "inferrsi.harness.run_store", "inferrsi.harness.errors", "inferrsi._json_v1",
    "inferrsi.harness", "inferrsi.claim",
}
# Prints a grandchild's pid, then outlives any test deadline with it.
TREE = (
    "import os, subprocess, sys, time; "
    "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
    "print(p.pid, flush=True); sys.stdout.flush(); os.fsync(sys.stdout.fileno()); "
    "time.sleep(60)"
)


def alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    (tmp_path / "controller").mkdir()
    store = RunStore(tmp_path / "store", NAMESPACE)
    target = LocalCpuTarget(
        "cpu-h02", "1", work_root=tmp_path / "work", controller_root=tmp_path / "controller"
    )
    return Harness(store, target)


def step(code: str, *, step_id: str = "main", outputs=(), timeout=None) -> dict:
    return {
        "step_id": step_id, "runtime_role": "local-python", "entrypoint_kind": "executable",
        "entrypoint": sys.executable, "entrypoint_revision": "1", "expected_code_sha256": None,
        "args": ["-c", code], "cwd": ".", "outputs": list(outputs), "timeout_seconds": timeout,
    }


def output(role: str, path: str, *, required: bool = True) -> dict:
    return {"role": role, "path": path, "required": required, "media_type": "text/plain",
            "format_schema": {"name": "text", "revision": "1"}}


def make_spec(h: Harness, steps, *, inputs=(), deadline="2099-01-01T00:00:00Z",
              resources=None, budget=None, output_root=None) -> dict:
    attempt = h.allocate(
        run_id="run-h02", owner="h02-test", target_request=dict(TARGET), deadline_utc=deadline,
        resources=resources or {"cpu_count": 1, "memory_bytes": None,
                                "required_capabilities": ["local-process-tree"]},
        budget=budget or dict(FREE_BUDGET),
    )
    return {
        **attempt, "schema_version": 1, "generation_record_ref": None, "prepared_ref": None,
        "protocol_digest": None, "operation": None, "validation_scope": None,
        "inputs": list(inputs), "candidate": None, "steps": list(steps),
        "output_root": output_root or f"attempts/{attempt['attempt_id']}",
        "required_capabilities": ["local-process-tree"],
    }


def counter_code(marker: Path, tail: str = "") -> str:
    # Appends one line per real start, so a replay that starts nothing leaves it unchanged.
    return f"open({str(marker)!r}, 'a').write('x\\n'); {tail}"


def starts(marker: Path) -> int:
    return len(marker.read_text().splitlines()) if marker.exists() else 0


def error_of(call, *args, **kwargs) -> PublicError:
    with pytest.raises(PublicError) as caught:
        call(*args, **kwargs)
    return caught.value


def open_ref(h: Harness, ref: dict) -> bytes:
    return RunStoreReader(h._store.root, NAMESPACE).open(ref).read()


def attempt_rows(h: Harness) -> list:
    with sqlite3.connect(h._store.root / run_store.INDEX_NAME) as conn:
        return conn.execute("SELECT attempt_id, state FROM attempts").fetchall()


def schema_check(record: dict) -> None:
    # The contract schema is the field authority; jsonschema is optional in the dev extras.
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator({**schema, "$ref": "#/$defs/ExecutionRecord"})
    assert sorted(e.message for e in validator.iter_errors(record)) == []


def test_h02_1_real_exit_zero_is_an_execution_fact_not_a_pass(h: Harness) -> None:
    spec = make_spec(h, [step("print('ok')", outputs=[output("report", "report.json")])])
    record = h.execute(spec)
    schema_check(record)
    assert (record["phase"], record["process_outcome"], record["exit_code"]) == (
        "finished", "exited", 0,
    )
    assert record["started"] is True and record["side_effect_unknown"] is False
    # Exit 0 with a missing required output is still only facts: no verdict, no PASS.
    text = json.dumps(record)
    assert "PASS" not in text and "verdict" not in text
    report = [a for a in record["artifacts"] if a["role"] == "report"][0]
    assert (report["status"], report["artifact"]) == ("missing", None)
    assert report["reasons"] == ["not_produced", "required_output_missing"]
    stdout = [a for a in record["artifacts"] if a["role"] == "stdout"][0]
    assert open_ref(h, stdout["artifact"]).strip() == b"ok"
    binding = record["target_binding"]["runtime_bindings_by_step"][0]
    assert binding["argv"][1:] == ["-c", "print('ok')"] and binding["code_sha256"] is None
    # read returns the same fixed payload; only the three outer items differ (V15).
    again = h.read(spec["attempt_id"])
    assert again["record_ref"] == record["record_ref"]
    outer = {"record_ref", "observed_at", "controller_observation"}
    assert {k: v for k, v in again.items() if k not in outer} == {
        k: v for k, v in record.items() if k not in outer
    }


def test_h02_2_timeout_cancel_and_cleanup_are_recorded_separately(h: Harness) -> None:
    timed = h.execute(make_spec(h, [step(TREE, timeout="8")]))
    schema_check(timed)
    assert (timed["process_outcome"], timed["exit_code"]) == ("timed_out", None)
    assert timed["steps"][0]["reasons"] == ["step_timeout"]
    assert timed["cancellation"] == {"requested": False, "requested_at": None, "source": None}
    assert timed["cleanup"] == {
        "status": "confirmed", "termination_requested": True, "process_exit_confirmed": True,
        "reasons": ["process_domain_empty"],
    }
    assert timed["phase"] == "finished" and timed["errors"][0]["code"] == "timeout"
    stdout = [a for a in timed["artifacts"] if a["role"] == "stdout"][0]
    grandchild = int(open_ref(h, stdout["artifact"]))
    assert not alive(grandchild), "descendant survived the step timeout"

    event = threading.Event()
    timer = threading.Timer(8.0, event.set)
    timer.start()
    try:
        cancelled = h.execute(make_spec(h, [step(TREE)]), cancellation=event)
    finally:
        timer.cancel()
    schema_check(cancelled)
    assert cancelled["process_outcome"] == "cancelled"
    assert cancelled["cancellation"]["requested"] is True
    assert cancelled["cancellation"]["source"] == "caller"
    assert cancelled["cancellation"]["requested_at"] is not None
    assert cancelled["cleanup"]["status"] == "confirmed"
    assert cancelled["cleanup"]["termination_requested"] is True
    stdout = [a for a in cancelled["artifacts"] if a["role"] == "stdout"][0]
    assert not alive(int(open_ref(h, stdout["artifact"])))

    # A cancellation seen before the first start starts nothing and needs no cleanup.
    preset = threading.Event()
    preset.set()
    early = h.execute(make_spec(h, [step("print(1)")]), cancellation=preset)
    assert (early["process_outcome"], early["started"]) == ("cancelled", False)
    assert early["cancellation"]["requested"] is True
    assert early["cancellation"]["requested_at"] is not None
    assert early["cleanup"]["status"] == "not_needed" and early["phase"] == "finished"

    # A whole-run deadline that passed before start leaves nothing to clean.
    late = h.execute(make_spec(h, [step("print(1)")], deadline="2000-01-01T00:00:00Z"))
    assert (late["process_outcome"], late["started"]) == ("not_started", False)
    assert late["cleanup"]["status"] == "not_needed"
    assert late["steps"][0]["reasons"] == ["deadline_exhausted"]


def test_h02_3_actual_input_mismatch_commits_a_fixed_not_started(h: Harness, tmp_path) -> None:
    source = tmp_path / "controller" / "candidate.txt"
    source.write_bytes("actual bytes 实际\n".encode("utf-8"))
    actual = input_binding.file_sha256(source)[0]
    marker = tmp_path / "starts.txt"

    def spec_for(expected):
        item = {"role": "candidate", "source": "candidate.txt", "source_namespace": "controller",
                "source_ref": None, "snapshot_format": "file-v1", "expected_sha256": expected,
                "materialized_path": "inputs/candidate.txt"}
        return make_spec(h, [step(counter_code(marker))], inputs=[item])

    record = h.execute(spec_for("0" * 64))
    schema_check(record)
    assert (record["phase"], record["process_outcome"], record["started"]) == (
        "finished", "not_started", False,
    )
    assert record["cleanup"]["status"] == "not_needed" and starts(marker) == 0
    bound = record["bound_inputs"][0]
    assert (bound["identity_status"], bound["actual_sha256"], bound["expected_sha256"]) == (
        "mismatched", actual, "0" * 64,
    )
    assert bound["materialized_path"] is None
    assert record["checks"][0]["status"] == "failed"
    assert record["errors"][0]["code"] == "input_identity_mismatch"
    # The actual bytes are retained under their own hash, never as the expected Ref.
    assert open_ref(h, bound["retained_ref"]) == source.read_bytes()

    matched = h.execute(spec_for(actual))
    assert matched["bound_inputs"][0]["identity_status"] == "matched"
    assert matched["process_outcome"] == "exited" and starts(marker) == 1
    copy = h._target.work_root / "workspaces" / "attempts" / matched["attempt_id"]
    assert (copy / "inputs" / "candidate.txt").read_bytes() == source.read_bytes()

    capture_only = h.execute(spec_for(None))
    assert capture_only["bound_inputs"][0]["identity_status"] == "not_performed"
    assert capture_only["bound_inputs"][0]["actual_sha256"] == actual
    assert starts(marker) == 2


def test_h02_4_reentry_unknown_owner_and_replay_start_nothing_new(h: Harness, tmp_path) -> None:
    marker = tmp_path / "starts.txt"
    spec = make_spec(h, [step(counter_code(marker))])
    first = h.execute(spec)
    replay = h.execute(spec)
    assert replay["record_ref"] == first["record_ref"] and starts(marker) == 1
    conflict = error_of(h.execute, {**spec, "output_root": "elsewhere"})
    assert conflict.code == "RequestConflict" and starts(marker) == 1

    # A live owner: the same request short-circuits without waiting or binding.
    event = threading.Event()
    running = make_spec(h, [step(counter_code(marker, "import time; time.sleep(60)"))])
    result = {}
    worker = threading.Thread(
        target=lambda: result.update(record=h.execute(running, cancellation=event))
    )
    worker.start()
    try:
        deadline = time.monotonic() + 60
        while starts(marker) < 2:
            assert time.monotonic() < deadline, "the owner never started"
            time.sleep(0.05)
        busy = error_of(h.execute, running)
        assert (busy.code, busy.latest_record_ref) == ("AttemptInProgress", None)
    finally:
        event.set()
        worker.join(60)
    assert result["record"]["process_outcome"] == "cancelled" and starts(marker) == 2

    # A registration whose owner left without a record is never taken over or rerun.
    orphan = make_spec(h, [step(counter_code(marker))])
    attempt = {name: orphan[name] for name in execution_service.ATTEMPT_FIELDS}
    h._store.claim(attempt, run_store.request_digest(orphan)).release()
    unknown = error_of(h.execute, orphan)
    assert (unknown.code, unknown.started, unknown.latest_record_ref) == (
        "RecoveryRequired", None, None,
    )
    assert starts(marker) == 2
    assert error_of(h.read, orphan["attempt_id"]).code == "NoCommittedRecord"


def test_h02_5_budget_facts_leases_and_persistence_start_state(
    h: Harness, tmp_path, monkeypatch
) -> None:
    marker = tmp_path / "starts.txt"
    ran = h.execute(make_spec(h, [step(counter_code(marker))]))
    admission = ran["budget_admission"]
    assert (admission["decision"], admission["reasons"]) == ("admitted", ["free_local_cpu"])
    usage = ran["usage"][0]
    assert (usage["dimension"], usage["unit"], usage["completeness"]) == (
        "wall-time", "second", "complete",
    )
    assert usage["amount"] is not None
    lease = ran["resource_leases"]["leases"][0]
    assert ran["resource_leases"]["applicability"] == "applicable"
    assert lease["release_confirmed"] is True and lease["release_confirmed_at"] is not None

    # A dimensioned budget needs a policy this target does not have: refused, not started.
    priced = dict(FREE_BUDGET, dimensions=[
        {"dimension": "api-cost", "unit": "USD", "limit": "1", "reserve_estimate": None}
    ])
    refused = h.execute(make_spec(h, [step(counter_code(marker))], budget=priced))
    schema_check(refused)
    assert refused["budget_admission"]["decision"] == "rejected"
    assert refused["budget_admission"]["reasons"] == ["budget_policy_required"]
    assert refused["budget_admission"]["dimensions"][0]["reserved_capacity"] is None
    assert refused["usage"][0]["amount"] is None
    assert refused["usage"][0]["completeness"] == "not_applicable"
    assert refused["resource_leases"]["applicability"] == "not_applicable"
    assert refused["process_outcome"] == "not_started" and starts(marker) == 1

    # Input retention fails before start: no start, no record, then RecoveryRequired.
    source = tmp_path / "controller" / "in.txt"
    source.write_bytes(b"input")
    item = {"role": "data", "source": "in.txt", "source_namespace": "controller",
            "source_ref": None, "snapshot_format": "file-v1", "expected_sha256": None,
            "materialized_path": "in.txt"}
    broken = make_spec(h, [step(counter_code(marker))], inputs=[item])

    def no_space(stream, target):
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as patch:
        patch.setattr(input_binding, "copy_stream", no_space)
        before = error_of(h.execute, broken)
    assert (before.code, before.started) == ("ExecutionPersistenceError", False)
    assert starts(marker) == 1
    assert error_of(h.read, broken["attempt_id"]).code == "NoCommittedRecord"
    assert error_of(h.execute, broken).code == "RecoveryRequired"

    # The commit fails after the process ran: started=true with partial facts, no new Ref.
    after_spec = make_spec(h, [step(counter_code(marker))])

    def fail_append(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    with monkeypatch.context() as patch:
        patch.setattr(RunStore, "_append", fail_append)
        after = error_of(h.execute, after_spec)
    assert (after.code, after.started, after.latest_record_ref) == (
        "ExecutionPersistenceError", True, None,
    )
    assert after.partial_record.started is True and after.retained_refs == []
    assert starts(marker) == 2
    assert error_of(h.read, after_spec["attempt_id"]).code == "NoCommittedRecord"


def test_h02_6_no_device_model_or_network_fallback(h: Harness, tmp_path) -> None:
    marker = tmp_path / "starts.txt"
    resources = {"cpu_count": 1, "memory_bytes": None, "required_capabilities": ["cuda"]}
    device = h.execute(make_spec(h, [step(counter_code(marker))], resources=resources))
    checks = {c["capability"]: c["status"] for c in device["target_binding"]["capability_checks"]}
    assert checks == {"cuda": "unsupported", "local-process-tree": "supported"}
    assert device["process_outcome"] == "not_started" and starts(marker) == 0

    # An artifact source with no configured reader is not fetched from anywhere else.
    ref = {"location": "remote/model.bin", "sha256": "a" * 64, "size_bytes": 1,
           "media_type": "application/octet-stream"}
    item = {"role": "weights", "source": ref["location"], "source_namespace": "artifact",
            "source_ref": ref, "snapshot_format": "file-v1", "expected_sha256": ref["sha256"],
            "materialized_path": "weights.bin"}
    remote = h.execute(make_spec(h, [step(counter_code(marker))], inputs=[item]))
    assert remote["bound_inputs"][0]["reasons"] == ["artifact_reader_unavailable"]
    assert remote["process_outcome"] == "not_started" and starts(marker) == 0

    # A snapshot format this target cannot capture is refused, not read as one file.
    (tmp_path / "controller" / "tree.txt").write_bytes(b"one file")
    tree = {"role": "tree", "source": "tree.txt", "source_namespace": "controller",
            "source_ref": None, "snapshot_format": "directory-v1", "expected_sha256": None,
            "materialized_path": "tree"}
    directory = h.execute(make_spec(h, [step(counter_code(marker))], inputs=[tree]))
    assert directory["bound_inputs"][0]["reasons"] == ["snapshot_format_unsupported"]
    assert directory["bound_inputs"][0]["retained_ref"] is None
    assert directory["process_outcome"] == "not_started" and starts(marker) == 0

    # Another executor kind or target is refused before registration.
    other = make_spec(h, [step(counter_code(marker))])
    other["target_request"] = dict(TARGET, target_id="gpu-h02")
    other_attempt = other["attempt_id"]
    assert error_of(h.execute, other).code == "UnsupportedOperation"
    assert other_attempt not in {row[0] for row in attempt_rows(h)} and starts(marker) == 0

    # Static and runtime closure: the new H entry loads no device, model or infra module.
    graph = _scan(ROOT, exact_pairs(load_manifest()))
    expanded, hits = _walk("inferrsi.harness.api", graph.edges, lambda n: n not in NEW_H_CLOSURE)
    assert hits == [] and set(expanded) == NEW_H_CLOSURE
    code = (
        "import json, sys, inferrsi.harness.api; "
        "print(json.dumps(sorted(m for m in sys.modules "
        "if m.split('.')[0] in ('inferrsi', 'torch', 'vllm', 'numpy', 'requests', 'urllib3'))))"
    )
    loaded = set(json.loads(
        subprocess.run(
            [sys.executable, "-c", code], capture_output=True, env=child_env(),
            encoding="utf-8", timeout=120, check=True,
        ).stdout
    ))
    assert loaded <= NEW_H_CLOSURE | {"inferrsi", "inferrsi._version"}


def test_spec_time_refusals_register_nothing(h: Harness) -> None:
    spec = make_spec(h, [step("print(1)")])
    digest = dict(spec, steps=[dict(spec["steps"][0], expected_code_sha256="b" * 64)])
    error = error_of(h.execute, digest)  # V32-N1, not T37
    assert error.code == "InvalidExecutionSpec"
    assert any("expected_code_sha256" in item for item in error.field_errors)
    evaluation_ref = {
        "schema_version": 1, "prepared_id": "sha256:" + "c" * 64,
        "artifact": {"location": "fixtures/prepared.json", "sha256": "d" * 64,
                     "size_bytes": 1, "media_type": "application/json"},
    }
    evaluation = dict(
        spec, prepared_ref=evaluation_ref, protocol_digest="sha256:" + "e" * 64,
        operation="evaluate", validation_scope="p1",
        candidate={"candidate_id": "cand", "context_refs": [], "input_role": "candidate",
                   "kind": "text", "parent_digest": None, "parent_id": None},
    )
    assert error_of(h.execute, evaluation).code == "UnsupportedOperation"
    assert error_of(h.execute, dict(spec, schema_version=2)).code == "UnsupportedSchema"
    float_timeout = dict(spec, steps=[dict(spec["steps"][0], timeout_seconds=1.5)])
    assert error_of(h.execute, float_timeout).code == "InvalidExecutionSpec"
    assert attempt_rows(h) == []


def test_steps_run_in_fixed_order_and_fail_fast(h: Harness, tmp_path) -> None:
    marker = tmp_path / "starts.txt"
    record = h.execute(make_spec(h, [
        step(counter_code(marker), step_id="first"),
        step("import sys; sys.exit(3)", step_id="second"),
        step(counter_code(marker), step_id="third"),
    ]))
    assert [s["status"] for s in record["steps"]] == ["exited", "exited", "not_started"]
    assert record["steps"][2]["reasons"] == ["previous_step_failed"]
    assert (record["process_outcome"], record["exit_code"]) == ("exited", 3)
    assert record["phase"] == "finished" and starts(marker) == 1
    assert len(record["resource_leases"]["leases"]) == 2


def _supervise_with_domain(domain_empty, calls: list[list[str]]):
    """Stub supervisor: first step uses the injected domain_empty fact; later steps are empty."""

    def fake(argv, cwd, environment, stdout_path, stderr_path, deadline, *, cancellation=None):
        calls.append(list(argv))
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(b"")
        now = run_store.utc_now()
        emptied = domain_empty if len(calls) == 1 else True
        return {
            "status": "completed",
            "returncode": 0,
            "pid": 4242 + len(calls),
            "process_group_id": None,
            "error": None,
            "started_at": now,
            "ended_at": now,
            "process_seconds": 0.01,
            "termination_requested": False,
            "cancellation_source": None,
            "cancellation_requested_at": None,
            "domain_empty": emptied,
            "elapsed_seconds": 0.01,
        }

    return fake


@pytest.mark.parametrize(
    ("domain_empty", "cleanup_status", "cleanup_reason", "skip_reason", "phase"),
    [
        (True, "confirmed", "process_domain_empty", None, "finished"),
        (False, "failed", "process_domain_not_empty",
         "previous_process_domain_not_empty", "recovery_required"),
        (None, "unknown", "process_domain_unconfirmed",
         "previous_process_domain_unconfirmed", "recovery_required"),
    ],
)
def test_next_step_starts_only_after_process_domain_confirmed_empty(
    h: Harness, monkeypatch, domain_empty, cleanup_status, cleanup_reason, skip_reason, phase,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(local_process, "_supervise", _supervise_with_domain(domain_empty, calls))
    record = h.execute(make_spec(h, [
        step("first-step", step_id="first"),
        step("second-step", step_id="second"),
    ]))
    schema_check(record)
    first, second = record["steps"]
    assert first["status"] == "exited" and first["exit_code"] == 0
    assert first["started_at"] is not None
    assert record["started"] is True
    assert record["cleanup"]["status"] == cleanup_status
    assert record["cleanup"]["reasons"] == [cleanup_reason]
    assert record["resource_leases"]["leases"][0]["release_confirmed"] is domain_empty
    assert record["phase"] == phase
    # One terminal committed record; attempt state tracks the payload phase.
    assert attempt_rows(h) == [(record["attempt_id"], phase)]
    assert h._store.committed(record["attempt_id"]).payload["phase"] == phase
    if domain_empty is True:
        assert [s["status"] for s in record["steps"]] == ["exited", "exited"]
        assert second["exit_code"] == 0
        assert len(calls) == 2 and calls[1][1:] == ["-c", "second-step"]
        assert (record["process_outcome"], record["exit_code"]) == ("exited", 0)
        assert len(record["resource_leases"]["leases"]) == 2
    else:
        # Unconfirmed or non-empty domain must not start step 2, report a timeout,
        # or pretend the attempt never started or finished as a PASS.
        assert [s["status"] for s in record["steps"]] == ["exited", "not_started"]
        assert second["reasons"] == [skip_reason]
        assert len(calls) == 1
        assert (record["process_outcome"], record["exit_code"]) == ("exited", 0)
        assert record["process_outcome"] not in ("timed_out", "not_started")
        assert record["phase"] == "recovery_required"
        assert "PASS" not in json.dumps(record)
        assert record["errors"] == []
        assert len(record["resource_leases"]["leases"]) == 1


def test_record_bytes_are_canonical_and_store_fixed(h: Harness) -> None:
    record = h.execute(make_spec(h, [step("print('bytes')")]))
    committed = h._store.committed(record["attempt_id"])
    assert _json_v1.encode(committed.payload) == committed.payload_bytes
    assert committed.record_ref == record["record_ref"]


def _tree_record(tmp_path: Path, seconds: float) -> tuple[dict, int]:
    record = local_process.execute_command(
        (sys.executable, "-c", TREE), tmp_path, tmp_path / "trial", time.monotonic() + seconds
    )
    return record, int((tmp_path / "trial" / "stdout.log").read_text().strip())


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object domain")
def test_windows_job_owns_and_empties_the_command_tree(tmp_path: Path) -> None:
    record, grandchild = _tree_record(tmp_path, 8)
    assert record["status"] == "timeout" and record["process_group_id"] is None
    # The Job is drained before the call returns; no asynchronous kill remains.
    assert not alive(grandchild)
    run = local_process._supervise(
        [sys.executable, "-c", TREE], tmp_path, dict(os.environ),
        tmp_path / "out.log", tmp_path / "err.log", time.monotonic() + 8,
    )
    assert (run["status"], run["domain_empty"]) == ("timeout", True)
    assert not alive(int((tmp_path / "out.log").read_text().strip()))


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group domain")
def test_posix_process_group_owns_and_empties_the_command_tree(tmp_path: Path) -> None:
    record, grandchild = _tree_record(tmp_path, 8)
    assert record["status"] == "timeout"
    assert record["process_group_id"] == record["pid"]
    assert not alive(grandchild)
    run = local_process._supervise(
        [sys.executable, "-c", TREE], tmp_path, dict(os.environ),
        tmp_path / "out.log", tmp_path / "err.log", time.monotonic() + 8,
    )
    assert (run["status"], run["domain_empty"]) == ("timeout", True)
    assert not alive(int((tmp_path / "out.log").read_text().strip()))


def test_normal_exit_still_empties_a_lingering_descendant(tmp_path: Path) -> None:
    code = (
        "import subprocess, sys; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "print(p.pid, flush=True)"
    )
    run = local_process._supervise(
        [sys.executable, "-c", code], tmp_path, dict(os.environ),
        tmp_path / "out.log", tmp_path / "err.log", time.monotonic() + 30,
    )
    assert (run["status"], run["returncode"], run["domain_empty"]) == ("completed", 0, True)
    assert run["termination_requested"] is False
    assert not alive(int((tmp_path / "out.log").read_text().strip()))
