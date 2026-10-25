import copy
import json
import shutil
import subprocess

import pytest

from inferrsi.infra.artifacts import sha256, write_json
from tests.fixtures.skill_eval_compare_support import FixedOutputClient, configuration
from tools import goal_checkpoint as checkpoint
from tools import skill_eval_compare as compare


@pytest.fixture(scope="module")
def comparison_templates(tmp_path_factory):
    root = tmp_path_factory.mktemp("checkpoint")
    try:
        compare.require_git_version(subprocess.check_output(("git", "--version"), text=True))
    except ValueError as error:
        pytest.skip(str(error))
    config, repo = configuration(root, ids=("one",))
    fresh = root / "fresh"
    plan_hash = compare.prepare(config, repo, fresh)
    completed = root / "completed"
    shutil.copytree(fresh, completed)
    client = FixedOutputClient(root)
    compare.execute(completed, plan_hash, client=client)
    assert len(client.calls) == 2
    return fresh, completed


def pin(path, root):
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}


def setup_goal(root, template):
    run = root / "comparison"
    shutil.copytree(template, run)
    scope = root / "scope.md"
    scope.write_text("Explicit fixture: verify the comparison and obtain owner acceptance.\n",
                     encoding="utf-8")
    goal = {"schema_version": 1, "id": "offline-goal", "title": "Comparison acceptance",
            "scope": pin(scope, root), "acceptance_owner": "Fixture Owner",
            "criteria": [{"id": "comparison", "description": "Owner accepts the evidence",
                          "evidence": [], "acceptance": None}],
            "dependencies": [], "next_step": "Propose the frozen comparison to the owner",
            "plan_sha256": sha256(run / "plan/freeze.json"), "authorization": None}
    path = root / "goal.json"
    write_json(path, goal)
    return path, goal, run


def authorize(path, goal):
    record = path.parent / "authorization.json"
    write_json(record, {"plan_sha256": goal["plan_sha256"], "authorized_by": "Fixture Owner",
                        "reference": "https://example.invalid/explicit-authorization"})
    goal["authorization"] = pin(record, path.parent)
    write_json(path, goal)


def accept(path, goal, run):
    criterion = goal["criteria"][0]
    criterion["evidence"] = [pin(run / "results/status.json", path.parent)]
    record = path.parent / "acceptance.json"
    write_json(record, {"goal_id": goal["id"], "criterion_id": criterion["id"],
                        "criterion_sha256": checkpoint.criterion_sha256(goal, criterion),
                        "accepted_by": goal["acceptance_owner"], "decision": "accepted"})
    criterion["acceptance"] = pin(record, path.parent)
    write_json(path, goal)


def files(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def test_read_only_deterministic_continuation_and_no_report_writes(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[0])
    authorize(path, goal)
    before = files(tmp_path)
    first = checkpoint.build_checkpoint(path, run)
    second = checkpoint.build_checkpoint(path, run)
    assert first == second
    assert first["recommendation"]["action"] == "propose_step"
    assert first["comparison"]["conditions"]["baseline"]["input_tokens"] is None
    assert first["comparison"]["status"] == {"execution_state": "not_completed"}
    assert first["recommendation"]["input_sha256"] == first["input_sha256"]
    view = checkpoint.markdown(first)
    assert "propose_step" in view and goal["next_step"] in view
    assert "remaining / unknown" in view and "plan_sha256" in view
    assert "authorization.json@" in view and "unknown" in view
    assert files(tmp_path) == before
    assert not (run / "report.json").exists()
    assert not (run / "report.md").exists()


def test_missing_or_changed_authorization_is_not_permission(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[0])
    assert checkpoint.build_checkpoint(path, run)["recommendation"]["action"] == (
        "request_authorization")
    authorize(path, goal)
    record = path.parent / "authorization.json"
    value = json.loads(record.read_bytes())
    value["plan_sha256"] = "0" * 64
    write_json(record, value)
    goal["authorization"] = pin(record, path.parent)
    write_json(path, goal)
    result = checkpoint.build_checkpoint(path, run)
    assert not result["authorized"]
    assert result["recommendation"]["action"] == "request_authorization"


def test_merged_code_and_unknown_acceptance_remain_incomplete(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    merged = tmp_path / "merged.json"
    write_json(merged, {"state": "merged", "checks": "passed"})
    goal["criteria"][0]["evidence"] = [pin(merged, tmp_path)]
    goal["acceptance_owner"] = None
    write_json(path, goal)
    result = checkpoint.build_checkpoint(path, run)
    assert result["remaining"] == ["comparison"]
    assert result["recommendation"]["action"] == "wait_acceptance"
    assert "Acceptance owner: unknown" in checkpoint.markdown(result)


def test_explicit_accepted_completion_preserves_paired_semantics(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    original = compare.read_report(run)
    before = files(run)
    accept(path, goal, run)
    result = checkpoint.build_checkpoint(path, run)
    assert result["recommendation"]["action"] == "report_accepted"
    assert not result["remaining"]
    assert result["comparison"]["counts"] == original["counts"]
    assert result["comparison"]["conditions"] == original["conditions"]
    assert compare.read_report(run) == original
    assert files(run) == before


@pytest.mark.parametrize("change", ["scope", "description", "evidence", "owner"])
def test_acceptance_is_bound_to_criteria_scope_evidence_and_owner(
    tmp_path, comparison_templates, change,
):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    accept(path, goal, run)
    if change == "scope":
        scope = tmp_path / "scope.md"
        scope.write_text("Different accepted scope", encoding="utf-8")
        goal["scope"] = pin(scope, tmp_path)
    elif change == "description":
        goal["criteria"][0]["description"] = "A changed requirement"
    elif change == "evidence":
        goal["criteria"][0]["evidence"] = [pin(run / "report.json", tmp_path)]
    else:
        goal["acceptance_owner"] = "Another Owner"
    write_json(path, goal)
    result = checkpoint.build_checkpoint(path, run)
    assert result["recommendation"]["action"] == "repair_evidence"
    assert "unbound_acceptance:comparison" in result["problems"]


@pytest.mark.parametrize("artifact", ["plan/tasks.json", "plan/freeze.json",
                                     "results/status.receipt.json",
                                     "results/one-candidate-1/receipt.json",
                                     "results/one-candidate-1/answer.json"])
@pytest.mark.parametrize("operation", ["delete", "corrupt"])
def test_stale_or_missing_evidence_cannot_be_proposed_or_accepted(
    tmp_path, comparison_templates, artifact, operation,
):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    accept(path, goal, run)
    target = run / artifact
    if operation == "delete":
        target.unlink()
    else:
        target.write_text("{broken", encoding="utf-8")
    before = files(tmp_path)
    result = checkpoint.build_checkpoint(path, run)
    assert result["recommendation"]["action"] == "repair_evidence"
    assert result["problems"]
    assert files(tmp_path) == before


def test_changed_plan_settings_require_fresh_authorization(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[0])
    authorize(path, goal)
    plan = run / "plan/freeze.json"
    value = json.loads(plan.read_bytes())
    value["model"]["effort"] = "changed-setting"
    write_json(plan, value)
    assert "stale_plan" in checkpoint.build_checkpoint(path, run)["problems"]
    goal["plan_sha256"] = sha256(plan)
    write_json(path, goal)
    result = checkpoint.build_checkpoint(path, run)
    assert not result["authorized"]
    assert result["recommendation"]["action"] == "request_authorization"


def test_interruption_never_becomes_a_fresh_or_accepted_attempt(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[0])
    authorize(path, goal)
    (run / "results/one-baseline-1").mkdir()
    write_json(run / "results/start.json", {"started_at": 1})
    result = checkpoint.build_checkpoint(path, run)
    assert result["recommendation"]["action"] == "repair_evidence"
    assert "interrupted_or_ambiguous_attempt" in result["problems"]


@pytest.mark.parametrize("reason", ["token_budget", "time_budget", "client_failed"])
def test_stopped_attempt_does_not_retry(tmp_path, comparison_templates, reason):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    status_path = run / "results/status.json"
    status = json.loads(status_path.read_bytes())
    status.update(execution_state="stopped", stop_reason=reason)
    write_json(status_path, status)
    write_json(run / "results/status.receipt.json", {"result_sha256": sha256(status_path)})
    result = checkpoint.build_checkpoint(path, run)
    expected = "prepare_new_plan" if reason == "client_failed" else "stop_budget"
    assert result["recommendation"]["action"] == expected


def test_dependency_is_named_and_completion_does_not_hide_it(tmp_path, comparison_templates):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    accept(path, goal, run)
    dependency = tmp_path / "review.md"
    dependency.write_text("Independent review is still pending", encoding="utf-8")
    goal["dependencies"] = [{"id": "review", "description": "Independent review",
                             "state": "waiting", "evidence": pin(dependency, tmp_path)}]
    write_json(path, goal)
    result = checkpoint.build_checkpoint(path, run)
    assert result["recommendation"]["action"] == "wait_dependency"
    assert result["recommendation"]["reasons"] == ("dependency:review",)
    assert "Independent review (waiting)" in checkpoint.markdown(result)


@pytest.mark.parametrize("usage", [None, "unknown", -1])
def test_unknown_or_invalid_status_usage_cannot_become_zero(
    tmp_path, comparison_templates, usage,
):
    path, goal, run = setup_goal(tmp_path, comparison_templates[1])
    accept(path, goal, run)
    status_path = run / "results/status.json"
    value = json.loads(status_path.read_bytes())
    value["observed_tokens"] = usage
    write_json(status_path, value)
    write_json(run / "results/status.receipt.json", {"result_sha256": sha256(status_path)})
    goal["criteria"][0]["acceptance"] = None
    goal["criteria"][0]["evidence"] = []
    write_json(path, goal)
    result = checkpoint.build_checkpoint(path, run)
    assert "invalid_status:observed_tokens" in result["problems"]
    assert result["recommendation"]["action"] == "repair_evidence"
    assert result["comparison"]["status"]["observed_tokens"] == usage


def test_cli_saves_complete_view_and_refuses_input_overwrite(
    tmp_path, comparison_templates, capsys,
):
    path, goal, run = setup_goal(tmp_path, comparison_templates[0])
    arguments = ["--goal", str(path), "--comparison", str(run)]
    assert checkpoint.main(arguments) == 0
    assert "request_authorization" in capsys.readouterr().out
    destination = tmp_path / "checkpoint.json"
    assert checkpoint.main([*arguments, "--format", "json", "--output", str(destination)]) == 0
    saved = json.loads(destination.read_bytes())
    assert saved["input_sha256"] == checkpoint.build_checkpoint(path, run)["input_sha256"]
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        checkpoint.main([*arguments, "--output", str(path)])
    assert error.value.code == 2
    assert path.read_bytes() == before
    with pytest.raises(SystemExit):
        checkpoint.main([*arguments, "--output", str(run / "plan/checkpoint.md")])
    assert not (run / "plan/checkpoint.md").exists()


@pytest.mark.parametrize("change", ["empty", "duplicate", "unknown", "invalid_pin"])
def test_invalid_explicit_goal_contract_fails_at_boundary(tmp_path, comparison_templates, change):
    path, goal, run = setup_goal(tmp_path, comparison_templates[0])
    if change == "empty":
        goal["criteria"] = []
    elif change == "duplicate":
        goal["criteria"].append(copy.deepcopy(goal["criteria"][0]))
    elif change == "unknown":
        goal["approve_everything"] = True
    else:
        goal["scope"]["sha256"] = "not-a-digest"
    write_json(path, goal)
    with pytest.raises(ValueError):
        checkpoint.build_checkpoint(path, run)
