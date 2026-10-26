import json
import subprocess

import pytest

from inferrsi.harness.improvement import SelectionPolicy, select
from inferrsi.harness.skill_evaluation import CodexClient, TrialBudget, usage_totals
from tests.fixtures.skill_eval_improvement_support import ImprovementClient, configuration
from tools import skill_eval_improve as improve
from tools.skill_eval_compare import require_git_version


@pytest.fixture
def prepared(tmp_path):
    try:
        require_git_version(subprocess.check_output(("git", "--version"), text=True))
    except ValueError as error:
        pytest.skip(str(error))
    config, repo = configuration(tmp_path)
    output = tmp_path / "run"
    digest = improve.prepare(config, repo, output)
    return output, digest, ImprovementClient(tmp_path)


def test_selects_cost_saving_only_after_quality_and_rerun(prepared):
    output, digest, client = prepared
    result = improve.execute_offline(output, digest, client=client)
    assert result["accepted"] and result["effective_candidate"] == "INV"
    assert result["selection"]["assessments"]["DOM"]["reason"] == "quality_floor"
    assert result["observed_execution"]["calls"] == 16
    assert result["observed_execution"]["total_tokens"] == 1400
    assert result["observed_execution"]["cached_input_tokens"] == 320
    assert result["observed_execution"]["command_calls"] == 32
    assert result["selected_execution"]["total_tokens"] == 120
    assert result["observed_execution"]["cost"] is None
    assert result["proposal_cost"] is None
    stages = [c["stage"] for c in client.calls]
    assert stages == sum(([stage] * 4 for stage in (
        "probe-INV", "probe-DOM", "rerun-INV", "holdout-INV")), [])
    for call in client.calls:
        assert call["files"] == ["knowledge/audit/SKILL.md", "knowledge/audit/notes.md",
                                  "task.json"]
        if call["stage"].startswith("probe"):
            assert call["case"].startswith("development")
            assert "holdout" not in call["prompt"]
    experience = json.loads((output / "development-experience.json").read_text())
    assert "holdout" not in json.dumps(experience)
    with pytest.raises(FileExistsError):
        improve.execute_offline(output, digest, client=client)
    assert len(client.calls) == 16


@pytest.mark.parametrize("stage", ["rerun-INV", "holdout-INV"])
@pytest.mark.parametrize("mode", ["incorrect", "unknown", "runner_error"])
def test_bad_successor_or_holdout_retains_h0(prepared, stage, mode):
    output, digest, client = prepared
    client.overrides[stage, "INV"] = mode
    result = improve.execute_offline(output, digest, client=client)
    assert not result["accepted"] and result["effective_candidate"] == "H0"
    if stage == "rerun-INV":
        assert not any(c["stage"].startswith("holdout") for c in client.calls)


@pytest.mark.parametrize("stage", ["rerun-INV", "holdout-INV"])
def test_cost_only_improvement_must_survive_rerun_and_holdout(prepared, stage):
    output, digest, client = prepared
    client.token_overrides[stage, "INV"] = 240
    result = improve.execute_offline(output, digest, client=client)
    assert not result["accepted"] and result["effective_candidate"] == "H0"


@pytest.mark.parametrize("mode", ["unknown", "malformed_usage"])
def test_unknown_probe_usage_stops_entire_step_and_keeps_h0(prepared, mode):
    output, digest, client = prepared
    client.overrides["probe-INV", "H0"] = mode
    result = improve.execute_offline(output, digest, client=client)
    assert not result["accepted"] and result["selection"]["selected"] == "H0"
    assert len(client.calls) == 1 and result["budget"]["stop_reason"] == "unknown_usage"


def test_tampered_probe_evidence_invalidates_cached_acceptance(prepared):
    output, digest, client = prepared
    assert improve.execute_offline(output, digest, client=client)["accepted"]
    trace = next((output / "comparisons/probe-INV/results").glob("*/agent/stdout.log"))
    trace.write_text("tampered", encoding="utf-8")
    replay = improve.report(output)
    assert not replay["accepted"] and not replay["retained_selection_consistent"]


def test_frozen_selection_and_hidden_input_tampering_are_rejected(prepared):
    output, digest, client = prepared
    hidden = output / "inputs/holdout.json"
    hidden.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen improvement input changed"):
        improve.execute_offline(output, digest, client=client)
    assert not client.calls


def test_real_client_cannot_use_offline_entry(prepared):
    output, digest, _ = prepared
    with pytest.raises(ValueError, match="Real-model"):
        improve.execute_offline(output, digest, client=CodexClient("unused", "unused", 1))


@pytest.mark.parametrize("limit", [1, 3, 9])
def test_outer_budget_bounds_all_phases(tmp_path, limit):
    try:
        require_git_version(subprocess.check_output(("git", "--version"), text=True))
    except ValueError as error:
        pytest.skip(str(error))
    config, repo = configuration(tmp_path, max_calls=limit)
    output = tmp_path / "run"
    digest = improve.prepare(config, repo, output)
    client = ImprovementClient(tmp_path)
    result = improve.execute_offline(output, digest, client=client)
    assert len(client.calls) == limit and not result["accepted"]
    assert result["budget"]["stop_reason"] == "call_budget"


def test_token_threshold_is_shared_across_probes_and_rerun(tmp_path):
    try:
        require_git_version(subprocess.check_output(("git", "--version"), text=True))
    except ValueError as error:
        pytest.skip(str(error))
    config, repo = configuration(tmp_path, token_stop=700)
    output = tmp_path / "run"
    digest = improve.prepare(config, repo, output)
    client = ImprovementClient(tmp_path)
    result = improve.execute_offline(output, digest, client=client)
    # Two probes consume 680 scripted tokens. One rerun request crosses the
    # admission threshold, then no new request (including holdout) may start.
    assert len(client.calls) == 9 and client.calls[-1]["stage"] == "rerun-INV"
    assert result["budget"]["stop_reason"] == "token_budget"
    assert result["effective_candidate"] == "H0"


def test_candidate_cannot_edit_an_unlisted_resource(tmp_path):
    try:
        require_git_version(subprocess.check_output(("git", "--version"), text=True))
    except ValueError as error:
        pytest.skip(str(error))
    config, repo = configuration(tmp_path)
    data = json.loads(config.read_text())
    data["allowlist"] = ["audit/SKILL.md"]
    config.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="outside the Markdown allowlist"):
        improve.prepare(config, repo, tmp_path / "run")


def test_usage_missing_and_cached_subset_are_not_double_counted():
    trial = {"observations": {"usage": {"input_tokens": 10, "output_tokens": 2,
                                        "cached_input_tokens": 8}, "command_count": 3}}
    assert usage_totals([trial])["total_tokens"] == 12
    unknown = {"observations": {"usage": {"input_tokens": 10}}}
    assert usage_totals([trial, unknown])["total_tokens"] is None
    assert usage_totals([trial, unknown])["cached_input_tokens"] is None
    assert usage_totals([trial, unknown])["command_calls"] is None


@pytest.mark.parametrize("changes", [{"min_success_rate": float("nan")},
                                   {"min_success_rate": 2}, {"max_regressions": True},
                                   {"token_weight": -1},
                                   {"quality_weight": 0, "token_weight": 0}])
def test_invalid_policy_rejected(changes):
    values = dict(min_success_rate=1, max_regressions=0, quality_weight=1, token_weight=1)
    with pytest.raises(ValueError):
        SelectionPolicy(**(values | changes))


def test_deadline_and_unknown_usage_are_external_admission_stops():
    budget = TrialBudget(1, 0, 1)
    assert budget.stop_reason() == "time_budget"
    budget.record({"observations": {"usage": None}})
    assert budget.stop_reason() == "unknown_usage"


def policy_report(baseline_passes, candidate_passes, tokens, regressions=0):
    return {
        "pairs": [{"case_id": str(i), "repeat": 1, "outcome": "unchanged_correct",
                   "baseline": {"split": "development"}, "candidate": {"split": "development"}}
                  for i in range(4)],
        "status": {"execution_state": "completed"}, "model": {"name": "fixture"},
        "exam": {"cases": "fixed"}, "arms": {"baseline": {"bundle": "fixed"}},
        "conditions": {"baseline": {"verdicts": {"PASS": baseline_passes}, "total_tokens": 100},
                       "candidate": {"verdicts": {"PASS": candidate_passes},
                                     "total_tokens": tokens}},
        "counts": {"regression": regressions},
    }


def test_cost_weight_can_retain_h0_over_higher_quality_expensive_candidates():
    reports = {"INV": policy_report(2, 4, 1000), "DOM": policy_report(2, 3, 800)}
    assert select(reports, SelectionPolicy(0.5, 0, 0, 1))["selected"] == "H0"
    assert select(reports, SelectionPolicy(0.5, 0, 1, 0))["selected"] == "INV"


def test_same_quality_regression_fails_before_cost_selection():
    report = policy_report(2, 2, 50, regressions=1)
    decision = select({"INV": report}, SelectionPolicy(0.5, 0, 1, 1))
    assert decision["selected"] == "H0"
    assert decision["assessments"]["INV"]["reason"] == "regressions"


def test_equal_candidates_keep_h0_and_mismatched_probes_are_rejected():
    reports = {"INV": policy_report(4, 4, 100), "DOM": policy_report(4, 4, 100)}
    assert select(reports, SelectionPolicy(1, 0, 1, 1))["selected"] == "H0"
    reports["DOM"]["exam"] = {"cases": "different"}
    with pytest.raises(ValueError, match="share H0"):
        select(reports, SelectionPolicy(1, 0, 1, 1))
