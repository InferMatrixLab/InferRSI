"""Credential-free tests: the in-memory CAS is NOT a production backend."""

import json
from dataclasses import replace

import pytest

from tools import skill_eval_budget as budget

KEY = budget.PRKey(123, 7)


def genesis(legacy=0):
    return budget.Ledger(KEY, budget.Genesis("audited-genesis-fixture", legacy))


def binding(number=1, amount=50_000_000):
    return budget.Binding(f"{number:064x}", f"workflow-{number}:attempt-1", amount)


class MemoryStore:
    def __init__(self, ledger):
        self.snapshot = budget.Snapshot("lineage-0", ledger)
        self.outcome = budget.WriteResult.COMMITTED
        self.write_on_unknown = False

    def read_verified(self, key):
        if self.snapshot is None or self.snapshot.ledger.key != key:
            raise budget.BudgetError("Missing existing history")
        return self.snapshot

    def compare_and_swap(self, expected, successor):
        if self.snapshot != expected:
            return budget.WriteResult.CONFLICT
        budget.validate_successor(expected.ledger, successor)
        if self.outcome is budget.WriteResult.COMMITTED or self.write_on_unknown:
            self.snapshot = budget.Snapshot(f"lineage-{successor.revision}", successor)
        return self.outcome


def test_budget_cumulative_across_revisions_retries_and_label_epochs():
    ledger = genesis(20_000_000)
    for number in range(1, 4):
        plan = binding(number, 60_000_000)
        ledger = budget.reserve(ledger, plan)
        ledger = budget.advance(ledger, plan, "claimed")
        ledger = budget.advance(ledger, plan, "finished", actual_cost=1)
    assert ledger.charged == 200_000_000
    assert ledger.remaining == 0
    with pytest.raises(budget.BudgetError):
        budget.reserve(ledger, binding(4, 1))
    assert budget.decode(budget.encode(ledger)) == ledger


def test_no_refunds_on_cancel_or_actual_cost():
    plan = binding(amount=200_000_000)
    ledger = budget.reserve(genesis(), plan)
    cancelled = budget.advance(ledger, plan, "cancelled")
    assert cancelled.remaining == 0
    assert budget.advance(cancelled, plan, "cancelled") == cancelled
    with pytest.raises(budget.BudgetError):
        budget.advance(cancelled, plan, "claimed")
    assert ledger.entries[0].phase == "reserved"  # pure transition


def test_reserve_exact_idempotency_and_conflicting_bindings():
    plan = binding()
    ledger = budget.reserve(genesis(), plan)
    assert budget.reserve(ledger, plan) is ledger
    for changed in (replace(plan, run_id="workflow-1:attempt-2"),
                    replace(plan, worst_case=1), replace(plan, plan_digest="a" * 64)):
        with pytest.raises(budget.BudgetError):
            budget.reserve(ledger, changed)


def test_claim_once_and_duplicate_execution_rejected():
    plan = binding()
    store = MemoryStore(budget.reserve(genesis(), plan))
    claimed = budget.claim_once(store, KEY, plan)
    assert claimed.entries[0].phase == "claimed"
    with pytest.raises(budget.BudgetError):
        budget.claim_once(store, KEY, plan)
    finished = budget.advance(claimed, plan, "finished", actual_cost=100)
    assert budget.advance(finished, plan, "finished", actual_cost=100) is finished
    with pytest.raises(budget.BudgetError):
        budget.advance(finished, plan, "finished", actual_cost=101)


@pytest.mark.parametrize("outcome,applied", [
    (budget.WriteResult.UNKNOWN, True), (budget.WriteResult.UNKNOWN, False),
    (budget.WriteResult.CONFLICT, False), ("committed", False), (None, False),
])
def test_uncertain_or_conflicted_claim_never_grants_execution(outcome, applied):
    plan = binding()
    store = MemoryStore(budget.reserve(genesis(), plan))
    store.outcome, store.write_on_unknown = outcome, applied
    with pytest.raises(budget.BudgetError, match="blocked"):
        budget.claim_once(store, KEY, plan)
    if applied:
        store.outcome = budget.WriteResult.COMMITTED
        with pytest.raises(budget.BudgetError, match="duplicate"):
            budget.claim_once(store, KEY, plan)


def test_lost_update_cannot_overwrite_or_overspend():
    store = MemoryStore(genesis())
    first = store.read_verified(KEY)
    stale = store.read_verified(KEY)
    a = budget.reserve(first.ledger, binding(1, 150_000_000))
    b = budget.reserve(stale.ledger, binding(2, 150_000_000))
    assert store.compare_and_swap(first, a) is budget.WriteResult.COMMITTED
    assert store.compare_and_swap(stale, b) is budget.WriteResult.CONFLICT
    with pytest.raises(budget.BudgetError, match="exhausted"):
        budget.reserve(store.read_verified(KEY).ledger, binding(2, 150_000_000))


def test_concurrent_claims_only_one_wins():
    plan = binding()
    store = MemoryStore(budget.reserve(genesis(), plan))
    first = store.read_verified(KEY)
    second = store.read_verified(KEY)
    claim = budget.advance(first.ledger, plan, "claimed")
    assert store.compare_and_swap(first, claim) is budget.WriteResult.COMMITTED
    assert store.compare_and_swap(second, claim) is budget.WriteResult.CONFLICT


def test_missing_history_does_not_create_zero_budget():
    store = MemoryStore(genesis())
    store.snapshot = None
    with pytest.raises(budget.BudgetError, match="Missing"):
        budget.claim_once(store, KEY, binding())
    with pytest.raises(budget.BudgetError):
        budget.Genesis("", 0)
    with pytest.raises(budget.BudgetError):
        budget.Genesis("unreconciled", None)
    assert genesis(200_000_000).remaining == 0


def test_wrong_pr_and_reset_rejected():
    old = budget.reserve(genesis(), binding())
    for reset in (genesis(), replace(old, key=budget.PRKey(124, 7)),
                  replace(old, genesis=budget.Genesis("replacement-audit", 0))):
        with pytest.raises(budget.BudgetError):
            budget.validate_successor(old, reset)
    store = MemoryStore(old)
    store.read_verified = lambda key: store.snapshot
    with pytest.raises(budget.BudgetError, match="wrong PR"):
        budget.claim_once(store, budget.PRKey(123, 8), binding())


@pytest.mark.parametrize("amount", [-1, True, 1.2, "1", None])
def test_non_integer_or_negative_money_rejected(amount):
    with pytest.raises(budget.BudgetError):
        budget.Genesis("audit", amount)
    with pytest.raises(budget.BudgetError):
        binding(amount=amount)


def test_zero_reservation_overrun_and_unreserved_execution_rejected():
    with pytest.raises(budget.BudgetError):
        binding(amount=0)
    plan = binding()
    with pytest.raises(budget.BudgetError):
        budget.advance(genesis(), plan, "claimed")
    ledger = budget.advance(budget.reserve(genesis(), plan), plan, "claimed")
    for phase, cost in (("cancelled", None), ("finished", plan.worst_case + 1),
                        ("finished", None), ("finished", -1)):
        with pytest.raises(budget.BudgetError):
            budget.advance(ledger, plan, phase, actual_cost=cost)


@pytest.mark.parametrize("payload", ["", "null", "{}", "[]", '{"x":1,"x":2}',
                                    '{"schema_version":NaN}', '{"revision":Infinity}'])
def test_corrupt_missing_ledger_rejected(payload):
    with pytest.raises(budget.BudgetError):
        budget.decode(payload)


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(extra=1), lambda v: v.update(schema_version=True),
    lambda v: v.update(revision=0), lambda v: v["key"].update(repository_id=True),
    lambda v: v["genesis"].update(legacy_charge=-1),
    lambda v: v["entries"].append(v["entries"][0]),
    lambda v: v["entries"][0].update(phase="unknown"),
    lambda v: v["entries"][0].update(actual_cost=0),
    lambda v: v["entries"][0]["binding"].update(worst_case=1.5),
])
def test_schema_corruption_rejected(mutation):
    value = json.loads(budget.encode(budget.reserve(genesis(), binding())))
    mutation(value)
    with pytest.raises(budget.BudgetError):
        budget.decode(json.dumps(value))


def test_storage_successor_validation_allows_only_one_transition():
    old = genesis()
    reserved = budget.reserve(old, binding())
    claimed = budget.advance(reserved, binding(), "claimed")
    finished = budget.advance(claimed, binding(), "finished", actual_cost=5)
    for before, after in ((old, reserved), (reserved, claimed), (claimed, finished)):
        budget.validate_successor(before, after)
    for before, after in ((old, claimed), (reserved, reserved), (finished, claimed)):
        with pytest.raises(budget.BudgetError):
            budget.validate_successor(before, after)


def test_unknown_reservation_write_reconciles_without_new_charge():
    store = MemoryStore(genesis())
    initial = store.read_verified(KEY)
    plan = binding()
    successor = budget.reserve(initial.ledger, plan)
    store.outcome = budget.WriteResult.UNKNOWN
    store.write_on_unknown = True
    assert store.compare_and_swap(initial, successor) is budget.WriteResult.UNKNOWN
    observed = store.read_verified(KEY)
    assert budget.reserve(observed.ledger, plan) is observed.ledger
    assert observed.ledger.charged == plan.worst_case


def test_storage_validator_rejects_reservation_rewrite_and_removal():
    first, second = binding(1), binding(2)
    old = budget.reserve(budget.reserve(genesis(), first), second)
    changed = replace(first, worst_case=1)
    rewritten = budget.advance(
        budget.reserve(budget.reserve(genesis(), changed), second), changed, "claimed")
    with pytest.raises(budget.BudgetError):
        budget.validate_successor(old, rewritten)
    removed = budget.advance(budget.advance(budget.reserve(genesis(), first), first,
                                           "claimed"), first, "finished", actual_cost=1)
    with pytest.raises(budget.BudgetError):
        budget.validate_successor(old, removed)


def test_storage_transport_exception_never_grants_execution():
    store = MemoryStore(budget.reserve(genesis(), binding()))

    def unknown(*args):
        raise OSError("Synthetic lost response")

    store.compare_and_swap = unknown
    with pytest.raises(OSError):
        budget.claim_once(store, KEY, binding())
