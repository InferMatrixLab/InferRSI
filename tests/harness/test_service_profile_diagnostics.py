"""Large collector diagnostics stay at their capture and leave campaign records readable."""

import json

import pytest

from inferrsi.harness import project_service as service
from inferrsi.harness.records import service_io
from tests.fixtures.service_reuse import begin, call, submit
from tests.fixtures.service_reuse import campaign as campaign

# A valid protocol receipt below the JSON size limit but too large to copy twice.
ERROR_EXPRESSION = '"collector detail\\n" * 155000'
ERROR_TEXT = "collector detail\n" * 155000


def assert_retained_error(root, command, expected_stage):
    diagnostic = command["profiling_error"]
    assert diagnostic["stage"] == expected_stage
    assert "collector detail" in diagnostic["message"]
    assert len(diagnostic["message"]) <= 2049
    receipt = root / diagnostic["details_path"]
    assert service_io.read(receipt)["error"] == ERROR_TEXT
    execution = service_io.read(receipt.parents[1] / "execution.json")
    assert execution["profiling_error"] == diagnostic
    assert len(json.dumps(execution)) < len(ERROR_TEXT)
    assert len(json.dumps(command)) < len(ERROR_TEXT)


def test_coordinator_failure_without_a_stage_receipt_retains_full_exception(tmp_path):
    directory = tmp_path / "capture"
    directory.mkdir()
    diagnostic = service.capture_diagnostic(tmp_path, directory, "startup", "failed", ERROR_TEXT)
    assert len(diagnostic["message"]) == 1024
    assert (tmp_path / diagnostic["details_path"]).read_text() == ERROR_TEXT


def test_nonzero_exit_links_process_receipt_even_when_script_wrote_a_result(tmp_path):
    directory = tmp_path / "capture"
    stage = directory / "execution/profile"
    stage.mkdir(parents=True)
    (stage / "result.json").write_text('{"status":"completed"}')
    (stage / "execution.json").write_text('{"status":"failed","returncode":1}')
    diagnostic = service.capture_diagnostic(
        tmp_path, directory, "profile", "failed", "profile: failed: exit 1", process_failed=True
    )
    assert (tmp_path / diagnostic["details_path"]) == stage / "execution.json"


@pytest.mark.parametrize("backfill", [False, True], ids=["inline", "backfill"])
def test_large_successful_profile_leaves_round_readable(campaign, backfill):
    root = campaign["root"]
    protocol = root.parent / "protocol" / "protocol.py"
    payload_size = 2560 * 1024
    encode = "            encoded = json.dumps(body).encode()"
    source = protocol.read_text().replace(
        encode,
        f'''            if stage == "profile" and config.get("large_profile"):
                if ("backfills" in attempt.parts) == {backfill!r}:
                    body["collector_metadata"] = "x" * {payload_size}
{encode}''',
    )
    protocol.write_text(source)
    begin(campaign)
    attempt = submit(campaign, a=90, large_profile=True)["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    profile = attempt["profiling"]
    if backfill:
        profile = call(campaign, "profile", "--round", 1)["profiling"]
        assert profile["result"] != attempt["profiling"]["result"]

    assert profile["available"]
    receipt = root / profile["result"]
    trace = service_io.read(receipt)
    assert trace["collector_metadata"] == "x" * payload_size
    for record in (
        receipt.parents[1] / "execution.json",
        root / attempt["path"] / "observation.json",
    ):
        assert len(json.dumps(service_io.read(record))) < payload_size
    status = call(campaign, "status")
    assert status["can_finalize"] and status["rounds"][0]["profiling"] == profile
    assert status["best"]["attempt_id"] == attempt["attempt_id"]
    assert submit(campaign, a=80)["latest_observation"]["assessment"]["verdict"] == "PASS"
    assert call(campaign, "final", "--reason", "Done")["final"]["assessment"]["verdict"] == "PASS"

    trace["binding"]["service_id"] = "another-service"
    receipt.write_text(json.dumps(trace))
    after = call(campaign, "status")["rounds"][0]
    assert after["profiling"] == (attempt["profiling"] if backfill else {"available": False})


def test_large_collector_error_retains_round_and_backfill(campaign):
    protocol = campaign["root"].parent / "protocol" / "protocol.py"
    source = protocol.read_text().replace('"synthetic collector failed"', ERROR_EXPRESSION)
    protocol.write_text(source)
    begin(campaign)
    result = submit(campaign, a=90, profile_mode="failed")
    attempt = result["latest_observation"]
    assert attempt["assessment"]["verdict"] == "PASS"
    assert attempt["profiling"] == {"available": False}
    assert_retained_error(campaign["root"], result, "profile")
    assert call(campaign, "status")["can_finalize"]

    backfill = call(campaign, "profile", "--round", 1, expected=2)
    assert_retained_error(campaign["root"], backfill, "profile")
    assert call(campaign, "recover")["profiling_error"] == backfill["profiling_error"]
    assert call(campaign, "final", "--reason", "Done")["final"]["assessment"]["verdict"] == "PASS"


def test_large_effective_config_allows_inline_and_backfill_profiles(campaign):
    config = service_io.read(campaign["config"])
    config["conditions"]["effective_config"].update(
        {f"engine.option_{i:04d}": i for i in range(1500)}
    )
    campaign["config"].write_text(json.dumps(config))
    begin(campaign)
    attempt = submit(campaign, a=90)["latest_observation"]
    inline = attempt["profiling"]
    assert attempt["assessment"]["verdict"] == "PASS"
    assert inline["available"]
    assert call(campaign, "status")["rounds"][0]["profiling"] == inline

    backfill = call(campaign, "profile", "--round", 1)["profiling"]
    assert backfill["available"] and backfill["result"] != inline["result"]
    assert call(campaign, "status")["rounds"][0]["profiling"] == backfill


def test_backfill_with_oversized_artifact_list_retains_inline_capture(campaign):
    root = campaign["root"]
    protocol = root.parent / "protocol" / "protocol.py"
    encode = "            encoded = json.dumps(body).encode()"
    protocol.write_text(protocol.read_text().replace(
        encode,
        '''            if stage == "profile" and "backfills" in attempt.parts:
                body["artifacts"] = [f"trace-{i:04d}.json" for i in range(512)]
                for name in body["artifacts"]:
                    (attempt / name).write_text("trace")
''' + encode,
    ))
    begin(campaign)
    attempt = submit(campaign, a=90)["latest_observation"]
    inline = attempt["profiling"]
    assert inline["available"]
    result = call(campaign, "profile", "--round", 1, expected=2)
    assert "metadata exceeds" in result["profiling_error"]["message"]
    assert result["profiling"] == inline
    status = call(campaign, "status")
    assert status["can_finalize"] and status["best"]["attempt_id"] == attempt["attempt_id"]
    assert status["rounds"][0]["verdict"] == "PASS" and status["rounds"][0]["profiling"] == inline


@pytest.mark.parametrize("failed", ["precheck", "ready"])
def test_large_backfill_prerequisite_failure_retains_inline_capture(campaign, failed):
    protocol = campaign["root"].parent / "protocol" / "protocol.py"
    status = "candidate_failure" if failed == "precheck" else "error"
    code = protocol.read_text().replace(
        'elif phase == "precheck":',
        f'''elif phase == "{failed}" and "backfills" in attempt.parts:
    write(result_path, {{"binding": request, "status": "{status}", "error": {ERROR_EXPRESSION}}})
elif phase == "precheck":''',
    )
    protocol.write_text(code)
    begin(campaign)
    inline = submit(campaign, a=90)["latest_observation"]["profiling"]
    backfill = call(campaign, "profile", "--round", 1, expected=2)
    assert_retained_error(campaign["root"], backfill, failed)
    assert backfill["profiling"] == inline and inline["available"]
    assert call(campaign, "status")["can_finalize"]


def test_settled_legacy_large_error_is_readable_through_next_round_and_final(campaign):
    from inferrsi.harness import optimization
    from inferrsi.harness.atomic_json import atomic_write_json

    begin(campaign)
    submit(campaign, a=90, profile_mode="failed")
    root = campaign["root"]
    state = json.loads((root / "state.json").read_text())
    old = state["attempts"][-1]
    execution = old["execution"]
    error = execution["profiling_error"]
    receipt = root / error.pop("details_path")
    atomic_write_json(receipt, {**service_io.read(receipt), "error": ERROR_TEXT})

    # Recreate the previous writer's settled state, including both copies of the full error.
    error["message"] = "profile: " + ERROR_TEXT
    state["last_profiling_error"] = error
    next(s for s in execution["steps"] if s["id"] == "profile")["reason"] = error["message"]
    attempt_dir = root / old["path"]
    observation = attempt_dir / "observation.json"
    atomic_write_json(attempt_dir / "execution/execution.json", execution)
    atomic_write_json(observation, old)
    atomic_write_json(root / "state.json", state)
    original = observation.read_bytes()
    assert len(original) > service_io.JSON_SIZE_LIMIT
    with pytest.raises(ValueError, match="oversized"):
        service_io.read(observation)

    old_state = (root / "state.json").read_bytes()
    status = call(campaign, "status")
    assert (root / "state.json").read_bytes() == old_state
    assert (
        status["can_finalize"] and status["latest_observation"]["assessment"]["verdict"] == "PASS"
    )
    projected = status["latest_observation"]["execution"]["profiling_error"]
    assert len(projected["message"]) == 1024
    assert (root / projected["details_path"]) == receipt
    assert len(json.dumps(status)) < len(ERROR_TEXT)
    assert call(campaign, "recover")["profiling_error"] == projected
    call(campaign, "profile", "--round", 1, expected=2)
    assert len((root / "summary.json").read_bytes()) < len(ERROR_TEXT)
    assert submit(campaign, a=80)["latest_observation"]["assessment"]["verdict"] == "PASS"
    assert (
        call(campaign, "final", "--reason", "Complete")["final"]["assessment"]["verdict"] == "PASS"
    )
    assert len(json.dumps(optimization.read_records(root)[2])) < len(ERROR_TEXT)
    assert observation.read_bytes() == original
    assert json.loads((root / "state.json").read_text())["attempts"][1] == old

    with observation.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="control record disagree"):
        optimization.read_records(root)


def test_settled_legacy_large_profile_is_readable_through_next_round_and_final(campaign):
    from inferrsi.harness import optimization
    from inferrsi.harness.atomic_json import atomic_write_json

    begin(campaign)
    submit(campaign, a=90)
    root = campaign["root"]
    state = json.loads((root / "state.json").read_text())
    old = state["attempts"][-1]
    execution = old["execution"]
    profile = execution["profile"]
    receipt = root / profile["result"]
    trace = {**service_io.read(receipt), "collector_metadata": "x" * (2560 * 1024)}
    atomic_write_json(receipt, trace)

    # The old writer embedded the same receipt in the profile step and in every selected reference.
    step = next(s for s in execution["steps"] if s["id"] == "profile")
    step["result"] = trace
    profile.pop("capture_started_at", None)
    profile.pop("capture_ended_at", None)
    profile["receipt"] = trace
    for choice in (old["best_after"], state["best"], state["comparison_parent"]):
        choice["profile"] = profile
    directory = root / old["path"]
    observation = directory / "observation.json"
    atomic_write_json(directory / "execution/execution.json", execution)
    atomic_write_json(observation, old)
    atomic_write_json(root / "state.json", state)
    assert observation.stat().st_size > service_io.JSON_SIZE_LIMIT
    status = call(campaign, "status")
    assert status["can_finalize"] and status["rounds"][0]["profiling"] == old["profiling"]
    assert status["best"]["attempt_id"] == old["attempt_id"]
    assert status["best"]["profile"] == profile

    rejected = submit(campaign, a=70, b=120)["latest_observation"]
    retained = service_io.read(root / rejected["path"] / "observation.json")
    assert retained["assessment"]["verdict"] == "FAIL"
    assert retained["best_after"]["attempt_id"] == old["attempt_id"]
    assert "profile" not in retained["best_after"]
    assert rejected["best_after"]["profile"] == {"result": old["profiling"]["result"]}
    accepted = submit(campaign, a=80)["latest_observation"]
    selected = service_io.read(root / accepted["path"] / "observation.json")
    assert selected["assessment"]["verdict"] == "PASS"
    assert selected["parent"]["attempt_id"] == old["attempt_id"]
    assert "profile" not in selected["parent"]
    assert accepted["parent"]["profile"] == rejected["best_after"]["profile"]
    assert selected["best_after"]["attempt_id"] == accepted["attempt_id"]
    final = call(campaign, "final", "--reason", "Done")["final"]
    completed = service_io.read(root / final["path"] / "observation.json")
    assert completed["assessment"]["verdict"] == "PASS"
    assert completed["revision"] == accepted["revision"]
    for record in (retained, selected, completed):
        assert "collector_metadata" not in json.dumps(record)

    old["selected"] = False
    atomic_write_json(observation, old)
    with pytest.raises(ValueError, match="control record disagree"):
        optimization.read_records(root)
