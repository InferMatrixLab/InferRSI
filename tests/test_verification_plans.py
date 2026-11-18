from dataclasses import replace
from itertools import combinations

import pytest

from inferrsi.contracts.claim import Verdict
from inferrsi.harness import search_tree as tree
from inferrsi.harness.verification_plans import Job, completion_menu
from tests.fixtures.speculative_search import add, attempt, contract, observe, start


def menu(state, jobs, **changes):
    options = dict(available_budget=100, available_jobs=20, max_targets=3, max_jobs=20)
    return completion_menu(state, jobs, **(options | changes))


def fixture():
    state = start()
    jobs = [Job("setup", 3)]
    for cid in ("a", "b", "c"):
        state = add(state, cid)
        jobs.extend((Job(f"{cid}-quality", 2, cid, "quality", ("setup",)),
                     Job(f"{cid}-objective", 4, cid, "objective", (f"{cid}-quality",))))
    return state, tuple(jobs)


def test_low_standalone_value_checks_are_preserved_as_completion_bundles():
    state, jobs = fixture()
    plans = menu(state, jobs, available_budget=9)
    assert len(plans) == 3
    assert {plan.candidate_ids for plan in plans} == {("a",), ("b",), ("c",)}
    assert all(len(plan.job_ids) == 3 and plan.cost == 9 for plan in plans)
    assert all(plan.job_ids[0] == "setup" for plan in plans)
    # No partial check subset can be presented as a completed candidate.
    assert menu(state, jobs, available_budget=8) == ()


def test_cross_branch_completion_counts_shared_preparation_once():
    state, jobs = fixture()
    plans = menu(state, jobs, available_budget=15, max_targets=2)
    pairs = [plan for plan in plans if len(plan.candidate_ids) == 2]
    assert len(pairs) == 3
    assert all(plan.cost == 15 and plan.job_ids.count("setup") == 1 for plan in pairs)
    assert all(len(plan.job_ids) == 5 for plan in pairs)


def exhaustive_oracle(jobs, budget, job_limit, target_limit):
    # Independent oracle enumerates all job subsets, not candidate-completion unions.
    result = {}
    for size in range(len(jobs) + 1):
        for subset in combinations(jobs, size):
            ids = {job.job_id for job in subset}
            if (len(ids) > job_limit or sum(job.cost for job in subset) > budget
                    or any(set(job.prerequisites) - ids or set(job.conflicts) & ids
                           for job in subset)):
                continue
            targets = tuple(cid for cid in ("a", "b", "c")
                            if {f"{cid}-quality", f"{cid}-objective"} <= ids)
            if not 0 < len(targets) <= target_limit:
                continue
            cost = sum(job.cost for job in subset)
            result[targets] = min(cost, result.get(targets, cost))
    return result


@pytest.mark.parametrize("budget", [0, 8, 9, 14, 15, 20, 21])
@pytest.mark.parametrize("target_limit", [1, 2, 3])
def test_exact_menu_matches_independent_exhaustive_job_subset_oracle(budget, target_limit):
    state, jobs = fixture()
    expected = exhaustive_oracle(jobs, budget, 7, target_limit)
    actual = {plan.candidate_ids: plan.cost for plan in menu(
        state, jobs, available_budget=budget, available_jobs=7, max_targets=target_limit,
    )}
    assert actual == expected


def test_conflicts_job_caps_and_attempt_caps_cannot_be_overridden_by_budget():
    state, jobs = fixture()
    jobs = tuple(replace(job, conflicts=("b-objective",)) if job.job_id == "a-objective"
                 else job for job in jobs)
    assert all(not {"a", "b"} <= set(plan.candidate_ids) for plan in menu(state, jobs))
    assert menu(state, jobs, available_jobs=2) == ()
    limited = replace(state, contract=replace(state.contract, max_attempts=3))
    assert menu(limited, jobs) == ()  # Root used two; completing another needs two.
    with pytest.raises(ValueError, match="enumeration"):
        menu(state, jobs, max_jobs=6)


def test_partial_evidence_reduces_work_but_failure_is_not_a_completion_target():
    state, jobs = fixture()
    state = observe(state, "a", "quality")
    state = observe(state, "b", "quality", Verdict.FAIL)
    # The adapter rebuilds the menu from remaining work and scopes prerequisite reuse.
    jobs = tuple(replace(job, prerequisites=("setup",)) if job.job_id == "a-objective"
                 else job for job in jobs if job.job_id != "a-quality")
    plans = menu(state, jobs, available_budget=7)
    assert [(plan.candidate_ids, plan.cost) for plan in plans] == [(("a",), 7)]


def test_unknown_cost_and_invalid_dependency_graphs_are_rejected():
    state, jobs = fixture()
    for cost in (0, -1, True, None, float("nan")):
        with pytest.raises(ValueError, match="cost"):
            Job("unknown", cost)
    with pytest.raises(ValueError, match="Unknown job relation"):
        menu(state, (*jobs, Job("orphan", 1, prerequisites=("absent",))))
    with pytest.raises(ValueError, match="Cyclic"):
        menu(state, (*jobs, Job("x", 1, prerequisites=("y",)),
                     Job("y", 1, prerequisites=("x",))))
    with pytest.raises(ValueError, match="Ambiguous"):
        menu(state, (*jobs, Job("duplicate", 1, "a", "quality")))
    with pytest.raises(ValueError, match="ordered"):
        Job("x", 1, prerequisites="setup")


def test_inflight_work_prevents_replanning_even_if_source_is_invalidated():
    dependency = tree.Dependency("source", 0)
    state = add(start(dependencies=(dependency,)), "a")
    binding = attempt(state, "a", "quality", dependencies=(dependency,))
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    state = tree.invalidate(state, dependency.key, expected_revision=state.revision)
    with pytest.raises(ValueError, match="Settle"):
        menu(state, [])


def test_inconclusive_outcome_remains_a_completion_job():
    state, jobs = fixture()
    state = observe(state, "a", "quality", Verdict.INCONCLUSIVE)
    assert ("a",) in {plan.candidate_ids for plan in menu(state, jobs, available_budget=9)}


def test_planning_never_changes_evidence_or_spends_the_supplied_budget():
    state, jobs = fixture()
    before = state
    plans = menu(state, jobs)
    assert plans
    assert all((plan.search_id, plan.state_revision) == (state.contract.search_id, state.revision)
               for plan in plans)
    assert state is before
    assert tree.accept(state).candidate_id == "root"
    assert tree.verified_gain(state) == 0
    with pytest.raises(ValueError, match="known integers"):
        menu(state, jobs, available_budget=None)


def test_all_jobs_must_name_known_candidates_and_frozen_required_checks():
    state = start(configuration=contract())
    with pytest.raises(ValueError, match="Unknown candidate"):
        menu(state, [Job("q", 1, "absent", "quality")])
    with pytest.raises(ValueError, match="Unknown required check"):
        menu(state, [Job("q", 1, "root", "unregistered-check")])
