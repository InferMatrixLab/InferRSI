"""Fake supervisor controls only; no providers or live ledger writes."""

import time
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
                                                    (1, False)])
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
