"""Native handoffs retain identity and evidence without launching a second Agent."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from inferrsi.cli import main
from inferrsi.harness import agent_sessions


@pytest.fixture
def job(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "job"
    agent_sessions.prepare(root, prompt="Read the entry skill and produce a patch.",
                           workspace=workspace, title="Native session control", max_seconds=120)
    return root


def export(root, name, value):
    path = root.parent / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def bind(job):
    agent_sessions.dispatch(job)
    return agent_sessions.bind(
        job, host="test-host", session_id="session-1", host_id="host-1",
        receipt=export(job, "creation.json", {"native_result": "session-1"}),
    )


def observation(job, state="running", **fields):
    return export(job, "observation.json", {
        "host": "test-host", "host_id": "host-1", "session_id": "session-1",
        "state": state, "native_receipt": {"status": state}, **fields,
    })


def test_dispatch_can_be_consumed_only_once_even_after_interruption(job):
    first = agent_sessions.dispatch(job)
    assert first["may_create"] is True
    assert first["handoff"]["context_mode"] == "fresh"
    assert "Read the entry skill" in first["handoff"]["prompt"]
    # Reopening the job after a caller crash never authorizes another launch.
    second = agent_sessions.dispatch(job)
    assert second["may_create"] is False
    assert "handoff" not in second
    assert "without_relaunch" in second["next_action"]


def test_concurrent_dispatch_allows_only_one_creation(job):
    def attempt():
        try:
            return agent_sessions.dispatch(job).get("may_create", False)
        except OSError:  # OS lock contention is an explicit refusal, not another launch.
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(lambda _: attempt(), range(2))) == 1


def test_binding_is_idempotent_but_cannot_be_replaced(job):
    first = bind(job)
    assert first["state"] == "running"
    receipt = export(job, "creation.json", {"native_result": "session-1"})
    same = agent_sessions.bind(job, host="test-host", session_id="session-1",
                               host_id="host-1", receipt=receipt)
    assert same["native_session"] == first["native_session"]
    with pytest.raises(ValueError, match="another native session"):
        agent_sessions.bind(job, host="test-host", session_id="session-2", receipt=receipt)
    wrong = observation(job, session_id="session-2")
    with pytest.raises(ValueError, match="bound native session"):
        agent_sessions.record(job, observation=wrong)


def test_definite_creation_failure_is_retained_without_inventing_a_session(job):
    agent_sessions.dispatch(job)
    receipt = export(job, "creation-error.json", {
        "host": "test-host", "session_id": None, "state": "failed",
        "creation_outcome": "not_created", "native_receipt": {"error": "invalid_project"},
    })
    result = agent_sessions.record(job, observation=receipt)
    assert result["state"] == "failed" and result["native_session"] is None
    assert agent_sessions.dispatch(job)["may_create"] is False


def test_ambiguous_creation_error_cannot_be_treated_as_definite_failure(job):
    agent_sessions.dispatch(job)
    receipt = export(job, "creation-error.json", {
        "host": "test-host", "state": "failed", "native_receipt": {"error": "disconnected"},
    })
    with pytest.raises(ValueError, match="definite not_created"):
        agent_sessions.record(job, observation=receipt)
    assert agent_sessions.status(job)["state"] == "dispatching"


def test_changed_entry_resource_prevents_dispatch(tmp_path):
    entry = tmp_path / "SKILL.md"
    entry.write_text("Original entry", encoding="utf-8")
    root = tmp_path / "job"
    agent_sessions.prepare(root, prompt="Read the entry", workspace=tmp_path,
                           title="Frozen entry", max_seconds=120, frozen_inputs=[entry])
    entry.write_text("Different procedure", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen Agent input"):
        agent_sessions.dispatch(root)


def test_native_completion_is_not_acceptance_and_deliverable_is_snapshotted(job):
    bind(job)
    artifact = job.parent / "workspace/candidate.py"
    artifact.write_text("result = 42\n", encoding="utf-8")
    result = agent_sessions.record(job, observation=observation(job, "completed"),
                                   artifacts=[artifact])
    assert result["state"] == "completed"
    assert result["task_acceptance"] == "not_assessed"
    assert result["usage"] is None and result["cost"] is None
    retained = job / result["artifacts"][0]["path"]
    artifact.write_text("changed later", encoding="utf-8")
    assert retained.read_text() == "result = 42\n"
    assert agent_sessions.status(job)["state"] == "completed"
    with pytest.raises(ValueError, match="terminal"):
        agent_sessions.record(job, observation=observation(job))
    retained.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact changed"):
        agent_sessions.status(job)


def test_usage_snapshots_are_not_summed_and_cannot_decrease(job):
    bind(job)
    for tokens in (100, 100, 120):
        result = agent_sessions.record(job, observation=observation(
            job, usage_scope="session_total",
            usage={"input_tokens": tokens, "output_tokens": 20, "cached_input_tokens": 10},
        ))
    assert result["usage"]["input_tokens"] == 120
    assert result["usage"]["output_tokens"] == 20
    with pytest.raises(ValueError, match="cannot decrease"):
        agent_sessions.record(job, observation=observation(
            job, usage_scope="session_total", usage={"input_tokens": 1, "output_tokens": 1},
        ))
    with pytest.raises(ValueError, match="valid session_total"):
        agent_sessions.record(job, observation=observation(
            job, usage_scope="turn", usage={"input_tokens": 200, "output_tokens": 40},
        ))


def test_terminal_observations_allow_late_usage_and_preserve_deliveries(job):
    bind(job)
    artifact = job.parent / "workspace/result.txt"
    artifact.write_text("first delivery", encoding="utf-8")
    usage = {"input_tokens": 100, "output_tokens": 20}
    receipt = observation(job, "completed", usage_scope="session_total", usage=usage)
    first = agent_sessions.record(job, observation=receipt, artifacts=[artifact])
    repeated = agent_sessions.record(job, observation=receipt, artifacts=[artifact])
    assert repeated["usage"] == first["usage"] == usage
    assert repeated["last_observation"] != first["last_observation"]
    # Observations append; record is not a deduplication API.
    assert len(repeated["artifacts"]) == 2
    artifact.write_text("later delivery", encoding="utf-8")
    latest_usage = {"input_tokens": 120, "output_tokens": 25}
    result = agent_sessions.record(job, observation=observation(
        job, "completed", usage_scope="session_total", usage=latest_usage), artifacts=[artifact])
    assert result["usage"] == latest_usage
    assert result["state"] == "completed" and result["task_acceptance"] == "not_assessed"
    assert (job / result["artifacts"][0]["path"]).read_text() == "first delivery"
    assert (job / result["artifacts"][-1]["path"]).read_text() == "later delivery"
    for state in ("running", "failed", "cancelled"):
        with pytest.raises(ValueError, match="terminal"):
            agent_sessions.record(job, observation=observation(job, state))
    with pytest.raises(ValueError, match="cannot decrease"):
        agent_sessions.record(job, observation=observation(
            job, "completed", usage_scope="session_total", usage=usage))
    missing = agent_sessions.record(job, observation=observation(job, "completed"))
    assert missing["usage"] is None
    assert missing["last_observed_usage"]["usage"] == latest_usage
    assert agent_sessions.dispatch(job)["may_create"] is False


def test_deadline_does_not_claim_that_native_host_was_stopped(job, monkeypatch):
    monkeypatch.setattr(agent_sessions.time, "time", lambda: 10**12)
    view = agent_sessions.status(job)
    assert view["deadline_exceeded"] is True
    assert view["state"] == "prepared"
    assert view["deadline_enforcement"] == "native_host_not_enforced"
    with pytest.raises(ValueError, match="deadline exhausted"):
        agent_sessions.dispatch(job)


def test_missing_final_usage_does_not_relabel_an_earlier_partial_meter(job):
    bind(job)
    agent_sessions.record(job, observation=observation(
        job, usage_scope="session_total", usage={"input_tokens": 100, "output_tokens": 20},
    ))
    result = agent_sessions.record(job, observation=observation(job, "completed"))
    assert result["usage"] is None
    assert result["last_observed_usage"]["usage"]["input_tokens"] == 100
    assert result["last_observed_usage"]["receipt"] != result["last_observation"]


@pytest.mark.parametrize("name", ["prompt.md", "request.json"])
def test_frozen_input_changes_are_rejected(job, name):
    path = job / name
    if name == "request.json":
        value = json.loads(path.read_text())
        value["workspace"] = "changed"
        path.write_text(json.dumps(value), encoding="utf-8")
    else:
        path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen Agent"):
        agent_sessions.dispatch(job)


def test_unrelated_files_cannot_be_collected(job):
    bind(job)
    outside = job.parent / "outside.txt"
    outside.write_text("unrelated", encoding="utf-8")
    with pytest.raises(ValueError, match="declared workspace"):
        agent_sessions.record(job, observation=observation(job), artifacts=[outside])


def test_cli_prepares_and_dispatches_but_does_not_claim_a_launched_session(tmp_path, capsys):
    prompt = tmp_path / "task.md"
    prompt.write_text("Create the requested artifact.", encoding="utf-8")
    root = tmp_path / "job"
    assert main(["agents", "prepare", "--job", str(root), "--workspace", str(tmp_path),
                 "--prompt-file", str(prompt), "--title", "Native smoke",
                 "--max-minutes", "3"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "prepared"
    assert main(["agents", "dispatch", "--job", str(root)]) == 0
    pending = json.loads(capsys.readouterr().out)
    assert pending["state"] == "dispatching"
    assert pending["native_session"] is None
