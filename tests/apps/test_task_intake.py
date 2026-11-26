"""intake/v1: spec validation, question selection, answers, conflicts and the campaign gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from inferrsi.apps import cli
from inferrsi.apps.cli import intake_contract as intake
from inferrsi.apps.cli import task_intake
from tests.apps.test_project_optimization import project, start_arguments  # noqa: F401

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "intake"
PERFORMANCE = FIXTURES / "performance"
COMPLETE = json.loads((PERFORMANCE / "complete.json").read_text(encoding="utf-8"))
PARTIAL = json.loads((PERFORMANCE / "partial.json").read_text(encoding="utf-8"))
ALL_VALUES = {**COMPLETE["fields"]["values"], **COMPLETE["acceptance"]["values"]}


def spec_for(task: str = "task-performance") -> dict:
    return task_intake.load_spec(task)


def build(paths: set[str] | None = None, *, task: str = "task-performance") -> dict:
    """A record built from the complete fixture, optionally restricted to ``paths``."""
    spec = spec_for(task)
    record = intake.new_record(task, record_id="intake-test")
    if task == "task-performance":
        chosen = {path: value for path, value in ALL_VALUES.items()
                  if paths is None or path in paths}
        stated = {path: value for path, value in chosen.items()
                  if path in COMPLETE["fields"]["values"]}
        accepted = {path: value for path, value in chosen.items()
                    if path in COMPLETE["acceptance"]["values"]}
        if stated:
            record = intake.set_fields(record, spec, stated, source="prompt")
        if accepted:
            accepted[intake.REFERENCE] = ALL_VALUES[intake.REFERENCE]
            record = intake.set_fields(record, spec, accepted, source="issue")
    return record


def ask(record: dict, spec: dict, frozen: dict | None = None) -> tuple[dict, dict]:
    """Evaluate and persist the open questions, as the CLI does."""
    view = intake.evaluate(record, spec, frozen=frozen)
    record = json.loads(json.dumps(record))
    record["open_questions"] = view["questions"]
    return record, view


def batch_paths(spec: dict, batch: int) -> set[str]:
    return {field["path"] for field in spec["fields"] if field.get("batch", 1) == batch}


def test_packaged_specs_validate_and_declare_their_targets():
    for task in ("task-performance", "task-day-0"):
        spec = spec_for(task)
        assert spec["task"] == task
        assert intake.validate_spec(spec) == []
        assert all(field["maps_to"] in intake.MAP_TARGETS for field in spec["fields"])


def test_day0_fields_stay_out_of_task_input_v1():
    spec = spec_for("task-day-0")
    assert all(field["maps_to"] == "day0-spec" for field in spec["fields"])


def test_complete_record_asks_nothing_and_unlocks_search():
    spec = spec_for()
    view = intake.evaluate(build(), spec)
    assert view["complete"] is True
    assert view["questions"] == []
    assert view["conflicts"] == []
    assert view["allowed_next"] == [
        "read_only_preparation", "baseline_measurement", "candidate_search"]
    assert view["execution"] == "not started"


def test_empty_record_asks_only_the_first_batch():
    spec = spec_for()
    view = intake.evaluate(intake.new_record("task-performance", record_id="intake-empty"), spec)
    asked = {question["field"] for question in view["questions"]}
    expected = batch_paths(spec, 1) - {"acceptance.min_improvement_pct"}
    assert asked == expected
    assert all(question["batch"] == 1 for question in view["questions"])
    assert view["complete"] is False


def test_second_batch_appears_once_the_first_is_settled():
    spec = spec_for()
    record = build(batch_paths(spec, 1))
    view = intake.evaluate(record, spec)
    asked = {question["field"] for question in view["questions"]}
    assert asked == batch_paths(spec, 2)
    assert all(question["batch"] == 2 for question in view["questions"])


def test_unknown_answer_blocks_its_stage_and_is_not_asked_again():
    spec = spec_for()
    record, view = ask(intake.new_record("task-performance", record_id="intake-unknown"), spec)
    question = next(item for item in view["questions"]
                    if item["field"] == "protocol.timing_boundary")
    record = intake.answer(record, spec, question_id=question["id"], unknown=True)
    view = intake.evaluate(record, spec)
    assert question["id"] not in {item["id"] for item in view["questions"]}
    baseline = next(item for item in view["blockers"]
                    if item["stage"] == "baseline_measurement")
    assert "protocol.timing_boundary" in {item["field"] for item in baseline["blocked_by"]}
    assert view["allowed_next"] == ["read_only_preparation"]
    assert record["fields"]["protocol.timing_boundary"] == {
        "value": None, "source": f"answer:{question['id']}",
        "status": "unknown", "asked": True,
    }


def test_stale_answer_after_a_dependency_change_is_rejected():
    spec = spec_for()
    record = build({"acceptance.metric_key", intake.REFERENCE})
    record, view = ask(record, spec)
    question = next(item for item in view["questions"]
                    if item["field"] == "acceptance.min_improvement_pct")
    changed = intake.set_fields(record, spec, {"acceptance.metric_key": "p99_ttft",
                                             intake.REFERENCE: ALL_VALUES[intake.REFERENCE]},
                                source="issue")
    with pytest.raises(intake.IntakeError) as error:
        intake.answer(changed, spec, question_id=question["id"], value=5)
    assert error.value.code == "stale_answer"


def test_duplicate_answer_is_rejected_once():
    spec = spec_for()
    record, view = ask(intake.new_record("task-performance", record_id="intake-dup"), spec)
    question = next(item for item in view["questions"]
                    if item["field"] == "acceptance.metric_key")
    record = intake.answer(record, spec, question_id=question["id"], value="p95_ttft")
    with pytest.raises(intake.IntakeError) as error:
        intake.answer(record, spec, question_id=question["id"], value="p95_ttft")
    assert error.value.code == "already_answered"


def test_acceptance_answer_from_a_card_stays_a_proposal():
    spec = spec_for()
    record, view = ask(intake.new_record("task-performance", record_id="intake-card"), spec)
    question = next(item for item in view["questions"]
                    if item["field"] == "acceptance.metric_key")
    record = intake.answer(record, spec, question_id=question["id"], value="p95_ttft")
    assert record["fields"]["acceptance.metric_key"]["status"] == "proposed"
    view = intake.evaluate(record, spec)
    search = next(item for item in view["blockers"] if item["stage"] == "candidate_search")
    assert "acceptance.metric_key" in {item["field"] for item in search["blocked_by"]}
    assert "candidate_search" not in view["allowed_next"]
    summary = intake.summary(record, spec)
    assert summary["proposed"]["acceptance.metric_key"] == "p95_ttft"


def test_acceptance_issue_confirms_a_previously_proposed_value():
    spec = spec_for()
    record = intake.new_record("task-performance", record_id="intake-upgrade")
    record = intake.set_fields(record, spec, {"acceptance.metric_key": "p95_ttft"},
                               source="prompt")
    assert record["fields"]["acceptance.metric_key"]["status"] == "proposed"
    record = intake.set_fields(record, spec, {intake.REFERENCE: "accepted issue"}, source="prompt")
    record = intake.set_fields(record, spec, {"acceptance.metric_key": "p95_ttft",
                                            intake.REFERENCE: "accepted issue"}, source="issue")
    assert record["fields"]["acceptance.metric_key"]["status"] == "confirmed"


def test_two_stated_values_become_a_question_with_both_options():
    spec = spec_for()
    record = intake.new_record("task-performance", record_id="intake-conflict")
    record = intake.set_fields(record, spec, {"acceptance.metric_key": "p95_ttft"},
                               source="prompt")
    record = intake.set_fields(record, spec, {"acceptance.metric_key": "p99_ttft"},
                               source="prompt")
    assert record["fields"]["acceptance.metric_key"]["status"] == "conflicting"
    record, view = ask(record, spec)
    question = view["questions"][0]
    assert question["field"] == "acceptance.metric_key"
    values = {option["value"] for option in question["options"]}
    assert values == {"p95_ttft", "p99_ttft"}


def test_frozen_gate_mismatch_blocks_candidate_search():
    spec = spec_for()
    frozen = {"acceptance.metric_key": "p99_ttft"}
    view = intake.evaluate(build(), spec, frozen=frozen)
    assert view["complete"] is False
    assert [item["field"] for item in view["conflicts"]] == ["acceptance.metric_key"]
    search = next(item for item in view["blockers"] if item["stage"] == "candidate_search")
    assert "acceptance.metric_key" in {item["field"] for item in search["blocked_by"]}
    assert "candidate_search" not in view["allowed_next"]


def test_unknown_paths_are_rejected_by_the_record_check():
    spec = spec_for()
    record = build()
    record["fields"]["bogus.path"] = {"value": 1, "source": "prompt", "status": "confirmed"}
    with pytest.raises(intake.IntakeError) as error:
        intake.evaluate(record, spec)
    assert error.value.code == "invalid_record"


def test_non_finite_numbers_are_rejected():
    spec = spec_for()
    record = intake.new_record("task-performance", record_id="intake-nan")
    with pytest.raises(intake.IntakeError) as error:
        intake.set_fields(record, spec, {"acceptance.min_improvement_pct": "nan"},
                          source="issue")
    assert error.value.code == "invalid_value"


def test_cli_evaluate_matches_the_python_view_and_writes_only_the_record(tmp_path, capsys):
    record_path = tmp_path / "record.json"
    code = cli.main([
        "task", "intake", "evaluate", "--task", "task-performance",
        "--record", str(record_path), "--json",
    ])
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    stored = json.loads(record_path.read_text(encoding="utf-8"))
    expected = intake.evaluate(stored, spec_for())
    for key in ("questions", "blockers", "conflicts", "allowed_next", "complete",
                "execution", "revision"):
        assert result[key] == expected[key]
    assert {path.name for path in tmp_path.iterdir()} == {"record.json"}


def test_cli_answer_then_summary(tmp_path, capsys):
    record_path = tmp_path / "record.json"
    assert cli.main([
        "task", "intake", "evaluate", "--task", "task-performance",
        "--record", str(record_path), "--set", "acceptance.metric_key=p95_ttft", "--json",
    ]) == 0
    view = json.loads(capsys.readouterr().out)
    question = next(item for item in view["questions"]
                    if item["field"] == "acceptance.metric_unit")
    assert cli.main([
        "task", "intake", "answer", "--record", str(record_path),
        "--question", question["id"], "--value", "ms", "--json",
    ]) == 0
    capsys.readouterr()
    assert cli.main(["task", "intake", "summary", "--record", str(record_path),
                     "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["proposed"]["acceptance.metric_unit"] == "ms"
    assert summary["execution"] == "not started"


def test_cli_stale_answer_exits_two(tmp_path, capsys):
    record_path = tmp_path / "record.json"
    assert cli.main([
        "task", "intake", "evaluate", "--task", "task-performance",
        "--record", str(record_path), "--set", "acceptance.metric_key=p95_ttft", "--json",
    ]) == 0
    view = json.loads(capsys.readouterr().out)
    question = next(item for item in view["questions"]
                    if item["field"] == "acceptance.min_improvement_pct")
    assert cli.main(["task", "intake", "evaluate", "--record", str(record_path),
                     "--set", "acceptance.metric_key=p99_ttft", "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["task", "intake", "answer", "--record", str(record_path),
                     "--question", question["id"], "--value", "5", "--json"]) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["error"] in ("stale_answer", "already_answered")


def test_frozen_values_read_the_gate_task_file():
    values = task_intake.frozen_values(PERFORMANCE / "frozen-gate.yaml")
    assert values["acceptance.metric_key"] == "p95_ttft"
    assert values["acceptance.min_improvement_pct"] == 10.0
    assert "acceptance.reference" not in values  # names the record; never compared


def test_matching_frozen_gate_keeps_a_complete_record_complete():
    frozen = task_intake.frozen_values(PERFORMANCE / "frozen-gate.yaml")
    view = intake.evaluate(build(), spec_for(), frozen=frozen)
    assert view["conflicts"] == [] and view["complete"] is True


@pytest.mark.parametrize("source", ["prompt", "task_file", "grilling_brief", "repo_inspection"])
def test_only_the_issue_or_frozen_record_confirms_an_acceptance_value(source):
    spec = spec_for()
    record = intake.new_record("task-performance", record_id="intake-source")
    record = intake.set_fields(record, spec, {"acceptance.metric_key": "p95_ttft"}, source=source)
    expected = "proposed" if source in ("prompt", "grilling_brief") else "assumed"
    assert record["fields"]["acceptance.metric_key"]["status"] == expected


def test_campaign_gate_blocks_until_complete(tmp_path):
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps(build(set(PARTIAL["fields"]["values"]))), encoding="utf-8")
    gate, _ = task_intake.campaign_gate(partial)
    assert gate["status"] == "blocked"
    assert gate["allowed_next"] == ["read_only_preparation"]
    complete = tmp_path / "complete.json"
    complete.write_text(json.dumps(build()), encoding="utf-8")
    gate, gated = task_intake.campaign_gate(complete)
    assert gate["status"] == "ready"
    assert gate["complete"] is True
    assert gated == build()


def test_campaign_start_refuses_an_incomplete_record_before_writing(project, tmp_path, capsys):  # noqa: F811
    record = tmp_path / "record.json"
    record.write_text(json.dumps(build(set(PARTIAL["fields"]["values"]))), encoding="utf-8")
    assert cli.main(start_arguments(project, extra=("--intake", str(record)))) == 2
    gate = json.loads(capsys.readouterr().out)
    assert gate["status"] == "blocked" and gate["execution"] == "not started"
    assert not project[3].exists()


def test_campaign_start_retains_the_record_it_gated(project, tmp_path, capsys):  # noqa: F811
    record = tmp_path / "record.json"
    record.write_text(json.dumps(build()), encoding="utf-8")
    assert cli.main(start_arguments(project, extra=("--intake", str(record)))) == 0
    result = json.loads(capsys.readouterr().out)
    retained = project[3] / "intake.json"
    assert result["intake"]["gate"] == "ready"
    assert result["intake"]["sha256"] == hashlib.sha256(retained.read_bytes()).hexdigest()
    assert json.loads(retained.read_text(encoding="utf-8")) == build()
    # The retained record does not disturb the managed campaign's own records.
    assert cli.main(["campaign", "status", "--directory", str(project[3])]) == 0


def test_campaign_start_without_a_record_warns_and_proceeds(project, capsys):  # noqa: F811
    assert cli.main(start_arguments(project)) == 0
    captured = capsys.readouterr()
    assert "intake gate was not evaluated" in captured.err
    assert "intake" not in json.loads(captured.out)


def test_day0_blocks_only_device_execution():
    spec = spec_for("task-day-0")
    view = intake.evaluate(intake.new_record("task-day-0", record_id="intake-day0"), spec)
    stages = {item["stage"] for item in view["blockers"]}
    assert stages == {"device_execution"}
    assert "device_execution" not in view["allowed_next"]
    record = intake.new_record("task-day-0", record_id="intake-day0")
    record = intake.set_fields(record, spec, {
        "day0.checkpoint": "checkpoints/model-v1",
        "day0.tokenizer_or_processor": "tokenizer-v1",
        "day0.target_engine_and_device": "engine x.y on device Z",
        "day0.first_scope": "text generation",
        "day0.reference_implementation": "reference wheel 1.0",
        "day0.replayable_inputs": "fixtures/day0-inputs",
        "day0.consistency_criteria": "top-1 token agreement >= 99%",
    }, source="prompt")
    view = intake.evaluate(record, spec)
    assert view["complete"] is True
    assert "device_execution" not in view["allowed_next"]


def test_partial_fixture_asks_only_the_remaining_first_batch():
    spec = spec_for()
    record = build(set(PARTIAL["fields"]["values"]))
    view = intake.evaluate(record, spec)
    asked = {question["field"] for question in view["questions"]}
    assert "optimization.objective" not in asked
    assert "protocol.timing_boundary" not in asked
    assert "acceptance.metric_key" in asked


def test_frozen_conflict_via_cli(tmp_path, capsys):
    record_path = tmp_path / "complete.json"
    record_path.write_text(json.dumps(build()), encoding="utf-8")
    assert cli.main([
        "task", "intake", "evaluate", "--record", str(record_path),
        "--frozen", str(PERFORMANCE / "frozen-mismatch.yaml"), "--json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["complete"] is False
    assert result["conflicts"][0]["field"] == "acceptance.metric_key"
    assert result["conflicts"][0]["frozen_value"] == "p99_ttft"


def test_self_written_gate_keeps_campaign_blocked(project, tmp_path, capsys):  # noqa: F811
    record_path = tmp_path / "record.json"
    gate_file = tmp_path / "gate.json"
    proposed = {**COMPLETE["acceptance"]["values"], intake.REFERENCE: str(gate_file)}
    gate_file.write_text(json.dumps({"schema_version": 1, "acceptance": {
        key.removeprefix("acceptance."): value for key, value in proposed.items()
    }}))
    cmd = ["task", "intake", "evaluate", "--record", str(record_path), "--json"]
    guesses = dict(COMPLETE["fields"]["values"])
    guesses.pop(intake.REFERENCE)
    for source, values, options in (
        ("workspace", guesses, ["--task", "task-performance"]),
        ("frozen_gate", proposed, ["--frozen", str(gate_file)]),
    ):
        args = []
        for key, value in values.items():
            args.extend(("--set", f"{key}={value}"))
        assert cli.main([*cmd, *options, "--source", source, *args]) == 0
        result = json.loads(capsys.readouterr().out)
    assert result["needs_user_input"] and not result["complete"]
    assert result["allowed_next"] == ["read_only_preparation"]
    questions = {q["field"]: q for q in result["questions"]}
    assert {"optimization.objective", "acceptance.metric_key", intake.REFERENCE} <= questions.keys()
    metric_option = questions["acceptance.metric_key"]["options"][0]
    assert metric_option["value"] == proposed["acceptance.metric_key"]
    assert result["fields"]["environment.backend"]["status"] == "confirmed"
    assert result["fields"]["optimization.objective"]["status"] == "assumed"
    assert result["fields"]["acceptance.metric_key"]["status"] == "assumed"
    assert cli.main([*cmd, "--set", f"{intake.REFERENCE}={gate_file}"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "user_answer_required"
    assert cli.main(start_arguments(project, extra=("--intake", str(record_path)))) == 2
    capsys.readouterr()
    assert not project[3].exists()

    # Records written before this fix may already say every workspace/gate value
    # was confirmed and cache a complete result. The execution path must recheck.
    record = json.loads(record_path.read_text())
    for field in record["fields"].values():
        field["status"] = "confirmed"
    record.update(complete=True, open_questions=[], allowed_next=["candidate_search"])
    record_path.write_text(json.dumps(record))
    assert task_intake.campaign_gate(record_path)[0]["status"] == "blocked"


def test_selected_gate_imports_only_its_values_and_changed_file_reopens_card(tmp_path, capsys):
    record = tmp_path / "record.json"
    gate = tmp_path / "gate.yaml"
    gate.write_bytes((PERFORMANCE / "frozen-gate.yaml").read_bytes())
    cmd = ["task", "intake", "evaluate", "--record", str(record), "--json"]
    assert cli.main([*cmd, "--task", "task-performance"]) == 0
    capsys.readouterr()

    # This is the separate reply to the outstanding reference question.
    answer = ["task", "intake", "answer", "--record", str(record), "--question",
              "q:acceptance.reference", "--value", str(gate), "--frozen", str(gate), "--json"]
    assert cli.main(answer) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["fields"]["acceptance.metric_key"]["status"] == "confirmed"
    assert view["fields"][intake.REFERENCE]["source"] == "answer:q:acceptance.reference"
    assert cli.main([*cmd, "--source", "frozen_gate", "--set",
                     "acceptance.min_improvement_pct=99"]) == 0
    assert json.loads(capsys.readouterr().out)["fields"]["acceptance.min_improvement_pct"][
        "value"] == 10

    gate.write_bytes((PERFORMANCE / "frozen-mismatch.yaml").read_bytes())
    assert cli.main([*cmd, "--frozen", str(gate)]) == 0
    view = json.loads(capsys.readouterr().out)
    assert any(q["field"] == intake.REFERENCE for q in view["questions"])
    assert view["fields"]["acceptance.metric_key"]["status"] == "assumed"
    assert task_intake.campaign_gate(record)[0]["status"] == "blocked"


def test_fully_specified_request_selects_existing_gate_without_questions(tmp_path, capsys):
    gate = PERFORMANCE / "frozen-gate.yaml"
    record = tmp_path / "record.json"
    values = {**COMPLETE["fields"]["values"], intake.REFERENCE: str(gate)}
    args = ["task", "intake", "evaluate", "--task", "task-performance", "--record",
            str(record), "--frozen", str(gate), "--json"]
    for key, value in values.items():
        args.extend(("--set", f"{key}={value}"))
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["complete"] and not result["needs_user_input"]
    assert task_intake.campaign_gate(record)[0]["status"] == "ready"


def test_user_can_replace_suggested_goal_and_settle_a_conflict():
    spec = spec_for()
    record = intake.new_record("task-performance", record_id="intake-suggested")
    record = intake.set_fields(record, spec, {"optimization.objective": "throughput"},
                               source="repo_inspection")
    record, _ = ask(record, spec)
    record = intake.answer(record, spec, question_id="q:optimization.objective", value="latency")
    assert record["fields"]["optimization.objective"]["value"] == "latency"
    assert record["fields"]["optimization.objective"]["status"] == "confirmed"
    record = intake.set_fields(record, spec, {"optimization.objective": "memory"}, source="prompt")
    record, view = ask(record, spec)
    assert view["questions"][0]["field"] == "optimization.objective"
    record = intake.answer(record, spec, question_id="q:optimization.objective", value="latency")
    assert record["fields"]["optimization.objective"]["status"] == "confirmed"
