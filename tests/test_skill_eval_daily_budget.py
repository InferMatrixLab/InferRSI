"""Offline standard-library tests; no credentials, network, or provider calls."""

import base64
import copy
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from tools import skill_eval_budget as b
from tools.skill_eval_budget_git import DailyLedgerAnchor, GitHubDailyStore

KEY = b.DailyKey(123)
PR = b.PRKey(123, 1)
DAY = "2026-10-29"
NEXT = "2026-10-30"
REF = "refs/heads/skill-eval-budget/123/daily"


def binding(n, amount=200_000_000):
    return b.Binding(f"{n:064x}", f"{n}.1", amount)


class API:
    def __init__(self, ledger=None):
        self.objects = {}
        self.tip = None
        self.before_patch = None
        self.lose_response = False
        self.genesis = self.append(ledger or b.DailyLedger(KEY, "reviewed legacy audit"), [])
        self.anchor = DailyLedgerAnchor(KEY, REF, self.genesis, self.genesis)

    def put(self, value):
        sha = hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()
        self.objects[sha] = {**value, "sha": sha}
        return sha

    def tree(self, content):
        raw = content.encode()
        blob = self.put({"encoding": "base64", "size": len(raw),
                         "content": base64.b64encode(raw).decode()})
        return self.put({"truncated": False, "tree": [{"path": "ledger.json",
                         "mode": "100644", "type": "blob", "sha": blob}]})

    def append(self, ledger, parents):
        self.tip = self.put({"tree": {"sha": self.tree(b.encode_daily(ledger))},
                             "parents": [{"sha": p} for p in parents]})
        return self.tip

    def ref(self):
        if self.tip is None:
            raise OSError("404")
        return {"ref": REF, "object": {"type": "commit", "sha": self.tip}}

    def request(self, method, path, data=None):
        if method == "GET":
            if path == "":
                return {"id": 123}
            if path.startswith("/git/ref/"):
                return self.ref()
            return copy.deepcopy(self.objects[path.rsplit("/", 1)[1]])
        if path == "/git/trees":
            return {"sha": self.tree(data["tree"][0]["content"])}
        if path == "/git/commits":
            return {"sha": self.put({"tree": {"sha": data["tree"]},
                    "parents": [{"sha": p} for p in data["parents"]],
                    "message": data["message"]})}
        assert method == "PATCH" and path == "/git/refs/heads/skill-eval-budget/123/daily"
        assert data["force"] is False
        if self.before_patch:
            callback, self.before_patch = self.before_patch, None
            callback()
        if self.objects[data["sha"]]["parents"] != [{"sha": self.tip}]:
            raise OSError("422")
        self.tip = data["sha"]
        if self.lose_response:
            raise TimeoutError("lost successful response")
        return self.ref()


class DailyBudgetTests(unittest.TestCase):
    def test_timezone_boundary(self):
        self.assertEqual(b.shanghai_day(datetime(2026, 10, 29, 15, 59, tzinfo=timezone.utc)), DAY)
        self.assertEqual(b.shanghai_day(datetime(2026, 10, 29, 16, tzinfo=timezone.utc)), NEXT)
        with self.assertRaises(b.BudgetError):
            b.shanghai_day(datetime(2026, 10, 29))

    def test_outstanding_rollover_and_immutable_settlement(self):
        ledger = b.daily_reserve(b.DailyLedger(KEY, "audit"), PR, binding(1), DAY)
        self.assertEqual(ledger.charged_on(NEXT), 200_000_000)
        self.assertEqual(b.daily_reserve(ledger, PR, binding(1), NEXT), ledger)
        with self.assertRaises(b.BudgetError):
            b.daily_advance(ledger, PR, binding(1), "claimed", NEXT)
        ledger = b.daily_advance(ledger, PR, binding(1), "claimed", DAY)
        done = b.daily_advance(ledger, PR, binding(1), "finished", NEXT, actual_cost=1)
        b.validate_daily_successor(ledger, done)
        self.assertEqual(done.charged_on(DAY), 200_000_000)
        self.assertEqual(done.charged_on(NEXT), 200_000_000)
        self.assertEqual(done.charged_on("2026-10-31"), 0)
        with self.assertRaises(b.BudgetError):
            b.daily_advance(done, PR, binding(1), "claimed", NEXT)

    def test_racing_different_pr_admission_cannot_overbook(self):
        ledger = b.DailyLedger(KEY, "audit")
        for n in range(1, 5):
            ledger = b.daily_reserve(ledger, b.PRKey(123, n), binding(n), DAY)
        # Audited imported genesis carries existing outstanding reservations.
        ledger = b.DailyLedger(KEY, "import audit", ledger.entries)
        api = API(ledger)
        a, other = GitHubDailyStore(api, api.anchor), GitHubDailyStore(api, api.anchor)
        snap = a.read_verified(KEY)
        one = b.daily_reserve(snap.ledger, b.PRKey(123, 5), binding(5), DAY)
        two = b.daily_reserve(snap.ledger, b.PRKey(123, 6), binding(6), DAY)
        api.before_patch = lambda: self.assertIs(
            other.compare_and_swap(snap, two), b.WriteResult.COMMITTED)
        self.assertIs(a.compare_and_swap(snap, one), b.WriteResult.UNKNOWN)
        latest = a.read_verified(KEY)
        with self.assertRaises(b.BudgetError):
            b.daily_reserve(latest.ledger, b.PRKey(123, 5), binding(5), NEXT)
        self.assertIs(a.compare_and_swap(snap, one), b.WriteResult.CONFLICT)

    def test_claim_race_and_unknown_outcome_never_grant_twice(self):
        for lose_response in (False, True):
            api = API()
            a, other = GitHubDailyStore(api, api.anchor), GitHubDailyStore(api, api.anchor)
            snap = a.read_verified(KEY)
            a.compare_and_swap(snap, b.daily_reserve(snap.ledger, PR, binding(1), DAY))
            if lose_response:
                api.lose_response = True
            else:
                api.before_patch = lambda: b.daily_claim_once(other, PR, binding(1), DAY)
            with self.assertRaises(b.BudgetError):
                b.daily_claim_once(a, PR, binding(1), DAY)
            api.lose_response = False
            with self.assertRaises(b.BudgetError):
                b.daily_claim_once(other, PR, binding(1), DAY)

    def test_strict_schema_and_history(self):
        ledger = b.DailyLedger(KEY, "audit")
        self.assertEqual(b.decode_daily(b.encode_daily(ledger)), ledger)
        for amount in (None, True, -1, 1.5):
            with self.assertRaises(b.BudgetError):
                binding(1, amount)
        with self.assertRaises(b.BudgetError):
            payload = b.encode_daily(ledger).replace('"revision":0', '"revision":0,"revision":0')
            b.decode_daily(payload)
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        snap = store.read_verified(KEY)
        store.compare_and_swap(snap, b.daily_reserve(snap.ledger, PR, binding(1), DAY))
        api.tip = api.genesis
        with self.assertRaises(b.BudgetError):
            store.read_verified(KEY)
        api.tip = None
        with self.assertRaises(b.BudgetError):
            store.read_verified(KEY)

    def test_quarantine_persists_and_blocks_all_execution_without_refund(self):
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        snap = store.read_verified(KEY)
        reserved = b.daily_reserve(snap.ledger, PR, binding(1), DAY)
        store.compare_and_swap(snap, reserved)
        snap = store.read_verified(KEY)
        stopped = b.daily_quarantine(snap.ledger, "audit: upper-bound exposure unknown")
        self.assertIs(store.compare_and_swap(snap, stopped), b.WriteResult.COMMITTED)
        fresh = GitHubDailyStore(api, api.anchor).read_verified(KEY).ledger
        self.assertEqual(fresh, stopped)
        self.assertEqual(fresh.charged_on(NEXT), 200_000_000)
        self.assertEqual(b.daily_quarantine(fresh, "another observation"), fresh)
        for action in (
            fresh.require_active,
            lambda: b.daily_reserve(fresh, b.PRKey(123, 9), binding(9), NEXT),
            lambda: b.daily_reserve(fresh, PR, binding(1), NEXT),
            lambda: b.daily_claim_once(store, PR, binding(1), DAY),
            lambda: b.validate_daily_successor(
                fresh, replace(fresh, quarantine=None, revision=fresh.revision + 1)),
            lambda: b.validate_daily_successor(
                snap.ledger, replace(stopped, entries=())),
        ):
            with self.assertRaises(b.BudgetError):
                action()

    def test_quarantine_race_and_unknown_write_remain_fail_closed(self):
        api = API()
        store, other = GitHubDailyStore(api, api.anchor), GitHubDailyStore(api, api.anchor)
        snap = store.read_verified(KEY)
        stopped = b.daily_quarantine(snap.ledger, "audit: observed bound exceeded")
        api.before_patch = lambda: other.compare_and_swap(snap, stopped)
        reserved = b.daily_reserve(snap.ledger, PR, binding(1), DAY)
        self.assertIs(store.compare_and_swap(snap, reserved), b.WriteResult.UNKNOWN)
        with self.assertRaises(b.BudgetError):
            store.read_verified(KEY).ledger.require_active()
        api = API()
        store = GitHubDailyStore(api, api.anchor)
        snap = store.read_verified(KEY)
        api.lose_response = True
        self.assertIs(store.compare_and_swap(snap, b.daily_quarantine(snap.ledger, "audit")),
                      b.WriteResult.UNKNOWN)
        with self.assertRaises(b.BudgetError):
            GitHubDailyStore(api, api.anchor).read_verified(KEY).ledger.require_active()

    def test_existing_pr_cap_is_not_reset(self):
        pr = b.reserve(b.Ledger(PR, b.Genesis("legacy audit", 100_000_000)),
                       binding(1, 100_000_000))
        with self.assertRaises(b.BudgetError):
            b.reserve(pr, binding(2, 1))
        with self.assertRaises(b.BudgetError):
            b.daily_reserve(b.DailyLedger(KEY, "audit"), b.PRKey(999, 1), binding(1), DAY)


if __name__ == "__main__":
    unittest.main()
