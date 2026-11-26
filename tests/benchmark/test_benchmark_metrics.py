"""Benchmark metrics use retained observations, never invented costs or generic scores."""

from copy import deepcopy

import pytest

from inferrsi.benchmark.summary import POLICY, comparison, single, token_usage

SELECTION = {"metric": "speedup", "direction": "maximize"}


def step(identity="r1", status="completed", *, accepted=False, verified=True):
    return {"candidate_id": identity, "assessment_status": status, "record_verified": verified,
            "execution_state": "completed", "execution_returncode": 0,
            "selection_decision": "retained" if accepted else "not_retained",
            "best_candidate": {"candidate_id": identity if accepted else "older"}}


def summary(*, speedup=2, tokens=None, rounds=None, policy=POLICY, selection=SELECTION):
    return single(policy, [step(accepted=True)] if rounds is None else rounds,
                  {"score": speedup}, {"kind": "candidate"}, final_verified=True,
                  usage=tokens, selection=selection)


def usage(inputs=100, outputs=20, cached=50, **changes):
    record = {"value": {"input_tokens": inputs, "output_tokens": outputs,
                        "cached_input_tokens": cached}, "source": "retained-receipt-sha256",
              "scope": "trial_agent_session", "coverage": "complete"}
    record.update(changes)
    return record


def test_acceptance_counts_promotions_rejections_and_uncertain_attempts_separately():
    rows = [step(accepted=True), step("r2"), step("r3", "candidate_failure"),
            step("r4", "infrastructure_failure"), step("r5", verified=False),
            {"phase": "final"}]
    value = summary(rounds=rows)
    assert value["accepted_steps"] == 1
    assert value["assessed_steps"] == 3
    assert value["submitted_steps"] == 5
    assert value["infrastructure_failures"] == value["unresolved_steps"] == 1
    assert value["step_acceptance_rate"] == pytest.approx(1 / 3)
    assert value["step_coverage"] == "partial"


def test_generic_score_cannot_be_a_speedup_even_with_a_successful_final():
    value = summary(selection={"metric": "latency", "direction": "minimize"})
    assert value["final_speedup"] is value["final_kind"] is None
    assert value["missing_reasons"]["final_speedup"]


@pytest.mark.parametrize("score", [None, 0, -1, float("nan"), float("inf"), True])
def test_invalid_final_values_stay_unknown(score):
    assert summary(speedup=score)["final_speedup"] is None


def test_baseline_fallback_is_identified_and_candidate_regression_not_clipped():
    fallback = single(POLICY, [], {"score": 0.99}, {"kind": "baseline"},
                      final_verified=True, selection=SELECTION)
    assert fallback["final_speedup"] == 1
    assert fallback["final_kind"] == "baseline_fallback"
    assert fallback["step_acceptance_rate"] is None
    assert summary(speedup=0.8)["final_speedup"] == 0.8
    assert summary(speedup=1)["final_kind"] == "candidate"
    incomplete = single(POLICY, [], {"score": 4}, {"kind": "candidate"}, selection=SELECTION)
    assert incomplete["final_speedup"] is incomplete["final_kind"] is None


def test_schema_binding_rejects_unknown_versions_and_legacy_without_mutating_input():
    policy = {**POLICY, "metrics_schema_version": 2}
    before = deepcopy(policy)
    for candidate in (None, [], [1], policy, {**POLICY, "metrics_schema_version": True}):
        value = summary(policy=candidate)
        assert value["final_speedup"] is value["step_acceptance_rate"] is None
        assert value["submitted_steps"] is value["assessed_steps"] is None
        assert value["missing_reasons"]
    assert policy == before
    assert summary(policy=deepcopy(POLICY))["final_speedup"] == 2


def test_complete_tokens_cached_subset_and_partial_subtotals():
    assert token_usage(usage())["total_tokens"] == 120
    partial = token_usage(usage(coverage="unknown"))
    assert partial["total_tokens"] is None
    assert partial["observed_tokens"] == 120
    assert token_usage(usage(cached=101))["total_tokens"] is None
    assert token_usage(usage(scope="settled_search_rounds"))["total_tokens"] is None
    no_cache = usage()
    del no_cache["value"]["cached_input_tokens"]
    assert token_usage(no_cache)["total_tokens"] == 120


def trial(side, repeat=1, *, speedup=2, tokens=None, **changes):
    value = {"task": "task", "condition": side, "repeat": repeat, "metrics_comparable": True,
             "benchmark_metrics": summary(speedup=speedup, tokens=tokens)}
    value.update(changes)
    return value


def test_paired_estimator_is_not_ratio_of_arm_medians_and_missing_tokens_is_local():
    trials = [trial("on", 1, speedup=2), trial("off", 1, speedup=1),
              trial("on", 2, speedup=4), trial("off", 2, speedup=8)]
    value = comparison(trials, ["task"], 2, POLICY)
    metrics = value["tasks"][0]["metrics"]
    assert metrics["performance_benefit_ratio"]["value"] == pytest.approx(1)
    assert metrics["token_consumption_ratio"]["value"] is None
    assert metrics["token_consumption_ratio"]["eligible_pairs"] == 0


def test_missing_required_pair_keeps_observed_only_but_no_official_total():
    value = comparison([trial("on"), trial("off")], ["task"], 2, POLICY)
    metric = value["tasks"][0]["metrics"]["performance_benefit_ratio"]
    assert metric["value"] is value["performance_benefit_ratio"] is None
    assert metric["observed_only"] == 1
    assert metric["eligible_pairs"] == 1 and metric["planned_pairs"] == 2
    assert any("on" in reason for reason in metric["missing_reasons"])
    assert any("off" in reason for reason in metric["missing_reasons"])


def test_three_pair_counterexample_preserves_pairing_and_reciprocity():
    # Synthetic example: https://github.com/InferMatrixLab/InferRSI/issues/536#issuecomment-7034821517
    reference, treatment = [1, 100, 100], [2, 3, 200]
    trials = [item for repeat, (off, on) in enumerate(zip(reference, treatment), 1)
              for item in (trial("on", repeat, speedup=on), trial("off", repeat, speedup=off))]
    assert comparison(trials, ["task"], 3, POLICY)["performance_benefit_ratio"] == pytest.approx(2)
    reversed_trials = deepcopy(trials)
    for item in reversed_trials:
        item["condition"] = "off" if item["condition"] == "on" else "on"
    assert comparison(reversed_trials, ["task"], 3, POLICY)[
        "performance_benefit_ratio"] == pytest.approx(0.5)


@pytest.mark.parametrize("on,off,expected", [(60, 120, 0.5), (0, 120, 0), (0, 0, None)])
def test_token_consumption_direction_and_zero_denominator(on, off, expected):
    trials = [trial("on", tokens=usage(on, 0, 0)), trial("off", tokens=usage(off, 0, 0))]
    result = comparison(trials, ["task"], 1, POLICY)
    assert result["tasks"][0]["metrics"]["token_consumption_ratio"]["value"] == expected


def test_partial_acceptance_and_incomparable_identity_do_not_produce_a_pair():
    trials = [trial("on"), trial("off")]
    trials[0]["benchmark_metrics"]["step_coverage"] = "partial"
    result = comparison(trials, ["task"], 1, POLICY)["tasks"][0]["metrics"]
    assert result["performance_benefit_ratio"]["value"] == 1
    assert result["acceptance_rate_delta_pp"]["value"] is None
    trials[0]["metrics_comparable"] = False
    assert comparison(trials, ["task"], 1, POLICY)["performance_benefit_ratio"] is None


@pytest.mark.parametrize("on,off", [(1e-300, 1e300), (1e300, 1e-300)])
def test_unrepresentable_performance_ratio_is_unknown_without_breaking_report(on, off):
    trials = [trial("on", speedup=on), trial("off", speedup=off)]
    result = comparison(trials, ["task"], 1, POLICY)
    assert result["performance_benefit_ratio"] is None
    metric = result["tasks"][0]["metrics"]["performance_benefit_ratio"]
    assert metric["value"] is None
    assert metric["missing_reasons"]
