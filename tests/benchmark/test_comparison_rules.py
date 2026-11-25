"""Controlled paired efficiency conclusions over retained normalized observations."""

from copy import deepcopy

import pytest

from inferrsi.benchmark.comparison import (
    DEFAULT_POLICY,
    DEFAULT_TASKS,
    summarize,
    validate_policy,
)


def trial(task="task", repeat=1, condition="on", *, speedup=2, wall=10, tokens=100):
    return {"id": f"{task}-{repeat}-{condition}", "task": task, "repeat": repeat,
            "condition": condition, "status": "completed", "eligible": True, "gaps": [],
            "metrics": {"speedup": speedup, "wall_seconds": wall, "tokens": tokens}}


def assess(on, off, policy=None):
    return summarize([on, off], ["task"], 1, policy or DEFAULT_POLICY)


@pytest.mark.parametrize(("speedup", "wall", "expected"), [
    (3, 9, "efficiency_improved"),
    (2, 10, "no_gain"),
    (1, 11, "regression"),
    (3, 11, "tradeoff"),
    (1, 9, "tradeoff"),
])
def test_effect_and_cost_are_both_required_for_efficiency(speedup, wall, expected):
    result = assess(trial(speedup=speedup, wall=wall), trial(condition="off"))
    assert result["conclusion"]["kind"] == expected
    assert result["conclusion"]["inference"] == "descriptive_only"
    assert result["counts"]["eligible_pairs"] == 1
    assert "statistical significance" in result["conclusion"]["limitation"]


def test_default_knowledge_suite_has_both_requested_tasks():
    assert DEFAULT_TASKS == ("qwen21-denoise-npu", "moe-forward-npu")


def test_unknown_supplemental_tokens_do_not_become_zero_or_imply_token_efficiency():
    result = assess(trial(speedup=3, wall=9, tokens=None), trial(condition="off"))
    assert result["conclusion"]["kind"] == "efficiency_improved"
    assert result["conclusion"]["scope"]["metrics"] == ["speedup", "wall_seconds"]
    assert result["tasks"][0]["metrics"]["tokens"]["paired_factor"] is None
    policy = deepcopy(DEFAULT_POLICY)
    policy["metrics"].append("tokens")
    assert assess(trial(tokens=None), trial(condition="off"), policy)["conclusion"]["kind"] == (
        "insufficient_evidence")


@pytest.mark.parametrize("mutation", [
    {"status": "failed", "eligible": False, "gaps": ["independent final failed"]},
    {"status": "running", "eligible": False},
    {"status": "blocked", "eligible": False},
    {"status": "completed", "eligible": False, "gaps": ["source binding unverified"]},
])
def test_failures_stay_in_denominator_instead_of_improving_the_result(mutation):
    on = trial(speedup=5, wall=1)
    on.update(mutation)
    result = assess(on, trial(condition="off"))
    assert result["conclusion"]["kind"] == "insufficient_evidence"
    assert result["counts"]["planned_trials"] == result["counts"]["observed_trials"] == 2
    assert result["counts"]["eligible_pairs"] == 0
    assert result["tasks"][0]["metrics"]["speedup"]["paired_factor"] is None
    assert result["pairs"][0]["gaps"]


def test_missing_pair_and_minimum_sample_policy_are_not_silently_dropped():
    records = [trial(repeat=1), trial(repeat=1, condition="off")]
    missing = summarize(records, ["task"], 2, DEFAULT_POLICY)
    assert missing["conclusion"]["kind"] == "insufficient_evidence"
    assert missing["counts"]["planned_trials"] == 4
    assert missing["counts"]["missing_trials"] == 2
    assert len(missing["pairs"]) == 2
    assert missing["pairs"][1]["on"] is None
    policy = {**DEFAULT_POLICY, "minimum_pairs": 2}
    assert summarize(records, ["task"], 1, policy)["conclusion"]["kind"] == (
        "insufficient_evidence")


def test_pairs_are_matched_before_aggregation():
    records = [trial(repeat=1, speedup=1), trial(repeat=1, condition="off", speedup=10),
               trial(repeat=2, speedup=10), trial(repeat=2, condition="off", speedup=20)]
    result = summarize(list(reversed(records)), ["task"], 2, DEFAULT_POLICY)
    metrics = result["tasks"][0]["metrics"]["speedup"]
    assert metrics["paired_factor"] == pytest.approx(0.05**0.5)
    assert metrics["on_median"] / metrics["off_median"] != pytest.approx(0.05**0.5)
    assert result["conclusion"]["kind"] == "regression"


def test_two_tasks_keep_separate_axes_and_mixed_effects_are_a_tradeoff():
    records = [trial(task="first", speedup=3), trial(task="first", condition="off"),
               trial(task="second", speedup=1), trial(task="second", condition="off")]
    result = summarize(records, ["first", "second"], 1, DEFAULT_POLICY)
    assert result["conclusion"]["kind"] == "tradeoff"
    assert [row["conclusion"]["kind"] for row in result["tasks"]] == [
        "efficiency_improved", "regression"]
    assert "aggregate_speedup" not in result


def test_frozen_neutral_band_is_reciprocal_and_does_not_claim_equivalence():
    policy = deepcopy(DEFAULT_POLICY)
    policy["tolerances"]["speedup"] = 0.1
    first = assess(trial(speedup=2.1), trial(condition="off"), policy)
    second = assess(trial(), trial(condition="off", speedup=2.1), policy)
    assert first["conclusion"]["kind"] == second["conclusion"]["kind"] == "no_gain"
    assert "neutral tolerances" in first["conclusion"]["text"]


@pytest.mark.parametrize("value", [None, True, 0, -1, float("nan"), float("inf"), 10**400])
def test_invalid_primary_metric_remains_insufficient(value):
    assert assess(trial(speedup=value), trial(condition="off"))["conclusion"]["kind"] == (
        "insufficient_evidence")


def test_ratio_overflow_stays_missing_instead_of_emitting_infinity():
    result = assess(trial(speedup=1e308), trial(condition="off", speedup=1e-308))
    assert result["pairs"][0]["metrics"]["speedup"]["factor"] is None
    assert result["conclusion"]["kind"] == "insufficient_evidence"


def test_even_count_medians_of_finite_observations_do_not_overflow():
    records = [trial(repeat=repeat, condition=condition, wall=1e308)
               for repeat in (1, 2) for condition in ("on", "off")]
    result = summarize(records, ["task"], 2, DEFAULT_POLICY)
    assert result["tasks"][0]["metrics"]["wall_seconds"]["on_median"] == 1e308
    assert result["conclusion"]["kind"] == "no_gain"


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(extra=True),
    lambda p: p.update(metrics=["wall_seconds"]),
    lambda p: p.update(metrics=["speedup", "speedup"]),
    lambda p: p.update(metrics=["speedup", "money"]),
    lambda p: p.update(minimum_pairs=True),
    lambda p: p.update(minimum_pairs=0),
    lambda p: p["tolerances"].update(speedup=True),
    lambda p: p["tolerances"].update(tokens=-1),
    lambda p: p["tolerances"].update(wall_seconds=float("inf")),
    lambda p: p["tolerances"].pop("tokens"),
])
def test_ambiguous_policy_is_rejected(mutate):
    policy = deepcopy(DEFAULT_POLICY)
    mutate(policy)
    with pytest.raises(ValueError):
        validate_policy(policy)


def test_validated_policy_is_independent_of_input_and_defaults():
    policy = validate_policy(DEFAULT_POLICY)
    policy["metrics"].append("tokens")
    policy["tolerances"]["speedup"] = 0.1
    assert DEFAULT_POLICY["metrics"] == ["speedup", "wall_seconds"]
    assert DEFAULT_POLICY["tolerances"]["speedup"] == 0


@pytest.mark.parametrize("records", [
    [trial(), trial()],
    [trial(task="unexpected")],
    [{**trial(), "repeat": True}],
    [{**trial(), "repeat": 2}],
    [{**trial(), "condition": "baseline"}],
    [{**trial(), "status": "PASS"}],
    [{**trial(), "eligible": "true"}],
    [trial(), {**trial(condition="off"), "id": "task-1-on"}],
])
def test_duplicate_or_out_of_matrix_records_are_rejected(records):
    with pytest.raises(ValueError):
        summarize(records, ["task"], 1, DEFAULT_POLICY)
