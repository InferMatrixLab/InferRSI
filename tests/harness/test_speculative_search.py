from dataclasses import FrozenInstanceError, fields, replace

import pytest

from inferrsi.contracts.claim import Verdict
from inferrsi.harness import candidates
from inferrsi.harness import search_tree as tree
from tests.fixtures.speculative_search import (
    add,
    attempt,
    complete,
    contract,
    digest,
    observe,
    producer,
    receipt,
    start,
)


@pytest.mark.parametrize("lane,filename", [("engine", "kernel.py"), ("skill", "SKILL.md")])
def test_failed_parent_can_be_repaired_with_its_own_snapshot_and_complete_evidence(
    tmp_path, lane, filename,
):
    # File retention is real; grades are synthetic controls, not either production adapter.
    work = tmp_path / "work"
    work.mkdir()
    source = work / filename
    state = start(configuration=contract(search_id=lane))
    for cid, value, parent in (("broken", -1, "root"), ("repaired", 3, "broken")):
        source.write_text(str(value))
        retained = tmp_path / cid
        identity = candidates.retain(work, retained)
        state = add(state, cid, parent, artifact_digest=identity)
        actual = int((retained / filename).read_text())
        state = observe(state, cid, "quality", Verdict.PASS if actual > 0 else Verdict.FAIL)
        if actual > 0:
            # A high objective alone never compensates for missing or failed quality.
            state = observe(state, cid, "objective", objective=actual)
    source.write_text("999")
    assert candidates.identity(tmp_path / "repaired") == tree.accept(state).artifact_digest
    assert tree.accept(state).candidate_id == "repaired"
    assert tree.verified_gain(state) == 2
    assert tree.missing_checks(state, "broken") == ("objective",)
    assert tree.evidence(state, "broken")["quality"].verdict == Verdict.FAIL
    assert tree.candidate_valid(state, "broken")


def test_incomplete_parent_can_be_extended_without_fabricating_parent_results():
    state = add(add(start(), "parent"), "child", "parent")
    state = complete(state, "child", 4)
    assert tree.accept(state).candidate_id == "child"
    assert tree.evidence(state, "parent") == {}


def test_objective_prediction_partial_results_and_failed_quality_cannot_win():
    state = add(start(), "candidate")
    state = observe(state, "candidate", "objective", objective=1000)
    assert tree.accept(state).candidate_id == "root"
    state = observe(state, "candidate", "quality", Verdict.FAIL)
    assert tree.missing_checks(state, "candidate") == ()  # Known failure is not missing.
    assert tree.accept(state).candidate_id == "root"
    assert tree.verified_gain(state) == 0


@pytest.mark.parametrize("direction,sign", [("maximize", 1), ("minimize", -1)])
def test_finite_objectives_cannot_publish_an_infinite_gain(direction, sign):
    state = start(configuration=contract(direction=direction), score=-sign * 1e308)
    state = complete(add(state, "candidate"), "candidate", sign * 1e308)
    with pytest.raises(ValueError, match="finite objective"):
        tree.verified_gain(state)


@pytest.mark.parametrize("direction", ["maximize", "minimize"])
@pytest.mark.parametrize("order", [("z", "a"), ("a", "z")])
def test_selection_is_independent_of_receipt_order_and_root_wins_ties(direction, order):
    state = start(configuration=contract(direction=direction), score=10)
    for cid in order:
        state = complete(add(state, cid), cid, 11 if direction == "maximize" else 9)
    assert tree.accept(state).candidate_id == "a"
    assert tree.verified_gain(state) == 1
    tied = complete(add(start(score=10), "a"), "a", 10)
    assert tree.accept(tied).candidate_id == "root"


@pytest.mark.parametrize("late", [True, False])
def test_real_dependency_invalidation_and_success_race_cannot_leave_stale_incumbent(late):
    dependency = tree.Dependency("measurement-source", 0)
    state = add(start(dependencies=(dependency,)), "candidate")
    state = observe(state, "candidate", "quality")
    binding = attempt(state, "candidate", "objective", dependencies=(dependency,))
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    result = receipt(binding, objective=5)
    if not late:
        state = tree.record_receipt(state, result, expected_revision=state.revision)
        assert tree.accept(state).candidate_id == "candidate"
    state = tree.invalidate(state, dependency.key, expected_revision=state.revision)
    if late:
        state = tree.record_receipt(state, result, expected_revision=state.revision)
    assert result in state.receipts  # Archive is distinct from evidence admission.
    assert tree.accept(state).candidate_id == "root"
    assert tree.missing_checks(state, "candidate") == ("objective",)


def test_old_receipt_after_new_attempt_cannot_override_current_outcome_or_be_reused():
    dependency = tree.Dependency("measurement-source", 0)
    state = add(start(dependencies=(dependency,)), "candidate")
    state = observe(state, "candidate", "quality")
    state = observe(state, "candidate", "objective", objective=9, dependencies=(dependency,))
    old = state.receipts[-1]
    state = tree.invalidate(state, dependency.key, expected_revision=state.revision)
    new_dependency = state.dependencies[0]
    binding = attempt(state, "candidate", "objective", dependencies=(new_dependency,))
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    state = tree.record_receipt(state, old, expected_revision=state.revision)
    assert tree.accept(state).candidate_id == "root"
    state = tree.record_receipt(state, receipt(binding, Verdict.FAIL),
                                expected_revision=state.revision)
    before = state
    state = tree.record_receipt(state, old, expected_revision=state.revision)
    assert state is before
    assert tree.evidence(state, "candidate")["objective"].verdict == Verdict.FAIL
    assert tree.accept(state).candidate_id == "root"


def test_generation_invalidation_affects_actual_descendants_but_not_other_branch():
    dependency = tree.Dependency("retrieved-context", 0)
    state = start(dependencies=(dependency,))
    state = add(state, "parent", dependencies=(dependency,))
    state = complete(add(state, "child", "parent"), "child", 10)
    state = complete(add(state, "other"), "other", 3)
    state = tree.invalidate(state, dependency.key, expected_revision=state.revision)
    assert not tree.candidate_valid(state, "child")
    assert tree.accept(state).candidate_id == "other"
    with pytest.raises(ValueError, match="dependencies"):
        add(state, "grandchild", "child", dependencies=())


def test_invalid_root_blocks_search_and_acceptance_but_allows_late_archival():
    dependency = tree.Dependency("root-source", 0)
    state = add(start(dependencies=(dependency,), root_dependencies=(dependency,)), "candidate")
    binding = attempt(state, "candidate", "quality")
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    state = tree.invalidate(state, dependency.key, expected_revision=state.revision)
    state = tree.record_receipt(state, receipt(binding), expected_revision=state.revision)
    with pytest.raises(ValueError, match="root"):
        tree.accept(state)
    with pytest.raises(ValueError, match="root"):
        add(state, "another")


def test_inconclusive_is_missing_and_may_be_retried_with_fresh_identity():
    state = add(start(), "candidate")
    state = observe(state, "candidate", "quality", Verdict.INCONCLUSIVE)
    assert tree.missing_checks(state, "candidate") == ("quality", "objective")
    state = complete(state, "candidate", 2)
    assert tree.accept(state).candidate_id == "candidate"
    assert len([item for item in state.attempts if item.check_id == "quality"]) == 3


@pytest.mark.parametrize("verdict", [Verdict.PASS, Verdict.FAIL])
def test_valid_outcomes_cannot_be_retried_until_they_pass(verdict):
    state = observe(add(start(), "candidate"), "candidate", "quality", verdict)
    with pytest.raises(ValueError, match="retried"):
        observe(state, "candidate", "quality")


def test_unsettled_attempt_blocks_replacement_even_after_invalidation():
    dependency = tree.Dependency("measurement-source", 0)
    state = add(start(dependencies=(dependency,)), "candidate")
    binding = attempt(state, "candidate", "quality", dependencies=(dependency,))
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    state = tree.invalidate(state, dependency.key, expected_revision=state.revision)
    replacement = attempt(state, "candidate", "quality", dependencies=state.dependencies)
    with pytest.raises(ValueError, match="Unsettled"):
        tree.register_attempt(state, replacement, expected_revision=state.revision)


@pytest.mark.parametrize("field", [field.name for field in fields(tree.Context)])
def test_receipts_from_changed_contract_plan_grader_environment_or_data_are_rejected(field):
    state = add(start(), "candidate")
    binding = attempt(state, "candidate", "quality")
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    wrong = replace(binding, context=replace(binding.context, **{field: "different"}))
    with pytest.raises(ValueError, match="registered"):
        tree.record_receipt(state, receipt(wrong), expected_revision=state.revision)


@pytest.mark.parametrize("field,value", [
    ("search_id", "other-search"), ("candidate_id", "root"),
    ("artifact_digest", digest("different")), ("check_id", "objective"),
    ("attempt_id", "other-attempt"), ("execution_key", "other-execution"),
    ("reservation_id", "other-reservation"), ("lease_id", "other-lease"),
])
def test_receipt_must_match_the_entire_registered_binding(field, value):
    state = add(start(), "candidate")
    binding = attempt(state, "candidate", "quality")
    state = tree.register_attempt(state, binding, expected_revision=state.revision)
    with pytest.raises(ValueError, match="registered"):
        tree.record_receipt(state, receipt(replace(binding, **{field: value})),
                            expected_revision=state.revision)


def test_same_bytes_do_not_transfer_evidence_and_conflicting_receipts_are_rejected():
    state = complete(add(start(), "first", artifact_digest=digest("same")), "first", 5)
    old = state.receipts[-1]
    state = add(state, "second", "first", artifact_digest=digest("same"))
    assert tree.evidence(state, "second") == {}
    with pytest.raises(ValueError, match="Conflicting"):
        tree.record_receipt(state, replace(old, objective=6), expected_revision=state.revision)
    with pytest.raises(ValueError, match="reused"):
        tree.register_attempt(state, replace(old.attempt, candidate_id="second"),
                              expected_revision=state.revision)


def test_generation_snapshot_candidates_and_history_are_immutable():
    state = start()
    with pytest.raises(ValueError, match="snapshot"):
        add(state, "candidate", snapshot="updated-mid-search")
    advanced = add(state, "candidate")
    assert len(state.candidates) == 1
    with pytest.raises(FrozenInstanceError):
        advanced.candidates[1].artifact_digest = digest("mutated")
    with pytest.raises(ValueError, match="immutable"):
        add(advanced, "candidate", artifact_digest=digest("changed"))
    with pytest.raises(ValueError, match="Stale"):
        tree.add_candidate(advanced, tree.Candidate("other", digest("other"), "root", producer()),
                            expected_revision=state.revision)


@pytest.mark.parametrize("limit", ["max_candidates", "max_depth", "max_attempts"])
def test_bounded_search_still_returns_the_qualified_root(limit):
    config = contract(**{limit: 2 if limit == "max_attempts" else 1})
    state = start(configuration=config)
    with pytest.raises(ValueError, match="limit"):
        if limit == "max_candidates":
            add(state, "first")
        elif limit == "max_depth":
            add(add(state, "first"), "second", "first")
        else:
            observe(add(state, "first"), "first", "quality")
    assert tree.accept(state).candidate_id == "root"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "10"])
def test_invalid_objective_never_becomes_evidence(value):
    state = add(start(), "candidate")
    with pytest.raises(ValueError, match="finite"):
        receipt(attempt(state, "candidate", "objective"), objective=value)


def test_root_bootstrap_requires_complete_scoped_passing_evidence():
    state = start()
    for receipts in (state.receipts[:1], (*state.receipts, state.receipts[0]),
                     (replace(state.receipts[0], verdict=Verdict.FAIL), state.receipts[1])):
        with pytest.raises(ValueError):
            tree.initialize(state.contract, state.candidates[0], receipts)
    with pytest.raises(ValueError, match="objective"):
        tree.initialize(state.contract, state.candidates[0],
                        (state.receipts[0], replace(state.receipts[1], objective=None)))


def test_contract_copies_ordered_checks_and_rejects_strings_and_unknown_dependencies():
    checks = ["quality", "objective"]
    configuration = contract(checks=checks)
    checks.clear()
    assert configuration.checks == ("quality", "objective")
    with pytest.raises(ValueError, match="ordered"):
        contract(checks="quality")
    with pytest.raises(ValueError, match="dependencies"):
        add(start(), "candidate", dependencies=(tree.Dependency("undeclared", 0),))
