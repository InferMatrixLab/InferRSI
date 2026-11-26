import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from inferrsi.harness.run_store import RunStore
from inferrsi.harness.work_control import WorkControl


@pytest.fixture
def control(tmp_path):
    result = WorkControl(RunStore(tmp_path / "store", "controls"))
    result.create(
        "campaign",
        {"fixed": "contract"},
        {"incumbent": "root"},
        cap_ms=1000,
        final_reserve_ms=100,
        deadline=time.time() + 60,
    )
    return result


def claim(control, op="work", **changes):
    args = dict(category="verify", cap_ms=200, domains=("device",), binding={"candidate": "c"})
    return control.claim("campaign", control.read("campaign")["revision"], op, **(args | changes))


def test_atomic_resource_and_budget_reservation_across_controllers(control):
    other = WorkControl(control.store)
    other.create("other", {}, {}, cap_ms=1000, final_reserve_ms=100, deadline=time.time() + 60)
    with ThreadPoolExecutor(2) as pool:

        def reserve(name):
            try:
                control.claim(
                    name, 0, name, category="verify", cap_ms=200, domains=("device",), binding={}
                )
                return True
            except ValueError:
                return False

        assert sum(pool.map(reserve, ("campaign", "other"))) == 1


def test_unknown_cleanup_or_usage_retains_reservation_and_never_relaunches(control):
    claim(control)
    control.launch("campaign", "work")
    control.settle(
        "campaign", "work", {"result": "unknown"}, actual_ms=None, cleanup_verified=False
    )
    assert control.available(control.read("campaign")) == 700
    with pytest.raises(ValueError, match="already claimed"):
        claim(control)
    with pytest.raises(ValueError, match="leased"):
        claim(control, "another")
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    assert reopened.read("campaign")["operations"]["work"]["status"] == "unknown"


def test_known_overrun_with_unknown_cleanup_blocks_other_domains_and_reconciles_once(control):
    claim(control)
    control.launch("campaign", "work")
    control.settle(
        "campaign", "work", {"result": "pending cleanup"}, actual_ms=950, cleanup_verified=False
    )
    reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
    result = reopened.read("campaign")
    assert result["blocked"]
    assert result["operations"]["work"]["status"] == "unknown"
    assert reopened.available(result) == -50
    with pytest.raises(ValueError, match="blocked"):
        claim(reopened, "other-domain", cap_ms=700, domains=("other-device",))
    reopened.create("other", {}, {}, cap_ms=1000, final_reserve_ms=100, deadline=time.time() + 60)
    with pytest.raises(ValueError, match="leased"):
        reopened.claim(
            "other", 0, "work", category="verify", cap_ms=200, domains=("device",), binding={}
        )
    # A later unknown observation cannot erase the retained lower bound.
    reopened.settle("campaign", "work", {}, actual_ms=None, cleanup_verified=False)
    assert reopened.available(reopened.read("campaign")) == -50
    with pytest.raises(ValueError, match="known usage"):
        reopened.settle("campaign", "work", {}, actual_ms=50, cleanup_verified=True)
    for _ in range(2):
        reopened.settle("campaign", "work", {"done": True}, actual_ms=950, cleanup_verified=True)
    result = reopened.read("campaign")
    assert result["spent_ms"] == 950 and result["blocked"]
    assert reopened.available(result) == -50
    reopened.claim(
        "other", 0, "work", category="verify", cap_ms=200, domains=("device",), binding={}
    )


def test_receipt_settlement_and_incumbent_are_atomic_and_idempotent(control):
    claim(control)
    control.launch("campaign", "work")

    def update(state):
        return state | {"incumbent": "child"}

    result = control.settle(
        "campaign",
        "work",
        {"proof": "bound"},
        actual_ms=50,
        cleanup_verified=True,
        transition=update,
    )
    assert result["state"]["incumbent"] == "child"
    control.settle("campaign", "work", {"proof": "bound"}, actual_ms=50, cleanup_verified=True)
    assert control.read("campaign")["spent_ms"] == 50
    with pytest.raises(ValueError, match="Conflicting"):
        control.settle("campaign", "work", {}, actual_ms=50, cleanup_verified=True)
    claim(control, "next")


def test_blocked_reconciliation_requires_settlement_and_preserves_accounting(control):
    claim(control)
    control.launch("campaign", "work")
    control.settle("campaign", "work", {}, actual_ms=950, cleanup_verified=False)
    before = control.read("campaign")
    with pytest.raises(ValueError, match="conclusively settled"):
        control.reconcile_blocked("campaign", before["revision"], "work", lambda state: {})
    assert control.read("campaign") == before
    control.settle("campaign", "work", {}, actual_ms=950, cleanup_verified=True)
    settled = control.read("campaign")
    with pytest.raises(ValueError, match="Stale"):
        control.reconcile_blocked("campaign", before["revision"], "work", lambda state: {})

    def fail(state):
        state["incumbent"] = "changed"
        raise ValueError("invalid recovery")

    with pytest.raises(ValueError, match="invalid recovery"):
        control.reconcile_blocked("campaign", settled["revision"], "work", fail)
    assert control.read("campaign") == settled
    after = control.reconcile_blocked(
        "campaign", settled["revision"], "work", lambda state: state | {"archived": "work"}
    )
    assert after == settled | {
        "revision": settled["revision"] + 1,
        "state": settled["state"] | {"archived": "work"},
    }


def test_expired_claim_cannot_start_and_does_not_charge_unstarted_work(control, monkeypatch):
    claim(control)
    monkeypatch.setattr("inferrsi.harness.work_control.time.time", lambda: 1e12)
    with pytest.raises(ValueError, match="expired"):
        control.launch("campaign", "work")
    result = control.read("campaign")
    assert result["operations"]["work"]["status"] == "settled"
    assert result["spent_ms"] == 0


@pytest.mark.parametrize("interrupted", [False, True])
def test_blocked_campaign_releases_preexisting_unstarted_claim(control, interrupted):
    claim(control, "overrun", domains=("first-device",))
    control.launch("campaign", "overrun")
    claim(control, "reserved")
    control.settle("campaign", "overrun", {}, actual_ms=201, cleanup_verified=False)
    if interrupted:
        reopened = WorkControl(RunStore(control.store.root, control.store.namespace))
        after = reopened.recover_unstarted("campaign")
        assert reopened.recover_unstarted("campaign") == after
    else:
        with pytest.raises(ValueError, match="blocked"):
            control.launch("campaign", "reserved")
        after = control.read("campaign")
    assert after["operations"]["reserved"]["receipt"] == {"not_started": "blocked"}
    assert after["operations"]["reserved"]["actual_ms"] == 0 and after["spent_ms"] == 0
    assert after["operations"]["overrun"]["status"] == "unknown"
    assert after["blocked"] and control.available(after) == 699
    assert [e["kind"] for e in after["events"] if e["operation"] == "reserved"] == [
        "claimed",
        "not_started",
    ]
    with control.store._connection() as db:
        assert [row["id"] for row in db.execute("SELECT id FROM work_domains")] == ["first-device"]


def test_cas_and_failed_transition_roll_back_accounting(control):
    before = control.read("campaign")
    control.update("campaign", before["revision"], lambda state: state | {"x": 1})
    with pytest.raises(ValueError, match="Stale"):
        control.update("campaign", before["revision"], lambda state: {})
    claim(control)
    control.launch("campaign", "work")

    def fail(state):
        raise ValueError("invalid receipt")

    with pytest.raises(ValueError, match="invalid receipt"):
        control.settle("campaign", "work", {}, actual_ms=20, cleanup_verified=True, transition=fail)
    assert control.read("campaign")["spent_ms"] == 0


def test_holdout_is_once_across_campaigns_even_after_interruption(control):
    before = control.read("campaign")
    control.claim_final("campaign", before["revision"], "heldout-data-v1", {"candidate": "c"})
    control.create("second", {}, {}, cap_ms=1000, final_reserve_ms=100, deadline=time.time() + 60)
    with pytest.raises(ValueError, match="consumed"):
        control.claim_final("second", 0, "heldout-data-v1", {"candidate": "other"})
    with pytest.raises(ValueError, match="frozen"):
        claim(control)
    control.finish_final("campaign", {"candidate": "c"}, {"verdict": "FAIL"})
    control.finish_final("campaign", {"candidate": "c"}, {"verdict": "FAIL"})
    with pytest.raises(ValueError, match="immutable"):
        control.finish_final("campaign", {"candidate": "c"}, {"verdict": "PASS"})
    with pytest.raises(ValueError, match="immutable"):
        claim(control, final=True, category="final")


def test_final_commit_rechecks_unreserved_operations_and_outstanding_usage(control):
    binding = {"candidate": "c"}
    result = {"verdict": "INCONCLUSIVE", "promoted": False}
    control.claim_final("campaign", 0, "held", binding)
    claim(control, "check", final=True, category="final", binding={"check": "objective"})
    control.launch("campaign", "check")
    before = control.read("campaign")
    with pytest.raises(ValueError, match="Unknown final usage"):
        control.finish_final("campaign", binding, result)
    assert control.read("campaign") == before
    control.settle("campaign", "check", {"done": True}, actual_ms=1, cleanup_verified=True)
    settled = control.read("campaign")
    with pytest.raises(ValueError, match="reservations changed"):
        control.finish_final("campaign", binding, result, unreserved=["objective"])
    assert control.read("campaign") == settled


def test_final_owner_uses_the_stored_campaign_identity(control):
    control.create("1", {}, {}, cap_ms=500, final_reserve_ms=100, deadline=time.time() + 60)
    with control.final_owner("1") as stored:
        assert stored == "1"
        with pytest.raises(BlockingIOError), control.final_owner(1):
            pytest.fail("SQLite aliases must not acquire a second finalizer")
    with control.final_owner(1) as stored:
        assert stored == "1"


def test_final_reserve_and_unknown_work_cannot_be_spent(control):
    with pytest.raises(ValueError, match="budget"):
        claim(control, cap_ms=901)
    claim(control)
    with pytest.raises(ValueError, match="unresolved"):
        control.claim_final("campaign", control.read("campaign")["revision"], "holdout", {})


def test_historical_terminal_final_cannot_launch_a_retained_reservation(control):
    control.claim_final("campaign", 0, "held", {})
    claim(control, "pending", final=True, category="final")
    claim(control, "started", final=True, category="final", domains=("other-device",))
    control.launch("campaign", "started")
    # Earlier versions could commit a non-promoting terminal result with unsettled work.
    result = {"verdict": "INCONCLUSIVE", "promoted": False}
    with control._transaction("campaign") as (_, body):
        body["final_result"] = result
    with pytest.raises(ValueError, match="finalized"):
        control.launch("campaign", "pending")
    doc = control.recover_unstarted("campaign")
    assert doc["operations"]["pending"]["receipt"] == {"not_started": "finalized"}
    assert doc["operations"]["started"]["status"] == "launched"
    assert doc["final_result"] == result and doc["spent_ms"] == 0
    with control.store._connection() as db:
        assert [row[0] for row in db.execute("SELECT operation FROM work_domains")] == ["started"]


def test_over_budget_final_is_accounted_but_never_promoted(control):
    control.claim_final("campaign", 0, "holdout", {"candidate": "c"})
    claim(control, final=True, category="final")
    control.launch("campaign", "work")
    control.settle("campaign", "work", {"verdict": "PASS"}, actual_ms=201, cleanup_verified=True)
    assert control.read("campaign")["spent_ms"] == 201
    assert control.read("campaign")["blocked"]
    with pytest.raises(ValueError, match="cannot promote"):
        control.finish_final(
            "campaign",
            {"candidate": "c"},
            {"verdict": "PASS"},
            transition=lambda state: state | {"incumbent": "c"},
        )


def test_read_only_control_does_not_create_or_change_tables(control):
    from inferrsi.harness.run_store import RunStoreReader

    reader = WorkControl(RunStoreReader(control.store.root, control.store.namespace))
    before = control.read("campaign")
    assert reader.read("campaign") == before
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader.update("campaign", before["revision"], lambda _: {"incumbent": "denied"})
    assert control.read("campaign") == before
