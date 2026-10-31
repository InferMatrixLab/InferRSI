"""Fake supervisor controls only; no providers or live ledger writes."""

import time
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from inferrsi.infra.artifacts import atomic_write_json
from tests.test_kv_edit_pilot import prepare
from tools import kv_edit_pilot as pilot
from tools import kv_worker_supervisor as supervisor


@pytest.mark.parametrize("extra", ["GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN", "PYTHONPATH", "HOME"])
def test_shared_supervisor_rejects_authority_and_path_environment_injection(tmp_path, extra):
    inputs, workspace, config = prepare(tmp_path)
    _, plan, *_ = pilot.checked_inputs(inputs)
    admission = Mock()
    with pytest.raises(ValueError, match="environment"):
        supervisor.supervise(config, plan, inputs, workspace, tmp_path / "output",
            time.monotonic() + 30, checkout=tmp_path, admission=admission,
            command_factory=Mock(), environment_factory=lambda gate: {**gate, extra: "offline"},
            execute=Mock(side_effect=AssertionError("must not execute")))
    admission.close.assert_called_once()


def test_shared_supervisor_closes_admission_on_outer_cancellation(tmp_path):
    inputs, workspace, config = prepare(tmp_path)
    _, plan, *_ = pilot.checked_inputs(inputs)
    admission = Mock()
    with pytest.raises(KeyboardInterrupt):
        supervisor.supervise(config, plan, inputs, workspace, tmp_path / "output",
            time.monotonic() + 30, checkout=tmp_path, admission=admission,
            command_factory=lambda *_: ("fixed",), environment_factory=lambda gate: gate,
            execute=Mock(side_effect=KeyboardInterrupt))
    admission.close.assert_called_once()


@pytest.mark.parametrize("status", ["cancelled", "timeout", "error"])
def test_returned_executor_failure_stops_session_without_finishing_arm(tmp_path, status):
    inputs, workspace, config = prepare(tmp_path)
    _, plan, *_ = pilot.checked_inputs(inputs)
    admission = Mock()
    result = supervisor.supervise(config, plan, inputs, workspace, tmp_path / "output",
        time.monotonic() + 30, checkout=tmp_path, admission=admission,
        command_factory=lambda *_: ("fixed",), environment_factory=lambda gate: gate,
        execute=Mock(return_value={"status": status}))
    assert not result["request_completion_known"]
    admission.close.assert_called_once()
    admission.finish_arm.assert_not_called()



@pytest.mark.parametrize("returncode,has_result", [(-15, True), (-9, True), (0, False),
                                                    (1, False), (1, True)])
def test_signal_death_or_missing_result_blocks_following_arm(tmp_path, returncode, has_result):
    inputs, workspace, config = prepare(tmp_path)
    _, plan, *_ = pilot.checked_inputs(inputs)
    admission = Mock()
    def execute(command, checkout, output, deadline, *, environment):
        if has_result:
            (output.parent / "worker").mkdir()
            atomic_write_json(output.parent / "worker/result.json", {"status": "completed"})
        return {"status": "failed" if returncode else "completed", "returncode": returncode}
    result = supervisor.supervise(config, plan, inputs, workspace, tmp_path / "output",
        time.monotonic() + 30, checkout=tmp_path, admission=admission,
        command_factory=lambda *_: ("fixed",), environment_factory=lambda gate: gate,
        execute=execute)
    assert not result["request_completion_known"]
    admission.close.assert_called_once()
    admission.finish_arm.assert_not_called()


@pytest.mark.parametrize("record,accepted", [
    ({"status": "completed", "returncode": 0}, True),
    ({"status": "failed", "returncode": 1}, False),
    ({"status": "failed", "returncode": 0}, False),
    ({"status": "completed", "returncode": 1}, False),
    ({"status": "completed", "returncode": False}, False),
    ({"status": "completed", "returncode": True}, False),
    ({"status": "completed", "returncode": 0.0}, False),
    ({"status": "completed", "returncode": "0"}, False),
    ({"status": "completed", "returncode": None}, False),
    ({"status": "completed"}, False),
    ({"returncode": 0}, False),
    ({"status": "unknown", "returncode": 0}, False),
    ({"status": "cancelled", "returncode": 0}, False),
    ({"status": "timeout", "returncode": 0}, False),
    ({"status": "error", "returncode": 0}, False),
])
def test_known_request_and_worker_result_cannot_upgrade_executor_outcome(
    tmp_path, monkeypatch, record, accepted
):
    inputs, workspace, config = prepare(tmp_path)
    _, plan, *_ = pilot.checked_inputs(inputs)
    admission = Mock()
    admission.authorize.return_value = True
    broker_check = None

    @contextmanager
    def broker(check, *args, **kwargs):
        nonlocal broker_check
        broker_check = check
        yield {}

    monkeypatch.setattr(supervisor, "authorization_broker", broker)

    def execute(command, checkout, output, deadline, *, environment):
        grant = {k: config[k] for k in ("plan_sha256", "execution_id", "arm", "actor_sha256")}
        grant.update(slot=1, request_sha256="a" * 64, reserved_microusd=10170000)
        bridge = output.parent / "bridge"
        atomic_write_json(bridge / "pending.json", grant)
        assert broker_check() is True
        atomic_write_json(bridge / "complete.json", {"grant": grant, "usage": {
            "input_tokens": 1, "output_tokens": 1,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}})
        (output.parent / "worker").mkdir()
        atomic_write_json(output.parent / "worker/result.json", {"status": "completed"})
        return record

    result = supervisor.supervise(config, plan, inputs, workspace, tmp_path / "output",
        time.monotonic() + 30, checkout=tmp_path, admission=admission,
        command_factory=lambda *_: ("fixed",), environment_factory=lambda gate: gate,
        execute=execute)
    assert result["execution"] == record and result["worker"]["status"] == "completed"
    assert result["slots_consumed"] == 1 and result["completions"][0]["status"] == "known"
    assert result["request_completion_known"] is accepted
    admission.complete.assert_called_once()
    if accepted:
        admission.finish_arm.assert_called_once_with(config["arm"])
        admission.close.assert_not_called()
    else:
        admission.close.assert_called_once()
        admission.finish_arm.assert_not_called()
