"""Recover profiling-only time if the stage supervisor persists its receipt first."""

import json
import time

import pytest
from test_project_service_reuse import begin, call, submit
from test_project_service_reuse import campaign as campaign

from inferrsi.harness import project_service as service


def test_crash_after_profile_process_receipt_before_capture_progress(campaign, monkeypatch):
    class CoordinatorStopped(BaseException):
        pass

    begin(campaign)
    root = campaign["root"]
    write = service.atomic_write_json
    stopped_at = None

    def stop_before_progress_write(path, document):
        nonlocal stopped_at
        if stopped_at == path:
            return
        steps = document.get("steps") or []
        if (
            document.get("capture")
            and steps
            and steps[-1]["id"] == "profile"
            and steps[-1]["status"] == "completed"
        ):
            stopped_at = path
            raise CoordinatorStopped()
        write(path, document)

    with monkeypatch.context() as m:
        m.setattr(service, "atomic_write_json", stop_before_progress_write)
        with pytest.raises(CoordinatorStopped):
            submit(campaign, version="stage-receipt", a=90)

    pending = service.read(root / "state.json")["pending"]
    execution = service.read(stopped_at)
    capture = execution["capture"]
    step = execution["steps"][-1]
    assert step["status"] == "running" and "ended_at" not in capture
    offset = step["capture_offset_seconds"]
    assert offset == capture["elapsed_seconds"]
    path = root / pending["path"] / "execution/profile/execution.json"
    receipt = service.read(path)
    proven = offset + receipt["elapsed_seconds"]
    assert proven > offset
    assert service.proven_capture_elapsed(root, pending, execution) == proven

    # Closed captures already include this stage. Never add a second interval.
    closed = {**execution, "capture": {**capture, "ended_at": 1, "elapsed_seconds": proven}}
    assert service.proven_capture_elapsed(root, pending, closed) == proven

    for invalid in (
        {**receipt, "result_path": "another-capture/result.json"},
        {**receipt, "cwd": "another-capture/workspace"},
        {**receipt, "status": "running"},
        {**receipt, "elapsed_seconds": -3},
    ):
        path.write_text(json.dumps(invalid))
        assert service.proven_capture_elapsed(root, pending, execution) == offset
    path.unlink()
    assert service.proven_capture_elapsed(root, pending, execution) == offset
    start_only = {**execution, "steps": [], "capture": {**capture, "elapsed_seconds": 0}}
    assert service.proven_capture_elapsed(root, pending, start_only) == 0

    path.write_text(json.dumps(receipt))
    owner = service.read(root / pending["path"] / "service/owner.json")
    inspection = root.parent / "inspection.json"
    inspected = {"service_id": owner["service_id"], "pid": owner["pid"], "domain_empty": True}
    write(inspection, {
        "attempt_id": pending["attempt_id"], "observed_at": time.time(),
        "reason": "Inspected owner", "cleanup_complete": True, "services": [inspected],
    })
    call(campaign, "recover", "--cleanup-receipt", inspection)
    call(campaign, "recover")
    ledger = service.read(root / "state.json")["profiling_accounting"]
    assert ledger == {
        capture["id"]: {"started_at": capture["started_at"], "elapsed_seconds": proven}
    }


def test_invalid_capture_progress_cannot_change_the_clock(tmp_path):
    pending = {"attempt_id": "capture-1"}
    for progress in ({}, {"elapsed_seconds": float("inf")}, {"elapsed_seconds": -1}):
        execution = {"capture": {"id": "capture-1", **progress}}
        assert service.proven_capture_elapsed(tmp_path, pending, execution) == 0
    for steps in (None, {}, [None], ["bad stage"]):
        execution = {"capture": {"id": "capture-1", "elapsed_seconds": 3}, "steps": steps}
        assert service.proven_capture_elapsed(tmp_path, pending, execution) == 3
