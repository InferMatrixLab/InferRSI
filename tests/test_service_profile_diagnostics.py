"""Large collector diagnostics stay at their capture and leave campaign records readable."""

import json

import pytest
from test_project_service_reuse import begin, call, submit
from test_project_service_reuse import campaign as campaign

from inferrsi.harness import project_service as service

# A valid protocol receipt below the JSON size limit but too large to copy twice.
ERROR_EXPRESSION = '"collector detail\\n" * 155000'
ERROR_TEXT = "collector detail\n" * 155000


def assert_retained_error(root, command, expected_stage):
    diagnostic = command["profiling_error"]
    assert diagnostic["stage"] == expected_stage
    assert "collector detail" in diagnostic["message"]
    assert len(diagnostic["message"]) <= 2049
    receipt = root / diagnostic["details_path"]
    assert service.read(receipt)["error"] == ERROR_TEXT
    execution = service.read(receipt.parents[1] / "execution.json")
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
    atomic_write_json(receipt, {**service.read(receipt), "error": ERROR_TEXT})

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
    assert len(original) > service.JSON_SIZE_LIMIT
    with pytest.raises(ValueError, match="oversized"):
        service.read(observation)

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
