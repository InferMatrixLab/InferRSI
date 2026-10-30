"""Fake stores/clock/launch only: no credentials, network or provider calls."""

import json
import pickle
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from inferrsi.model import anthropic_agent as provider
from tools import kv_pilot_admission as pilot
from tools import skill_eval_budget as b

NOW = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)
KEY = b.PRKey(123, 999)
DAY = b.shanghai_day(NOW)
BOUND = pilot.FULL_RESERVATION_MICROUSD
USAGE = {"input_tokens": 10, "output_tokens": 4,
         "cache_read_input_tokens": 5, "cache_creation_input_tokens": 6}


def policy(**changes):
    config = {
        "model": {"name": "claude-opus-5-5", "effort": "not_applicable"},
        "client": {"kind": provider.EDIT_KIND, "provider": "yibuapi",
                   "endpoint": provider.ENDPOINT, "api_version": "2023-06-01",
                   "max_requests": 8, "max_output_tokens": 4096,
                   "max_request_bytes": 262144, "max_read_bytes": 32768,
                   "max_tool_calls": 32},
        "pricing": {"currency": "USD", "unit": "per_million_tokens",
                    "model": "claude-opus-5-5", "group": "audited-example-group",
                    "rates": {"input": "8", "output": "40", "cache_read": "0.4",
                              "cache_write": "10"}, "request_fee": "0",
                    "max_input_tokens": 1_000_000,
                    "rate_evidence": "https://github.com/example/repo/issues/1#issuecomment-1",
                    "expires_at": int(NOW.timestamp()) + 7200},
        "spend_limit": {"currency": "USD", "amount": "200"},
    }
    values = {"campaign_id": "example-feasibility", "key": KEY,
              "execution_id": "example-run-1.1", "plan_sha256": "1" * 64,
              "pr_head": "2" * 40, "source_revision": "3" * 40,
              "actor_sha256": ("4" * 64, "5" * 64),
              "provider_json": provider.canonical(config),
              "expires_at": int(NOW.timestamp()) + 7200}
    return pilot.PilotPolicy(**(values | changes))


class FakeStore:
    """Exercise the existing store transition/CAS contract, including ambiguity."""

    def __init__(self, ledger, events):
        self.ledger, self.events = ledger, events
        self.daily = type(ledger) is b.DailyLedger
        self.name = "daily" if self.daily else "pr"
        self.token = 0
        self.outcomes = []
        self.before_cas = None
        self.on_read = None

    def read_verified(self, key):
        if self.on_read:
            self.on_read(self)
        assert key == self.ledger.key
        cls = b.DailySnapshot if self.daily else b.Snapshot
        return cls(str(self.token), self.ledger)

    def compare_and_swap(self, expected, successor):
        validate = b.validate_daily_successor if self.daily else b.validate_successor
        validate(expected.ledger, successor)
        if self.before_cas:
            callback, self.before_cas = self.before_cas, None
            callback(self)
        if expected != self.read_verified(self.ledger.key):
            return b.WriteResult.CONFLICT
        outcome = self.outcomes.pop(0) if self.outcomes else "commit"
        if outcome == "conflict":
            return b.WriteResult.CONFLICT
        if outcome == "unknown":
            return b.WriteResult.UNKNOWN
        self.ledger = successor
        self.token += 1
        self.events.append((self.name, successor.entries[-1].phase))
        if outcome == "crash":
            raise KeyboardInterrupt("simulated process death after durable write")
        return b.WriteResult.UNKNOWN if outcome == "unknown_commit" else b.WriteResult.COMMITTED


class World:
    def __init__(self, *, carryover=True, legacy=0):
        self.now, self.monotonic = NOW, 100.0
        self.events, self.live = [], True
        entries = []
        if carryover:
            # Synthetic ledger identities reproduce the audited $491.35 retained
            # obligation, not invoices or a claim that old reservations settled.
            for index, amount in enumerate((162_720_000, 122_720_000, 185_570_000,
                                             20_340_000), 1):
                entries.append(b.DailyEntry(b.PRKey(KEY.repository_id, index),
                                           b.Binding(f"{index:064x}", f"old-{index}.1", amount),
                                           "2026-10-29", "claimed"))
        if legacy:
            entries.append(b.DailyEntry(KEY, b.Binding("9" * 64, "legacy.1", legacy),
                                       "2026-10-29", "claimed"))
        self.daily = FakeStore(b.DailyLedger(b.DailyKey(KEY.repository_id), "audited-import",
                                            tuple(entries)), self.events)
        self.pr = FakeStore(b.Ledger(KEY, b.Genesis("audited-pr-history", legacy)), self.events)

    def kwargs(self):
        return {"check_current": lambda value: self.live,
                "wall_clock": lambda: self.now, "monotonic_clock": lambda: self.monotonic}

    def admit(self, config=None):
        return pilot.admit(config or policy(), self.daily, self.pr, **self.kwargs())


def grant(session, arm="A2", slot=1, **changes):
    return {"plan_sha256": session.policy.plan_sha256,
            "execution_id": session.policy.execution_id, "arm": arm, "slot": slot,
            "request_sha256": f"{slot:064x}",
            "actor_sha256": session.policy.actor_sha256[pilot.ARMS.index(arm)],
            "reserved_microusd": pilot.PER_REQUEST_MICROUSD} | changes


def started(world=None):
    world = world or World()
    session = world.admit()
    session.start_arm("A2", 700.0)
    return world, session


def test_full_reservation_and_both_claims_precede_launch_and_every_send():
    world = World()
    launched = []

    def launch(session):
        assert world.events == [("daily", "reserved"), ("pr", "reserved"),
                                ("daily", "claimed"), ("pr", "claimed")]
        assert world.daily.ledger.charged_on(DAY) == 654_070_000
        assert world.pr.ledger.remaining == 37_280_000
        session.start_arm("A2", 700.0)
        request = grant(session)
        assert session.authorize(request, 700.0) is True
        session.complete(request, USAGE)
        launched.append(session)
        return "offline-result"

    assert pilot.run_admitted(policy(), world.daily, world.pr, launch=launch,
                              **world.kwargs()) == "offline-result"
    with pytest.raises(b.BudgetError):
        launched[0].authorize(grant(launched[0], slot=2), 700.0)
    assert world.pr.ledger.charged == BOUND  # No release after success either.


@pytest.mark.parametrize("changes", [{}, {"plan_sha256": "6" * 64},
                                      {"campaign_id": "new-id"},
                                      {"execution_id": "example-run-2.1"},
                                      {"expires_at": int(NOW.timestamp()) + 7000}])
def test_duplicate_new_digest_new_id_replan_relaunch_cannot_reset(changes):
    world = World()
    world.admit()
    with pytest.raises(b.BudgetError):
        world.admit(policy(**changes))
    assert len(world.events) == 4
    assert world.pr.ledger.charged == BOUND


def test_moving_campaign_to_another_pr_cannot_reset():
    world = World()
    world.admit()
    other_key = b.PRKey(KEY.repository_id, KEY.pr_number + 1)
    other_pr = FakeStore(b.Ledger(other_key, b.Genesis("new-pr-audit", 0)), world.events)
    with pytest.raises(b.BudgetError, match="already bound"):
        pilot.admit(policy(key=other_key, campaign_id="also-new-id"), world.daily,
                    other_pr, **world.kwargs())
    assert other_pr.ledger.charged == 0


@pytest.mark.parametrize("store_name, outcomes", [
    ("daily", ["conflict"]), ("daily", ["unknown"]), ("daily", ["unknown_commit"]),
    ("pr", ["conflict"]), ("pr", ["unknown"]), ("pr", ["unknown_commit"]),
    ("daily", ["commit", "unknown_commit"]), ("pr", ["commit", "unknown_commit"]),
])
def test_conflict_unknown_and_partial_reservation_never_launch(store_name, outcomes):
    world = World()
    getattr(world, store_name).outcomes = outcomes
    launches = []
    with pytest.raises(b.BudgetError):
        pilot.run_admitted(policy(), world.daily, world.pr,
                           launch=launches.append, **world.kwargs())
    assert not launches
    charged = world.daily.ledger.charged_on(DAY)
    if charged > 491_350_000:
        with pytest.raises(b.BudgetError):
            world.admit()
        assert world.daily.ledger.charged_on(DAY) == charged


@pytest.mark.parametrize("store_name, outcomes", [
    ("daily", ["crash"]), ("pr", ["crash"]),
    ("daily", ["commit", "crash"]), ("pr", ["commit", "crash"]),
])
def test_crash_after_any_durable_step_has_no_takeover(store_name, outcomes):
    world = World()
    getattr(world, store_name).outcomes = outcomes
    with pytest.raises(KeyboardInterrupt):
        world.admit()
    with pytest.raises(b.BudgetError):
        world.admit()
    assert world.daily.ledger.charged_on(DAY) == 654_070_000


def test_stale_pr_cas_keeps_daily_reservation_no_launch():
    world = World()
    world.pr.before_cas = lambda store: setattr(store, "token", store.token + 1)
    with pytest.raises(b.BudgetError, match="conflicted"):
        world.admit()
    assert world.events == [("daily", "reserved")]
    assert world.daily.ledger.charged_on(DAY) == 654_070_000
    assert world.pr.ledger.charged == 0


def test_pr_cap_includes_legacy_and_prechecks_before_any_write():
    world = World(legacy=37_280_001)
    with pytest.raises(b.BudgetError, match="PR cumulative"):
        world.admit()
    assert not world.events
    assert World(legacy=37_280_000).admit()


def test_unrelated_settled_history_is_not_new_pilot_spend_or_current_day_charge():
    world = World(carryover=False)
    entries = tuple(b.DailyEntry(b.PRKey(123, index),
                               b.Binding(f"{index:064x}", f"past-{index}.1", 200_000_000),
                               f"2026-10-{index:02}", "finished", f"2026-10-{index:02}", 1)
                    for index in range(1, 6))
    world.daily.ledger = b.DailyLedger(b.DailyKey(123), "audited-import", entries)
    assert world.daily.ledger.charged_on(DAY) == 0
    world.admit()
    assert world.pr.ledger.charged == BOUND
    assert world.daily.ledger.charged_on(DAY) == BOUND
    assert sum(e.binding.worst_case for e in world.daily.ledger.entries) > 1_000_000_000


def test_unsettled_historical_charges_still_carry_and_enforce_daily_cap():
    world = World(carryover=False)
    entries = tuple(b.DailyEntry(b.PRKey(123, index),
                               b.Binding(f"{index:064x}", f"past-{index}.1", 200_000_000),
                               f"2026-10-{index:02}", "claimed") for index in range(1, 6))
    world.daily.ledger = b.DailyLedger(b.DailyKey(123), "audited-import", entries)
    assert world.daily.ledger.charged_on(DAY) == 1_000_000_000
    with pytest.raises(b.BudgetError, match="Global Shanghai daily budget"):
        world.admit()
    assert not world.events


def test_inconsistent_pr_tip_cannot_erase_imported_daily_obligations():
    world = World(legacy=1)
    world.pr.ledger = b.Ledger(KEY, b.Genesis("incorrect-tip-subtotal", 0))
    with pytest.raises(b.BudgetError, match="Inconsistent"):
        world.admit()
    assert not world.events


def test_rollover_during_claim_burns_reservations_without_launch():
    world = World()

    def rollover(store):
        world.now = NOW.replace(hour=16)

    world.pr.before_cas = rollover
    with pytest.raises(b.BudgetError, match="admission day"):
        world.admit()
    assert world.pr.ledger.charged == BOUND
    assert world.daily.ledger.charged_on("2026-10-31") == 654_070_000
    assert world.events == [("daily", "reserved"), ("pr", "reserved")]


def test_rollover_and_pricing_expiry_block_new_grants_without_refund():
    for change in (lambda w: setattr(w, "now", NOW.replace(hour=16)),
                   lambda w: setattr(w, "now", NOW + timedelta(hours=2))):
        world, session = started()
        change(world)
        with pytest.raises(b.BudgetError):
            session.authorize(grant(session), 700.0)
        assert session.attempts() == {"A2": 1, "A3": 0}
        assert world.pr.ledger.charged == BOUND


@pytest.mark.parametrize("which", ["daily", "pr"])
def test_each_grant_rechecks_both_exact_durable_claims(which):
    world, session = started()
    store = getattr(world, which)
    old = store.ledger.entries[-1]
    store.ledger = replace(store.ledger, entries=store.ledger.entries[:-1] + (
        replace(old, phase="reserved"),), revision=store.ledger.revision - 1)
    with pytest.raises(b.BudgetError, match="Both exact durable"):
        session.authorize(grant(session), 700.0)
    assert session.attempts()["A2"] == 1


def test_revoked_authorization_burns_attempt_and_stops_both_arms():
    world, session = started()
    world.live = False
    with pytest.raises(b.BudgetError):
        session.authorize(grant(session), 700.0)
    world.live = True
    with pytest.raises(b.BudgetError):
        session.start_arm("A3", 700.0)
    assert session.attempts()["A2"] == 1


def test_known_usage_allows_exactly_eight_per_arm_sixteen_total():
    world = World()
    session = world.admit()
    for arm in pilot.ARMS:
        session.start_arm(arm, 700.0)
        for slot in range(1, 9):
            request = grant(session, arm, slot)
            assert session.authorize(request, 700.0)
            session.complete(request, USAGE)
        session.finish_arm(arm)
    assert session.attempts() == {"A2": 8, "A3": 8}
    with pytest.raises(b.BudgetError):
        session.authorize(grant(session, "A3", 9), 700.0)
    assert session.attempts() == {"A2": 8, "A3": 8}
    assert world.pr.ledger.charged == BOUND


def test_ninth_slot_cannot_borrow_from_other_arm():
    _, session = started()
    for slot in range(1, 9):
        request = grant(session, slot=slot)
        session.authorize(request, 700.0)
        session.complete(request, USAGE)
    with pytest.raises(b.BudgetError):
        session.authorize(grant(session, slot=9), 700.0)
    assert session.attempts() == {"A2": 8, "A3": 0}


@pytest.mark.parametrize("usage", [None, {}, {**USAGE, "output_tokens": True},
                                    {**USAGE, "output_tokens": 4097},
                                    {**USAGE, "cache_creation_input_tokens": 1_000_001}])
def test_unknown_or_overbound_usage_stops_both_arms(usage):
    world, session = started()
    request = grant(session)
    session.authorize(request, 700.0)
    with pytest.raises((b.BudgetError, provider.AgentError)):
        session.complete(request, usage)
    for action in (lambda: session.authorize(grant(session, slot=2), 700.0),
                   lambda: session.finish_arm("A2"),
                   lambda: session.start_arm("A3", 700.0)):
        with pytest.raises(b.BudgetError):
            action()
    assert world.pr.ledger.charged == BOUND


def test_missing_usage_lost_reply_blocks_next_request_and_restart():
    world, session = started()
    session.authorize(grant(session), 700.0)
    with pytest.raises(b.BudgetError):
        session.authorize(grant(session, slot=2), 700.0)
    with pytest.raises(b.BudgetError):
        world.admit()
    assert session.attempts() == {"A2": 1, "A3": 0}


@pytest.mark.parametrize("changes", [{"plan_sha256": "a" * 64}, {"slot": True},
                                      {"slot": 2}, {"execution_id": "other"},
                                      {"actor_sha256": "a" * 64},
                                      {"reserved_microusd": 1}])
def test_candidate_grant_cannot_choose_plan_actor_slot_or_budget(changes):
    _, session = started()
    with pytest.raises(b.BudgetError):
        session.authorize(grant(session, **changes), 700.0)
    assert session.attempts()["A2"] == 1


def test_repeated_completion_and_wrong_request_never_reopen_latch():
    for wrong in (False, True):
        _, session = started()
        request = grant(session)
        session.authorize(request, 700.0)
        if not wrong:
            session.complete(request, USAGE)
        with pytest.raises(b.BudgetError):
            session.complete(grant(session, slot=2) if wrong else request, USAGE)
        with pytest.raises(b.BudgetError):
            session.authorize(grant(session, slot=2), 700.0)


def test_deadline_cannot_be_extended_and_session_cannot_be_serialized():
    for deadline in (701.0, 699.0):
        _, session = started()
        with pytest.raises(b.BudgetError):
            session.authorize(grant(session), deadline)
    world, session = started()
    world.monotonic = 700
    with pytest.raises(b.BudgetError, match="deadline"):
        session.authorize(grant(session), 700)
    with pytest.raises(TypeError):
        pickle.dumps(session)


def test_existing_full_context_read_submit_kind_is_not_editing_authority():
    config = json.loads(policy().provider_json)
    config["client"].update(kind=provider.FULL_CONTEXT_KIND, max_requests=1)
    with pytest.raises(b.BudgetError):
        policy(provider_json=provider.canonical(config))
