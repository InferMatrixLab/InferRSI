"""Supervised scripted worker and fake-store admission: no model/provider calls."""

import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from inferrsi.harness import kv_reclamation as kv
from inferrsi.infra.executors.local import execute_command
from inferrsi.model import anthropic_agent as provider
from tests.test_anthropic_edit_agent import read_task, submit, work
from tests.test_kv_edit_workbench import BASELINE, CANDIDATE, fake_sandbox, stage, suite
from tests.test_kv_pilot_admission import World, policy
from tools import kv_edit_pilot as pilot
from tools import kv_pilot_admission as admission


def prepare(tmp_path, arm="A2", scripts=None):
    parent = tmp_path / arm
    parent.mkdir()
    root, plan = stage(parent)
    spec = {"kind": provider.EDIT_KIND, "provider": "yibuapi", "endpoint": provider.ENDPOINT,
            "api_version": "2023-06-01", "max_requests": 8, "max_output_tokens": 4096,
            "max_request_bytes": 262144, "max_read_bytes": 32768, "max_tool_calls": 32}
    config = pilot.prepare_scripted(parent / "inputs", root, plan, suite(), BASELINE,
        scripts or [read_task(), work(CANDIDATE), submit()], plan_sha256="1" * 64,
        execution_id="example-run-1.1", arm=arm, model="claude-opus-5-5", spec=spec,
        prompt="Optimize only the public task.", input_token_ceiling=1000000)
    return parent / "inputs", root, config


def in_process_worker(command, cwd, trial_dir, deadline, *, environment):
    """Test-only scripted executor: does not certify the subprocess/isolation boundary."""
    assert provider.KEY_ENV not in environment and "GITHUB_TOKEN" not in environment
    assert "-I" in command and command[0] == sys.executable
    assert "--offline-worker" in command
    args = dict(zip(command[4::2], command[5::2]))
    assert float(args["--deadline"]) == deadline
    trial_dir.mkdir(parents=True)
    with (trial_dir / "stdout.log").open("w") as stream:
        code = pilot.scripted_worker(Path(args["--inputs"]), Path(args["--workspace"]),
            Path(args["--output"]), deadline, environment=environment,
            emit=lambda e: stream.write(provider.canonical(e) + "\n"))
    (trial_dir / "stderr.log").write_text("")
    return {"status": "completed" if code == 0 else "failed", "returncode": code,
            "stdout_path": str(trial_dir / "stdout.log"),
            "stderr_path": str(trial_dir / "stderr.log"), "elapsed_seconds": 0.01}


def fake_isolation(output, deadline, forbidden):
    assert deadline > time.monotonic() and len(forbidden) == 4
    return {"scope": "scripted unit-test output; not isolation qualification"}


def test_supervised_scripted_pair_with_existing_claims_and_usage_bridge(tmp_path, monkeypatch):
    a, b = prepare(tmp_path, "A2"), prepare(tmp_path, "A3")
    monkeypatch.setattr(kv, "invoke", fake_sandbox)
    monkeypatch.setattr(kv, "probe_isolation", fake_isolation)
    world = World()
    config = policy(actor_sha256=(a[2]["actor_sha256"], b[2]["actor_sha256"]))
    session = admission.admit(config, world.daily, world.pr, check_current=lambda _: True,
                              wall_clock=lambda: world.now, monotonic_clock=time.monotonic)
    assert len(world.events) == 4  # Whole plan reserved/claimed before either disclosure.
    for inputs, root, _ in (a, b):
        result = pilot.run_supervised(inputs, root, inputs.parent / "run",
            time.monotonic() + 600, admission=session, execute=in_process_worker)
        assert result["worker"]["status"] == "completed"
        assert result["simulated_slots_consumed"] == 3
        assert result["request_completion_known"]
        assert result["model_calls"] == 0 and result["provider_charges_usd"] == 0
        final = inputs.parent / "run/worker/final/candidate.py"
        assert final.read_text() == CANDIDATE
    assert world.pr.ledger.charged == 162720000  # No refund from simulated usage.
    assert world.daily.ledger.charged_on("2026-10-30") == 654070000
    with pytest.raises(Exception):
        session.start_arm("A2", time.monotonic() + 600)
    session.close()


def test_unknown_usage_blocks_other_arm_and_retains_full_reservation(tmp_path, monkeypatch):
    a = prepare(tmp_path, scripts=[{**read_task(), "usage": None}])
    b = prepare(tmp_path, "A3")
    monkeypatch.setattr(kv, "invoke", fake_sandbox)
    monkeypatch.setattr(kv, "probe_isolation", fake_isolation)
    world = World()
    session = admission.admit(policy(actor_sha256=(a[2]["actor_sha256"], b[2]["actor_sha256"])),
        world.daily, world.pr, check_current=lambda _: True, wall_clock=lambda: world.now,
        monotonic_clock=time.monotonic)
    result = pilot.run_supervised(a[0], a[1], a[0].parent / "run", time.monotonic() + 600,
                                  admission=session, execute=in_process_worker)
    assert result["worker"]["status"] == "failed"
    assert not result["request_completion_known"] and result["simulated_slots_consumed"] == 1
    with pytest.raises(Exception):
        pilot.run_supervised(b[0], b[1], b[0].parent / "run", time.monotonic() + 600,
                             admission=session, execute=in_process_worker)
    assert world.pr.ledger.charged == 162720000


def test_missing_completion_after_grant_is_not_recovered_or_refunded(tmp_path, monkeypatch):
    a = prepare(tmp_path)
    monkeypatch.setattr(kv, "invoke", fake_sandbox)
    monkeypatch.setattr(kv, "probe_isolation", fake_isolation)
    original = pilot.atomic_write_json
    def lose_completion(path, value):
        if Path(path).name == "complete.json":
            raise OSError("simulated loss")
        return original(path, value)
    monkeypatch.setattr(pilot, "atomic_write_json", lose_completion)
    result = pilot.run_supervised(a[0], a[1], a[0].parent / "run", time.monotonic() + 600,
                                  execute=in_process_worker)
    assert result["simulated_slots_consumed"] == 1
    assert not result["request_completion_known"]
    assert result["worker"]["reason"] == "provider_transport_error"


@pytest.mark.parametrize("name", ["suite.json", "baseline.py", "responses.json"])
def test_changed_private_frozen_inputs_fail_before_worker_or_slots(tmp_path, name):
    inputs, root, _ = prepare(tmp_path)
    (inputs / name).write_text("changed")
    with pytest.raises(ValueError):
        pilot.run_supervised(inputs, root, inputs.parent / "run", time.monotonic() + 600,
                             execute=lambda *_args, **_kwargs: pytest.fail("must not launch"))


def test_changed_prompt_or_dependencies_fail_before_launch(tmp_path):
    inputs, root, _ = prepare(tmp_path)
    path = inputs / "worker.json"
    config = json.loads(path.read_text())
    config["prompt"] = "changed prompt"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="binding changed"):
        pilot.run_supervised(inputs, root, inputs.parent / "run", time.monotonic() + 600)


def test_sandbox_unavailable_precedes_every_simulated_request(tmp_path, monkeypatch):
    inputs, root, _ = prepare(tmp_path)
    def unavailable(*_):
        raise kv.SandboxUnavailable("sandbox unavailable")
    monkeypatch.setattr(kv, "probe_isolation", unavailable)
    result = pilot.run_supervised(inputs, root, inputs.parent / "run", time.monotonic() + 30,
                                  execute=in_process_worker)
    assert result["worker"]["status"] == "inconclusive"
    assert result["worker"]["reason"] == "sandbox_unavailable"
    assert result["simulated_slots_consumed"] == 0


def test_existing_executor_really_kills_blocked_trusted_worker_at_inherited_deadline(tmp_path):
    inputs, root, _ = prepare(tmp_path)
    def blocking_executor(command, cwd, output, deadline, *, environment):
        # Trusted sleep fixture, NOT submitted Python or a candidate host fallback.
        return execute_command((sys.executable, "-I", "-c", "import time; time.sleep(30)"),
                                cwd, output, deadline, environment=environment)
    started = time.monotonic()
    result = pilot.run_supervised(inputs, root, inputs.parent / "run", started + 0.2,
                                  execute=blocking_executor)
    assert result["execution"]["status"] == "timeout"
    assert result["execution"]["elapsed_seconds"] < 2
    assert kv.process_group_gone(result["execution"])
    assert result["worker"]["status"] == "missing"


def test_shanghai_day_change_blocks_bridge_next_grant(tmp_path, monkeypatch):
    a = prepare(tmp_path)
    monkeypatch.setattr(kv, "invoke", fake_sandbox)
    monkeypatch.setattr(kv, "probe_isolation", fake_isolation)
    world = World()
    session = admission.admit(policy(actor_sha256=(a[2]["actor_sha256"], "5" * 64)),
        world.daily, world.pr, check_current=lambda _: True, wall_clock=lambda: world.now,
        monotonic_clock=time.monotonic)
    original = session.complete
    def midnight(grant, usage):
        original(grant, usage)
        world.now += timedelta(hours=1)
    session.complete = midnight
    result = pilot.run_supervised(a[0], a[1], a[0].parent / "run", time.monotonic() + 600,
                                  admission=session, execute=in_process_worker)
    assert result["worker"]["status"] == "failed"
    assert result["worker"]["reason"] == "request_authorization_denied"
    assert world.pr.ledger.charged == 162720000
